"""Independent-headline backtest core for Armilar v0.9.0.

B0 and B1 consume a separate official CP00 panel. B2 and B3 retain the v0.8.8
completion definitions unchanged.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .backtest_core_v088 import (
    BacktestError,
    BacktestPolicy,
    Case,
    Cell,
    MODELS,
    Panel,
    Prediction,
    _assert_common_sample,
    _mask_keys,
    _observed_donor_factors,
    _scenario_groups,
    _simple_mean,
    _weighted_mean,
    index_value,
    load_panel,
    predict_masked_cell as predict_v088_masked_cell,
    rolling_origin_pairs,
)
from .eurostat_headline_v090 import verify_manifest as verify_headline_manifest

REQUIRED_HEADLINE_FIELDS = {
    "universe_id",
    "economy_code",
    "source_category",
    "period",
    "price_relative",
    "economy_fixed_universe_weight",
    "price_evidence_class",
}


@dataclass(frozen=True)
class HeadlinePanel:
    universe_id: str
    periods: tuple[str, ...]
    economies: tuple[str, ...]
    values: Mapping[tuple[str, str], Decimal]
    economy_weights: Mapping[str, Decimal]
    snapshot_kind: str
    snapshot_manifest_sha256: str

    def factor(self, model: str, origin_period: str, target_period: str) -> Decimal:
        factors = {
            economy: self.values[(economy, target_period)]
            / self.values[(economy, origin_period)]
            for economy in self.economies
        }
        if model == "B0_GLOBAL_EQUAL_HEADLINE":
            value = _simple_mean(list(factors.values()))
        elif model == "B1_ARMILAR_WEIGHTED_HEADLINE":
            value = _weighted_mean(
                [
                    (factors[economy], self.economy_weights[economy])
                    for economy in self.economies
                ]
            )
        else:
            raise BacktestError("UNKNOWN_HEADLINE_MODEL", model)
        if value is None:
            raise BacktestError("NO_HEADLINE_FACTOR", model)
        return value


def load_headline_panel(
    headline_input_dir: Path | str,
    category_panel: Panel,
    policy: BacktestPolicy,
) -> HeadlinePanel:
    root = Path(headline_input_dir)
    observations_path = root / "normalized_headline_observations.csv"
    indices_path = root / "monthly_headline_indices.csv"
    summary_path = root / "run_summary.json"
    if not observations_path.is_file() or not indices_path.is_file() or not summary_path.is_file():
        raise BacktestError("HEADLINE_INPUT_FILE_MISSING", str(root))
    try:
        verify_headline_manifest(root)
    except Exception as exc:
        raise BacktestError("HEADLINE_MANIFEST_INVALID", str(exc)) from exc
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("universe_id") != policy.input_universe_id:
        raise BacktestError("HEADLINE_UNIVERSE_MISMATCH", str(summary.get("universe_id")))
    if summary.get("snapshot_kind") != "OFFICIAL_PROVIDER_ACQUISITION":
        raise BacktestError("OFFICIAL_HEADLINE_REQUIRED", str(summary.get("snapshot_kind")))
    if summary.get("source_category") != "CP00":
        raise BacktestError("HEADLINE_CONCEPT_MISMATCH", str(summary.get("source_category")))
    if summary.get("headline_source_independent") is not True:
        raise BacktestError("HEADLINE_INDEPENDENCE_UNPROVEN", "summary flag missing")
    if summary.get("category_panel_used_to_construct_headline") is not False:
        raise BacktestError("HEADLINE_INDEPENDENCE_VIOLATION", "category prices used")
    if summary.get("rejected_v089_experiment_reused") is not False:
        raise BacktestError("REJECTED_EXPERIMENT_REUSE", "v0.8.9 code or output reused")

    values: dict[tuple[str, str], Decimal] = {}
    weights: dict[str, Decimal] = {}
    periods: set[str] = set()
    economies: set[str] = set()
    with observations_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_HEADLINE_FIELDS.issubset(reader.fieldnames):
            missing = sorted(REQUIRED_HEADLINE_FIELDS - set(reader.fieldnames or ()))
            raise BacktestError("HEADLINE_SCHEMA_MISMATCH", ", ".join(missing))
        for line_number, row in enumerate(reader, start=2):
            if row["universe_id"] != policy.input_universe_id:
                raise BacktestError("HEADLINE_UNIVERSE_MISMATCH", f"line {line_number}")
            if row["source_category"] != "CP00":
                raise BacktestError("HEADLINE_CONCEPT_MISMATCH", f"line {line_number}")
            if row["price_evidence_class"] != "P1_OFFICIAL_HEADLINE":
                raise BacktestError("OFFICIAL_HEADLINE_REQUIRED", f"line {line_number}")
            economy = str(row["economy_code"])
            period = str(row["period"])
            key = (economy, period)
            if key in values:
                raise BacktestError("DUPLICATE_HEADLINE_OBSERVATION", str(key))
            try:
                value = Decimal(str(row["price_relative"]))
                weight = Decimal(str(row["economy_fixed_universe_weight"]))
            except Exception as exc:
                raise BacktestError("NON_NUMERIC_HEADLINE_VALUE", f"line {line_number}") from exc
            if not value.is_finite() or value <= 0 or not weight.is_finite() or weight <= 0:
                raise BacktestError("INVALID_HEADLINE_VALUE", f"line {line_number}")
            values[key] = value
            periods.add(period)
            economies.add(economy)
            previous = weights.get(economy)
            if previous is not None and previous != weight:
                raise BacktestError("HEADLINE_WEIGHT_DRIFT", economy)
            weights[economy] = weight

    ordered_periods = tuple(sorted(periods))
    ordered_economies = tuple(sorted(economies))
    if ordered_periods != category_panel.periods:
        raise BacktestError(
            "HEADLINE_PERIOD_MISMATCH",
            f"headline={len(ordered_periods)} category={len(category_panel.periods)}",
        )
    if ordered_economies != category_panel.economies:
        raise BacktestError(
            "HEADLINE_ECONOMY_MISMATCH",
            f"headline={ordered_economies} category={category_panel.economies}",
        )
    expected = {
        (economy, period)
        for economy in ordered_economies
        for period in ordered_periods
    }
    if set(values) != expected:
        raise BacktestError(
            "INCOMPLETE_HEADLINE_GRID",
            f"missing={len(expected - set(values))} extra={len(set(values) - expected)}",
        )
    if abs(sum(weights.values(), Decimal("0")) - Decimal("1")) > Decimal("1e-18"):
        raise BacktestError("HEADLINE_WEIGHTS_DO_NOT_SUM_TO_ONE", str(sum(weights.values())))

    declared: dict[str, tuple[Decimal, Decimal]] = {}
    with indices_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "period",
            "b0_equal_country_official_headline",
            "b1_armilar_economy_weighted_official_headline",
            "headline_source_independent",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise BacktestError("HEADLINE_INDEX_SCHEMA_MISMATCH", str(indices_path))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["period"])
            if period in declared:
                raise BacktestError("DUPLICATE_HEADLINE_INDEX_PERIOD", period)
            if row["headline_source_independent"].lower() != "true":
                raise BacktestError("HEADLINE_INDEPENDENCE_UNPROVEN", f"line {line_number}")
            declared[period] = (
                Decimal(str(row["b0_equal_country_official_headline"])),
                Decimal(str(row["b1_armilar_economy_weighted_official_headline"])),
            )
    if set(declared) != set(ordered_periods):
        raise BacktestError("HEADLINE_INDEX_PERIOD_MISMATCH", str(len(declared)))
    for period in ordered_periods:
        b0 = Decimal("100") * sum(
            (values[(economy, period)] for economy in ordered_economies), Decimal("0")
        ) / Decimal(len(ordered_economies))
        b1 = Decimal("100") * sum(
            (values[(economy, period)] * weights[economy] for economy in ordered_economies),
            Decimal("0"),
        )
        declared_b0, declared_b1 = declared[period]
        if abs(b0 - declared_b0) > Decimal("1e-9") or abs(b1 - declared_b1) > Decimal("1e-9"):
            raise BacktestError("HEADLINE_INDEX_IDENTITY_FAILED", period)

    return HeadlinePanel(
        universe_id=policy.input_universe_id,
        periods=ordered_periods,
        economies=ordered_economies,
        values=values,
        economy_weights=weights,
        snapshot_kind=str(summary["snapshot_kind"]),
        snapshot_manifest_sha256=str(summary["snapshot_manifest_sha256"]),
    )


def predict_masked_cell(
    panel: Panel,
    headline_panel: HeadlinePanel,
    model: str,
    cell: Cell,
    origin_period: str,
    target_period: str,
    masked: set[tuple[str, str]],
    donor_factors: Mapping[tuple[str, str], Decimal],
) -> Prediction:
    origin_value = panel.values[(cell.economy_code, cell.source_category, origin_period)]
    if model == "B0_GLOBAL_EQUAL_HEADLINE":
        return Prediction(
            origin_value * headline_panel.factor(model, origin_period, target_period),
            "P1_OFFICIAL_CP00_EQUAL_COUNTRY",
        )
    if model == "B1_ARMILAR_WEIGHTED_HEADLINE":
        return Prediction(
            origin_value * headline_panel.factor(model, origin_period, target_period),
            "P1_OFFICIAL_CP00_ARMILAR_ECONOMY_WEIGHTED",
        )
    return predict_v088_masked_cell(
        panel,
        model,
        cell,
        origin_period,
        target_period,
        masked,
        donor_factors,
    )


def run_cases(
    panel: Panel,
    headline_panel: HeadlinePanel,
    policy: BacktestPolicy,
) -> tuple[Case, ...]:
    if headline_panel.periods != panel.periods:
        raise BacktestError("HEADLINE_PERIOD_MISMATCH", "run-time mismatch")
    cases: list[Case] = []
    pairs = rolling_origin_pairs(panel, policy)
    cell_lookup = panel.cell_by_key
    for scenario in policy.scenarios:
        for masked_group in _scenario_groups(panel, scenario):
            masked_keys = set(_mask_keys(panel, scenario, masked_group))
            for origin, target, horizon in pairs:
                donor_factors = _observed_donor_factors(panel, origin, target, masked_keys)
                truth = index_value(panel, target)
                actual_masked = {
                    key: panel.values[(key[0], key[1], target)] for key in masked_keys
                }
                for model in policy.models:
                    replacements: dict[tuple[str, str], Decimal] = {}
                    evidence_classes: set[str] = set()
                    ape_values: list[Decimal] = []
                    for key in sorted(masked_keys):
                        cell = cell_lookup[key]
                        prediction = predict_masked_cell(
                            panel,
                            headline_panel,
                            model,
                            cell,
                            origin,
                            target,
                            masked_keys,
                            donor_factors,
                        )
                        replacements[key] = prediction.value
                        evidence_classes.add(prediction.evidence_class)
                        actual = actual_masked[key]
                        ape_values.append(
                            abs(prediction.value / actual - Decimal("1")) * Decimal("100")
                        )
                    estimate = index_value(panel, target, replacements)
                    error = estimate - truth
                    bps = abs(error / truth) * Decimal("10000")
                    mape = sum(ape_values, Decimal("0")) / Decimal(len(ape_values))
                    case_id = f"{scenario}|{masked_group}|{origin}|{target}|H{horizon:02d}"
                    economy_code = masked_group if scenario == "ECONOMY_OUTAGE" else ""
                    source_category = masked_group if scenario == "CATEGORY_OUTAGE" else ""
                    if scenario == "SINGLE_CELL":
                        economy_code, source_category = masked_group.split("|", 1)
                    cases.append(
                        Case(
                            case_id=case_id,
                            scenario=scenario,
                            origin_period=origin,
                            target_period=target,
                            horizon_months=horizon,
                            masked_group=masked_group,
                            model=model,
                            truth_index=truth,
                            estimated_index=estimate,
                            index_error=error,
                            absolute_error_bps=bps,
                            masked_cell_mape_percent=mape,
                            evidence_class="+".join(sorted(evidence_classes)),
                            economy_code=economy_code,
                            source_category=source_category,
                        )
                    )
    _assert_common_sample(cases, policy.models)
    return tuple(cases)


__all__ = [
    "BacktestError",
    "BacktestPolicy",
    "Case",
    "HeadlinePanel",
    "MODELS",
    "Panel",
    "index_value",
    "load_headline_panel",
    "load_panel",
    "run_cases",
]
