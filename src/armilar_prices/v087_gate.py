"""Single local empirical gate for the Eurostat vertical series.

This orchestration deliberately does not change the project version, contracts,
or public/latest.  It acquires an immutable provider snapshot, replays it through
the deterministic engine, and writes a compact gate report for human review.
"""
from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .eurostat_vertical import (
    OFFICIAL_SNAPSHOT_KIND,
    EurostatVerticalError,
    VerticalPolicy,
    acquire_official_snapshot,
    build_vertical_series,
    verify_manifest,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def hash_tree(root: Path | str) -> Mapping[str, Any]:
    """Return a deterministic digest of every regular file under *root*."""

    base = Path(root)
    entries: list[dict[str, str]] = []
    if base.exists():
        for path in sorted(base.rglob("*")):
            if path.is_file():
                entries.append(
                    {
                        "path": path.relative_to(base).as_posix(),
                        "sha256": _sha256(path.read_bytes()),
                    }
                )
    return {
        "root_exists": base.exists(),
        "file_count": len(entries),
        "files": entries,
        "tree_sha256": _sha256(_canonical_json_bytes(entries)),
    }


def _require_empty(path: Path, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise EurostatVerticalError(
            "EMPIRICAL_GATE_PATH_NOT_EMPTY",
            f"{label} must be a new empty directory: {path}",
        )


def _read_index_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _validate_reference_average(rows: list[dict[str, str]], reference_year: int) -> str:
    selected = [row for row in rows if row["period"].startswith(f"{reference_year:04d}-")]
    if len(selected) != 12:
        raise EurostatVerticalError(
            "REFERENCE_YEAR_INCOMPLETE",
            f"expected 12 months for {reference_year}, got {len(selected)}",
        )
    average = sum((Decimal(row["index_value"]) for row in selected), Decimal("0")) / Decimal(
        "12"
    )
    if abs(average - Decimal("100")) > Decimal("1e-10"):
        raise EurostatVerticalError(
            "REFERENCE_AVERAGE_IDENTITY_FAILED", f"{reference_year} average={average}"
        )
    return format(average, "f")


def run_official_gate(
    *,
    policy_path: Path | str,
    weights_path: Path | str,
    public_latest_dir: Path | str,
    snapshot_dir: Path | str,
    output_dir: Path | str,
    report_path: Path | str,
    retrieved_at: str | None = None,
    opener: Any = urllib.request.urlopen,
    test_mode: bool = False,
) -> Mapping[str, Any]:
    """Acquire and validate the complete v0.8.7 vertical series locally.

    ``test_mode`` exists only for unit tests with an injected transport.  A report
    produced in that mode can never claim that the official empirical gate passed.
    """

    policy = VerticalPolicy.load(policy_path)
    weights = Path(weights_path)
    latest = Path(public_latest_dir)
    snapshot = Path(snapshot_dir)
    output = Path(output_dir)
    report = Path(report_path)

    if not weights.is_file():
        raise EurostatVerticalError("WEIGHTS_FILE_MISSING", str(weights))
    _require_empty(snapshot, "snapshot_dir")
    _require_empty(output, "output_dir")
    if report.exists():
        raise EurostatVerticalError("EMPIRICAL_GATE_REPORT_EXISTS", str(report))

    latest_before = hash_tree(latest)
    started_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    snapshot_manifest = acquire_official_snapshot(
        policy_path,
        snapshot,
        retrieved_at=started_at,
        opener=opener,
    )
    if snapshot_manifest.get("snapshot_kind") != OFFICIAL_SNAPSHOT_KIND:
        raise EurostatVerticalError(
            "OFFICIAL_SNAPSHOT_REQUIRED",
            str(snapshot_manifest.get("snapshot_kind")),
        )
    verify_manifest(snapshot)

    summary = build_vertical_series(policy_path, snapshot, weights, output)
    verify_manifest(output)

    latest_after = hash_tree(latest)
    if latest_before != latest_after:
        raise EurostatVerticalError(
            "PUBLIC_LATEST_MUTATED",
            "public/latest changed during the local empirical gate",
        )

    if summary.get("snapshot_kind") != OFFICIAL_SNAPSHOT_KIND:
        raise EurostatVerticalError("OFFICIAL_SNAPSHOT_REQUIRED", "output lost snapshot class")
    if summary.get("status") != "RESEARCH_VERTICAL_SERIES_BUILT":
        raise EurostatVerticalError(
            "EMPIRICAL_GATE_STATUS_INVALID", str(summary.get("status"))
        )
    if summary.get("observation_count") != len(policy.economies) * len(
        policy.source_categories
    ) * len(_read_index_rows(output / "monthly_index.csv")):
        raise EurostatVerticalError(
            "OBSERVATION_COUNT_IDENTITY_FAILED", str(summary.get("observation_count"))
        )
    if summary.get("research_release_allowed") is not False:
        raise EurostatVerticalError("RELEASE_GATE_WEAKENED", "research release changed")
    if summary.get("monetary_release_allowed") is not False:
        raise EurostatVerticalError("RELEASE_GATE_WEAKENED", "monetary release changed")

    index_rows = _read_index_rows(output / "monthly_index.csv")
    reference_average = _validate_reference_average(index_rows, policy.reference_year)
    snapshot_manifest_path = snapshot / "snapshot_manifest.json"
    output_manifest_path = output / "MANIFEST.sha256"

    gate_status = (
        "TEST_GATE_SIMULATION_PASSED" if test_mode else "OFFICIAL_EMPIRICAL_GATE_PASSED"
    )
    payload = {
        "gate_schema_version": "1.0",
        "gate_status": gate_status,
        "test_mode": test_mode,
        "policy_version": policy.policy_version,
        "policy_sha256": policy.policy_sha256,
        "universe_id": policy.universe_id,
        "provider": "EUROSTAT",
        "dataset": policy.dataset,
        "started_at": started_at,
        "snapshot_dir": snapshot.as_posix(),
        "snapshot_manifest_sha256": _sha256(snapshot_manifest_path.read_bytes()),
        "output_dir": output.as_posix(),
        "output_manifest_sha256": _sha256(output_manifest_path.read_bytes()),
        "weights_path": weights.as_posix(),
        "weights_sha256": _sha256(weights.read_bytes()),
        "observation_count": summary["observation_count"],
        "month_count": summary["month_count"],
        "economy_count": summary["economy_count"],
        "source_category_count": summary["source_category_count"],
        "armilar_category_count": summary["armilar_category_count"],
        "declared_universe_world_weight": summary["declared_universe_world_weight"],
        "reference_year_average": reference_average,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
        "public_latest_before": latest_before,
        "public_latest_after": latest_after,
        "limitations": [
            "The declared universe covers only the five fixed economies and is not a world release.",
            "HICP HFMCE and Armilar HFCE scopes are not fully aligned.",
            "Numeric uncertainty bounds have not yet been calibrated.",
            "The Eurostat Statistics API supplies the latest available values, so this local snapshot must be preserved as the vintage record.",
        ],
        "next_action": (
            "Review the real economic report and only then close the project release."
            if not test_mode
            else "Discard this simulation report; it is not provider evidence."
        ),
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_bytes(_canonical_json_bytes(payload))
    return payload
