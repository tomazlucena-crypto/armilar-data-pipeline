"""Core contracts and completion engine for Armilar v0.8.8."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

try:
    from armilar_prices.eurostat_vertical import verify_manifest as verify_v087_manifest
except ModuleNotFoundError:  # The import is required after the overlay is applied.
    verify_v087_manifest = None

getcontext().prec = 42

MODELS = (
    "B0_GLOBAL_EQUAL_HEADLINE",
    "B1_ARMILAR_WEIGHTED_HEADLINE",
    "B2_CATEGORY_CARRY_FORWARD",
    "B3_HIERARCHICAL_COMPLETION",
)
SCENARIOS = ("SINGLE_CELL", "ECONOMY_OUTAGE", "CATEGORY_OUTAGE")
DEFAULT_HORIZONS = (1, 3, 6, 12)
REQUIRED_PANEL_FIELDS = {
    "universe_id",
    "economy_code",
    "economy_name",
    "source_category",
    "armilar_category",
    "period",
    "price_relative",
    "fixed_universe_weight",
    "price_evidence_class",
}


class BacktestError(RuntimeError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class BacktestPolicy:
    policy_version: str
    input_universe_id: str
    evaluation_start: str
    evaluation_end: str
    horizons: tuple[int, ...]
    scenarios: tuple[str, ...]
    models: tuple[str, ...]
    minimum_history_months: int
    vintage_mode: str
    publication_aware: bool
    same_period_donor_assumption: bool
    research_release_allowed: bool
    monetary_release_allowed: bool
    top_source_minimum_cases: int

    @classmethod
    def load(cls, path: Path | str) -> "BacktestPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "input_universe_id",
            "evaluation_start",
            "evaluation_end",
            "horizons",
            "scenarios",
            "models",
            "minimum_history_months",
            "vintage_mode",
            "publication_aware",
            "same_period_donor_assumption",
            "research_release_allowed",
            "monetary_release_allowed",
            "top_source_minimum_cases",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise BacktestError("POLICY_FIELD_MISSING", ", ".join(missing))
        policy = cls(
            policy_version=str(payload["policy_version"]),
            input_universe_id=str(payload["input_universe_id"]),
            evaluation_start=str(payload["evaluation_start"]),
            evaluation_end=str(payload["evaluation_end"]),
            horizons=tuple(int(x) for x in payload["horizons"]),
            scenarios=tuple(str(x) for x in payload["scenarios"]),
            models=tuple(str(x) for x in payload["models"]),
            minimum_history_months=int(payload["minimum_history_months"]),
            vintage_mode=str(payload["vintage_mode"]),
            publication_aware=bool(payload["publication_aware"]),
            same_period_donor_assumption=bool(payload["same_period_donor_assumption"]),
            research_release_allowed=bool(payload["research_release_allowed"]),
            monetary_release_allowed=bool(payload["monetary_release_allowed"]),
            top_source_minimum_cases=int(payload["top_source_minimum_cases"]),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        _parse_period(self.evaluation_start)
        _parse_period(self.evaluation_end)
        if self.evaluation_start > self.evaluation_end:
            raise BacktestError("INVALID_EVALUATION_INTERVAL", "start exceeds end")
        if self.horizons != tuple(sorted(set(self.horizons))):
            raise BacktestError("INVALID_HORIZONS", "horizons must be unique and sorted")
        if not self.horizons or any(h <= 0 for h in self.horizons):
            raise BacktestError("INVALID_HORIZONS", "horizons must be positive")
        if self.models != MODELS:
            raise BacktestError("MODEL_CONTRACT_MISMATCH", f"expected {MODELS}")
        if set(self.scenarios) != set(SCENARIOS):
            raise BacktestError("SCENARIO_CONTRACT_MISMATCH", f"expected {SCENARIOS}")
        if self.minimum_history_months < 12:
            raise BacktestError("INSUFFICIENT_HISTORY_POLICY", "minimum history must be >= 12")
        if self.vintage_mode != "FINAL_VINTAGE_PSEUDO_REAL_TIME":
            raise BacktestError("VINTAGE_MODE_UNSUPPORTED", self.vintage_mode)
        if self.publication_aware:
            raise BacktestError(
                "VINTAGE_CLAIM_UNSUPPORTED",
                "v0.8.7 contains one final vintage and cannot support publication-aware claims",
            )
        if not self.same_period_donor_assumption:
            raise BacktestError(
                "DONOR_ASSUMPTION_MISSING",
                "same-period donor availability must be explicit",
            )
        if self.research_release_allowed or self.monetary_release_allowed:
            raise BacktestError("RELEASE_GATE_WEAKENED", "release flags must remain false")
        if self.top_source_minimum_cases < 1:
            raise BacktestError("INVALID_TOP_SOURCE_MINIMUM", "must be positive")


@dataclass(frozen=True)
class Cell:
    economy_code: str
    economy_name: str
    source_category: str
    armilar_category: str
    weight: Decimal
    evidence_class: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.economy_code, self.source_category)


@dataclass(frozen=True)
class Panel:
    universe_id: str
    periods: tuple[str, ...]
    cells: tuple[Cell, ...]
    values: Mapping[tuple[str, str, str], Decimal]

    @property
    def cell_by_key(self) -> Mapping[tuple[str, str], Cell]:
        return {cell.key: cell for cell in self.cells}

    @property
    def economies(self) -> tuple[str, ...]:
        return tuple(sorted({cell.economy_code for cell in self.cells}))

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({cell.source_category for cell in self.cells}))


@dataclass(frozen=True)
class Case:
    case_id: str
    scenario: str
    origin_period: str
    target_period: str
    horizon_months: int
    masked_group: str
    model: str
    truth_index: Decimal
    estimated_index: Decimal
    index_error: Decimal
    absolute_error_bps: Decimal
    masked_cell_mape_percent: Decimal
    evidence_class: str
    economy_code: str
    source_category: str


@dataclass(frozen=True)
class Prediction:
    value: Decimal
    evidence_class: str


def _parse_period(period: str) -> tuple[int, int]:
    try:
        year_text, month_text = period.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (ValueError, AttributeError) as exc:
        raise BacktestError("INVALID_PERIOD", str(period)) from exc
    if year < 1900 or not 1 <= month <= 12 or period != f"{year:04d}-{month:02d}":
        raise BacktestError("INVALID_PERIOD", str(period))
    return year, month


def add_months(period: str, months: int) -> str:
    year, month = _parse_period(period)
    index = year * 12 + (month - 1) + months
    if index < 0:
        raise BacktestError("INVALID_PERIOD_SHIFT", f"{period} + {months}")
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def iter_periods(start: str, end: str) -> Iterator[str]:
    current = start
    while current <= end:
        yield current
        current = add_months(current, 1)


def load_panel(input_dir: Path | str, policy: BacktestPolicy) -> Panel:
    root = Path(input_dir)
    panel_path = root / "normalized_price_observations.csv"
    index_path = root / "monthly_index.csv"
    summary_path = root / "run_summary.json"
    if not panel_path.is_file() or not index_path.is_file() or not summary_path.is_file():
        raise BacktestError("INPUT_FILE_MISSING", str(root))
    if verify_v087_manifest is not None:
        try:
            verify_v087_manifest(root)
        except Exception as exc:  # Preserve the v0.8.7 stable code in the detail.
            raise BacktestError("INPUT_MANIFEST_INVALID", str(exc)) from exc
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("universe_id") != policy.input_universe_id:
        raise BacktestError(
            "UNIVERSE_MISMATCH",
            f"{summary.get('universe_id')} != {policy.input_universe_id}",
        )
    if summary.get("snapshot_kind") != "OFFICIAL_PROVIDER_ACQUISITION":
        raise BacktestError(
            "OFFICIAL_INPUT_REQUIRED",
            f"snapshot_kind={summary.get('snapshot_kind')}",
        )

    values: dict[tuple[str, str, str], Decimal] = {}
    cell_metadata: dict[tuple[str, str], Cell] = {}
    periods: set[str] = set()
    with panel_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_PANEL_FIELDS.issubset(reader.fieldnames):
            missing = sorted(REQUIRED_PANEL_FIELDS - set(reader.fieldnames or ()))
            raise BacktestError("INPUT_SCHEMA_MISMATCH", ", ".join(missing))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["period"])
            _parse_period(period)
            key = (str(row["economy_code"]), str(row["source_category"]), period)
            if key in values:
                raise BacktestError("DUPLICATE_PANEL_CELL", f"line {line_number}: {key}")
            try:
                value = Decimal(str(row["price_relative"]))
                weight = Decimal(str(row["fixed_universe_weight"]))
            except Exception as exc:
                raise BacktestError("NON_NUMERIC_PANEL_VALUE", f"line {line_number}") from exc
            if not value.is_finite() or value <= 0 or not weight.is_finite() or weight <= 0:
                raise BacktestError("INVALID_PANEL_VALUE", f"line {line_number}")
            values[key] = value
            periods.add(period)
            cell_key = key[:2]
            candidate = Cell(
                economy_code=key[0],
                economy_name=str(row["economy_name"]),
                source_category=key[1],
                armilar_category=str(row["armilar_category"]),
                weight=weight,
                evidence_class=str(row["price_evidence_class"]),
            )
            existing = cell_metadata.get(cell_key)
            if existing is not None and existing != candidate:
                raise BacktestError("CELL_METADATA_DRIFT", str(cell_key))
            cell_metadata[cell_key] = candidate

    ordered_periods = tuple(sorted(periods))
    cells = tuple(sorted(cell_metadata.values(), key=lambda c: c.key))
    if not ordered_periods or not cells:
        raise BacktestError("EMPTY_PANEL", str(panel_path))
    expected = {(cell.economy_code, cell.source_category, period) for cell in cells for period in ordered_periods}
    missing_keys = expected - values.keys()
    extra_keys = values.keys() - expected
    if missing_keys or extra_keys:
        detail = f"missing={len(missing_keys)} extra={len(extra_keys)}"
        raise BacktestError("INCOMPLETE_PANEL_GRID", detail)
    weight_total = sum((cell.weight for cell in cells), Decimal("0"))
    if abs(weight_total - Decimal("1")) > Decimal("1e-18"):
        raise BacktestError("WEIGHTS_DO_NOT_SUM_TO_ONE", str(weight_total))
    if policy.evaluation_start not in ordered_periods or policy.evaluation_end not in ordered_periods:
        raise BacktestError("EVALUATION_INTERVAL_OUTSIDE_PANEL", "policy periods unavailable")
    if ordered_periods.index(policy.evaluation_start) < policy.minimum_history_months:
        raise BacktestError("INSUFFICIENT_HISTORY", policy.evaluation_start)
    panel = Panel(
        universe_id=policy.input_universe_id,
        periods=ordered_periods,
        cells=cells,
        values=values,
    )
    declared_indices: dict[str, Decimal] = {}
    with index_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required_index = {"period", "index_value"}
        if not reader.fieldnames or not required_index.issubset(reader.fieldnames):
            raise BacktestError("INPUT_INDEX_SCHEMA_MISMATCH", str(index_path))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["period"])
            if period in declared_indices:
                raise BacktestError("DUPLICATE_INPUT_INDEX_PERIOD", period)
            try:
                declared_indices[period] = Decimal(str(row["index_value"]))
            except Exception as exc:
                raise BacktestError("NON_NUMERIC_INPUT_INDEX", f"line {line_number}") from exc
    if set(declared_indices) != set(ordered_periods):
        raise BacktestError(
            "INPUT_INDEX_PERIOD_MISMATCH",
            f"declared={len(declared_indices)} panel={len(ordered_periods)}",
        )
    for period in ordered_periods:
        recomputed = index_value(panel, period)
        if abs(recomputed - declared_indices[period]) > Decimal("1e-9"):
            raise BacktestError(
                "INPUT_INDEX_IDENTITY_FAILED",
                f"{period}: recomputed={recomputed} declared={declared_indices[period]}",
            )
    return panel


def index_value(panel: Panel, period: str, replacements: Mapping[tuple[str, str], Decimal] | None = None) -> Decimal:
    replacements = replacements or {}
    total = Decimal("0")
    for cell in panel.cells:
        value = replacements.get(cell.key, panel.values[(cell.economy_code, cell.source_category, period)])
        total += Decimal("100") * cell.weight * value
    return total


def _weighted_mean(items: Sequence[tuple[Decimal, Decimal]]) -> Decimal | None:
    if not items:
        return None
    denominator = sum((weight for _, weight in items), Decimal("0"))
    if denominator <= 0:
        return None
    return sum((value * weight for value, weight in items), Decimal("0")) / denominator


def _simple_mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _mask_keys(panel: Panel, scenario: str, masked_group: str) -> tuple[tuple[str, str], ...]:
    if scenario == "SINGLE_CELL":
        economy, category = masked_group.split("|", 1)
        return ((economy, category),)
    if scenario == "ECONOMY_OUTAGE":
        return tuple(cell.key for cell in panel.cells if cell.economy_code == masked_group)
    if scenario == "CATEGORY_OUTAGE":
        return tuple(cell.key for cell in panel.cells if cell.source_category == masked_group)
    raise BacktestError("UNKNOWN_SCENARIO", scenario)


def _observed_donor_factors(
    panel: Panel,
    origin_period: str,
    target_period: str,
    masked: set[tuple[str, str]],
) -> Mapping[tuple[str, str], Decimal]:
    factors: dict[tuple[str, str], Decimal] = {}
    for cell in panel.cells:
        if cell.key in masked:
            continue
        origin = panel.values[(cell.economy_code, cell.source_category, origin_period)]
        target = panel.values[(cell.economy_code, cell.source_category, target_period)]
        factors[cell.key] = target / origin
    return factors


def predict_masked_cell(
    panel: Panel,
    model: str,
    cell: Cell,
    origin_period: str,
    target_period: str,
    masked: set[tuple[str, str]],
    donor_factors: Mapping[tuple[str, str], Decimal],
) -> Prediction:
    origin_value = panel.values[(cell.economy_code, cell.source_category, origin_period)]
    observed_cells = [candidate for candidate in panel.cells if candidate.key not in masked]
    if model == "B0_GLOBAL_EQUAL_HEADLINE":
        factor = _simple_mean([donor_factors[c.key] for c in observed_cells])
        if factor is None:
            raise BacktestError("NO_DONOR_AVAILABLE", "B0")
        return Prediction(origin_value * factor, "P5_GLOBAL_EQUAL_HEADLINE")
    if model == "B1_ARMILAR_WEIGHTED_HEADLINE":
        factor = _weighted_mean([(donor_factors[c.key], c.weight) for c in observed_cells])
        if factor is None:
            raise BacktestError("NO_DONOR_AVAILABLE", "B1")
        return Prediction(origin_value * factor, "P5_GLOBAL_ARMILAR_WEIGHTED")
    if model == "B2_CATEGORY_CARRY_FORWARD":
        return Prediction(origin_value, "P3_CARRY_FORWARD")
    if model != "B3_HIERARCHICAL_COMPLETION":
        raise BacktestError("UNKNOWN_MODEL", model)

    economy_donors = [
        candidate
        for candidate in observed_cells
        if candidate.economy_code == cell.economy_code
    ]
    category_donors = [
        candidate
        for candidate in observed_cells
        if candidate.source_category == cell.source_category
    ]
    economy_factor = _weighted_mean([(donor_factors[c.key], c.weight) for c in economy_donors])
    category_factor = _weighted_mean([(donor_factors[c.key], c.weight) for c in category_donors])
    global_factor = _weighted_mean([(donor_factors[c.key], c.weight) for c in observed_cells])
    if economy_factor is not None and category_factor is not None:
        # Geometric combination is scale-consistent for price relatives and deterministic.
        factor = (economy_factor * category_factor).sqrt()
        return Prediction(origin_value * factor, "P4_ECONOMY_AND_CATEGORY")
    if category_factor is not None:
        return Prediction(origin_value * category_factor, "P4_CATEGORY_PEERS")
    if economy_factor is not None:
        return Prediction(origin_value * economy_factor, "P4_ECONOMY_CONTEXT")
    if global_factor is not None:
        return Prediction(origin_value * global_factor, "P5_GLOBAL_FALLBACK")
    raise BacktestError("NO_DONOR_AVAILABLE", "B3")


def _scenario_groups(panel: Panel, scenario: str) -> tuple[str, ...]:
    if scenario == "SINGLE_CELL":
        return tuple(f"{cell.economy_code}|{cell.source_category}" for cell in panel.cells)
    if scenario == "ECONOMY_OUTAGE":
        return panel.economies
    if scenario == "CATEGORY_OUTAGE":
        return panel.categories
    raise BacktestError("UNKNOWN_SCENARIO", scenario)


def rolling_origin_pairs(panel: Panel, policy: BacktestPolicy) -> tuple[tuple[str, str, int], ...]:
    period_set = set(panel.periods)
    pairs: list[tuple[str, str, int]] = []
    for origin in panel.periods:
        if origin < add_months(policy.evaluation_start, -1):
            continue
        if origin >= policy.evaluation_end:
            continue
        for horizon in policy.horizons:
            target = add_months(origin, horizon)
            if target < policy.evaluation_start or target > policy.evaluation_end:
                continue
            if target not in period_set:
                continue
            if origin >= target:
                raise BacktestError("LOOK_AHEAD_DETECTED", f"{origin} >= {target}")
            pairs.append((origin, target, horizon))
    if not pairs:
        raise BacktestError("EMPTY_EVALUATION_SAMPLE", "no rolling-origin pairs")
    return tuple(pairs)


def run_cases(panel: Panel, policy: BacktestPolicy) -> tuple[Case, ...]:
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
                        ape_values.append(abs(prediction.value / actual - Decimal("1")) * Decimal("100"))
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


def _assert_common_sample(cases: Sequence[Case], models: Sequence[str]) -> None:
    by_model: dict[str, set[str]] = {model: set() for model in models}
    for case in cases:
        if case.model not in by_model:
            raise BacktestError("UNKNOWN_MODEL", case.model)
        by_model[case.model].add(case.case_id)
    reference: set[str] | None = None
    for model in models:
        sample = by_model[model]
        if reference is None:
            reference = sample
        elif sample != reference:
            raise BacktestError(
                "COMPARISON_SAMPLE_MISMATCH",
                f"{model}: {len(sample)} != {len(reference)}",
            )


