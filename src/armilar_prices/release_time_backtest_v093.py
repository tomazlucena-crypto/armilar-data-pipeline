"""Publication-aware release-time completion backtest for Armilar v0.9.3.

This module evaluates B0-B4 using Eurostat values as first published on each
monthly full-data release.  The as-of timestamp for every case is the official
release date of the target month.  Unmasked target-period donors are therefore
available at the as-of date, which makes this a release-time missing-cell
completion test.  It is deliberately not described as a pre-release forecast.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, getcontext
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from armilar_prices.backtest_core_v088 import Cell, Panel
from armilar_prices.backtest_core_v090 import HeadlinePanel, run_cases
from armilar_prices.first_published_v093 import verify_manifest as verify_first_published_manifest

getcontext().prec = 42

B0 = "B0_GLOBAL_EQUAL_HEADLINE"
B1 = "B1_ARMILAR_WEIGHTED_HEADLINE"
B2 = "B2_CATEGORY_CARRY_FORWARD"
B3 = "B3_HIERARCHICAL_COMPLETION"
B4 = "B4_TEMPORAL_SAFEGUARD"
MODELS = (B0, B1, B2, B3)
ALL_MODELS = MODELS + (B4,)
SCENARIOS = ("SINGLE_CELL", "ECONOMY_OUTAGE", "CATEGORY_OUTAGE")
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
COMPLETION_MODE = "FIRST_PUBLISHED_TARGET_RELEASE_COMPLETION"
VALUE_VINTAGE_CLASS = "FIRST_PUBLISHED_FULL_DATA_RELEASE"
REQUIRED_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
REQUIRED_CATEGORIES = tuple(f"CP{index:02d}" for index in range(13))
REQUIRED_PANEL_FIELDS = {
    "universe_id",
    "economy_code",
    "economy_name",
    "source_category",
    "period",
    "available_from_date",
    "price_relative_first_published",
    "value_vintage_class",
    "fixed_universe_weight",
    "economy_fixed_universe_weight",
    "armilar_category",
    "price_evidence_class",
}


class ReleaseTimeBacktestError(RuntimeError):
    """Fail-closed error with a stable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class CandidateRule:
    rule_id: str
    rule_type: str
    source_category: str = ""
    scenario: str = ""
    horizon_months: int = 0

    def matches(self, case: Any) -> bool:
        if self.rule_type == "SOURCE_CATEGORY":
            return case.source_category == self.source_category
        if self.rule_type == "SCENARIO_HORIZON":
            return case.scenario == self.scenario and case.horizon_months == self.horizon_months
        raise ReleaseTimeBacktestError("RULE_TYPE_UNSUPPORTED", self.rule_type)


