"""Independent-headline economic backtest orchestration for Armilar v0.9.0."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

try:
    from armilar_pipeline.version import installed_version
except ModuleNotFoundError:
    def installed_version() -> str:
        return "0+unknown"

from .backtest_core_v088 import (
    BacktestPolicy,
    Case,
    MODELS,
    Panel,
    _simple_mean,
    index_value,
)
from .backtest_core_v090 import (
    BacktestError,
    HeadlinePanel,
    load_headline_panel,
    load_panel,
    run_cases,
)

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


def _decimal_text(value: Decimal, places: int = 12) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _resolve_inside(root: Path, relative: str, code: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise BacktestError(code, relative)
    return candidate


def _percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise BacktestError("EMPTY_METRIC_GROUP", "percentile")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] * (Decimal("1") - fraction) + ordered[upper] * fraction


def _metrics(cases: Sequence[Case]) -> Mapping[str, Any]:
    if not cases:
        raise BacktestError("EMPTY_METRIC_GROUP", "cases")
    n = Decimal(len(cases))
    errors = [case.index_error for case in cases]
    absolute_errors = [abs(value) for value in errors]
    absolute_bps = [case.absolute_error_bps for case in cases]
    mapes = [case.masked_cell_mape_percent for case in cases]
    mse = sum((value * value for value in errors), Decimal("0")) / n
    return {
        "case_count": len(cases),
        "mae_index_points": sum(absolute_errors, Decimal("0")) / n,
        "rmse_index_points": mse.sqrt(),
        "bias_index_points": sum(errors, Decimal("0")) / n,
        "mean_absolute_bps": sum(absolute_bps, Decimal("0")) / n,
        "p95_absolute_bps": _percentile(absolute_bps, Decimal("0.95")),
        "masked_cell_mape_percent": sum(mapes, Decimal("0")) / n,
        "total_absolute_bps": sum(absolute_bps, Decimal("0")),
    }


def _group_metrics(cases: Sequence[Case], fields: Sequence[str]) -> list[dict[str, Any]]:
    groups: MutableMapping[tuple[Any, ...], list[Case]] = defaultdict(list)
    for case in cases:
        key = tuple(getattr(case, field) for field in fields)
        groups[key].append(case)
    rows: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda value: tuple(str(x) for x in value)):
        metrics = _metrics(groups[key])
        row = {field: value for field, value in zip(fields, key)}
        row.update(metrics)
        rows.append(row)
    return rows


def construction_sensitivity(
    panel: Panel,
    headline: HeadlinePanel,
    policy: BacktestPolicy,
) -> tuple[list[dict[str, Any]], Mapping[str, Any]]:
    rows: list[dict[str, Any]] = []
    b0_differences: list[Decimal] = []
    b1_differences: list[Decimal] = []
    for period in panel.periods:
        if not (policy.evaluation_start <= period <= policy.evaluation_end):
            continue
        truth = index_value(panel, period)
        b0 = Decimal("100") * _simple_mean(
            [headline.values[(economy, period)] for economy in headline.economies]
        )
        b1 = Decimal("100") * sum(
            (
                headline.values[(economy, period)] * headline.economy_weights[economy]
                for economy in headline.economies
            ),
            Decimal("0"),
        )
        b0_bps = (b0 / truth - Decimal("1")) * Decimal("10000")
        b1_bps = (b1 / truth - Decimal("1")) * Decimal("10000")
        b0_differences.append(abs(b0_bps))
        b1_differences.append(abs(b1_bps))
        rows.append(
            {
                "period": period,
                "armilar_category_index": truth,
                "b0_equal_country_official_headline": b0,
                "b1_armilar_economy_weighted_official_headline": b1,
                "b0_difference_bps": b0_bps,
                "b1_difference_bps": b1_bps,
            }
        )
    if not rows:
        raise BacktestError("EMPTY_CONSTRUCTION_COMPARISON", "no evaluation periods")
    summary = {
        "comparison_truth": "ARMILAR_FULL_CELL_WEIGHT_INDEX",
        "official_headline_improvement_identifiable": True,
        "official_headline_source": "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT",
        "b0_mean_absolute_difference_bps": sum(b0_differences, Decimal("0"))
        / Decimal(len(b0_differences)),
        "b0_max_absolute_difference_bps": max(b0_differences),
        "b1_mean_absolute_difference_bps": sum(b1_differences, Decimal("0"))
        / Decimal(len(b1_differences)),
        "b1_max_absolute_difference_bps": max(b1_differences),
        "headline_source_independent": True,
    }
    return rows, summary

def _top_three_error_sources(cases: Sequence[Case], policy: BacktestPolicy) -> Mapping[str, Any]:
    b3 = [case for case in cases if case.model == "B3_HIERARCHICAL_COMPLETION"]
    dimensions = (
        ("scenario", "horizon_months"),
        ("source_category",),
        ("economy_code",),
    )
    selected: list[dict[str, Any]] = []
    for fields in dimensions:
        candidates: list[dict[str, Any]] = []
        for row in _group_metrics(b3, fields):
            if row["case_count"] < policy.top_source_minimum_cases:
                continue
            if any(row[field] == "" for field in fields):
                continue
            candidates.append(row)
        if not candidates:
            raise BacktestError(
                "TOP_THREE_NOT_IDENTIFIABLE",
                f"no qualifying group for {'+'.join(fields)}",
            )
        worst = max(
            candidates,
            key=lambda row: (
                row["mean_absolute_bps"],
                row["p95_absolute_bps"],
                tuple(str(row[field]) for field in fields),
            ),
        )
        selected.append(
            {
                "dimension": "+".join(fields),
                "label": " | ".join(f"{field}={worst[field]}" for field in fields),
                "case_count": worst["case_count"],
                "mean_absolute_bps": worst["mean_absolute_bps"],
                "p95_absolute_bps": worst["p95_absolute_bps"],
                "masked_cell_mape_percent": worst["masked_cell_mape_percent"],
            }
        )
    selected.sort(
        key=lambda row: (
            -row["mean_absolute_bps"],
            -row["p95_absolute_bps"],
            row["dimension"],
            row["label"],
        )
    )
    return {
        "ranking_metric": "mean_absolute_bps",
        "model": "B3_HIERARCHICAL_COMPLETION",
        "minimum_cases_per_source": policy.top_source_minimum_cases,
        "selection_rule": (
            "Worst actionable stratum from each of scenario+horizon, source category and economy."
        ),
        "top_three": selected,
    }


def _serialize_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    decimal_fields = {
        "mae_index_points": 12,
        "rmse_index_points": 12,
        "bias_index_points": 12,
        "mean_absolute_bps": 8,
        "p95_absolute_bps": 8,
        "masked_cell_mape_percent": 8,
        "total_absolute_bps": 8,
    }
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = _decimal_text(value, decimal_fields.get(key, 12))
        else:
            result[key] = value
    return result


def _write_manifest(root: Path) -> None:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
    )
    lines = [
        f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files
    ]
    _atomic_write(root / "MANIFEST.sha256", ("\n".join(lines) + "\n").encode("utf-8"))


def verify_manifest(root: Path | str) -> None:
    root_path = Path(root)
    manifest = root_path / "MANIFEST.sha256"
    if not manifest.is_file():
        raise BacktestError("MANIFEST_MISSING", str(manifest))
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise BacktestError("MANIFEST_INVALID", line) from exc
        target = _resolve_inside(root_path, relative, "MANIFEST_PATH_INVALID")
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise BacktestError("MANIFEST_HASH_MISMATCH", relative)


def build_backtest(
    policy_path: Path | str,
    input_dir: Path | str,
    headline_input_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = BacktestPolicy.load(policy_path)
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise BacktestError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)
    panel = load_panel(input_dir, policy)
    headline = load_headline_panel(headline_input_dir, panel, policy)
    cases = run_cases(panel, headline, policy)

    case_rows = [
        {
            "case_id": case.case_id,
            "scenario": case.scenario,
            "origin_period": case.origin_period,
            "target_period": case.target_period,
            "horizon_months": case.horizon_months,
            "masked_group": case.masked_group,
            "model": case.model,
            "truth_index": _decimal_text(case.truth_index, 12),
            "estimated_index": _decimal_text(case.estimated_index, 12),
            "index_error": _decimal_text(case.index_error, 12),
            "absolute_error_bps": _decimal_text(case.absolute_error_bps, 8),
            "masked_cell_mape_percent": _decimal_text(case.masked_cell_mape_percent, 8),
            "evidence_class": case.evidence_class,
            "economy_code": case.economy_code,
            "source_category": case.source_category,
        }
        for case in cases
    ]
    _write_csv(
        output_root / "backtest_cases.csv",
        list(case_rows[0].keys()),
        case_rows,
    )

    metric_specs = {
        "model_metrics.csv": ("model",),
        "error_by_scenario.csv": ("model", "scenario"),
        "error_by_horizon.csv": ("model", "horizon_months"),
        "error_by_economy.csv": ("model", "economy_code"),
        "error_by_category.csv": ("model", "source_category"),
        "error_by_evidence_class.csv": ("model", "evidence_class"),
    }
    metric_outputs: dict[str, list[dict[str, Any]]] = {}
    for filename, fields in metric_specs.items():
        grouped = [
            _serialize_metric_row(row)
            for row in _group_metrics(cases, fields)
            if not any(row[field] == "" for field in fields)
        ]
        metric_outputs[filename] = grouped
        _write_csv(output_root / filename, list(grouped[0].keys()), grouped)

    sensitivity_rows, sensitivity_summary = construction_sensitivity(panel, headline, policy)
    _write_csv(
        output_root / "construction_sensitivity.csv",
        [
            "period",
            "armilar_category_index",
            "b0_equal_country_official_headline",
            "b1_armilar_economy_weighted_official_headline",
            "b0_difference_bps",
            "b1_difference_bps",
        ],
        [
            {
                key: _decimal_text(value, 12) if isinstance(value, Decimal) else value
                for key, value in row.items()
            }
            for row in sensitivity_rows
        ],
    )
    serialised_sensitivity = {
        key: _decimal_text(value, 8) if isinstance(value, Decimal) else value
        for key, value in sensitivity_summary.items()
    }
    _atomic_write(
        output_root / "sensitivity_summary.json",
        _canonical_json_bytes(
            {
                **serialised_sensitivity,
                "fx_methodology_sensitivity_available": False,
                "fx_methodology_sensitivity_reason": (
                    "The v0.8.7 primary series excludes current FX and the input package contains no vintage-aligned FX panel."
                ),
                "imputed_economy_effect_available": False,
                "imputed_economy_effect_reason": (
                    "The declared five-economy v0.8.7 universe contains direct Eurostat prices only and no imputed economies."
                ),
            }
        ),
    )

    top_three = _top_three_error_sources(cases, policy)
    serialised_top_three = {
        **{key: value for key, value in top_three.items() if key != "top_three"},
        "top_three": [
            {
                key: _decimal_text(value, 8) if isinstance(value, Decimal) else value
                for key, value in row.items()
            }
            for row in top_three["top_three"]
        ],
    }
    _atomic_write(
        output_root / "top_three_error_sources.json",
        _canonical_json_bytes(serialised_top_three),
    )

    model_metrics = {
        row["model"]: row for row in metric_outputs["model_metrics.csv"]
    }
    input_root = Path(input_dir)
    headline_root = Path(headline_input_dir)
    input_manifest_hash = _sha256((input_root / "MANIFEST.sha256").read_bytes())
    headline_manifest_hash = _sha256((headline_root / "MANIFEST.sha256").read_bytes())
    summary = {
        "schema_version": "1.0",
        "pipeline_version": installed_version(),
        "policy_version": policy.policy_version,
        "status": "INDEPENDENT_HEADLINE_BACKTEST_COMPLETED_WITH_VINTAGE_LIMITATION",
        "universe_id": panel.universe_id,
        "vintage_mode": policy.vintage_mode,
        "publication_aware": False,
        "vintage_limitation": (
            "The category panel and the independent CP00 panel are final-vintage snapshots. Origins enforce period cutoffs for masked cells, "
            "but historical publication lags and revision vintages are unavailable."
        ),
        "same_period_donor_assumption": True,
        "headline_availability_assumption": "CP00_AVAILABLE_WHEN_CATEGORY_CELLS_MASKED",
        "evaluation_start": policy.evaluation_start,
        "evaluation_end": policy.evaluation_end,
        "horizons": list(policy.horizons),
        "scenario_count": len(policy.scenarios),
        "model_count": len(policy.models),
        "common_case_count_per_model": int(model_metrics[MODELS[0]]["case_count"]),
        "total_case_rows": len(cases),
        "cell_count": len(panel.cells),
        "economy_count": len(panel.economies),
        "category_count": len(panel.categories),
        "official_headline_comparison_available": True,
        "official_headline_source": "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT",
        "headline_source_independent": True,
        "headline_snapshot_manifest_sha256": headline.snapshot_manifest_sha256,
        "rejected_v089_experiment_reused": False,
        "fx_methodology_sensitivity_available": False,
        "imputed_economy_effect_available": False,
        "input_manifest_sha256": input_manifest_hash,
        "headline_input_manifest_sha256": headline_manifest_hash,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "backtest_summary.json", _canonical_json_bytes(summary))
    _write_report(output_root, policy, summary, metric_outputs, serialised_sensitivity, serialised_top_three)
    _write_manifest(output_root)
    return summary


def _write_report(
    output_root: Path,
    policy: BacktestPolicy,
    summary: Mapping[str, Any],
    metric_outputs: Mapping[str, Sequence[Mapping[str, Any]]],
    sensitivity: Mapping[str, Any],
    top_three: Mapping[str, Any],
) -> None:
    model_rows = metric_outputs["model_metrics.csv"]
    lines = [
        "# Armilar v0.9.0 independent-headline economic backtest",
        "",
        "## Evaluation contract",
        "",
        f"- Universe: `{summary['universe_id']}`",
        f"- Evaluation interval: {policy.evaluation_start} to {policy.evaluation_end}",
        f"- Horizons: {', '.join(str(h) for h in policy.horizons)} months",
        f"- Common cases per model: {summary['common_case_count_per_model']}",
        "- Target: complete v0.8.7 Armilar category-price index",
        "- B0/B1 source: independently acquired Eurostat CP00",
        "- Missingness interpretation: CP00 remains available while category cells are masked",
        "- Missingness scenarios: one cell, whole economy and whole source category",
        "",
        "## Model comparison",
        "",
        "| Model | Mean absolute error (bps) | P95 absolute error (bps) | Masked-cell MAPE |",
        "|---|---:|---:|---:|",
    ]
    for row in model_rows:
        lines.append(
            f"| {row['model']} | {row['mean_absolute_bps']} | {row['p95_absolute_bps']} | {row['masked_cell_mape_percent']}% |"
        )
    lines.extend(["", "## Three largest measured B3 error sources", ""])
    for rank, row in enumerate(top_three["top_three"], start=1):
        lines.append(
            f"{rank}. `{row['label']}`: mean absolute error {row['mean_absolute_bps']} bps, "
            f"P95 {row['p95_absolute_bps']} bps, {row['case_count']} cases."
        )
    lines.extend(
        [
            "",
            "## Construction sensitivity",
            "",
            f"- B0 equal-country CP00 mean absolute difference: {sensitivity['b0_mean_absolute_difference_bps']} bps.",
            f"- B1 Armilar-economy-weighted CP00 mean absolute difference: {sensitivity['b1_mean_absolute_difference_bps']} bps.",
            "- CP00 is acquired and replayed independently from the CP01-CP12 category panel.",
            "- FX sensitivity is not estimated because current FX is excluded from the primary series and no vintage-aligned FX panel is present.",
            "- The effect of imputed economies is not estimated because the five-economy input contains no imputed economies.",
            "",
            "## Vintage limitation",
            "",
            str(summary["vintage_limitation"]),
            "",
            "The backtest enforces origin periods strictly before target periods for every masked cell. It must not be described as a fully publication-aware real-time backtest.",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
        ]
    )
    _atomic_write(output_root / "BACKTEST_REPORT.md", ("\n".join(lines) + "\n").encode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.0 independent-headline economic backtest")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--headline-input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verify_only:
        verify_manifest(args.output_dir)
        print(json.dumps({"status": "MANIFEST_VERIFIED", "output_dir": args.output_dir}))
        return 0
    summary = build_backtest(
        args.policy, args.input_dir, args.headline_input_dir, args.output_dir
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
