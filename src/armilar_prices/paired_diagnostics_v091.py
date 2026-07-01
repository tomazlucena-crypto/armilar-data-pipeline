"""Paired economic diagnostics for the Armilar v0.9.0 B0-B3 backtest."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

getcontext().prec = 42

MODELS = (
    "B0_GLOBAL_EQUAL_HEADLINE",
    "B1_ARMILAR_WEIGHTED_HEADLINE",
    "B2_CATEGORY_CARRY_FORWARD",
    "B3_HIERARCHICAL_COMPLETION",
)
REQUIRED_CASE_FIELDS = {
    "case_id",
    "scenario",
    "origin_period",
    "target_period",
    "horizon_months",
    "masked_group",
    "model",
    "truth_index",
    "estimated_index",
    "absolute_error_bps",
    "masked_cell_mape_percent",
    "evidence_class",
    "economy_code",
    "source_category",
}
INVARIANT_FIELDS = (
    "case_id",
    "scenario",
    "origin_period",
    "target_period",
    "horizon_months",
    "masked_group",
    "truth_index",
    "economy_code",
    "source_category",
)


class PairedDiagnosticsError(RuntimeError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    challenger: str
    baseline: str


@dataclass(frozen=True)
class DiagnosticsPolicy:
    policy_version: str
    required_backtest_policy_version: str
    required_vintage_mode: str
    minimum_cases_per_priority: int
    pairs: tuple[PairSpec, ...]
    research_release_allowed: bool
    monetary_release_allowed: bool

    @classmethod
    def load(cls, path: Path | str) -> "DiagnosticsPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "required_backtest_policy_version",
            "required_vintage_mode",
            "minimum_cases_per_priority",
            "pairs",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise PairedDiagnosticsError("POLICY_FIELD_MISSING", ", ".join(missing))
        try:
            pairs = tuple(
                PairSpec(
                    pair_id=str(item["pair_id"]),
                    challenger=str(item["challenger"]),
                    baseline=str(item["baseline"]),
                )
                for item in payload["pairs"]
            )
        except (KeyError, TypeError) as exc:
            raise PairedDiagnosticsError("PAIR_POLICY_INVALID", str(exc)) from exc
        policy = cls(
            policy_version=str(payload["policy_version"]),
            required_backtest_policy_version=str(payload["required_backtest_policy_version"]),
            required_vintage_mode=str(payload["required_vintage_mode"]),
            minimum_cases_per_priority=int(payload["minimum_cases_per_priority"]),
            pairs=pairs,
            research_release_allowed=bool(payload["research_release_allowed"]),
            monetary_release_allowed=bool(payload["monetary_release_allowed"]),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.policy_version != "0.9.1":
            raise PairedDiagnosticsError("POLICY_VERSION_UNSUPPORTED", self.policy_version)
        if self.required_backtest_policy_version != "0.9.0":
            raise PairedDiagnosticsError(
                "BACKTEST_POLICY_VERSION_UNSUPPORTED", self.required_backtest_policy_version
            )
        if self.required_vintage_mode != "FINAL_VINTAGE_PSEUDO_REAL_TIME":
            raise PairedDiagnosticsError("VINTAGE_MODE_UNSUPPORTED", self.required_vintage_mode)
        if self.minimum_cases_per_priority < 1:
            raise PairedDiagnosticsError("INVALID_MINIMUM_CASES", "must be positive")
        if self.research_release_allowed or self.monetary_release_allowed:
            raise PairedDiagnosticsError("RELEASE_GATE_WEAKENED", "flags must remain false")
        if not self.pairs:
            raise PairedDiagnosticsError("EMPTY_PAIR_POLICY", "no model pairs")
        pair_ids = [item.pair_id for item in self.pairs]
        if len(pair_ids) != len(set(pair_ids)):
            raise PairedDiagnosticsError("DUPLICATE_PAIR_ID", str(pair_ids))
        for item in self.pairs:
            if item.challenger not in MODELS or item.baseline not in MODELS:
                raise PairedDiagnosticsError("UNKNOWN_MODEL", item.pair_id)
            if item.challenger == item.baseline:
                raise PairedDiagnosticsError("SELF_COMPARISON", item.pair_id)
        required_pairs = {
            ("B1_ARMILAR_WEIGHTED_HEADLINE", "B0_GLOBAL_EQUAL_HEADLINE"),
            ("B2_CATEGORY_CARRY_FORWARD", "B1_ARMILAR_WEIGHTED_HEADLINE"),
            ("B3_HIERARCHICAL_COMPLETION", "B2_CATEGORY_CARRY_FORWARD"),
            ("B3_HIERARCHICAL_COMPLETION", "B1_ARMILAR_WEIGHTED_HEADLINE"),
        }
        actual_pairs = {(item.challenger, item.baseline) for item in self.pairs}
        if actual_pairs != required_pairs:
            raise PairedDiagnosticsError("PAIR_CONTRACT_MISMATCH", str(sorted(actual_pairs)))


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    scenario: str
    origin_period: str
    target_period: str
    horizon_months: int
    masked_group: str
    model: str
    truth_index: Decimal
    estimated_index: Decimal
    absolute_error_bps: Decimal
    masked_cell_mape_percent: Decimal
    evidence_class: str
    economy_code: str
    source_category: str


@dataclass(frozen=True)
class PairDelta:
    pair_id: str
    challenger: str
    baseline: str
    case_id: str
    scenario: str
    origin_period: str
    target_period: str
    horizon_months: int
    masked_group: str
    economy_code: str
    source_category: str
    challenger_absolute_error_bps: Decimal
    baseline_absolute_error_bps: Decimal
    delta_absolute_bps: Decimal
    challenger_masked_cell_mape_percent: Decimal
    baseline_masked_cell_mape_percent: Decimal
    delta_masked_cell_mape_percent: Decimal
    outcome: str


def _installed_version() -> str:
    try:
        return package_version("armilar-data-pipeline")
    except PackageNotFoundError:
        return "0+unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _resolve_inside(root: Path, relative: str, code: str) -> Path:
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise PairedDiagnosticsError(code, relative)
    return candidate


def verify_manifest(root: Path | str) -> None:
    base = Path(root)
    manifest = base / "MANIFEST.sha256"
    if not manifest.is_file():
        raise PairedDiagnosticsError("MANIFEST_MISSING", str(manifest))
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise PairedDiagnosticsError("MANIFEST_INVALID", line)
        expected, relative = parts
        if len(expected) != 64 or any(character not in "0123456789abcdefABCDEF" for character in expected):
            raise PairedDiagnosticsError("MANIFEST_INVALID", line)
        expected = expected.lower()
        if relative in seen:
            raise PairedDiagnosticsError("MANIFEST_DUPLICATE_PATH", relative)
        seen.add(relative)
        target = _resolve_inside(base, relative, "MANIFEST_PATH_INVALID")
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise PairedDiagnosticsError("MANIFEST_HASH_MISMATCH", relative)


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise PairedDiagnosticsError(code, detail) from exc
    if not result.is_finite():
        raise PairedDiagnosticsError(code, detail)
    return result


def _load_summary(input_root: Path, policy: DiagnosticsPolicy) -> Mapping[str, Any]:
    path = input_root / "backtest_summary.json"
    if not path.is_file():
        raise PairedDiagnosticsError("BACKTEST_SUMMARY_MISSING", str(path))
    summary = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "policy_version": policy.required_backtest_policy_version,
        "vintage_mode": policy.required_vintage_mode,
        "publication_aware": False,
        "headline_source_independent": True,
        "rejected_v089_experiment_reused": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            code = "RELEASE_GATE_WEAKENED" if field.endswith("release_allowed") else "BACKTEST_CONTRACT_MISMATCH"
            raise PairedDiagnosticsError(code, f"{field}={summary.get(field)!r}")
    if summary.get("official_headline_source") != "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT":
        raise PairedDiagnosticsError("HEADLINE_SOURCE_MISMATCH", str(summary.get("official_headline_source")))
    return summary


def _load_cases(input_root: Path) -> tuple[CaseResult, ...]:
    path = input_root / "backtest_cases.csv"
    if not path.is_file():
        raise PairedDiagnosticsError("BACKTEST_CASES_MISSING", str(path))
    rows: list[CaseResult] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_CASE_FIELDS - fields)
        if missing:
            raise PairedDiagnosticsError("BACKTEST_CASE_SCHEMA_MISMATCH", ", ".join(missing))
        for line_number, row in enumerate(reader, start=2):
            absolute_error = _decimal(
                row["absolute_error_bps"], "INVALID_ABSOLUTE_ERROR", f"line {line_number}"
            )
            mape = _decimal(row["masked_cell_mape_percent"], "INVALID_MAPE", f"line {line_number}")
            if absolute_error < 0 or mape < 0:
                raise PairedDiagnosticsError("NEGATIVE_ERROR_METRIC", f"line {line_number}")
            model = str(row["model"])
            if model not in MODELS:
                raise PairedDiagnosticsError("UNKNOWN_MODEL", f"line {line_number}: {model}")
            try:
                horizon = int(row["horizon_months"])
            except ValueError as exc:
                raise PairedDiagnosticsError("INVALID_HORIZON", f"line {line_number}") from exc
            if horizon <= 0:
                raise PairedDiagnosticsError("INVALID_HORIZON", f"line {line_number}")
            rows.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    scenario=str(row["scenario"]),
                    origin_period=str(row["origin_period"]),
                    target_period=str(row["target_period"]),
                    horizon_months=horizon,
                    masked_group=str(row["masked_group"]),
                    model=model,
                    truth_index=_decimal(row["truth_index"], "INVALID_TRUTH_INDEX", f"line {line_number}"),
                    estimated_index=_decimal(
                        row["estimated_index"], "INVALID_ESTIMATED_INDEX", f"line {line_number}"
                    ),
                    absolute_error_bps=absolute_error,
                    masked_cell_mape_percent=mape,
                    evidence_class=str(row["evidence_class"]),
                    economy_code=str(row["economy_code"]),
                    source_category=str(row["source_category"]),
                )
            )
    if not rows:
        raise PairedDiagnosticsError("EMPTY_BACKTEST_CASES", str(path))
    return tuple(rows)


def _index_cases(cases: Sequence[CaseResult], summary: Mapping[str, Any]) -> Mapping[str, Mapping[str, CaseResult]]:
    indexed: MutableMapping[str, dict[str, CaseResult]] = defaultdict(dict)
    for case in cases:
        if case.model in indexed[case.case_id]:
            raise PairedDiagnosticsError("DUPLICATE_MODEL_CASE", f"{case.case_id}/{case.model}")
        indexed[case.case_id][case.model] = case
    expected_models = set(MODELS)
    for case_id, by_model in indexed.items():
        if set(by_model) != expected_models:
            raise PairedDiagnosticsError(
                "COMPARISON_SAMPLE_MISMATCH", f"{case_id}: {sorted(by_model)}"
            )
        reference = by_model[MODELS[0]]
        for model in MODELS[1:]:
            candidate = by_model[model]
            for field in INVARIANT_FIELDS:
                if getattr(reference, field) != getattr(candidate, field):
                    raise PairedDiagnosticsError(
                        "CASE_METADATA_MISMATCH", f"{case_id}/{model}/{field}"
                    )
    declared = summary.get("common_case_count_per_model")
    if not isinstance(declared, int) or declared != len(indexed):
        raise PairedDiagnosticsError(
            "CASE_COUNT_MISMATCH", f"declared={declared} actual={len(indexed)}"
        )
    if len(cases) != len(indexed) * len(MODELS):
        raise PairedDiagnosticsError("CASE_COUNT_MISMATCH", str(len(cases)))
    return indexed


def _build_deltas(
    indexed: Mapping[str, Mapping[str, CaseResult]], policy: DiagnosticsPolicy
) -> tuple[PairDelta, ...]:
    rows: list[PairDelta] = []
    for case_id in sorted(indexed):
        by_model = indexed[case_id]
        for pair in policy.pairs:
            challenger = by_model[pair.challenger]
            baseline = by_model[pair.baseline]
            delta = challenger.absolute_error_bps - baseline.absolute_error_bps
            if delta < 0:
                outcome = "IMPROVEMENT"
            elif delta > 0:
                outcome = "REGRESSION"
            else:
                outcome = "TIE"
            rows.append(
                PairDelta(
                    pair_id=pair.pair_id,
                    challenger=pair.challenger,
                    baseline=pair.baseline,
                    case_id=case_id,
                    scenario=challenger.scenario,
                    origin_period=challenger.origin_period,
                    target_period=challenger.target_period,
                    horizon_months=challenger.horizon_months,
                    masked_group=challenger.masked_group,
                    economy_code=challenger.economy_code,
                    source_category=challenger.source_category,
                    challenger_absolute_error_bps=challenger.absolute_error_bps,
                    baseline_absolute_error_bps=baseline.absolute_error_bps,
                    delta_absolute_bps=delta,
                    challenger_masked_cell_mape_percent=challenger.masked_cell_mape_percent,
                    baseline_masked_cell_mape_percent=baseline.masked_cell_mape_percent,
                    delta_masked_cell_mape_percent=(
                        challenger.masked_cell_mape_percent - baseline.masked_cell_mape_percent
                    ),
                    outcome=outcome,
                )
            )
    return tuple(rows)


def _percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise PairedDiagnosticsError("EMPTY_METRIC_GROUP", "percentile")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] * (Decimal("1") - fraction) + ordered[upper] * fraction


def _aggregate(rows: Sequence[PairDelta]) -> Mapping[str, Any]:
    if not rows:
        raise PairedDiagnosticsError("EMPTY_METRIC_GROUP", "pair rows")
    count = len(rows)
    n = Decimal(count)
    deltas = [row.delta_absolute_bps for row in rows]
    mape_deltas = [row.delta_masked_cell_mape_percent for row in rows]
    challenger = [row.challenger_absolute_error_bps for row in rows]
    baseline = [row.baseline_absolute_error_bps for row in rows]
    improvements = sum(row.outcome == "IMPROVEMENT" for row in rows)
    regressions = sum(row.outcome == "REGRESSION" for row in rows)
    ties = count - improvements - regressions
    minimum = min(deltas)
    maximum = max(deltas)
    return {
        "case_count": count,
        "improvement_count": improvements,
        "tie_count": ties,
        "regression_count": regressions,
        "improvement_rate": Decimal(improvements) / n,
        "regression_rate": Decimal(regressions) / n,
        "mean_challenger_absolute_bps": sum(challenger, Decimal("0")) / n,
        "mean_baseline_absolute_bps": sum(baseline, Decimal("0")) / n,
        "mean_delta_absolute_bps": sum(deltas, Decimal("0")) / n,
        "median_delta_absolute_bps": _percentile(deltas, Decimal("0.5")),
        "p95_delta_absolute_bps": _percentile(deltas, Decimal("0.95")),
        "worst_regression_bps": max(maximum, Decimal("0")),
        "best_improvement_bps": max(-minimum, Decimal("0")),
        "mean_delta_masked_cell_mape_percent": sum(mape_deltas, Decimal("0")) / n,
    }


def _group(rows: Sequence[PairDelta], fields: Sequence[str]) -> list[dict[str, Any]]:
    groups: MutableMapping[tuple[Any, ...], list[PairDelta]] = defaultdict(list)
    for row in rows:
        key = tuple(getattr(row, field) for field in fields)
        groups[key].append(row)
    result: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda item: tuple(str(value) for value in item)):
        metrics = dict(_aggregate(groups[key]))
        item = {field: value for field, value in zip(fields, key)}
        item.update(metrics)
        result.append(item)
    return result


def _decimal_text(value: Decimal, places: int = 8) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _serialise_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            places = 10 if key.endswith("rate") else 8
            result[key] = _decimal_text(value, places)
        else:
            result[key] = value
    return result


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    _atomic_write(root / "MANIFEST.sha256", ("\n".join(lines) + "\n").encode("utf-8"))


def _priority_sources(
    deltas: Sequence[PairDelta], minimum_cases: int
) -> Mapping[str, Any]:
    target = [row for row in deltas if row.pair_id == "B3_VS_B2"]
    if not target:
        raise PairedDiagnosticsError("PAIR_NOT_AVAILABLE", "B3_VS_B2")
    dimensions = (
        ("scenario", "horizon_months"),
        ("economy_code",),
        ("source_category",),
    )
    eligible: list[dict[str, Any]] = []
    for fields in dimensions:
        for row in _group(target, fields):
            if row["case_count"] < minimum_cases:
                continue
            if any(row[field] == "" for field in fields):
                continue
            eligible.append(
                {
                    "dimension": "+".join(fields),
                    "label": " | ".join(f"{field}={row[field]}" for field in fields),
                    "case_count": row["case_count"],
                    "mean_delta_absolute_bps_vs_b2": row["mean_delta_absolute_bps"],
                    "p95_delta_absolute_bps_vs_b2": row["p95_delta_absolute_bps"],
                    "regression_rate_vs_b2": row["regression_rate"],
                    "mean_b3_absolute_bps": row["mean_challenger_absolute_bps"],
                    "mean_b2_absolute_bps": row["mean_baseline_absolute_bps"],
                }
            )
    regressions = [
        {**row, "priority_status": "MEAN_REGRESSION"}
        for row in eligible
        if row["mean_delta_absolute_bps_vs_b2"] > 0
    ]
    improvements = [
        {**row, "priority_status": "MEAN_IMPROVEMENT"}
        for row in eligible
        if row["mean_delta_absolute_bps_vs_b2"] < 0
    ]
    regressions.sort(
        key=lambda row: (
            -row["mean_delta_absolute_bps_vs_b2"],
            -row["regression_rate_vs_b2"],
            row["dimension"],
            row["label"],
        )
    )
    improvements.sort(
        key=lambda row: (
            row["mean_delta_absolute_bps_vs_b2"],
            row["regression_rate_vs_b2"],
            row["dimension"],
            row["label"],
        )
    )
    overall = _aggregate(target)
    return {
        "comparison": "B3_HIERARCHICAL_COMPLETION_VS_B2_CATEGORY_CARRY_FORWARD",
        "ranking_metric": "mean_delta_absolute_bps_vs_b2",
        "interpretation": "Positive values are B3 regressions; negative values are B3 improvements.",
        "minimum_cases_per_priority": minimum_cases,
        "overall": overall,
        "top_regressions": regressions[:3],
        "top_improvements": improvements[:3],
        "regression_priority_count": len(regressions),
        "model_promotion_allowed": False,
    }


def build_diagnostics(
    policy_path: Path | str,
    input_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = DiagnosticsPolicy.load(policy_path)
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise PairedDiagnosticsError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)
    verify_manifest(input_root)
    summary = _load_summary(input_root, policy)
    cases = _load_cases(input_root)
    indexed = _index_cases(cases, summary)
    deltas = _build_deltas(indexed, policy)

    case_rows = [
        _serialise_row(
            {
                "pair_id": row.pair_id,
                "challenger": row.challenger,
                "baseline": row.baseline,
                "case_id": row.case_id,
                "scenario": row.scenario,
                "origin_period": row.origin_period,
                "target_period": row.target_period,
                "horizon_months": row.horizon_months,
                "masked_group": row.masked_group,
                "economy_code": row.economy_code,
                "source_category": row.source_category,
                "challenger_absolute_error_bps": row.challenger_absolute_error_bps,
                "baseline_absolute_error_bps": row.baseline_absolute_error_bps,
                "delta_absolute_bps": row.delta_absolute_bps,
                "challenger_masked_cell_mape_percent": row.challenger_masked_cell_mape_percent,
                "baseline_masked_cell_mape_percent": row.baseline_masked_cell_mape_percent,
                "delta_masked_cell_mape_percent": row.delta_masked_cell_mape_percent,
                "outcome": row.outcome,
            }
        )
        for row in deltas
    ]
    _write_csv(output_root / "paired_case_deltas.csv", list(case_rows[0]), case_rows)

    specs = {
        "pair_summary.csv": ("pair_id", "challenger", "baseline"),
        "pair_by_scenario_horizon.csv": (
            "pair_id",
            "challenger",
            "baseline",
            "scenario",
            "horizon_months",
        ),
        "pair_by_economy.csv": ("pair_id", "challenger", "baseline", "economy_code"),
        "pair_by_category.csv": ("pair_id", "challenger", "baseline", "source_category"),
    }
    outputs: dict[str, list[dict[str, Any]]] = {}
    for filename, fields in specs.items():
        grouped = [
            _serialise_row(row)
            for row in _group(deltas, fields)
            if not any(row[field] == "" for field in fields)
        ]
        if not grouped:
            raise PairedDiagnosticsError("EMPTY_METRIC_OUTPUT", filename)
        outputs[filename] = grouped
        _write_csv(output_root / filename, list(grouped[0]), grouped)

    priorities = _priority_sources(deltas, policy.minimum_cases_per_priority)
    serialised_priorities = {
        **{
            key: value
            for key, value in priorities.items()
            if key not in {"overall", "top_regressions", "top_improvements"}
        },
        "overall": _serialise_row(priorities["overall"]),
        "top_regressions": [_serialise_row(row) for row in priorities["top_regressions"]],
        "top_improvements": [_serialise_row(row) for row in priorities["top_improvements"]],
    }
    _atomic_write(
        output_root / "priority_error_sources.json",
        _canonical_json_bytes(serialised_priorities),
    )

    input_manifest_hash = _sha256((input_root / "MANIFEST.sha256").read_bytes())
    run_summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "input_backtest_policy_version": summary["policy_version"],
        "status": "PAIRED_DIAGNOSTICS_COMPLETED_WITH_VINTAGE_LIMITATION",
        "vintage_mode": summary["vintage_mode"],
        "publication_aware": False,
        "headline_source_independent": True,
        "common_case_count_per_model": len(indexed),
        "pair_count": len(policy.pairs),
        "paired_case_row_count": len(deltas),
        "input_backtest_manifest_sha256": input_manifest_hash,
        "rejected_v089_experiment_reused": False,
        "model_code_changed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "run_summary.json", _canonical_json_bytes(run_summary))
    _write_report(output_root, outputs["pair_summary.csv"], serialised_priorities, run_summary)
    _write_manifest(output_root)
    return run_summary


def _write_report(
    output_root: Path,
    pair_summary: Sequence[Mapping[str, Any]],
    priorities: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    lines = [
        "# Armilar v0.9.1 paired economic diagnostics",
        "",
        "## Interpretation",
        "",
        "Every comparison uses the exact same v0.9.0 `case_id`. Negative mean deltas indicate that the challenger reduced absolute index error. Positive values indicate regression.",
        "",
        "## Overall paired comparisons",
        "",
        "| Pair | Mean challenger error (bps) | Mean baseline error (bps) | Mean delta (bps) | Improvement rate | Regression rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in pair_summary:
        lines.append(
            f"| {row['pair_id']} | {row['mean_challenger_absolute_bps']} | "
            f"{row['mean_baseline_absolute_bps']} | {row['mean_delta_absolute_bps']} | "
            f"{row['improvement_rate']} | {row['regression_rate']} |"
        )
    lines.extend(["", "## Measured B3-versus-B2 mean regressions", ""])
    if not priorities["top_regressions"]:
        lines.append("No eligible mean regressions were measured.")
    for rank, row in enumerate(priorities["top_regressions"], start=1):
        lines.append(
            f"{rank}. `{row['label']}`: mean B3-minus-B2 delta "
            f"{row['mean_delta_absolute_bps_vs_b2']} bps; regression rate "
            f"{row['regression_rate_vs_b2']}; {row['case_count']} cases; "
            f"status `{row['priority_status']}`."
        )
    lines.extend(["", "## Largest B3-versus-B2 mean improvements", ""])
    if not priorities["top_improvements"]:
        lines.append("No eligible mean improvements were measured.")
    for rank, row in enumerate(priorities["top_improvements"], start=1):
        lines.append(
            f"{rank}. `{row['label']}`: mean B3-minus-B2 delta "
            f"{row['mean_delta_absolute_bps_vs_b2']} bps; regression rate "
            f"{row['regression_rate_vs_b2']}; {row['case_count']} cases; "
            f"status `{row['priority_status']}`."
        )
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "These diagnostics identify where further work should be concentrated. They do not authorise promotion of B3, a change in methodology or a release-gate change.",
            "",
            "## Vintage limitation",
            "",
            "The input remains `FINAL_VINTAGE_PSEUDO_REAL_TIME` and is not publication-aware. Paired results therefore measure missing-cell completion under final-vintage data, not a fully reconstructed real-time information set.",
            "",
            f"Input cases per model: {summary['common_case_count_per_model']}.",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
        ]
    )
    _atomic_write(output_root / "PAIRED_DIAGNOSTICS_REPORT.md", ("\n".join(lines) + "\n").encode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.1 paired economic diagnostics")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verify_only:
        verify_manifest(args.output_dir)
        print(json.dumps({"status": "MANIFEST_VERIFIED", "output_dir": args.output_dir}))
        return 0
    summary = build_diagnostics(args.policy, args.input_dir, args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
