"""ARMILAR v0.10.1 verified ARM-O materialization bridge.

This module converts a replay-verified Eurostat v0.8.7 official vertical bundle
into the canonical v0.9.6 observation contract, materializes an immutable ARM-O
run, appends the temporal ledger, replays the run, and builds the v0.10.0 target
archive. It never claims historical official publication timestamps. Where the
source does not expose row-level publication times, availability is conservatively
anchored to the first verified Armilar retrieval timestamp.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from armilar_prices.official_engine_v096 import (
    BuildRequest,
    OfficialEngineError,
    SeriesKind,
    build_run,
    replay_run,
    verify_ledger,
    verify_manifest as verify_v096_manifest,
)
from .core_v0100 import (
    BacktestProtocolError,
    canonical_json_bytes,
    canonical_utc,
    directory_manifest_sha256,
    parse_utc,
    read_csv,
    sha256_path,
    verify_manifest,
    write_manifest,
)
from .target_archive_v0100 import build_target_archive, verify_target_archive

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
V087_MANIFEST_LINE_RE = re.compile(r"^([0-9a-f]{64}) {1,2}([^ ].*)$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CANONICAL_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
CANONICAL_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
START_PERIOD = "2021-01"
END_PERIOD = "2025-12"
EXPECTED_MONTHS = 60
EXPECTED_CELLS = 60
EXPECTED_OBSERVATIONS = 3600
AVAILABILITY_SEMANTICS = "FIRST_VERIFIED_ARMILAR_RETRIEVAL_NOT_OFFICIAL_PUBLICATION_TIME"
EVIDENCE_CLASS = "OFFICIAL_CATEGORY_FIRST_SEEN_AT_VERIFIED_RETRIEVAL"

OBSERVATION_COLUMNS = (
    "series_id",
    "economy_code",
    "category_code",
    "period",
    "value",
    "published_at",
    "retrieved_at",
    "vintage_id",
    "revision_sequence",
    "raw_snapshot_id",
    "source_sha256",
    "evidence_class",
)


class MaterializationBridgeError(RuntimeError):
    """Raised when the v0.10.1 bridge cannot prove every required input."""


def _canonical_file_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise MaterializationBridgeError(f"UTF-8 BOM forbidden: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializationBridgeError(f"invalid UTF-8: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(path: Path) -> str:
    if not path.is_file():
        raise MaterializationBridgeError(f"required file missing: {path}")
    return _digest_bytes(path.read_bytes())


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved = root.resolve()
    if candidate != resolved and resolved not in candidate.parents:
        raise MaterializationBridgeError(f"path escapes root: {relative}")
    return candidate


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_canonical_file_bytes(path).decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationBridgeError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MaterializationBridgeError(f"JSON object required: {path}")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise MaterializationBridgeError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise MaterializationBridgeError(f"cannot read CSV: {path}") from exc


def _csv_bytes(rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return stream.getvalue().encode("utf-8")


def _iter_months(start: str, end: str) -> tuple[str, ...]:
    if not MONTH_RE.fullmatch(start) or not MONTH_RE.fullmatch(end):
        raise MaterializationBridgeError("invalid monthly interval")
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    if (sy, sm) > (ey, em):
        raise MaterializationBridgeError("start period after end period")
    result: list[str] = []
    year, month = sy, sm
    while (year, month) <= (ey, em):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(result)


def _positive_decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MaterializationBridgeError(f"invalid decimal in {field}: {value!r}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise MaterializationBridgeError(f"{field} must be finite and positive")
    return parsed


def _verify_v087_manifest(root: Path) -> dict[str, str]:
    """Verify historical v0.8.7 manifests with one or two ASCII separators.

    Both grammars were emitted by genuine Armilar artefacts. The parser remains
    fail-closed: tabs, three or more spaces, empty paths, paths beginning with a
    space, duplicate entries and path traversal are rejected.
    """
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise MaterializationBridgeError(f"manifest missing: {manifest}")
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        match = V087_MANIFEST_LINE_RE.fullmatch(line)
        if match is None:
            raise MaterializationBridgeError(f"invalid manifest line {number}")
        digest, relative = match.groups()
        if relative in entries:
            raise MaterializationBridgeError(f"invalid manifest entry {number}")
        target = _safe_child(root, relative)
        if not target.is_file() or _digest(target) != digest:
            raise MaterializationBridgeError(f"manifest mismatch: {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != actual:
        raise MaterializationBridgeError(
            f"manifest file set mismatch; missing={sorted(actual-set(entries))}, extra={sorted(set(entries)-actual)}"
        )
    return entries


@dataclass(frozen=True, slots=True)
class BridgePolicy:
    policy_id: str
    policy_version: str
    source_policy_version: str
    official_engine_version: str
    target_protocol_version: str
    availability_semantics: str
    require_official_snapshot: bool
    require_exact_grid: bool
    require_replay: bool
    require_ledger: bool
    require_target_archive: bool
    gates: Mapping[str, bool]

    @classmethod
    def load(cls, path: Path) -> "BridgePolicy":
        payload = _read_json(path)
        required = {
            "policy_id", "policy_version", "source_policy_version",
            "official_engine_version", "target_protocol_version",
            "availability_semantics", "require_official_snapshot",
            "require_exact_grid", "require_replay", "require_ledger",
            "require_target_archive", "gates",
        }
        if set(payload) != required:
            raise MaterializationBridgeError(
                f"policy keys mismatch; missing={sorted(required-set(payload))}, extra={sorted(set(payload)-required)}"
            )
        if payload["policy_id"] != "ARMILAR_ARM_O_MATERIALIZATION_BRIDGE_V0101":
            raise MaterializationBridgeError("unexpected bridge policy_id")
        if payload["policy_version"] != "0.10.1":
            raise MaterializationBridgeError("policy_version must be 0.10.1")
        if payload["source_policy_version"] != "0.8.7":
            raise MaterializationBridgeError("source_policy_version must be 0.8.7")
        if payload["official_engine_version"] != "0.9.6":
            raise MaterializationBridgeError("official_engine_version must be 0.9.6")
        if payload["target_protocol_version"] != "0.10.0":
            raise MaterializationBridgeError("target_protocol_version must be 0.10.0")
        if payload["availability_semantics"] != AVAILABILITY_SEMANTICS:
            raise MaterializationBridgeError("availability semantics changed")
        for name in (
            "require_official_snapshot", "require_exact_grid", "require_replay",
            "require_ledger", "require_target_archive",
        ):
            if payload[name] is not True:
                raise MaterializationBridgeError(f"{name} must remain true")
        gates = payload["gates"]
        expected_gates = {
            "historical_publication_time_claim_allowed",
            "research_release_allowed",
            "backtest_execution_claim_allowed",
            "model_training_allowed",
            "arm_l_use_allowed",
            "shadow_production_allowed",
            "monetary_use_allowed",
        }
        if not isinstance(gates, dict) or set(gates) != expected_gates:
            raise MaterializationBridgeError("bridge gate set mismatch")
        if any(bool(gates[name]) for name in expected_gates):
            raise MaterializationBridgeError("all v0.10.1 gates must remain false")
        return cls(
            policy_id=payload["policy_id"], policy_version=payload["policy_version"],
            source_policy_version=payload["source_policy_version"],
            official_engine_version=payload["official_engine_version"],
            target_protocol_version=payload["target_protocol_version"],
            availability_semantics=payload["availability_semantics"],
            require_official_snapshot=True, require_exact_grid=True,
            require_replay=True, require_ledger=True, require_target_archive=True,
            gates={name: False for name in sorted(expected_gates)},
        )


def _validate_v087_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    _verify_v087_manifest(snapshot_dir)
    manifest = _read_json(snapshot_dir / "snapshot_manifest.json")
    if manifest.get("snapshot_kind") != "OFFICIAL_PROVIDER_ACQUISITION":
        raise MaterializationBridgeError("v0.10.1 requires an official provider acquisition")
    if manifest.get("provider") != "EUROSTAT" or manifest.get("dataset") != "prc_hicp_midx":
        raise MaterializationBridgeError("unexpected snapshot provider or dataset")
    if manifest.get("policy_version") != "0.8.7":
        raise MaterializationBridgeError("snapshot policy version mismatch")
    retrieved_at = canonical_utc(str(manifest.get("retrieved_at", "")), "snapshot retrieved_at")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or len(requests) != 12:
        raise MaterializationBridgeError("snapshot must contain exactly 12 category requests")
    by_id: dict[str, dict[str, Any]] = {}
    categories: set[str] = set()
    for item in requests:
        if not isinstance(item, dict):
            raise MaterializationBridgeError("snapshot request must be an object")
        request_id = str(item.get("request_id", ""))
        category = str(item.get("source_category", ""))
        if request_id in by_id or category in categories:
            raise MaterializationBridgeError("duplicate snapshot request or category")
        if category not in CANONICAL_CATEGORIES:
            raise MaterializationBridgeError(f"unexpected snapshot category: {category}")
        raw_sha = str(item.get("raw_sha256", ""))
        if not SHA256_RE.fullmatch(raw_sha):
            raise MaterializationBridgeError("invalid raw request hash")
        raw_path = _safe_child(snapshot_dir, str(item.get("raw_file", "")))
        if not raw_path.is_file() or _digest(raw_path) != raw_sha:
            raise MaterializationBridgeError(f"raw request mismatch: {request_id}")
        if canonical_utc(str(item.get("retrieved_at", "")), "request retrieved_at") != retrieved_at:
            raise MaterializationBridgeError("request retrieval timestamp differs from snapshot")
        by_id[request_id] = item
        categories.add(category)
    if categories != set(CANONICAL_CATEGORIES):
        raise MaterializationBridgeError("snapshot category coverage is incomplete")
    return manifest, by_id, retrieved_at


def _validate_v087_output(
    output_dir: Path,
    snapshot_dir: Path,
    requests: Mapping[str, Mapping[str, Any]],
    snapshot_retrieved_at: str,
) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    _verify_v087_manifest(output_dir)
    summary = _read_json(output_dir / "run_summary.json")
    if summary.get("status") != "RESEARCH_VERTICAL_SERIES_BUILT":
        raise MaterializationBridgeError("v0.8.7 output is not an official research vertical series")
    if summary.get("snapshot_kind") != "OFFICIAL_PROVIDER_ACQUISITION":
        raise MaterializationBridgeError("v0.8.7 output does not reference an official snapshot")
    if summary.get("provider") != "EUROSTAT" or summary.get("dataset") != "prc_hicp_midx":
        raise MaterializationBridgeError("v0.8.7 output provider or dataset mismatch")
    if summary.get("start_period") != START_PERIOD or summary.get("end_period") != END_PERIOD:
        raise MaterializationBridgeError("v0.8.7 output interval mismatch")
    if int(summary.get("month_count", -1)) != EXPECTED_MONTHS:
        raise MaterializationBridgeError("v0.8.7 output month count mismatch")
    if int(summary.get("economy_count", -1)) != len(CANONICAL_ECONOMIES):
        raise MaterializationBridgeError("v0.8.7 output economy count mismatch")
    if int(summary.get("source_category_count", -1)) != len(CANONICAL_CATEGORIES):
        raise MaterializationBridgeError("v0.8.7 output category count mismatch")
    if int(summary.get("observation_count", -1)) != EXPECTED_OBSERVATIONS:
        raise MaterializationBridgeError("v0.8.7 output observation count mismatch")
    if bool(summary.get("research_release_allowed")) or bool(summary.get("monetary_release_allowed")):
        raise MaterializationBridgeError("v0.8.7 gates must remain closed")
    snapshot_manifest_hash = _digest(snapshot_dir / "snapshot_manifest.json")
    if summary.get("snapshot_manifest_sha256") != snapshot_manifest_hash:
        raise MaterializationBridgeError("v0.8.7 output references a different snapshot manifest")
    if canonical_utc(str(summary.get("source_snapshot_retrieved_at", "")), "output source_snapshot_retrieved_at") != snapshot_retrieved_at:
        raise MaterializationBridgeError("v0.8.7 output retrieval timestamp mismatch")

    rows = _read_csv(output_dir / "normalized_price_observations.csv")
    if len(rows) != EXPECTED_OBSERVATIONS:
        raise MaterializationBridgeError("normalised observation row count mismatch")
    required = {
        "economy_code", "source_category", "period", "price_value",
        "price_evidence_class", "provider", "dataset", "request_id",
        "raw_file", "raw_sha256",
    }
    if not rows or not required.issubset(rows[0]):
        raise MaterializationBridgeError("v0.8.7 observation schema incomplete")
    expected_grid = {
        (economy, category, period)
        for economy in CANONICAL_ECONOMIES
        for category in CANONICAL_CATEGORIES
        for period in _iter_months(START_PERIOD, END_PERIOD)
    }
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["economy_code"], row["source_category"], row["period"])
        if key in seen:
            raise MaterializationBridgeError(f"duplicate v0.8.7 observation: {key}")
        seen.add(key)
        if key not in expected_grid:
            raise MaterializationBridgeError(f"unexpected v0.8.7 observation: {key}")
        if row["price_evidence_class"] != "P1_OFFICIAL_CATEGORY":
            raise MaterializationBridgeError("non-official v0.8.7 price evidence")
        if row["provider"] != "EUROSTAT" or row["dataset"] != "prc_hicp_midx":
            raise MaterializationBridgeError("observation provider or dataset mismatch")
        _positive_decimal(row["price_value"], "price_value")
        request = requests.get(row["request_id"])
        if request is None:
            raise MaterializationBridgeError("observation request_id not found in snapshot")
        if request.get("source_category") != row["source_category"]:
            raise MaterializationBridgeError("observation request category mismatch")
        if request.get("raw_file") != row["raw_file"] or request.get("raw_sha256") != row["raw_sha256"]:
            raise MaterializationBridgeError("observation raw provenance mismatch")
    if seen != expected_grid:
        raise MaterializationBridgeError(f"v0.8.7 grid mismatch; missing={len(expected_grid-seen)}")
    return summary, rows, directory_manifest_sha256_legacy(output_dir)


def directory_manifest_sha256_legacy(root: Path) -> str:
    _verify_v087_manifest(root)
    return _digest(root / "MANIFEST.sha256")


def build_observation_bridge(
    *, policy_path: Path, snapshot_dir: Path, vertical_output_dir: Path,
    output_dir: Path, created_at: str,
) -> dict[str, Any]:
    policy = BridgePolicy.load(policy_path)
    created_at = canonical_utc(created_at, "created_at")
    snapshot, requests, retrieved_at = _validate_v087_snapshot(snapshot_dir)
    summary, source_rows, vertical_manifest_sha256 = _validate_v087_output(
        vertical_output_dir, snapshot_dir, requests, retrieved_at
    )
    snapshot_manifest_sha256 = _digest(snapshot_dir / "snapshot_manifest.json")
    vintage_id = f"EUROSTAT_V087_{snapshot_manifest_sha256[:16]}"
    converted: list[dict[str, str]] = []
    for row in sorted(source_rows, key=lambda item: (item["economy_code"], item["source_category"], item["period"])):
        converted.append({
            "series_id": f"EUROSTAT_PRC_HICP_MIDX_I15_{row['economy_code']}_{row['source_category']}",
            "economy_code": row["economy_code"],
            "category_code": row["source_category"],
            "period": row["period"],
            "value": str(_positive_decimal(row["price_value"], "price_value")),
            "published_at": retrieved_at,
            "retrieved_at": retrieved_at,
            "vintage_id": vintage_id,
            "revision_sequence": "0",
            "raw_snapshot_id": f"EUROSTAT_V087:{snapshot_manifest_sha256}:{row['request_id']}",
            "source_sha256": row["raw_sha256"],
            "evidence_class": EVIDENCE_CLASS,
        })
    bridge_summary: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "0.10.1",
        "status": "VERIFIED_V087_TO_V096_OBSERVATION_BRIDGE",
        "created_at": created_at,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "source_policy_version": policy.source_policy_version,
        "source_universe_id": summary["universe_id"],
        "source_snapshot_retrieved_at": retrieved_at,
        "source_snapshot_manifest_sha256": snapshot_manifest_sha256,
        "source_snapshot_tree_manifest_sha256": _digest(snapshot_dir / "MANIFEST.sha256"),
        "source_vertical_manifest_sha256": vertical_manifest_sha256,
        "availability_semantics": AVAILABILITY_SEMANTICS,
        "historical_publication_time_claim_allowed": False,
        "observation_count": len(converted),
        "economy_count": len(CANONICAL_ECONOMIES),
        "category_count": len(CANONICAL_CATEGORIES),
        "period_count": EXPECTED_MONTHS,
        "start_period": START_PERIOD,
        "end_period": END_PERIOD,
        "vintage_id": vintage_id,
        "evidence_class": EVIDENCE_CLASS,
        "gates": dict(policy.gates),
    }

    def writer(staging: Path) -> None:
        (staging / "category_observations_v096.csv").write_bytes(_csv_bytes(converted, OBSERVATION_COLUMNS))
        (staging / "observation_bridge_summary.json").write_bytes(canonical_json_bytes(bridge_summary))
        write_manifest(staging)

    _write_transactional(output_dir, writer)
    verify_observation_bridge(output_dir, policy_path=policy_path)
    return bridge_summary


def _write_transactional(output_dir: Path, writer) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MaterializationBridgeError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        writer(staging)
        verify_manifest(staging)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def verify_observation_bridge(path: Path, *, policy_path: Path) -> dict[str, Any]:
    policy = BridgePolicy.load(policy_path)
    verify_manifest(path)
    summary = _read_json(path / "observation_bridge_summary.json")
    if summary.get("status") != "VERIFIED_V087_TO_V096_OBSERVATION_BRIDGE":
        raise MaterializationBridgeError("unexpected observation bridge status")
    if summary.get("policy_id") != policy.policy_id or summary.get("policy_version") != policy.policy_version:
        raise MaterializationBridgeError("observation bridge policy mismatch")
    if summary.get("availability_semantics") != AVAILABILITY_SEMANTICS:
        raise MaterializationBridgeError("observation bridge availability semantics changed")
    if summary.get("historical_publication_time_claim_allowed") is not False:
        raise MaterializationBridgeError("historical publication-time claim was opened")
    if summary.get("gates") != dict(policy.gates):
        raise MaterializationBridgeError("observation bridge gates mismatch")
    rows = read_csv(path / "category_observations_v096.csv")
    if len(rows) != EXPECTED_OBSERVATIONS or len(rows) != int(summary.get("observation_count", -1)):
        raise MaterializationBridgeError("observation bridge row count mismatch")
    if not rows or set(rows[0]) != set(OBSERVATION_COLUMNS):
        raise MaterializationBridgeError("observation bridge columns mismatch")
    retrieved_at = canonical_utc(str(summary["source_snapshot_retrieved_at"]), "source_snapshot_retrieved_at")
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["economy_code"], row["category_code"], row["period"])
        if key in seen:
            raise MaterializationBridgeError("duplicate converted observation")
        seen.add(key)
        if row["published_at"] != retrieved_at or row["retrieved_at"] != retrieved_at:
            raise MaterializationBridgeError("converted availability must equal first verified retrieval")
        if row["evidence_class"] != EVIDENCE_CLASS:
            raise MaterializationBridgeError("converted evidence class mismatch")
        if row["revision_sequence"] != "0":
            raise MaterializationBridgeError("initial bridge revision sequence must be zero")
        if not SHA256_RE.fullmatch(row["source_sha256"]):
            raise MaterializationBridgeError("converted source hash invalid")
        _positive_decimal(row["value"], "value")
    expected = {
        (economy, category, period)
        for economy in CANONICAL_ECONOMIES
        for category in CANONICAL_CATEGORIES
        for period in _iter_months(START_PERIOD, END_PERIOD)
    }
    if seen != expected:
        raise MaterializationBridgeError("converted observation grid mismatch")
    return summary



def _build_v0100_arm_o_view(source_run: Path, view_dir: Path) -> str:
    """Create a byte-identical non-manifest view using the v0.10.0 manifest grammar.

    v0.9.6 manifests use one separator space; v0.10.0 uses two. Historical
    artefacts are not rewritten. The compatibility view preserves every payload
    byte and changes only the manifest representation.
    """
    verify_v096_manifest(source_run)
    if view_dir.exists() and any(view_dir.iterdir()):
        raise MaterializationBridgeError("TARGET_VIEW_DIRECTORY_NOT_EMPTY")
    view_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(p for p in source_run.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"):
        relative = path.relative_to(source_run)
        target = view_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    write_manifest(view_dir)
    verify_manifest(view_dir)
    source_files = {
        path.relative_to(source_run).as_posix(): _digest(path)
        for path in source_run.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    view_files = {
        path.relative_to(view_dir).as_posix(): _digest(path)
        for path in view_dir.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if source_files != view_files:
        raise MaterializationBridgeError("ARM-O compatibility view changed payload bytes")
    return directory_manifest_sha256(view_dir)

def materialize_arm_o_bridge(
    *, bridge_policy_path: Path, engine_policy_path: Path,
    target_policy_path: Path, weights_path: Path, observation_bridge: Path,
    output_dir: Path, run_id: str, vintage_id: str, created_at: str,
) -> dict[str, Any]:
    policy = BridgePolicy.load(bridge_policy_path)
    created_at = canonical_utc(created_at, "created_at")
    bridge = verify_observation_bridge(observation_bridge, policy_path=bridge_policy_path)
    cutoff_at = canonical_utc(str(bridge["source_snapshot_retrieved_at"]), "cutoff_at")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MaterializationBridgeError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        arm_o_dir = staging / "arm_o_run"
        ledger_path = staging / "temporal_ledger.jsonl"
        try:
            run_summary = build_run(
                policy_path=engine_policy_path,
                weights_path=weights_path,
                category_observations_path=observation_bridge / "category_observations_v096.csv",
                headline_observations_path=None,
                output_dir=arm_o_dir,
                ledger_path=ledger_path,
                request=BuildRequest(
                    run_id=run_id,
                    series_kind=SeriesKind.ARM_O,
                    vintage_id=vintage_id,
                    cutoff_at=cutoff_at,
                    created_at=created_at,
                ),
            )
            replay_summary = replay_run(arm_o_dir)
            ledger_entries = verify_ledger(ledger_path)
        except OfficialEngineError as exc:
            raise MaterializationBridgeError(f"official engine materialization failed: {exc}") from exc
        target_view_dir = staging / "arm_o_target_input_view"
        target_view_manifest_sha256 = _build_v0100_arm_o_view(arm_o_dir, target_view_dir)
        target_dir = staging / "target_archive"
        try:
            target_summary = build_target_archive(
                policy_path=target_policy_path,
                arm_o_run=target_view_dir,
                output_dir=target_dir,
                created_at=created_at,
            )
        except BacktestProtocolError as exc:
            raise MaterializationBridgeError(f"target archive materialization failed: {exc}") from exc
        summary = {
            "schema_version": "1.0",
            "contract_version": "0.10.1",
            "status": "ARM_O_MATERIALIZATION_AND_TARGET_BRIDGE_VALID",
            "created_at": created_at,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "availability_semantics": AVAILABILITY_SEMANTICS,
            "historical_publication_time_claim_allowed": False,
            "observation_bridge_manifest_sha256": directory_manifest_sha256(observation_bridge),
            "arm_o_run_id": run_summary["run_id"],
            "arm_o_vintage_id": run_summary["vintage_id"],
            "arm_o_cutoff_at": run_summary["cutoff_at"],
            "arm_o_manifest_sha256": _digest(arm_o_dir / "MANIFEST.sha256"),
            "target_input_view_manifest_sha256": target_view_manifest_sha256,
            "manifest_compatibility_mode": "V096_SINGLE_SPACE_TO_V0100_DOUBLE_SPACE_VIEW_PAYLOAD_BYTES_IDENTICAL",
            "arm_o_period_count": run_summary["period_count"],
            "arm_o_observation_count": run_summary["normalised_observation_count"],
            "arm_o_replay_status": replay_summary["status"],
            "ledger_entry_count": len(ledger_entries),
            "target_archive_manifest_sha256": directory_manifest_sha256(target_dir),
            "target_count": target_summary["target_count"],
            "target_cell_count": target_summary["cell_count"],
            "target_latest_period": target_summary["latest_target_period"],
            "backtest_overlap_status": "NO_FUTURE_TARGETS_AFTER_2025_UNTIL_OFFICIAL_ENGINE_PERIOD_IS_EXTENDED",
            "research_release_allowed": False,
            "backtest_execution_claim_allowed": False,
            "model_training_allowed": False,
            "arm_l_use_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
            "gates": dict(policy.gates),
        }
        (staging / "materialization_summary.json").write_bytes(canonical_json_bytes(summary))
        write_manifest(staging)
        verify_manifest(staging)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    verify_materialization(output_dir, bridge_policy_path=bridge_policy_path, target_policy_path=target_policy_path)
    return summary


def verify_materialization(
    path: Path, *, bridge_policy_path: Path, target_policy_path: Path,
) -> dict[str, Any]:
    policy = BridgePolicy.load(bridge_policy_path)
    verify_manifest(path)
    summary = _read_json(path / "materialization_summary.json")
    if summary.get("status") != "ARM_O_MATERIALIZATION_AND_TARGET_BRIDGE_VALID":
        raise MaterializationBridgeError("unexpected materialization status")
    if summary.get("policy_id") != policy.policy_id or summary.get("gates") != dict(policy.gates):
        raise MaterializationBridgeError("materialization policy or gates mismatch")
    if summary.get("availability_semantics") != AVAILABILITY_SEMANTICS:
        raise MaterializationBridgeError("materialization availability semantics changed")
    if summary.get("historical_publication_time_claim_allowed") is not False:
        raise MaterializationBridgeError("historical publication-time claim opened")
    try:
        replay = replay_run(path / "arm_o_run")
        ledger = verify_ledger(path / "temporal_ledger.jsonl")
        verify_manifest(path / "arm_o_target_input_view")
        target = verify_target_archive(path / "target_archive", policy_path=target_policy_path)
    except (OfficialEngineError, BacktestProtocolError) as exc:
        raise MaterializationBridgeError(f"nested artefact verification failed: {exc}") from exc
    if replay.get("status") != summary.get("arm_o_replay_status"):
        raise MaterializationBridgeError("ARM-O replay status mismatch")
    if len(ledger) != summary.get("ledger_entry_count"):
        raise MaterializationBridgeError("ledger count mismatch")
    if target.get("target_count") != summary.get("target_count"):
        raise MaterializationBridgeError("target count mismatch")
    if _digest(path / "arm_o_run" / "MANIFEST.sha256") != summary.get("arm_o_manifest_sha256"):
        raise MaterializationBridgeError("ARM-O manifest hash mismatch")
    if directory_manifest_sha256(path / "arm_o_target_input_view") != summary.get("target_input_view_manifest_sha256"):
        raise MaterializationBridgeError("target input view manifest hash mismatch")
    original_files = {
        item.relative_to(path / "arm_o_run").as_posix(): _digest(item)
        for item in (path / "arm_o_run").rglob("*")
        if item.is_file() and item.name != "MANIFEST.sha256"
    }
    view_files = {
        item.relative_to(path / "arm_o_target_input_view").as_posix(): _digest(item)
        for item in (path / "arm_o_target_input_view").rglob("*")
        if item.is_file() and item.name != "MANIFEST.sha256"
    }
    if original_files != view_files:
        raise MaterializationBridgeError("target input view payload differs from ARM-O run")
    if directory_manifest_sha256(path / "target_archive") != summary.get("target_archive_manifest_sha256"):
        raise MaterializationBridgeError("target archive manifest hash mismatch")
    if summary.get("backtest_overlap_status") != "NO_FUTURE_TARGETS_AFTER_2025_UNTIL_OFFICIAL_ENGINE_PERIOD_IS_EXTENDED":
        raise MaterializationBridgeError("unexpected overlap status")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-policy")
    validate.add_argument("--policy", type=Path, required=True)
    convert = sub.add_parser("convert-v087")
    convert.add_argument("--policy", type=Path, required=True)
    convert.add_argument("--snapshot", type=Path, required=True)
    convert.add_argument("--vertical-output", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--created-at", required=True)
    verify_bridge = sub.add_parser("verify-observations")
    verify_bridge.add_argument("--policy", type=Path, required=True)
    verify_bridge.add_argument("--bridge", type=Path, required=True)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--bridge-policy", type=Path, required=True)
    materialize.add_argument("--engine-policy", type=Path, required=True)
    materialize.add_argument("--target-policy", type=Path, required=True)
    materialize.add_argument("--weights", type=Path, required=True)
    materialize.add_argument("--observation-bridge", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    materialize.add_argument("--run-id", required=True)
    materialize.add_argument("--vintage-id", required=True)
    materialize.add_argument("--created-at", required=True)
    verify_materialized = sub.add_parser("verify-materialization")
    verify_materialized.add_argument("--bridge-policy", type=Path, required=True)
    verify_materialized.add_argument("--target-policy", type=Path, required=True)
    verify_materialized.add_argument("--materialization", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-policy":
            policy = BridgePolicy.load(args.policy)
            payload = {
                "status": "ARM_O_MATERIALIZATION_BRIDGE_V0101_VALID",
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "availability_semantics": policy.availability_semantics,
                "gates": dict(policy.gates),
            }
        elif args.command == "convert-v087":
            payload = build_observation_bridge(
                policy_path=args.policy, snapshot_dir=args.snapshot,
                vertical_output_dir=args.vertical_output, output_dir=args.output,
                created_at=args.created_at,
            )
        elif args.command == "verify-observations":
            payload = verify_observation_bridge(args.bridge, policy_path=args.policy)
        elif args.command == "materialize":
            payload = materialize_arm_o_bridge(
                bridge_policy_path=args.bridge_policy,
                engine_policy_path=args.engine_policy,
                target_policy_path=args.target_policy,
                weights_path=args.weights,
                observation_bridge=args.observation_bridge,
                output_dir=args.output, run_id=args.run_id,
                vintage_id=args.vintage_id, created_at=args.created_at,
            )
        elif args.command == "verify-materialization":
            payload = verify_materialization(
                args.materialization, bridge_policy_path=args.bridge_policy,
                target_policy_path=args.target_policy,
            )
        else:  # pragma: no cover
            raise MaterializationBridgeError("unknown command")
    except (MaterializationBridgeError, BacktestProtocolError, OfficialEngineError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
