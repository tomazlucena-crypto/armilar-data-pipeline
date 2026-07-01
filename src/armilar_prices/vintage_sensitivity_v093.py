"""Compare first-published release-time B0-B4 results with final-vintage results."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from armilar_prices.release_time_backtest_v093 import (
    ALL_MODELS,
    B4,
    COMPLETION_MODE,
    ReleaseTimeBacktestError,
    verify_manifest,
)

FINAL_MODE = "FINAL_VINTAGE_PSEUDO_REAL_TIME"
FIRST_MODE = COMPLETION_MODE


class VintageSensitivityError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _installed_version() -> str:
    try:
        return metadata.version("armilar-data-pipeline")
    except metadata.PackageNotFoundError:
        return "0.9.3"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", newline="", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_manifest(root: Path) -> None:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
    )
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    _atomic_write(
        root / "MANIFEST.sha256",
        (("\n".join(lines) + "\n") if lines else "").encode("utf-8"),
    )


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise VintageSensitivityError(code, detail) from exc
    if not parsed.is_finite() or parsed < 0:
        raise VintageSensitivityError(code, detail)
    return parsed


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise VintageSensitivityError("EMPTY_METRIC_SAMPLE")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _p95(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise VintageSensitivityError("EMPTY_METRIC_SAMPLE")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(Decimal("0.95") * Decimal(len(ordered))) - 1)]


def _text(value: Decimal, places: int = 10) -> str:
    return format(value.quantize(Decimal(1).scaleb(-places)), "f")


def _load_json(path: Path, code: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VintageSensitivityError(code, str(path)) from exc
    if not isinstance(payload, Mapping):
        raise VintageSensitivityError(code, str(path))
    return payload


def _load_release_cases(root: Path) -> tuple[Mapping[tuple[str, str], Mapping[str, str]], Mapping[str, Any]]:
    verify_manifest(root)
    summary = _load_json(root / "backtest_summary.json", "RELEASE_SUMMARY_INVALID")
    checks = {
        "status": "FIRST_PUBLISHED_RELEASE_TIME_COMPLETION_BACKTEST_COMPLETED",
        "completion_mode": FIRST_MODE,
        "release_time_completion_comparison_allowed": True,
        "pre_release_forecast": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            raise VintageSensitivityError("RELEASE_CONTRACT_MISMATCH", field)
    path = root / "backtest_cases.csv"
    rows: dict[tuple[str, str], Mapping[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "case_id",
            "model",
            "scenario",
            "horizon_months",
            "economy_code",
            "source_category",
            "absolute_error_bps",
            "target_period",
        }
        if not required.issubset(set(reader.fieldnames or ())):
            raise VintageSensitivityError("RELEASE_CASE_SCHEMA_INVALID")
        for row in reader:
            key = (str(row["case_id"]), str(row["model"]))
            if key in rows:
                raise VintageSensitivityError("DUPLICATE_RELEASE_CASE", "/".join(key))
            if key[1] not in ALL_MODELS:
                raise VintageSensitivityError("UNKNOWN_RELEASE_MODEL", key[1])
            _decimal(str(row["absolute_error_bps"]), "RELEASE_ERROR_INVALID", "/".join(key))
            rows[key] = row
    declared = summary.get("common_case_count_per_model")
    if not isinstance(declared, int) or len(rows) != declared * len(ALL_MODELS):
        raise VintageSensitivityError("RELEASE_CASE_COUNT_MISMATCH")
    return rows, summary


def _load_final_core_cases(root: Path) -> tuple[Mapping[tuple[str, str], Mapping[str, str]], Mapping[str, Any]]:
    verify_manifest(root)
    summary = _load_json(root / "backtest_summary.json", "FINAL_SUMMARY_INVALID")
    checks = {
        "policy_version": "0.9.0",
        "vintage_mode": FINAL_MODE,
        "publication_aware": False,
        "headline_source_independent": True,
        "rejected_v089_experiment_reused": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            raise VintageSensitivityError("FINAL_BACKTEST_CONTRACT_MISMATCH", field)
    path = root / "backtest_cases.csv"
    rows: dict[tuple[str, str], Mapping[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "case_id",
            "model",
            "scenario",
            "horizon_months",
            "economy_code",
            "source_category",
            "absolute_error_bps",
            "target_period",
        }
        if not required.issubset(set(reader.fieldnames or ())):
            raise VintageSensitivityError("FINAL_CASE_SCHEMA_INVALID")
        for row in reader:
            key = (str(row["case_id"]), str(row["model"]))
            if key in rows:
                raise VintageSensitivityError("DUPLICATE_FINAL_CASE", "/".join(key))
            if key[1] not in ALL_MODELS[:-1]:
                raise VintageSensitivityError("UNKNOWN_FINAL_MODEL", key[1])
            _decimal(str(row["absolute_error_bps"]), "FINAL_ERROR_INVALID", "/".join(key))
            rows[key] = row
    return rows, summary


def _load_final_b4(root: Path) -> tuple[Mapping[str, Mapping[str, str]], Mapping[str, Any]]:
    verify_manifest(root)
    summary = _load_json(root / "run_summary.json", "FINAL_B4_SUMMARY_INVALID")
    checks = {
        "policy_version": "0.9.2",
        "vintage_mode": FINAL_MODE,
        "publication_aware": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            raise VintageSensitivityError("FINAL_B4_CONTRACT_MISMATCH", field)
    path = root / "safeguard_case_results.csv"
    rows: dict[str, Mapping[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "case_id",
            "scenario",
            "horizon_months",
            "economy_code",
            "source_category",
            "target_period",
            "b4_absolute_error_bps",
        }
        if not required.issubset(set(reader.fieldnames or ())):
            raise VintageSensitivityError("FINAL_B4_CASE_SCHEMA_INVALID")
        for row in reader:
            case_id = str(row["case_id"])
            if case_id in rows:
                raise VintageSensitivityError("DUPLICATE_FINAL_B4_CASE", case_id)
            _decimal(str(row["b4_absolute_error_bps"]), "FINAL_B4_ERROR_INVALID", case_id)
            rows[case_id] = row
    return rows, summary


def _scope_values(row: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    values = [
        ("overall", "ALL"),
        ("scenario", str(row["scenario"])),
        ("horizon_months", str(row["horizon_months"])),
    ]
    if str(row.get("economy_code", "")):
        values.append(("economy_code", str(row["economy_code"])))
    if str(row.get("source_category", "")):
        values.append(("source_category", str(row["source_category"])))
    return tuple(values)


def build_vintage_sensitivity(
    release_time_dir: Path | str,
    final_backtest_dir: Path | str,
    final_safeguard_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    release_root = Path(release_time_dir)
    final_root = Path(final_backtest_dir)
    safeguard_root = Path(final_safeguard_dir)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise VintageSensitivityError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)
    release_rows, release_summary = _load_release_cases(release_root)
    final_rows, final_summary = _load_final_core_cases(final_root)
    final_b4_rows, final_b4_summary = _load_final_b4(safeguard_root)

    release_case_ids = {case_id for case_id, _ in release_rows}
    final_case_ids = {case_id for case_id, _ in final_rows}
    if release_case_ids != final_case_ids or release_case_ids != set(final_b4_rows):
        raise VintageSensitivityError(
            "VINTAGE_COMPARISON_SAMPLE_MISMATCH",
            f"release={len(release_case_ids)} final={len(final_case_ids)} b4={len(final_b4_rows)}",
        )
    for case_id in release_case_ids:
        release_reference = release_rows[(case_id, ALL_MODELS[0])]
        final_reference = final_rows[(case_id, ALL_MODELS[0])]
        final_b4 = final_b4_rows[case_id]
        for field in (
            "scenario",
            "horizon_months",
            "economy_code",
            "source_category",
            "target_period",
        ):
            if str(release_reference[field]) != str(final_reference[field]):
                raise VintageSensitivityError("CASE_METADATA_MISMATCH", f"{case_id}/{field}")
            if str(release_reference[field]) != str(final_b4[field]):
                raise VintageSensitivityError("B4_CASE_METADATA_MISMATCH", f"{case_id}/{field}")

    grouped: MutableMapping[tuple[str, str, str], list[tuple[Decimal, Decimal]]] = defaultdict(list)
    case_rows: list[dict[str, str]] = []
    for case_id in sorted(release_case_ids):
        reference = release_rows[(case_id, ALL_MODELS[0])]
        for model in ALL_MODELS:
            release_error = _decimal(
                str(release_rows[(case_id, model)]["absolute_error_bps"]),
                "RELEASE_ERROR_INVALID",
                f"{case_id}/{model}",
            )
            if model == B4:
                final_error = _decimal(
                    str(final_b4_rows[case_id]["b4_absolute_error_bps"]),
                    "FINAL_ERROR_INVALID",
                    f"{case_id}/{model}",
                )
            else:
                final_error = _decimal(
                    str(final_rows[(case_id, model)]["absolute_error_bps"]),
                    "FINAL_ERROR_INVALID",
                    f"{case_id}/{model}",
                )
            delta = release_error - final_error
            case_rows.append(
                {
                    "case_id": case_id,
                    "model": model,
                    "scenario": str(reference["scenario"]),
                    "horizon_months": str(reference["horizon_months"]),
                    "economy_code": str(reference["economy_code"]),
                    "source_category": str(reference["source_category"]),
                    "target_period": str(reference["target_period"]),
                    "first_published_absolute_error_bps": _text(release_error),
                    "final_vintage_absolute_error_bps": _text(final_error),
                    "first_minus_final_error_bps": _text(delta),
                }
            )
            for dimension, label in _scope_values(reference):
                grouped[(model, dimension, label)].append((release_error, final_error))
    _write_csv(output / "vintage_sensitivity_cases.csv", list(case_rows[0]), case_rows)

    aggregate_rows: list[dict[str, str]] = []
    for (model, dimension, label), values in sorted(grouped.items()):
        first = [left for left, _ in values]
        final = [right for _, right in values]
        deltas = [left - right for left, right in values]
        aggregate_rows.append(
            {
                "model": model,
                "dimension": dimension,
                "label": label,
                "case_count": str(len(values)),
                "first_published_mean_error_bps": _text(_mean(first)),
                "final_vintage_mean_error_bps": _text(_mean(final)),
                "mean_error_delta_bps": _text(_mean(deltas)),
                "first_published_p95_error_bps": _text(_p95(first)),
                "final_vintage_p95_error_bps": _text(_p95(final)),
                "p95_error_delta_bps": _text(_p95(first) - _p95(final)),
                "first_published_better_rate": _text(
                    Decimal(sum(left < right for left, right in values)) / Decimal(len(values))
                ),
                "first_published_worse_rate": _text(
                    Decimal(sum(left > right for left, right in values)) / Decimal(len(values))
                ),
            }
        )
    _write_csv(
        output / "vintage_sensitivity_by_dimension.csv",
        list(aggregate_rows[0]),
        aggregate_rows,
    )

    overall = [row for row in aggregate_rows if row["dimension"] == "overall"]
    first_ranking = sorted(
        overall, key=lambda row: (Decimal(row["first_published_mean_error_bps"]), row["model"])
    )
    final_ranking = sorted(
        overall, key=lambda row: (Decimal(row["final_vintage_mean_error_bps"]), row["model"])
    )
    first_positions = {row["model"]: index + 1 for index, row in enumerate(first_ranking)}
    final_positions = {row["model"]: index + 1 for index, row in enumerate(final_ranking)}
    ranking_payload = {
        "first_published_ranking": [row["model"] for row in first_ranking],
        "final_vintage_ranking": [row["model"] for row in final_ranking],
        "ranking_changed": [row["model"] for row in first_ranking]
        != [row["model"] for row in final_ranking],
        "models": [
            {
                "model": model,
                "first_published_position": first_positions[model],
                "final_vintage_position": final_positions[model],
                "position_change": final_positions[model] - first_positions[model],
            }
            for model in ALL_MODELS
        ],
        "model_promotion_allowed": False,
    }
    _atomic_write(output / "model_ranking_sensitivity.json", _canonical_json(ranking_payload))

    summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": "0.9.3",
        "status": "FIRST_PUBLISHED_VS_FINAL_VINTAGE_SENSITIVITY_COMPLETED",
        "case_count_per_model": len(release_case_ids),
        "model_count": len(ALL_MODELS),
        "ranking_changed": ranking_payload["ranking_changed"],
        "release_time_input_manifest_sha256": _sha256(
            (release_root / "MANIFEST.sha256").read_bytes()
        ),
        "final_backtest_input_manifest_sha256": _sha256(
            (final_root / "MANIFEST.sha256").read_bytes()
        ),
        "final_safeguard_input_manifest_sha256": _sha256(
            (safeguard_root / "MANIFEST.sha256").read_bytes()
        ),
        "release_completion_mode": release_summary["completion_mode"],
        "final_vintage_mode": final_summary["vintage_mode"],
        "final_b4_vintage_mode": final_b4_summary["vintage_mode"],
        "pre_release_forecast_comparison_allowed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "run_summary.json", _canonical_json(summary))
    report = [
        "# Armilar v0.9.3 vintage sensitivity",
        "",
        "This report compares identical B0-B4 stress-test cases using official first-published values and the prior current-final snapshot.",
        "",
        f"Model ranking changed: `{str(ranking_payload['ranking_changed']).lower()}`.",
        "",
        "The comparison measures sensitivity to revisions and historical corrections. It does not constitute a pre-release forecast and does not authorise model promotion.",
        "",
        "`pre_release_forecast_comparison_allowed=false`",
        "",
        "`model_promotion_allowed=false`",
        "",
        "`research_release_allowed=false`",
        "",
        "`monetary_release_allowed=false`",
    ]
    _atomic_write(
        output / "VINTAGE_SENSITIVITY_REPORT.md", ("\n".join(report) + "\n").encode("utf-8")
    )
    _write_manifest(output)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.3 vintage sensitivity")
    parser.add_argument("--release-time-dir", required=True)
    parser.add_argument("--final-backtest-dir", required=True)
    parser.add_argument("--final-safeguard-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify_only:
        try:
            verify_manifest(args.output_dir)
        except ReleaseTimeBacktestError as exc:
            raise VintageSensitivityError(exc.code, exc.detail) from exc
        result = {"status": "MANIFEST_VERIFIED", "output_dir": args.output_dir}
    else:
        result = build_vintage_sensitivity(
            args.release_time_dir,
            args.final_backtest_dir,
            args.final_safeguard_dir,
            args.output_dir,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