@dataclass(frozen=True)
class ReleaseTimePolicy:
    policy_version: str
    universe_id: str
    required_first_published_policy_version: str
    evaluation_start: str
    evaluation_end: str
    horizons: tuple[int, ...]
    scenarios: tuple[str, ...]
    models: tuple[str, ...]
    minimum_history_months: int
    completion_mode: str
    target_period_donors_allowed_at_release: bool
    pre_release_forecast: bool
    development_target_start: str
    development_target_end: str
    evaluation_target_start: str
    evaluation_target_end: str
    minimum_development_cases_per_rule: int
    activation_mean_delta_bps_gt: Decimal
    activation_regression_rate_gte: Decimal
    candidate_rules: tuple[CandidateRule, ...]
    rejected_v089_experiment_reused: bool
    release_time_completion_comparison_allowed: bool
    pre_release_forecast_comparison_allowed: bool
    model_promotion_allowed: bool
    research_release_allowed: bool
    monetary_release_allowed: bool
    policy_sha256: str

    @classmethod
    def load(cls, path: Path | str) -> "ReleaseTimePolicy":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseTimeBacktestError("POLICY_INVALID", str(source)) from exc
        required = {
            "policy_version",
            "universe_id",
            "required_first_published_policy_version",
            "evaluation_start",
            "evaluation_end",
            "horizons",
            "scenarios",
            "models",
            "minimum_history_months",
            "completion_mode",
            "target_period_donors_allowed_at_release",
            "pre_release_forecast",
            "development_target_start",
            "development_target_end",
            "evaluation_target_start",
            "evaluation_target_end",
            "minimum_development_cases_per_rule",
            "activation_mean_delta_bps_gt",
            "activation_regression_rate_gte",
            "candidate_rules",
            "rejected_v089_experiment_reused",
            "release_time_completion_comparison_allowed",
            "pre_release_forecast_comparison_allowed",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ReleaseTimeBacktestError("POLICY_FIELD_MISSING", ",".join(missing))
        try:
            rules = tuple(
                CandidateRule(
                    rule_id=str(item["rule_id"]),
                    rule_type=str(item["rule_type"]),
                    source_category=str(item.get("source_category", "")),
                    scenario=str(item.get("scenario", "")),
                    horizon_months=int(item.get("horizon_months", 0)),
                )
                for item in payload["candidate_rules"]
            )
            policy = cls(
                policy_version=str(payload["policy_version"]),
                universe_id=str(payload["universe_id"]),
                required_first_published_policy_version=str(
                    payload["required_first_published_policy_version"]
                ),
                evaluation_start=str(payload["evaluation_start"]),
                evaluation_end=str(payload["evaluation_end"]),
                horizons=tuple(int(value) for value in payload["horizons"]),
                scenarios=tuple(str(value) for value in payload["scenarios"]),
                models=tuple(str(value) for value in payload["models"]),
                minimum_history_months=int(payload["minimum_history_months"]),
                completion_mode=str(payload["completion_mode"]),
                target_period_donors_allowed_at_release=bool(
                    payload["target_period_donors_allowed_at_release"]
                ),
                pre_release_forecast=bool(payload["pre_release_forecast"]),
                development_target_start=str(payload["development_target_start"]),
                development_target_end=str(payload["development_target_end"]),
                evaluation_target_start=str(payload["evaluation_target_start"]),
                evaluation_target_end=str(payload["evaluation_target_end"]),
                minimum_development_cases_per_rule=int(
                    payload["minimum_development_cases_per_rule"]
                ),
                activation_mean_delta_bps_gt=_decimal(
                    str(payload["activation_mean_delta_bps_gt"]),
                    "ACTIVATION_THRESHOLD_INVALID",
                    "activation_mean_delta_bps_gt",
                ),
                activation_regression_rate_gte=_decimal(
                    str(payload["activation_regression_rate_gte"]),
                    "ACTIVATION_THRESHOLD_INVALID",
                    "activation_regression_rate_gte",
                ),
                candidate_rules=rules,
                rejected_v089_experiment_reused=bool(
                    payload["rejected_v089_experiment_reused"]
                ),
                release_time_completion_comparison_allowed=bool(
                    payload["release_time_completion_comparison_allowed"]
                ),
                pre_release_forecast_comparison_allowed=bool(
                    payload["pre_release_forecast_comparison_allowed"]
                ),
                model_promotion_allowed=bool(payload["model_promotion_allowed"]),
                research_release_allowed=bool(payload["research_release_allowed"]),
                monetary_release_allowed=bool(payload["monetary_release_allowed"]),
                policy_sha256=_sha256(source.read_bytes()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReleaseTimeBacktestError("POLICY_INVALID", str(exc)) from exc
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.policy_version != "0.9.3":
            raise ReleaseTimeBacktestError("POLICY_VERSION_UNSUPPORTED", self.policy_version)
        if self.required_first_published_policy_version != "0.9.3":
            raise ReleaseTimeBacktestError(
                "FIRST_PUBLISHED_POLICY_VERSION_UNSUPPORTED",
                self.required_first_published_policy_version,
            )
        for period in (
            self.evaluation_start,
            self.evaluation_end,
            self.development_target_start,
            self.development_target_end,
            self.evaluation_target_start,
            self.evaluation_target_end,
        ):
            _validate_period(period)
        if self.evaluation_start > self.evaluation_end:
            raise ReleaseTimeBacktestError("EVALUATION_INTERVAL_INVALID")
        if self.horizons != tuple(sorted(set(self.horizons))) or any(
            value <= 0 for value in self.horizons
        ):
            raise ReleaseTimeBacktestError("HORIZONS_INVALID")
        if self.scenarios != SCENARIOS:
            raise ReleaseTimeBacktestError("SCENARIO_CONTRACT_MISMATCH", str(self.scenarios))
        if self.models != MODELS:
            raise ReleaseTimeBacktestError("MODEL_CONTRACT_MISMATCH", str(self.models))
        if self.minimum_history_months < 12:
            raise ReleaseTimeBacktestError("MINIMUM_HISTORY_INVALID")
        if self.completion_mode != COMPLETION_MODE:
            raise ReleaseTimeBacktestError("COMPLETION_MODE_UNSUPPORTED", self.completion_mode)
        if not self.target_period_donors_allowed_at_release:
            raise ReleaseTimeBacktestError("RELEASE_TIME_DONOR_CONTRACT_MISSING")
        if self.pre_release_forecast:
            raise ReleaseTimeBacktestError("PRE_RELEASE_FORECAST_CLAIM_PROHIBITED")
        if self.development_target_start > self.development_target_end:
            raise ReleaseTimeBacktestError("DEVELOPMENT_INTERVAL_INVALID")
        if self.evaluation_target_start > self.evaluation_target_end:
            raise ReleaseTimeBacktestError("HOLDOUT_INTERVAL_INVALID")
        if self.development_target_end >= self.evaluation_target_start:
            raise ReleaseTimeBacktestError("TEMPORAL_SPLIT_OVERLAP")
        if self.development_target_start < self.evaluation_start:
            raise ReleaseTimeBacktestError("DEVELOPMENT_OUTSIDE_EVALUATION")
        if self.evaluation_target_end > self.evaluation_end:
            raise ReleaseTimeBacktestError("HOLDOUT_OUTSIDE_EVALUATION")
        if self.minimum_development_cases_per_rule < 1:
            raise ReleaseTimeBacktestError("MINIMUM_RULE_CASES_INVALID")
        if self.activation_mean_delta_bps_gt < 0:
            raise ReleaseTimeBacktestError("ACTIVATION_THRESHOLD_INVALID")
        if not Decimal("0") <= self.activation_regression_rate_gte <= Decimal("1"):
            raise ReleaseTimeBacktestError("ACTIVATION_RATE_INVALID")
        expected_rules = {
            "CP08_FALLBACK_TO_B2": ("SOURCE_CATEGORY", "CP08", "", 0),
            "CATEGORY_OUTAGE_H1_FALLBACK_TO_B2": (
                "SCENARIO_HORIZON",
                "",
                "CATEGORY_OUTAGE",
                1,
            ),
        }
        actual_rules = {
            rule.rule_id: (
                rule.rule_type,
                rule.source_category,
                rule.scenario,
                rule.horizon_months,
            )
            for rule in self.candidate_rules
        }
        if actual_rules != expected_rules:
            raise ReleaseTimeBacktestError("RULE_CONTRACT_MISMATCH", str(actual_rules))
        if self.rejected_v089_experiment_reused:
            raise ReleaseTimeBacktestError("REJECTED_EXPERIMENT_REUSED")
        if not self.release_time_completion_comparison_allowed:
            raise ReleaseTimeBacktestError("RELEASE_TIME_COMPARISON_MUST_BE_ENABLED")
        if self.pre_release_forecast_comparison_allowed:
            raise ReleaseTimeBacktestError("PRE_RELEASE_COMPARISON_MUST_REMAIN_FALSE")
        if (
            self.model_promotion_allowed
            or self.research_release_allowed
            or self.monetary_release_allowed
        ):
            raise ReleaseTimeBacktestError("RELEASE_GATE_MUST_REMAIN_FALSE")

    def split_for(self, target_period: str) -> str:
        if self.development_target_start <= target_period <= self.development_target_end:
            return "DEVELOPMENT"
        if self.evaluation_target_start <= target_period <= self.evaluation_target_end:
            return "EVALUATION"
        raise ReleaseTimeBacktestError("TARGET_OUTSIDE_TEMPORAL_SPLIT", target_period)


@dataclass(frozen=True)
class CorePolicyAdapter:
    evaluation_start: str
    evaluation_end: str
    horizons: tuple[int, ...]
    scenarios: tuple[str, ...]
    models: tuple[str, ...]


@dataclass(frozen=True)
class LoadedPanel:
    panel: Panel
    headline: HeadlinePanel
    release_dates: Mapping[str, str]
    input_summary: Mapping[str, Any]
    input_manifest_sha256: str


@dataclass(frozen=True)
class RuleActivation:
    rule: CandidateRule
    development_case_count: int
    mean_b3_minus_b2_bps: Decimal
    regression_rate_b3_vs_b2: Decimal
    activated: bool


@dataclass(frozen=True)
class B4Case:
    case_id: str
    split: str
    selected_model: str
    matched_rule_ids: tuple[str, ...]
    active_rule_ids: tuple[str, ...]
    absolute_error_bps: Decimal
    estimated_index: Decimal
    evidence_class: str


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


def verify_manifest(root: Path | str) -> None:
    base = Path(root)
    manifest = base / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ReleaseTimeBacktestError("MANIFEST_MISSING", str(manifest))
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.strip().split(maxsplit=1)
        if len(parts) != 2 or not HEX64.fullmatch(parts[0].lower()):
            raise ReleaseTimeBacktestError("MANIFEST_INVALID", raw_line)
        expected, relative = parts[0].lower(), parts[1].strip()
        target = (base / relative).resolve()
        resolved = base.resolve()
        if target != resolved and resolved not in target.parents:
            raise ReleaseTimeBacktestError("MANIFEST_PATH_INVALID", relative)
        if not target.is_file():
            raise ReleaseTimeBacktestError("MANIFEST_FILE_MISSING", relative)
        actual = _sha256(target.read_bytes())
        if actual != expected:
            raise ReleaseTimeBacktestError("MANIFEST_HASH_MISMATCH", relative)


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ReleaseTimeBacktestError(code, detail) from exc
    if not parsed.is_finite():
        raise ReleaseTimeBacktestError(code, detail)
    return parsed


def _validate_period(value: str) -> None:
    if not PERIOD_PATTERN.fullmatch(value):
        raise ReleaseTimeBacktestError("PERIOD_INVALID", value)


def _parse_date(value: str, detail: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ReleaseTimeBacktestError("RELEASE_DATE_INVALID", detail) from exc
    return parsed


def _text(value: Decimal, places: int = 8) -> str:
    return format(value.quantize(Decimal(1).scaleb(-places)), "f")


def _p95(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ReleaseTimeBacktestError("EMPTY_METRIC_SAMPLE")
    ordered = sorted(values)
    index = max(0, math.ceil(Decimal("0.95") * Decimal(len(ordered))) - 1)
    return ordered[index]


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ReleaseTimeBacktestError("EMPTY_METRIC_SAMPLE")
    return sum(values, Decimal("0")) / Decimal(len(values))


def load_first_published_panel(
    policy: ReleaseTimePolicy, input_dir: Path | str
) -> LoadedPanel:
    root = Path(input_dir)
    verify_first_published_manifest(root)
    summary_path = root / "run_summary.json"
    observations_path = root / "first_published_observations.csv"
    if not summary_path.is_file() or not observations_path.is_file():
        raise ReleaseTimeBacktestError("FIRST_PUBLISHED_INPUT_MISSING", str(root))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checks = {
        "policy_version": policy.required_first_published_policy_version,
        "universe_id": policy.universe_id,
        "status": "OFFICIAL_FIRST_PUBLISHED_HICP_PANEL_BUILT",
        "value_vintage_class": VALUE_VINTAGE_CLASS,
        "historical_value_vintages_available": True,
        "release_timing_attached": True,
        "first_published_values_attached": True,
        "model_code_changed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            raise ReleaseTimeBacktestError(
                "FIRST_PUBLISHED_CONTRACT_MISMATCH", f"{field}={summary.get(field)!r}"
            )
    if summary.get("observation_count") != 3900:
        raise ReleaseTimeBacktestError(
            "FIRST_PUBLISHED_OBSERVATION_COUNT_MISMATCH", str(summary.get("observation_count"))
        )

    values: dict[tuple[str, str, str], Decimal] = {}
    metadata_by_cell: dict[tuple[str, str], Cell] = {}
    headline_values: dict[tuple[str, str], Decimal] = {}
    economy_weights: dict[str, Decimal] = {}
    release_dates: dict[str, str] = {}
    periods: set[str] = set()
    economies: set[str] = set()
    categories: set[str] = set()
    with observations_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_PANEL_FIELDS - set(reader.fieldnames or ()))
        if missing:
            raise ReleaseTimeBacktestError("FIRST_PUBLISHED_SCHEMA_MISMATCH", ",".join(missing))
        for line_number, row in enumerate(reader, start=2):
            economy = str(row["economy_code"])
            category = str(row["source_category"])
            period = str(row["period"])
            _validate_period(period)
            if economy not in REQUIRED_ECONOMIES or category not in REQUIRED_CATEGORIES:
                raise ReleaseTimeBacktestError(
                    "FIRST_PUBLISHED_UNIVERSE_MISMATCH", f"line {line_number}"
                )
            if row["value_vintage_class"] != VALUE_VINTAGE_CLASS:
                raise ReleaseTimeBacktestError("VALUE_VINTAGE_CLASS_MISMATCH", f"line {line_number}")
            release_date = str(row["available_from_date"])
            parsed_release = _parse_date(release_date, f"line {line_number}")
            if period in release_dates and release_dates[period] != release_date:
                raise ReleaseTimeBacktestError("TARGET_RELEASE_DATE_INCONSISTENT", period)
            release_dates[period] = release_date
            if parsed_release <= date(int(period[:4]), int(period[5:]), 1):
                raise ReleaseTimeBacktestError("RELEASE_DATE_NOT_AFTER_REFERENCE_MONTH", period)
            relative = _decimal(
                str(row["price_relative_first_published"]),
                "FIRST_PUBLISHED_RELATIVE_INVALID",
                f"line {line_number}",
            )
            weight = _decimal(
                str(row["fixed_universe_weight"]),
                "FIRST_PUBLISHED_WEIGHT_INVALID",
                f"line {line_number}",
            )
            economy_weight = _decimal(
                str(row["economy_fixed_universe_weight"]),
                "FIRST_PUBLISHED_ECONOMY_WEIGHT_INVALID",
                f"line {line_number}",
            )
            if relative <= 0 or weight < 0 or economy_weight <= 0:
                raise ReleaseTimeBacktestError("FIRST_PUBLISHED_NUMERIC_VALUE_INVALID", f"line {line_number}")
            periods.add(period)
            economies.add(economy)
            categories.add(category)
            previous_economy_weight = economy_weights.get(economy)
            if previous_economy_weight is not None and previous_economy_weight != economy_weight:
                raise ReleaseTimeBacktestError("ECONOMY_WEIGHT_DRIFT", economy)
            economy_weights[economy] = economy_weight
            if category == "CP00":
                key = (economy, period)
                if key in headline_values:
                    raise ReleaseTimeBacktestError("DUPLICATE_HEADLINE_VALUE", str(key))
                if weight != economy_weight:
                    raise ReleaseTimeBacktestError("HEADLINE_WEIGHT_IDENTITY_FAILED", f"line {line_number}")
                headline_values[key] = relative
                continue
            key3 = (economy, category, period)
            if key3 in values:
                raise ReleaseTimeBacktestError("DUPLICATE_CATEGORY_VALUE", str(key3))
            if weight <= 0:
                raise ReleaseTimeBacktestError("CATEGORY_WEIGHT_INVALID", f"line {line_number}")
            values[key3] = relative
            cell_key = (economy, category)
            candidate = Cell(
                economy_code=economy,
                economy_name=str(row["economy_name"]),
                source_category=category,
                armilar_category=str(row["armilar_category"]),
                weight=weight,
                evidence_class=str(row["price_evidence_class"]),
            )
            existing = metadata_by_cell.get(cell_key)
            if existing is not None and existing != candidate:
                raise ReleaseTimeBacktestError("CELL_METADATA_DRIFT", str(cell_key))
            metadata_by_cell[cell_key] = candidate

    ordered_periods = tuple(sorted(periods))
    ordered_economies = tuple(sorted(economies))
    ordered_categories = tuple(sorted(categories))
    if ordered_economies != REQUIRED_ECONOMIES:
        raise ReleaseTimeBacktestError("ECONOMY_UNIVERSE_MISMATCH", str(ordered_economies))
    if ordered_categories != REQUIRED_CATEGORIES:
        raise ReleaseTimeBacktestError("CATEGORY_UNIVERSE_MISMATCH", str(ordered_categories))
    expected_periods = tuple(_iter_periods("2021-01", "2025-12"))
    if ordered_periods != expected_periods:
        raise ReleaseTimeBacktestError("PERIOD_UNIVERSE_MISMATCH", str(len(ordered_periods)))
    if tuple(sorted(release_dates)) != ordered_periods:
        raise ReleaseTimeBacktestError("RELEASE_DATE_GRID_INCOMPLETE")
    previous_release: date | None = None
    for period in ordered_periods:
        release = _parse_date(release_dates[period], period)
        if previous_release is not None and release <= previous_release:
            raise ReleaseTimeBacktestError("RELEASE_DATES_NOT_STRICTLY_INCREASING", period)
        previous_release = release
    expected_headline = {(economy, period) for economy in REQUIRED_ECONOMIES for period in ordered_periods}
    if set(headline_values) != expected_headline:
        raise ReleaseTimeBacktestError(
            "HEADLINE_GRID_INCOMPLETE",
            f"missing={len(expected_headline - set(headline_values))}",
        )
    expected_categories = {
        (economy, category, period)
        for economy in REQUIRED_ECONOMIES
        for category in REQUIRED_CATEGORIES[1:]
        for period in ordered_periods
    }
    if set(values) != expected_categories:
        raise ReleaseTimeBacktestError(
            "CATEGORY_GRID_INCOMPLETE",
            f"missing={len(expected_categories - set(values))}",
        )
    expected_cells = {
        (economy, category)
        for economy in REQUIRED_ECONOMIES
        for category in REQUIRED_CATEGORIES[1:]
    }
    if set(metadata_by_cell) != expected_cells:
        raise ReleaseTimeBacktestError("CELL_METADATA_GRID_INCOMPLETE")
    weight_total = sum((cell.weight for cell in metadata_by_cell.values()), Decimal("0"))
    if abs(weight_total - Decimal("1")) > Decimal("1e-18"):
        raise ReleaseTimeBacktestError("CATEGORY_WEIGHTS_DO_NOT_SUM_TO_ONE", str(weight_total))
    economy_weight_total = sum(economy_weights.values(), Decimal("0"))
    if abs(economy_weight_total - Decimal("1")) > Decimal("1e-18"):
        raise ReleaseTimeBacktestError("ECONOMY_WEIGHTS_DO_NOT_SUM_TO_ONE", str(economy_weight_total))
    for economy in REQUIRED_ECONOMIES:
        derived = sum(
            (
                metadata_by_cell[(economy, category)].weight
                for category in REQUIRED_CATEGORIES[1:]
            ),
            Decimal("0"),
        )
        if abs(derived - economy_weights[economy]) > Decimal("1e-18"):
            raise ReleaseTimeBacktestError("ECONOMY_WEIGHT_IDENTITY_FAILED", economy)

    panel = Panel(
        universe_id=policy.universe_id,
        periods=ordered_periods,
        cells=tuple(sorted(metadata_by_cell.values(), key=lambda cell: cell.key)),
        values=values,
    )
    headline = HeadlinePanel(
        universe_id=policy.universe_id,
        periods=ordered_periods,
        economies=REQUIRED_ECONOMIES,
        values=headline_values,
        economy_weights=economy_weights,
        snapshot_kind="OFFICIAL_FIRST_PUBLISHED_HICP",
        snapshot_manifest_sha256=str(summary["snapshot_manifest_sha256"]),
    )
    return LoadedPanel(
        panel=panel,
        headline=headline,
        release_dates=release_dates,
        input_summary=summary,
        input_manifest_sha256=_sha256((root / "MANIFEST.sha256").read_bytes()),
    )


def _iter_periods(start: str, end: str) -> Iterable[str]:
    year, month = int(start[:4]), int(start[5:])
    while True:
        period = f"{year:04d}-{month:02d}"
        if period > end:
            return
        yield period
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _index_core_cases(cases: Sequence[Any]) -> Mapping[str, Mapping[str, Any]]:
    indexed: MutableMapping[str, dict[str, Any]] = defaultdict(dict)
    for case in cases:
        if case.model in indexed[case.case_id]:
            raise ReleaseTimeBacktestError("DUPLICATE_MODEL_CASE", f"{case.case_id}/{case.model}")
        indexed[case.case_id][case.model] = case
    for case_id, by_model in indexed.items():
        if set(by_model) != set(MODELS):
            raise ReleaseTimeBacktestError("COMPARISON_SAMPLE_MISMATCH", case_id)
        reference = by_model[B0]
        for model in MODELS[1:]:
            candidate = by_model[model]
            for field in (
                "scenario",
                "origin_period",
                "target_period",
                "horizon_months",
                "masked_group",
                "truth_index",
                "economy_code",
                "source_category",
            ):
                if getattr(reference, field) != getattr(candidate, field):
                    raise ReleaseTimeBacktestError("CASE_METADATA_MISMATCH", f"{case_id}/{field}")
    return indexed


def _activate_rules(
    indexed: Mapping[str, Mapping[str, Any]], policy: ReleaseTimePolicy
) -> tuple[RuleActivation, ...]:
    results: list[RuleActivation] = []
    for rule in policy.candidate_rules:
        deltas: list[Decimal] = []
        regressions = 0
        for by_model in indexed.values():
            case = by_model[B3]
            if policy.split_for(case.target_period) != "DEVELOPMENT" or not rule.matches(case):
                continue
            delta = case.absolute_error_bps - by_model[B2].absolute_error_bps
            deltas.append(delta)
            regressions += delta > 0
        count = len(deltas)
        mean_delta = _mean(deltas) if deltas else Decimal("0")
        regression_rate = Decimal(regressions) / Decimal(count) if count else Decimal("0")
        activated = (
            count >= policy.minimum_development_cases_per_rule
            and mean_delta > policy.activation_mean_delta_bps_gt
            and regression_rate >= policy.activation_regression_rate_gte
        )
        results.append(
            RuleActivation(
                rule=rule,
                development_case_count=count,
                mean_b3_minus_b2_bps=mean_delta,
                regression_rate_b3_vs_b2=regression_rate,
                activated=activated,
            )
        )
    return tuple(results)


def _build_b4_cases(
    indexed: Mapping[str, Mapping[str, Any]],
    policy: ReleaseTimePolicy,
    activations: Sequence[RuleActivation],
) -> Mapping[str, B4Case]:
    active = {result.rule.rule_id: result.activated for result in activations}
    by_id: dict[str, B4Case] = {}
    for case_id, by_model in indexed.items():
        reference = by_model[B3]
        matched = tuple(
            rule.rule_id for rule in policy.candidate_rules if rule.matches(reference)
        )
        active_matched = tuple(rule_id for rule_id in matched if active[rule_id])
        selected_model = B2 if active_matched else B3
        selected = by_model[selected_model]
        by_id[case_id] = B4Case(
            case_id=case_id,
            split=policy.split_for(reference.target_period),
            selected_model=selected_model,
            matched_rule_ids=matched,
            active_rule_ids=active_matched,
            absolute_error_bps=selected.absolute_error_bps,
            estimated_index=selected.estimated_index,
            evidence_class=f"B4_SELECTED_{selected_model}",
        )
    return by_id


def _aggregate_model(cases: Sequence[Any]) -> Mapping[str, Any]:
    errors = [case.absolute_error_bps for case in cases]
    return {
        "case_count": len(cases),
        "mean_absolute_error_bps": _mean(errors),
        "p95_absolute_error_bps": _p95(errors),
        "maximum_absolute_error_bps": max(errors),
    }


def _comparison(
    challenger: Sequence[Decimal], baseline: Sequence[Decimal]
) -> Mapping[str, Any]:
    if len(challenger) != len(baseline) or not challenger:
        raise ReleaseTimeBacktestError("COMPARISON_SAMPLE_INVALID")
    deltas = [left - right for left, right in zip(challenger, baseline)]
    return {
        "case_count": len(deltas),
        "mean_delta_absolute_bps": _mean(deltas),
        "p95_delta_absolute_bps": _p95(deltas),
        "improvement_rate": Decimal(sum(delta < 0 for delta in deltas)) / Decimal(len(deltas)),
        "regression_rate": Decimal(sum(delta > 0 for delta in deltas)) / Decimal(len(deltas)),
        "tie_rate": Decimal(sum(delta == 0 for delta in deltas)) / Decimal(len(deltas)),
    }


def _serialise(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _text(value, 10)
    if isinstance(value, Mapping):
        return {str(key): _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    return value


def build_release_time_backtest(
    policy_path: Path | str,
    first_published_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = ReleaseTimePolicy.load(policy_path)
    loaded = load_first_published_panel(policy, first_published_dir)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ReleaseTimeBacktestError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)

    adapter = CorePolicyAdapter(
        evaluation_start=policy.evaluation_start,
        evaluation_end=policy.evaluation_end,
        horizons=policy.horizons,
        scenarios=policy.scenarios,
        models=policy.models,
    )
    core_cases = run_cases(loaded.panel, loaded.headline, adapter)  # type: ignore[arg-type]
    indexed = _index_core_cases(core_cases)
    activations = _activate_rules(indexed, policy)
    b4_cases = _build_b4_cases(indexed, policy, activations)

    case_rows: list[dict[str, Any]] = []
    for case in sorted(core_cases, key=lambda item: (item.case_id, item.model)):
        as_of_date = loaded.release_dates[case.target_period]
        origin_release_date = loaded.release_dates[case.origin_period]
        if _parse_date(origin_release_date, case.origin_period) >= _parse_date(
            as_of_date, case.target_period
        ):
            raise ReleaseTimeBacktestError("ORIGIN_NOT_AVAILABLE_BEFORE_AS_OF", case.case_id)
        case_rows.append(
            {
                "case_id": case.case_id,
                "scenario": case.scenario,
                "origin_period": case.origin_period,
                "origin_available_from_date": origin_release_date,
                "target_period": case.target_period,
                "as_of_date": as_of_date,
                "horizon_months": case.horizon_months,
                "masked_group": case.masked_group,
                "model": case.model,
                "truth_index": _text(case.truth_index, 12),
                "estimated_index": _text(case.estimated_index, 12),
                "index_error": _text(case.index_error, 12),
                "absolute_error_bps": _text(case.absolute_error_bps, 8),
                "masked_cell_mape_percent": _text(case.masked_cell_mape_percent, 8),
                "evidence_class": case.evidence_class,
                "economy_code": case.economy_code,
                "source_category": case.source_category,
                "value_vintage_class": VALUE_VINTAGE_CLASS,
                "completion_mode": COMPLETION_MODE,
                "target_period_donors_available_at_as_of": "true",
                "pre_release_forecast": "false",
                "temporal_split": policy.split_for(case.target_period),
            }
        )
    for case_id in sorted(indexed):
        reference = indexed[case_id][B3]
        b4 = b4_cases[case_id]
        selected = indexed[case_id][b4.selected_model]
        case_rows.append(
            {
                "case_id": case_id,
                "scenario": reference.scenario,
                "origin_period": reference.origin_period,
                "origin_available_from_date": loaded.release_dates[reference.origin_period],
                "target_period": reference.target_period,
                "as_of_date": loaded.release_dates[reference.target_period],
                "horizon_months": reference.horizon_months,
                "masked_group": reference.masked_group,
                "model": B4,
                "truth_index": _text(reference.truth_index, 12),
                "estimated_index": _text(b4.estimated_index, 12),
                "index_error": _text(selected.index_error, 12),
                "absolute_error_bps": _text(b4.absolute_error_bps, 8),
                "masked_cell_mape_percent": _text(selected.masked_cell_mape_percent, 8),
                "evidence_class": b4.evidence_class,
                "economy_code": reference.economy_code,
                "source_category": reference.source_category,
                "value_vintage_class": VALUE_VINTAGE_CLASS,
                "completion_mode": COMPLETION_MODE,
                "target_period_donors_available_at_as_of": "true",
                "pre_release_forecast": "false",
                "temporal_split": b4.split,
            }
        )
    case_rows.sort(key=lambda row: (str(row["case_id"]), str(row["model"])))
    _write_csv(output / "backtest_cases.csv", list(case_rows[0]), case_rows)

    metrics_rows: list[dict[str, Any]] = []
    errors_by_model: dict[str, list[Decimal]] = {model: [] for model in ALL_MODELS}
    for case in core_cases:
        errors_by_model[case.model].append(case.absolute_error_bps)
    errors_by_model[B4] = [b4_cases[case_id].absolute_error_bps for case_id in sorted(indexed)]
    for split in ("ALL", "DEVELOPMENT", "EVALUATION"):
        selected_ids = [
            case_id
            for case_id, by_model in indexed.items()
            if split == "ALL" or policy.split_for(by_model[B3].target_period) == split
        ]
        for model in ALL_MODELS:
            if model == B4:
                model_errors = [b4_cases[case_id].absolute_error_bps for case_id in selected_ids]
            else:
                model_errors = [indexed[case_id][model].absolute_error_bps for case_id in selected_ids]
            payload = _aggregate_model(
                [type("MetricCase", (), {"absolute_error_bps": value}) for value in model_errors]
            )
            metrics_rows.append(
                {
                    "split": split,
                    "model": model,
                    "case_count": payload["case_count"],
                    "mean_absolute_error_bps": _text(payload["mean_absolute_error_bps"], 10),
                    "p95_absolute_error_bps": _text(payload["p95_absolute_error_bps"], 10),
                    "maximum_absolute_error_bps": _text(payload["maximum_absolute_error_bps"], 10),
                }
            )
    _write_csv(output / "model_metrics.csv", list(metrics_rows[0]), metrics_rows)

    activation_payload = {
        "development_target_start": policy.development_target_start,
        "development_target_end": policy.development_target_end,
        "evaluation_data_used_for_activation": False,
        "rules": [
            {
                "rule_id": result.rule.rule_id,
                "development_case_count": result.development_case_count,
                "development_mean_b3_minus_b2_bps": result.mean_b3_minus_b2_bps,
                "development_regression_rate_b3_vs_b2": result.regression_rate_b3_vs_b2,
                "activated": result.activated,
            }
            for result in activations
        ],
    }
    _atomic_write(
        output / "b4_rule_activation.json", _canonical_json(_serialise(activation_payload))
    )

    evaluation_ids = [
        case_id
        for case_id, by_model in indexed.items()
        if policy.split_for(by_model[B3].target_period) == "EVALUATION"
    ]
    b4_eval = [b4_cases[case_id].absolute_error_bps for case_id in evaluation_ids]
    b3_eval = [indexed[case_id][B3].absolute_error_bps for case_id in evaluation_ids]
    b2_eval = [indexed[case_id][B2].absolute_error_bps for case_id in evaluation_ids]
    b1_eval = [indexed[case_id][B1].absolute_error_bps for case_id in evaluation_ids]
    evaluation_payload = {
        "evaluation_target_start": policy.evaluation_target_start,
        "evaluation_target_end": policy.evaluation_target_end,
        "evaluation_data_used_for_activation": False,
        "b4_vs_b3": _comparison(b4_eval, b3_eval),
        "b4_vs_b2": _comparison(b4_eval, b2_eval),
        "b4_vs_b1": _comparison(b4_eval, b1_eval),
        "model_promotion_allowed": False,
    }
    _atomic_write(
        output / "holdout_evaluation.json", _canonical_json(_serialise(evaluation_payload))
    )

    common_case_count = len(indexed)
    summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "status": "FIRST_PUBLISHED_RELEASE_TIME_COMPLETION_BACKTEST_COMPLETED",
        "completion_mode": COMPLETION_MODE,
        "value_vintage_class": VALUE_VINTAGE_CLASS,
        "universe_id": policy.universe_id,
        "common_case_count_per_model": common_case_count,
        "case_row_count": len(case_rows),
        "model_count": len(ALL_MODELS),
        "release_time_completion_comparison_allowed": True,
        "target_period_donors_available_at_as_of": True,
        "pre_release_forecast": False,
        "pre_release_forecast_comparison_allowed": False,
        "as_of_date_definition": "OFFICIAL_TARGET_MONTH_FULL_DATA_RELEASE_DATE",
        "truth_uses_first_published_values": True,
        "donors_use_first_published_values": True,
        "b0_b3_model_code_changed": False,
        "b4_retrained_on_first_published_development_period": True,
        "evaluation_data_used_for_b4_activation": False,
        "first_published_input_manifest_sha256": loaded.input_manifest_sha256,
        "first_published_snapshot_manifest_sha256": loaded.input_summary.get(
            "snapshot_manifest_sha256"
        ),
        "rejected_v089_experiment_reused": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "backtest_summary.json", _canonical_json(summary))

    report_lines = [
        "# Armilar v0.9.3 first-published release-time completion backtest",
        "",
        "## Interpretation",
        "",
        "Every case is evaluated as of the official full-data release date of the target month. Unmasked target-period first-published observations are available at that date and may serve as donors.",
        "",
        "This is a publication-aware missing-cell completion test. It is not a pre-release forecast and must not be described as one.",
        "",
        "## Models",
        "",
        "B0-B3 use the existing v0.9.0 model code with first-published CP00-CP12 values. B4 is reactivated using only 2022-2023 first-published cases and evaluated on 2024-2025.",
        "",
        "## B4 activation",
        "",
        "| Rule | Development cases | Mean B3-B2 (bps) | Regression rate | Activated |",
        "|---|---:|---:|---:|---|",
    ]
    for result in activations:
        report_lines.append(
            f"| {result.rule.rule_id} | {result.development_case_count} | "
            f"{_text(result.mean_b3_minus_b2_bps, 10)} | "
            f"{_text(result.regression_rate_b3_vs_b2, 10)} | {str(result.activated).lower()} |"
        )
    report_lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "Release-time completion comparisons are now valid for this five-economy first-published panel. Pre-release forecast comparisons and model promotion remain prohibited.",
            "",
            "`pre_release_forecast_comparison_allowed=false`",
            "",
            "`model_promotion_allowed=false`",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
        ]
    )
    _atomic_write(
        output / "RELEASE_TIME_BACKTEST_REPORT.md",
        ("\n".join(report_lines) + "\n").encode("utf-8"),
    )
    _write_manifest(output)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Armilar v0.9.3 first-published release-time completion backtest"
    )
    parser.add_argument("--policy", required=True)
    parser.add_argument("--first-published-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify_only:
        verify_manifest(args.output_dir)
        result = {"status": "MANIFEST_VERIFIED", "output_dir": args.output_dir}
    else:
        result = build_release_time_backtest(
            args.policy, args.first_published_dir, args.output_dir
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
