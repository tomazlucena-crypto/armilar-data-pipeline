"""Armilar v0.9.4 pre-publication forecast backtest.

The forecast is generated as of the official full-data release date of the
origin month.  No value from the target month, and no donor from the target
month, is available to any model.  Historical inputs use Eurostat values as
first published.  This removes target leakage, while remaining explicit that
later revisions known at each historical origin are not reconstructed.
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

from armilar_prices.first_published_v093 import verify_manifest as verify_first_published_manifest

getcontext().prec = 42

P0 = "P0_GLOBAL_EQUAL_HEADLINE_CARRY_FORWARD"
P1 = "P1_ARMILAR_WEIGHTED_HEADLINE_CARRY_FORWARD"
P2 = "P2_CATEGORY_CARRY_FORWARD"
P3 = "P3_CATEGORY_SEASONAL_YOY"
P4 = "P4_CATEGORY_HALF_ENSEMBLE"
MODELS = (P0, P1, P2, P3, P4)
CATEGORY_MODELS = (P2, P3, P4)
ECONOMY_MODELS = (P1, P2, P3, P4)
PAIRWISE_COMPARISONS = (
    (P1, P0),
    (P2, P1),
    (P3, P1),
    (P4, P1),
    (P4, P2),
    (P4, P3),
)
FORECAST_MODE = "FIRST_PUBLISHED_HISTORY_PRE_RELEASE_FORECAST"
TRUTH_DEFINITION = "FIRST_PUBLISHED_CATEGORY_WEIGHTED_ARMILAR_INDEX"
AS_OF_DEFINITION = "OFFICIAL_ORIGIN_MONTH_FULL_DATA_RELEASE_DATE"
VALUE_VINTAGE_CLASS = "FIRST_PUBLISHED_FULL_DATA_RELEASE"
HISTORICAL_REVISION_STATE = "INITIAL_RELEASE_ONLY"
CANONICAL_UNIVERSE = "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7"
REQUIRED_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
REQUIRED_CATEGORIES = tuple(f"CP{index:02d}" for index in range(13))
PRICE_CATEGORIES = REQUIRED_CATEGORIES[1:]
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
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
}


class PreReleaseBacktestError(RuntimeError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class PreReleasePolicy:
    policy_version: str
    universe_id: str
    required_first_published_policy_version: str
    history_start: str
    history_end: str
    evaluation_target_start: str
    evaluation_target_end: str
    development_target_start: str
    development_target_end: str
    holdout_target_start: str
    holdout_target_end: str
    horizons: tuple[int, ...]
    models: tuple[str, ...]
    minimum_history_months: int
    seasonal_lag_months: int
    ensemble_carry_forward_weight: Decimal
    ensemble_seasonal_weight: Decimal
    forecast_mode: str
    truth_definition: str
    as_of_definition: str
    pre_release_forecast: bool
    target_period_values_allowed: bool
    target_period_donors_allowed: bool
    future_period_source_values_allowed: bool
    target_release_date_used_for_prediction: bool
    uses_first_published_history: bool
    historical_as_of_revisions_available: bool
    development_data_used_for_model_selection: bool
    holdout_data_used_for_model_selection: bool
    rejected_v089_experiment_reused: bool
    pre_release_forecast_comparison_allowed: bool
    model_promotion_allowed: bool
    research_release_allowed: bool
    monetary_release_allowed: bool
    policy_sha256: str

    @classmethod
    def load(cls, path: Path | str) -> "PreReleasePolicy":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PreReleaseBacktestError("POLICY_INVALID", str(source)) from exc
        required = {
            "policy_version",
            "universe_id",
            "required_first_published_policy_version",
            "history_start",
            "history_end",
            "evaluation_target_start",
            "evaluation_target_end",
            "development_target_start",
            "development_target_end",
            "holdout_target_start",
            "holdout_target_end",
            "horizons",
            "models",
            "minimum_history_months",
            "seasonal_lag_months",
            "ensemble_carry_forward_weight",
            "ensemble_seasonal_weight",
            "forecast_mode",
            "truth_definition",
            "as_of_definition",
            "pre_release_forecast",
            "target_period_values_allowed",
            "target_period_donors_allowed",
            "future_period_source_values_allowed",
            "target_release_date_used_for_prediction",
            "uses_first_published_history",
            "historical_as_of_revisions_available",
            "development_data_used_for_model_selection",
            "holdout_data_used_for_model_selection",
            "rejected_v089_experiment_reused",
            "pre_release_forecast_comparison_allowed",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise PreReleaseBacktestError("POLICY_FIELD_MISSING", ",".join(missing))
        try:
            policy = cls(
                policy_version=str(payload["policy_version"]),
                universe_id=str(payload["universe_id"]),
                required_first_published_policy_version=str(
                    payload["required_first_published_policy_version"]
                ),
                history_start=str(payload["history_start"]),
                history_end=str(payload["history_end"]),
                evaluation_target_start=str(payload["evaluation_target_start"]),
                evaluation_target_end=str(payload["evaluation_target_end"]),
                development_target_start=str(payload["development_target_start"]),
                development_target_end=str(payload["development_target_end"]),
                holdout_target_start=str(payload["holdout_target_start"]),
                holdout_target_end=str(payload["holdout_target_end"]),
                horizons=tuple(int(value) for value in payload["horizons"]),
                models=tuple(str(value) for value in payload["models"]),
                minimum_history_months=int(payload["minimum_history_months"]),
                seasonal_lag_months=int(payload["seasonal_lag_months"]),
                ensemble_carry_forward_weight=_decimal(
                    str(payload["ensemble_carry_forward_weight"]),
                    "ENSEMBLE_WEIGHT_INVALID",
                    "ensemble_carry_forward_weight",
                ),
                ensemble_seasonal_weight=_decimal(
                    str(payload["ensemble_seasonal_weight"]),
                    "ENSEMBLE_WEIGHT_INVALID",
                    "ensemble_seasonal_weight",
                ),
                forecast_mode=str(payload["forecast_mode"]),
                truth_definition=str(payload["truth_definition"]),
                as_of_definition=str(payload["as_of_definition"]),
                pre_release_forecast=bool(payload["pre_release_forecast"]),
                target_period_values_allowed=bool(payload["target_period_values_allowed"]),
                target_period_donors_allowed=bool(payload["target_period_donors_allowed"]),
                future_period_source_values_allowed=bool(
                    payload["future_period_source_values_allowed"]
                ),
                target_release_date_used_for_prediction=bool(
                    payload["target_release_date_used_for_prediction"]
                ),
                uses_first_published_history=bool(payload["uses_first_published_history"]),
                historical_as_of_revisions_available=bool(
                    payload["historical_as_of_revisions_available"]
                ),
                development_data_used_for_model_selection=bool(
                    payload["development_data_used_for_model_selection"]
                ),
                holdout_data_used_for_model_selection=bool(
                    payload["holdout_data_used_for_model_selection"]
                ),
                rejected_v089_experiment_reused=bool(
                    payload["rejected_v089_experiment_reused"]
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
            raise PreReleaseBacktestError("POLICY_INVALID", str(exc)) from exc
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.policy_version != "0.9.4":
            raise PreReleaseBacktestError("POLICY_VERSION_UNSUPPORTED", self.policy_version)
        if self.required_first_published_policy_version != "0.9.3":
            raise PreReleaseBacktestError(
                "FIRST_PUBLISHED_POLICY_VERSION_UNSUPPORTED",
                self.required_first_published_policy_version,
            )
        if self.universe_id != CANONICAL_UNIVERSE:
            raise PreReleaseBacktestError("UNIVERSE_CONTRACT_MISMATCH", self.universe_id)
        for period in (
            self.history_start,
            self.history_end,
            self.evaluation_target_start,
            self.evaluation_target_end,
            self.development_target_start,
            self.development_target_end,
            self.holdout_target_start,
            self.holdout_target_end,
        ):
            _validate_period(period)
        if self.history_start != "2021-01" or self.history_end != "2025-12":
            raise PreReleaseBacktestError("HISTORY_INTERVAL_CONTRACT_MISMATCH")
        temporal_contract = (
            self.evaluation_target_start,
            self.evaluation_target_end,
            self.development_target_start,
            self.development_target_end,
            self.holdout_target_start,
            self.holdout_target_end,
        )
        if temporal_contract != (
            "2023-01",
            "2025-12",
            "2023-01",
            "2023-12",
            "2024-01",
            "2025-12",
        ):
            raise PreReleaseBacktestError("TEMPORAL_CONTRACT_MISMATCH")
        if self.evaluation_target_start != self.development_target_start:
            raise PreReleaseBacktestError("DEVELOPMENT_START_MISMATCH")
        if self.evaluation_target_end != self.holdout_target_end:
            raise PreReleaseBacktestError("HOLDOUT_END_MISMATCH")
        if not (
            self.development_target_start
            <= self.development_target_end
            < self.holdout_target_start
            <= self.holdout_target_end
        ):
            raise PreReleaseBacktestError("TEMPORAL_SPLIT_INVALID")
        if add_months(self.development_target_end, 1) != self.holdout_target_start:
            raise PreReleaseBacktestError("TEMPORAL_SPLIT_NOT_CONTIGUOUS")
        if self.horizons != (1, 3, 6, 12):
            raise PreReleaseBacktestError("HORIZON_CONTRACT_MISMATCH", str(self.horizons))
        if self.models != MODELS:
            raise PreReleaseBacktestError("MODEL_CONTRACT_MISMATCH", str(self.models))
        if self.minimum_history_months != 12:
            raise PreReleaseBacktestError("MINIMUM_HISTORY_CONTRACT_MISMATCH")
        if self.seasonal_lag_months != 12:
            raise PreReleaseBacktestError("SEASONAL_LAG_CONTRACT_MISMATCH")
        if (
            self.ensemble_carry_forward_weight != Decimal("0.5")
            or self.ensemble_seasonal_weight != Decimal("0.5")
            or self.ensemble_carry_forward_weight + self.ensemble_seasonal_weight
            != Decimal("1")
        ):
            raise PreReleaseBacktestError("ENSEMBLE_WEIGHT_CONTRACT_MISMATCH")
        if self.forecast_mode != FORECAST_MODE:
            raise PreReleaseBacktestError("FORECAST_MODE_MISMATCH", self.forecast_mode)
        if self.truth_definition != TRUTH_DEFINITION:
            raise PreReleaseBacktestError("TRUTH_DEFINITION_MISMATCH")
        if self.as_of_definition != AS_OF_DEFINITION:
            raise PreReleaseBacktestError("AS_OF_DEFINITION_MISMATCH")
        if not self.pre_release_forecast:
            raise PreReleaseBacktestError("PRE_RELEASE_FORECAST_MUST_BE_TRUE")
        if (
            self.target_period_values_allowed
            or self.target_period_donors_allowed
            or self.future_period_source_values_allowed
            or self.target_release_date_used_for_prediction
        ):
            raise PreReleaseBacktestError("TARGET_INFORMATION_LEAKAGE_ALLOWED")
        if not self.uses_first_published_history:
            raise PreReleaseBacktestError("FIRST_PUBLISHED_HISTORY_REQUIRED")
        if self.historical_as_of_revisions_available:
            raise PreReleaseBacktestError("HISTORICAL_REVISION_CLAIM_UNSUPPORTED")
        if (
            self.development_data_used_for_model_selection
            or self.holdout_data_used_for_model_selection
        ):
            raise PreReleaseBacktestError("MODEL_SELECTION_MUST_REMAIN_DISABLED")
        if self.rejected_v089_experiment_reused:
            raise PreReleaseBacktestError("REJECTED_EXPERIMENT_REUSED")
        if not self.pre_release_forecast_comparison_allowed:
            raise PreReleaseBacktestError("PRE_RELEASE_COMPARISON_MUST_BE_ENABLED")
        if (
            self.model_promotion_allowed
            or self.research_release_allowed
            or self.monetary_release_allowed
        ):
            raise PreReleaseBacktestError("RELEASE_GATE_MUST_REMAIN_FALSE")

    def split_for(self, target_period: str) -> str:
        if self.development_target_start <= target_period <= self.development_target_end:
            return "DEVELOPMENT"
        if self.holdout_target_start <= target_period <= self.holdout_target_end:
            return "HOLDOUT"
        raise PreReleaseBacktestError("TARGET_OUTSIDE_TEMPORAL_SPLIT", target_period)


@dataclass(frozen=True)
class LoadedFirstPublishedPanel:
    values: Mapping[tuple[str, str, str], Decimal]
    cell_weights: Mapping[tuple[str, str], Decimal]
    economy_weights: Mapping[str, Decimal]
    economy_names: Mapping[str, str]
    release_dates: Mapping[str, str]
    periods: tuple[str, ...]
    input_summary: Mapping[str, Any]
    input_manifest_sha256: str


@dataclass(frozen=True)
class ForecastResult:
    value: Decimal
    source_periods: tuple[str, ...]
    evidence_class: str


@dataclass(frozen=True)
class GlobalForecastCase:
    case_id: str
    split: str
    model: str
    origin_period: str
    target_period: str
    horizon_months: int
    as_of_date: str
    target_release_date: str
    truth_index: Decimal
    forecast_index: Decimal
    index_error: Decimal
    absolute_error_bps: Decimal
    source_periods: tuple[str, ...]
    evidence_class: str


@dataclass(frozen=True)
class EconomyForecastCase:
    case_id: str
    split: str
    model: str
    economy_code: str
    origin_period: str
    target_period: str
    horizon_months: int
    truth_index: Decimal
    forecast_index: Decimal
    absolute_error_bps: Decimal


@dataclass(frozen=True)
class CellForecastCase:
    case_id: str
    split: str
    model: str
    economy_code: str
    source_category: str
    origin_period: str
    target_period: str
    horizon_months: int
    truth_value: Decimal
    forecast_value: Decimal
    absolute_error_bps: Decimal


def _installed_version() -> str:
    try:
        return metadata.version("armilar-data-pipeline")
    except metadata.PackageNotFoundError:
        return "0.9.4"


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
        raise PreReleaseBacktestError("MANIFEST_MISSING", str(manifest))
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.strip().split(maxsplit=1)
        if len(parts) != 2 or not HEX64.fullmatch(parts[0].lower()):
            raise PreReleaseBacktestError("MANIFEST_INVALID", raw_line)
        expected, relative = parts[0].lower(), parts[1].strip()
        target = (base / relative).resolve()
        resolved = base.resolve()
        if target != resolved and resolved not in target.parents:
            raise PreReleaseBacktestError("MANIFEST_PATH_INVALID", relative)
        if not target.is_file():
            raise PreReleaseBacktestError("MANIFEST_FILE_MISSING", relative)
        if _sha256(target.read_bytes()) != expected:
            raise PreReleaseBacktestError("MANIFEST_HASH_MISMATCH", relative)


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise PreReleaseBacktestError(code, detail) from exc
    if not parsed.is_finite():
        raise PreReleaseBacktestError(code, detail)
    return parsed


def _validate_period(value: str) -> None:
    if not PERIOD_PATTERN.fullmatch(value):
        raise PreReleaseBacktestError("PERIOD_INVALID", value)


def add_months(period: str, months: int) -> str:
    _validate_period(period)
    year = int(period[:4])
    month = int(period[5:])
    index = year * 12 + month - 1 + months
    if index < 0:
        raise PreReleaseBacktestError("PERIOD_SHIFT_INVALID", f"{period}/{months}")
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _iter_periods(start: str, end: str) -> Iterable[str]:
    current = start
    while current <= end:
        yield current
        current = add_months(current, 1)


def _parse_date(value: str, detail: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PreReleaseBacktestError("RELEASE_DATE_INVALID", detail) from exc


def _text(value: Decimal, places: int = 10) -> str:
    return format(value.quantize(Decimal(1).scaleb(-places)), "f")


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise PreReleaseBacktestError("EMPTY_METRIC_SAMPLE")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise PreReleaseBacktestError("EMPTY_METRIC_SAMPLE")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _p95(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise PreReleaseBacktestError("EMPTY_METRIC_SAMPLE")
    ordered = sorted(values)
    index = max(0, math.ceil(Decimal("0.95") * Decimal(len(ordered))) - 1)
    return ordered[index]


def _signed_bps(forecast: Decimal, truth: Decimal) -> Decimal:
    if truth <= 0:
        raise PreReleaseBacktestError("TRUTH_VALUE_NON_POSITIVE")
    return (forecast / truth - Decimal("1")) * Decimal("10000")


def _absolute_bps(forecast: Decimal, truth: Decimal) -> Decimal:
    return abs(_signed_bps(forecast, truth))


def _manifest_sha256(root: Path) -> str:
    return _sha256((root / "MANIFEST.sha256").read_bytes())


def load_first_published_panel(
    policy: PreReleasePolicy, input_dir: Path | str
) -> LoadedFirstPublishedPanel:
    root = Path(input_dir)
    verify_first_published_manifest(root)
    summary_path = root / "run_summary.json"
    observations_path = root / "first_published_observations.csv"
    if not summary_path.is_file() or not observations_path.is_file():
        raise PreReleaseBacktestError("FIRST_PUBLISHED_INPUT_MISSING", str(root))
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
            raise PreReleaseBacktestError(
                "FIRST_PUBLISHED_CONTRACT_MISMATCH", f"{field}={summary.get(field)!r}"
            )
    if summary.get("observation_count") != 3900:
        raise PreReleaseBacktestError(
            "FIRST_PUBLISHED_OBSERVATION_COUNT_MISMATCH", str(summary.get("observation_count"))
        )

    values: dict[tuple[str, str, str], Decimal] = {}
    cell_weights: dict[tuple[str, str], Decimal] = {}
    economy_weights: dict[str, Decimal] = {}
    economy_names: dict[str, str] = {}
    release_dates: dict[str, str] = {}
    periods: set[str] = set()
    economies: set[str] = set()
    categories: set[str] = set()

    with observations_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_PANEL_FIELDS - set(reader.fieldnames or ()))
        if missing:
            raise PreReleaseBacktestError("FIRST_PUBLISHED_SCHEMA_MISMATCH", ",".join(missing))
        for line_number, row in enumerate(reader, start=2):
            if row["universe_id"] != policy.universe_id:
                raise PreReleaseBacktestError("UNIVERSE_MISMATCH", f"line {line_number}")
            economy = str(row["economy_code"])
            category = str(row["source_category"])
            period = str(row["period"])
            _validate_period(period)
            if economy not in REQUIRED_ECONOMIES or category not in REQUIRED_CATEGORIES:
                raise PreReleaseBacktestError("PANEL_UNIVERSE_MISMATCH", f"line {line_number}")
            if row["value_vintage_class"] != VALUE_VINTAGE_CLASS:
                raise PreReleaseBacktestError("VALUE_VINTAGE_CLASS_MISMATCH", f"line {line_number}")
            release_date = str(row["available_from_date"])
            parsed_release = _parse_date(release_date, f"line {line_number}")
            if parsed_release <= date(int(period[:4]), int(period[5:]), 1):
                raise PreReleaseBacktestError("RELEASE_DATE_NOT_AFTER_REFERENCE_MONTH", period)
            if period in release_dates and release_dates[period] != release_date:
                raise PreReleaseBacktestError("RELEASE_DATE_INCONSISTENT", period)
            release_dates[period] = release_date
            relative = _decimal(
                str(row["price_relative_first_published"]),
                "FIRST_PUBLISHED_RELATIVE_INVALID",
                f"line {line_number}",
            )
            if relative <= 0:
                raise PreReleaseBacktestError("FIRST_PUBLISHED_RELATIVE_NON_POSITIVE", f"line {line_number}")
            key = (economy, category, period)
            if key in values:
                raise PreReleaseBacktestError("DUPLICATE_OBSERVATION", f"line {line_number}")
            values[key] = relative
            economy_weight = _decimal(
                str(row["economy_fixed_universe_weight"]),
                "ECONOMY_WEIGHT_INVALID",
                f"line {line_number}",
            )
            if economy_weight <= 0:
                raise PreReleaseBacktestError("ECONOMY_WEIGHT_NON_POSITIVE", economy)
            if economy in economy_weights and economy_weights[economy] != economy_weight:
                raise PreReleaseBacktestError("ECONOMY_WEIGHT_CHANGED", economy)
            economy_weights[economy] = economy_weight
            if category != "CP00":
                cell_weight = _decimal(
                    str(row["fixed_universe_weight"]),
                    "CELL_WEIGHT_INVALID",
                    f"line {line_number}",
                )
                if cell_weight <= 0:
                    raise PreReleaseBacktestError("CELL_WEIGHT_NON_POSITIVE", f"{economy}/{category}")
                cell_key = (economy, category)
                if cell_key in cell_weights and cell_weights[cell_key] != cell_weight:
                    raise PreReleaseBacktestError("CELL_WEIGHT_CHANGED", f"{economy}/{category}")
                cell_weights[cell_key] = cell_weight
            economy_names[economy] = str(row["economy_name"])
            periods.add(period)
            economies.add(economy)
            categories.add(category)

    expected_periods = tuple(_iter_periods(policy.history_start, policy.history_end))
    if tuple(sorted(periods)) != expected_periods:
        raise PreReleaseBacktestError("PERIOD_GRID_MISMATCH")
    if tuple(sorted(economies)) != REQUIRED_ECONOMIES:
        raise PreReleaseBacktestError("ECONOMY_GRID_MISMATCH")
    if tuple(sorted(categories)) != REQUIRED_CATEGORIES:
        raise PreReleaseBacktestError("CATEGORY_GRID_MISMATCH")
    expected_keys = {
        (economy, category, period)
        for economy in REQUIRED_ECONOMIES
        for category in REQUIRED_CATEGORIES
        for period in expected_periods
    }
    if set(values) != expected_keys:
        raise PreReleaseBacktestError("GRID_INCOMPLETE")
    if len(cell_weights) != len(REQUIRED_ECONOMIES) * len(PRICE_CATEGORIES):
        raise PreReleaseBacktestError("CELL_WEIGHT_GRID_INCOMPLETE")
    if sum(cell_weights.values(), Decimal("0")) != Decimal("1"):
        raise PreReleaseBacktestError("CELL_WEIGHTS_DO_NOT_SUM_TO_ONE")
    if sum(economy_weights.values(), Decimal("0")) != Decimal("1"):
        raise PreReleaseBacktestError("ECONOMY_WEIGHTS_DO_NOT_SUM_TO_ONE")
    for economy in REQUIRED_ECONOMIES:
        cell_total = sum(
            (cell_weights[(economy, category)] for category in PRICE_CATEGORIES),
            Decimal("0"),
        )
        if cell_total != economy_weights[economy]:
            raise PreReleaseBacktestError("ECONOMY_WEIGHT_RECONCILIATION_FAILED", economy)
    ordered_release_dates = [_parse_date(release_dates[period], period) for period in expected_periods]
    if ordered_release_dates != sorted(ordered_release_dates) or len(set(ordered_release_dates)) != len(ordered_release_dates):
        raise PreReleaseBacktestError("RELEASE_DATES_NOT_STRICTLY_INCREASING")

    return LoadedFirstPublishedPanel(
        values=values,
        cell_weights=cell_weights,
        economy_weights=economy_weights,
        economy_names=economy_names,
        release_dates=release_dates,
        periods=expected_periods,
        input_summary=summary,
        input_manifest_sha256=_manifest_sha256(root),
    )


def _forecast_pairs(
    policy: PreReleasePolicy, panel: LoadedFirstPublishedPanel
) -> tuple[tuple[str, str, int], ...]:
    available = set(panel.periods)
    pairs: list[tuple[str, str, int]] = []
    for target in _iter_periods(policy.evaluation_target_start, policy.evaluation_target_end):
        for horizon in policy.horizons:
            origin = add_months(target, -horizon)
            required_sources = {
                origin,
                add_months(origin, -policy.seasonal_lag_months),
                add_months(target, -policy.seasonal_lag_months),
            }
            if not required_sources <= available:
                raise PreReleaseBacktestError(
                    "INSUFFICIENT_HISTORY_FOR_FORECAST", f"{origin}/{target}/H{horizon}"
                )
            if not all(source <= origin for source in required_sources):
                raise PreReleaseBacktestError("SOURCE_PERIOD_AFTER_ORIGIN", f"{origin}/{target}")
            if _parse_date(panel.release_dates[origin], origin) >= _parse_date(
                panel.release_dates[target], target
            ):
                raise PreReleaseBacktestError("ORIGIN_RELEASE_NOT_BEFORE_TARGET_RELEASE")
            pairs.append((origin, target, horizon))
    return tuple(pairs)


def _truth_global(panel: LoadedFirstPublishedPanel, target: str) -> Decimal:
    return sum(
        (
            panel.cell_weights[(economy, category)]
            * panel.values[(economy, category, target)]
            for economy in REQUIRED_ECONOMIES
            for category in PRICE_CATEGORIES
        ),
        Decimal("0"),
    )


def _truth_economy(panel: LoadedFirstPublishedPanel, economy: str, target: str) -> Decimal:
    economy_weight = panel.economy_weights[economy]
    return sum(
        (
            panel.cell_weights[(economy, category)]
            / economy_weight
            * panel.values[(economy, category, target)]
            for category in PRICE_CATEGORIES
        ),
        Decimal("0"),
    )


def _seasonal_cell_forecast(
    panel: LoadedFirstPublishedPanel,
    economy: str,
    category: str,
    origin: str,
    target: str,
    seasonal_lag: int,
) -> ForecastResult:
    target_season = add_months(target, -seasonal_lag)
    origin_year_ago = add_months(origin, -seasonal_lag)
    source_periods = tuple(sorted({origin, target_season, origin_year_ago}))
    _assert_no_lookahead(origin, target, source_periods)
    origin_value = panel.values[(economy, category, origin)]
    origin_year_ago_value = panel.values[(economy, category, origin_year_ago)]
    target_season_value = panel.values[(economy, category, target_season)]
    if origin_year_ago_value <= 0:
        raise PreReleaseBacktestError("SEASONAL_DENOMINATOR_NON_POSITIVE")
    value = target_season_value * (origin_value / origin_year_ago_value)
    return ForecastResult(
        value=value,
        source_periods=source_periods,
        evidence_class="FIRST_PUBLISHED_SEASONAL_YOY_WITH_ORIGIN_CUTOFF",
    )


def _assert_no_lookahead(origin: str, target: str, source_periods: Sequence[str]) -> None:
    if target in source_periods:
        raise PreReleaseBacktestError("TARGET_PERIOD_VALUE_USED", target)
    if any(period > origin for period in source_periods):
        raise PreReleaseBacktestError("FUTURE_SOURCE_PERIOD_USED", ",".join(source_periods))


def _cell_forecast(
    panel: LoadedFirstPublishedPanel,
    policy: PreReleasePolicy,
    model: str,
    economy: str,
    category: str,
    origin: str,
    target: str,
) -> ForecastResult:
    if model == P2:
        source_periods = (origin,)
        _assert_no_lookahead(origin, target, source_periods)
        return ForecastResult(
            value=panel.values[(economy, category, origin)],
            source_periods=source_periods,
            evidence_class="FIRST_PUBLISHED_CATEGORY_CARRY_FORWARD",
        )
    seasonal = _seasonal_cell_forecast(
        panel, economy, category, origin, target, policy.seasonal_lag_months
    )
    if model == P3:
        return seasonal
    if model == P4:
        carry_value = panel.values[(economy, category, origin)]
        value = (
            policy.ensemble_carry_forward_weight * carry_value
            + policy.ensemble_seasonal_weight * seasonal.value
        )
        return ForecastResult(
            value=value,
            source_periods=seasonal.source_periods,
            evidence_class="FIRST_PUBLISHED_FIXED_HALF_CARRY_HALF_SEASONAL",
        )
    raise PreReleaseBacktestError("CELL_MODEL_UNSUPPORTED", model)


def _global_forecast(
    panel: LoadedFirstPublishedPanel,
    policy: PreReleasePolicy,
    model: str,
    origin: str,
    target: str,
) -> ForecastResult:
    if model == P0:
        values = [panel.values[(economy, "CP00", origin)] for economy in REQUIRED_ECONOMIES]
        return ForecastResult(
            value=_mean(values),
            source_periods=(origin,),
            evidence_class="FIRST_PUBLISHED_EQUAL_HEADLINE_CARRY_FORWARD",
        )
    if model == P1:
        value = sum(
            (
                panel.economy_weights[economy]
                * panel.values[(economy, "CP00", origin)]
                for economy in REQUIRED_ECONOMIES
            ),
            Decimal("0"),
        )
        return ForecastResult(
            value=value,
            source_periods=(origin,),
            evidence_class="FIRST_PUBLISHED_ARMILAR_WEIGHTED_HEADLINE_CARRY_FORWARD",
        )
    if model in CATEGORY_MODELS:
        results = {
            (economy, category): _cell_forecast(
                panel, policy, model, economy, category, origin, target
            )
            for economy in REQUIRED_ECONOMIES
            for category in PRICE_CATEGORIES
        }
        source_periods = tuple(
            sorted({period for result in results.values() for period in result.source_periods})
        )
        _assert_no_lookahead(origin, target, source_periods)
        value = sum(
            (
                panel.cell_weights[(economy, category)]
                * results[(economy, category)].value
                for economy in REQUIRED_ECONOMIES
                for category in PRICE_CATEGORIES
            ),
            Decimal("0"),
        )
        return ForecastResult(
            value=value,
            source_periods=source_periods,
            evidence_class={
                P2: "FIRST_PUBLISHED_CATEGORY_CARRY_FORWARD_INDEX",
                P3: "FIRST_PUBLISHED_CATEGORY_SEASONAL_YOY_INDEX",
                P4: "FIRST_PUBLISHED_FIXED_HALF_ENSEMBLE_INDEX",
            }[model],
        )
    raise PreReleaseBacktestError("GLOBAL_MODEL_UNSUPPORTED", model)


def _economy_forecast(
    panel: LoadedFirstPublishedPanel,
    policy: PreReleasePolicy,
    model: str,
    economy: str,
    origin: str,
    target: str,
) -> Decimal:
    if model == P1:
        return panel.values[(economy, "CP00", origin)]
    if model in CATEGORY_MODELS:
        economy_weight = panel.economy_weights[economy]
        return sum(
            (
                panel.cell_weights[(economy, category)]
                / economy_weight
                * _cell_forecast(
                    panel, policy, model, economy, category, origin, target
                ).value
                for category in PRICE_CATEGORIES
            ),
            Decimal("0"),
        )
    raise PreReleaseBacktestError("ECONOMY_MODEL_UNSUPPORTED", model)


def _aggregate_errors(errors: Sequence[Decimal]) -> Mapping[str, Any]:
    if not errors:
        raise PreReleaseBacktestError("EMPTY_METRIC_SAMPLE")
    return {
        "case_count": len(errors),
        "mean_absolute_error_bps": _mean(errors),
        "p95_absolute_error_bps": _p95(errors),
        "maximum_absolute_error_bps": max(errors),
    }


def _comparison(challenger: Sequence[Decimal], baseline: Sequence[Decimal]) -> Mapping[str, Any]:
    if len(challenger) != len(baseline) or not challenger:
        raise PreReleaseBacktestError("COMPARISON_SAMPLE_INVALID")
    deltas = [left - right for left, right in zip(challenger, baseline)]
    return {
        "case_count": len(deltas),
        "mean_delta_absolute_bps": _mean(deltas),
        "median_delta_absolute_bps": _median(deltas),
        "p95_delta_absolute_bps": _p95(deltas),
        "worst_regression_bps": max(deltas),
        "best_improvement_bps": min(deltas),
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


def _global_metrics_rows(cases: Sequence[GlobalForecastCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("ALL", "DEVELOPMENT", "HOLDOUT"):
        for horizon in ("ALL", 1, 3, 6, 12):
            for model in MODELS:
                selected = [
                    case
                    for case in cases
                    if case.model == model
                    and (split == "ALL" or case.split == split)
                    and (horizon == "ALL" or case.horizon_months == horizon)
                ]
                payload = _aggregate_errors([case.absolute_error_bps for case in selected])
                signed_errors = [
                    _signed_bps(case.forecast_index, case.truth_index)
                    for case in selected
                ]
                rows.append(
                    {
                        "split": split,
                        "horizon_months": horizon,
                        "model": model,
                        "case_count": payload["case_count"],
                        "mean_signed_error_bps": _text(_mean(signed_errors)),
                        "mean_absolute_error_bps": _text(payload["mean_absolute_error_bps"]),
                        "p95_absolute_error_bps": _text(payload["p95_absolute_error_bps"]),
                        "maximum_absolute_error_bps": _text(payload["maximum_absolute_error_bps"]),
                    }
                )
    return rows


def _economy_metrics_rows(cases: Sequence[EconomyForecastCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("ALL", "HOLDOUT"):
        for economy in REQUIRED_ECONOMIES:
            for model in ECONOMY_MODELS:
                selected = [
                    case
                    for case in cases
                    if case.economy_code == economy
                    and case.model == model
                    and (split == "ALL" or case.split == split)
                ]
                payload = _aggregate_errors([case.absolute_error_bps for case in selected])
                rows.append(
                    {
                        "split": split,
                        "economy_code": economy,
                        "model": model,
                        "case_count": payload["case_count"],
                        "mean_absolute_error_bps": _text(payload["mean_absolute_error_bps"]),
                        "p95_absolute_error_bps": _text(payload["p95_absolute_error_bps"]),
                        "maximum_absolute_error_bps": _text(payload["maximum_absolute_error_bps"]),
                    }
                )
    return rows


def _category_metrics_rows(cases: Sequence[CellForecastCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("ALL", "HOLDOUT"):
        for category in PRICE_CATEGORIES:
            for model in CATEGORY_MODELS:
                selected = [
                    case
                    for case in cases
                    if case.source_category == category
                    and case.model == model
                    and (split == "ALL" or case.split == split)
                ]
                payload = _aggregate_errors([case.absolute_error_bps for case in selected])
                rows.append(
                    {
                        "split": split,
                        "source_category": category,
                        "model": model,
                        "case_count": payload["case_count"],
                        "mean_absolute_error_bps": _text(payload["mean_absolute_error_bps"]),
                        "p95_absolute_error_bps": _text(payload["p95_absolute_error_bps"]),
                        "maximum_absolute_error_bps": _text(payload["maximum_absolute_error_bps"]),
                    }
                )
    return rows



def _assert_common_global_sample(cases: Sequence[GlobalForecastCase]) -> tuple[str, ...]:
    samples: dict[str, tuple[str, ...]] = {}
    for model in MODELS:
        identifiers = [case.case_id for case in cases if case.model == model]
        if len(identifiers) != len(set(identifiers)):
            raise PreReleaseBacktestError("DUPLICATE_GLOBAL_CASE_ID", model)
        samples[model] = tuple(sorted(identifiers))
    reference = samples[P0]
    if not reference:
        raise PreReleaseBacktestError("EMPTY_GLOBAL_SAMPLE")
    for model in MODELS[1:]:
        if samples[model] != reference:
            raise PreReleaseBacktestError("GLOBAL_CASE_ID_SAMPLE_MISMATCH", model)
    return reference


def _selected_global_cases(
    cases: Sequence[GlobalForecastCase], split: str, horizon: str | int
) -> list[GlobalForecastCase]:
    return [
        case
        for case in cases
        if (split == "ALL" or case.split == split)
        and (horizon == "ALL" or case.horizon_months == horizon)
    ]


def _paired_global_metrics_rows(cases: Sequence[GlobalForecastCase]) -> list[dict[str, Any]]:
    _assert_common_global_sample(cases)
    by_key = {(case.case_id, case.model): case for case in cases}
    rows: list[dict[str, Any]] = []
    for split in ("ALL", "DEVELOPMENT", "HOLDOUT"):
        for horizon in ("ALL", 1, 3, 6, 12):
            selected = _selected_global_cases(cases, split, horizon)
            case_ids = tuple(sorted({case.case_id for case in selected}))
            if not case_ids:
                raise PreReleaseBacktestError(
                    "EMPTY_PAIRED_SAMPLE", f"{split}/{horizon}"
                )
            for challenger, baseline in PAIRWISE_COMPARISONS:
                challenger_cases = [by_key[(case_id, challenger)] for case_id in case_ids]
                baseline_cases = [by_key[(case_id, baseline)] for case_id in case_ids]
                comparison = _comparison(
                    [case.absolute_error_bps for case in challenger_cases],
                    [case.absolute_error_bps for case in baseline_cases],
                )
                signed_deltas = [
                    _signed_bps(left.forecast_index, left.truth_index)
                    - _signed_bps(right.forecast_index, right.truth_index)
                    for left, right in zip(challenger_cases, baseline_cases)
                ]
                rows.append(
                    {
                        "split": split,
                        "horizon_months": horizon,
                        "challenger": challenger,
                        "baseline": baseline,
                        "case_count": comparison["case_count"],
                        "mean_delta_absolute_bps": _text(
                            comparison["mean_delta_absolute_bps"]
                        ),
                        "median_delta_absolute_bps": _text(
                            comparison["median_delta_absolute_bps"]
                        ),
                        "p95_delta_absolute_bps": _text(
                            comparison["p95_delta_absolute_bps"]
                        ),
                        "worst_regression_bps": _text(
                            comparison["worst_regression_bps"]
                        ),
                        "best_improvement_bps": _text(
                            comparison["best_improvement_bps"]
                        ),
                        "mean_signed_error_delta_bps": _text(_mean(signed_deltas)),
                        "improvement_rate": _text(comparison["improvement_rate"]),
                        "regression_rate": _text(comparison["regression_rate"]),
                        "tie_rate": _text(comparison["tie_rate"]),
                    }
                )
    return rows


def _model_ranking(
    cases: Sequence[GlobalForecastCase], split: str, horizon: str | int
) -> list[dict[str, Any]]:
    selected = _selected_global_cases(cases, split, horizon)
    ranking: list[dict[str, Any]] = []
    for model in MODELS:
        model_cases = [case for case in selected if case.model == model]
        errors = [case.absolute_error_bps for case in model_cases]
        signed_errors = [
            _signed_bps(case.forecast_index, case.truth_index) for case in model_cases
        ]
        payload = _aggregate_errors(errors)
        ranking.append(
            {
                "model": model,
                **payload,
                "mean_signed_error_bps": _mean(signed_errors),
            }
        )
    ranking.sort(
        key=lambda item: (
            item["mean_absolute_error_bps"],
            item["p95_absolute_error_bps"],
            item["model"],
        )
    )
    return [{"rank": index, **item} for index, item in enumerate(ranking, start=1)]


def _ranking_stability_payload(cases: Sequence[GlobalForecastCase]) -> Mapping[str, Any]:
    development = _model_ranking(cases, "DEVELOPMENT", "ALL")
    holdout = _model_ranking(cases, "HOLDOUT", "ALL")
    development_models = [item["model"] for item in development]
    holdout_models = [item["model"] for item in holdout]
    horizons = []
    for horizon in (1, 3, 6, 12):
        dev = _model_ranking(cases, "DEVELOPMENT", horizon)
        out = _model_ranking(cases, "HOLDOUT", horizon)
        dev_models = [item["model"] for item in dev]
        out_models = [item["model"] for item in out]
        horizons.append(
            {
                "horizon_months": horizon,
                "development_ranking": dev_models,
                "holdout_ranking": out_models,
                "ranking_changed": dev_models != out_models,
                "winner_changed": dev_models[0] != out_models[0],
            }
        )
    return {
        "development_ranking": development_models,
        "holdout_ranking": holdout_models,
        "ranking_changed": development_models != holdout_models,
        "winner_changed": development_models[0] != holdout_models[0],
        "development_winner": development_models[0],
        "holdout_winner": holdout_models[0],
        "by_horizon": horizons,
        "development_data_used_for_model_selection": False,
        "holdout_data_used_for_model_selection": False,
        "model_promotion_allowed": False,
    }


def _focus_diagnostics_payload(
    model_metrics: Sequence[Mapping[str, Any]],
    economy_metrics: Sequence[Mapping[str, Any]],
    category_metrics: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    def rank(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(
            rows,
            key=lambda row: (
                Decimal(str(row["mean_absolute_error_bps"])),
                Decimal(str(row["p95_absolute_error_bps"])),
                str(row["model"]),
            ),
        )
        return [
            {
                "rank": index,
                "model": row["model"],
                "case_count": int(row["case_count"]),
                "mean_absolute_error_bps": row["mean_absolute_error_bps"],
                "p95_absolute_error_bps": row["p95_absolute_error_bps"],
                "maximum_absolute_error_bps": row["maximum_absolute_error_bps"],
            }
            for index, row in enumerate(ordered, start=1)
        ]

    italy = [
        row
        for row in economy_metrics
        if row["split"] == "HOLDOUT" and row["economy_code"] == "ITA"
    ]
    portugal = [
        row
        for row in economy_metrics
        if row["split"] == "HOLDOUT" and row["economy_code"] == "PRT"
    ]
    cp04 = [
        row
        for row in category_metrics
        if row["split"] == "HOLDOUT" and row["source_category"] == "CP04"
    ]
    twelve_month = [
        row
        for row in model_metrics
        if row["split"] == "HOLDOUT" and row["horizon_months"] == 12
    ]
    return {
        "italy_holdout": rank(italy),
        "portugal_holdout": rank(portugal),
        "cp04_holdout": rank(cp04),
        "twelve_month_holdout": rank(twelve_month),
        "model_promotion_allowed": False,
    }


def build_pre_release_backtest(
    policy_path: Path | str,
    first_published_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = PreReleasePolicy.load(policy_path)
    panel = load_first_published_panel(policy, first_published_dir)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise PreReleaseBacktestError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)

    global_cases: list[GlobalForecastCase] = []
    economy_cases: list[EconomyForecastCase] = []
    cell_cases: list[CellForecastCase] = []

    for origin, target, horizon in _forecast_pairs(policy, panel):
        split = policy.split_for(target)
        truth_global = _truth_global(panel, target)
        for model in MODELS:
            forecast = _global_forecast(panel, policy, model, origin, target)
            _assert_no_lookahead(origin, target, forecast.source_periods)
            case_id = f"{origin}|{target}|H{horizon:02d}"
            global_cases.append(
                GlobalForecastCase(
                    case_id=case_id,
                    split=split,
                    model=model,
                    origin_period=origin,
                    target_period=target,
                    horizon_months=horizon,
                    as_of_date=panel.release_dates[origin],
                    target_release_date=panel.release_dates[target],
                    truth_index=truth_global,
                    forecast_index=forecast.value,
                    index_error=forecast.value - truth_global,
                    absolute_error_bps=_absolute_bps(forecast.value, truth_global),
                    source_periods=forecast.source_periods,
                    evidence_class=forecast.evidence_class,
                )
            )

        for economy in REQUIRED_ECONOMIES:
            truth_economy = _truth_economy(panel, economy, target)
            for model in ECONOMY_MODELS:
                forecast_value = _economy_forecast(
                    panel, policy, model, economy, origin, target
                )
                economy_cases.append(
                    EconomyForecastCase(
                        case_id=f"{economy}|{origin}|{target}|H{horizon:02d}",
                        split=split,
                        model=model,
                        economy_code=economy,
                        origin_period=origin,
                        target_period=target,
                        horizon_months=horizon,
                        truth_index=truth_economy,
                        forecast_index=forecast_value,
                        absolute_error_bps=_absolute_bps(forecast_value, truth_economy),
                    )
                )

        for economy in REQUIRED_ECONOMIES:
            for category in PRICE_CATEGORIES:
                truth_value = panel.values[(economy, category, target)]
                for model in CATEGORY_MODELS:
                    forecast = _cell_forecast(
                        panel, policy, model, economy, category, origin, target
                    )
                    cell_cases.append(
                        CellForecastCase(
                            case_id=f"{economy}|{category}|{origin}|{target}|H{horizon:02d}",
                            split=split,
                            model=model,
                            economy_code=economy,
                            source_category=category,
                            origin_period=origin,
                            target_period=target,
                            horizon_months=horizon,
                            truth_value=truth_value,
                            forecast_value=forecast.value,
                            absolute_error_bps=_absolute_bps(forecast.value, truth_value),
                        )
                    )

    expected_global_per_model = len(tuple(_iter_periods(
        policy.evaluation_target_start, policy.evaluation_target_end
    ))) * len(policy.horizons)
    for model in MODELS:
        if sum(case.model == model for case in global_cases) != expected_global_per_model:
            raise PreReleaseBacktestError("GLOBAL_SAMPLE_MISMATCH", model)
    common_case_ids = _assert_common_global_sample(global_cases)

    global_rows = [
        {
            "case_id": case.case_id,
            "temporal_split": case.split,
            "model": case.model,
            "origin_period": case.origin_period,
            "as_of_date": case.as_of_date,
            "target_period": case.target_period,
            "target_release_date": case.target_release_date,
            "horizon_months": case.horizon_months,
            "truth_index": _text(case.truth_index, 12),
            "forecast_index": _text(case.forecast_index, 12),
            "index_error": _text(case.index_error, 12),
            "absolute_error_bps": _text(case.absolute_error_bps, 10),
            "forecast_mode": FORECAST_MODE,
            "truth_definition": TRUTH_DEFINITION,
            "as_of_definition": AS_OF_DEFINITION,
            "source_periods": ";".join(case.source_periods),
            "maximum_source_period": max(case.source_periods),
            "target_period_values_used_for_prediction": "false",
            "target_period_donors_used": "false",
            "target_release_date_used_for_prediction": "false",
            "historical_revision_state": HISTORICAL_REVISION_STATE,
            "evidence_class": case.evidence_class,
        }
        for case in sorted(global_cases, key=lambda item: (item.case_id, item.model))
    ]
    _write_csv(output / "forecast_cases.csv", list(global_rows[0]), global_rows)

    economy_rows = [
        {
            "case_id": case.case_id,
            "temporal_split": case.split,
            "model": case.model,
            "economy_code": case.economy_code,
            "origin_period": case.origin_period,
            "target_period": case.target_period,
            "horizon_months": case.horizon_months,
            "truth_index": _text(case.truth_index, 12),
            "forecast_index": _text(case.forecast_index, 12),
            "absolute_error_bps": _text(case.absolute_error_bps, 10),
        }
        for case in sorted(
            economy_cases,
            key=lambda item: (item.case_id, item.model),
        )
    ]
    _write_csv(output / "economy_forecast_cases.csv", list(economy_rows[0]), economy_rows)

    cell_rows = [
        {
            "case_id": case.case_id,
            "temporal_split": case.split,
            "model": case.model,
            "economy_code": case.economy_code,
            "source_category": case.source_category,
            "origin_period": case.origin_period,
            "target_period": case.target_period,
            "horizon_months": case.horizon_months,
            "truth_value": _text(case.truth_value, 12),
            "forecast_value": _text(case.forecast_value, 12),
            "absolute_error_bps": _text(case.absolute_error_bps, 10),
        }
        for case in sorted(cell_cases, key=lambda item: (item.case_id, item.model))
    ]
    _write_csv(output / "cell_forecast_cases.csv", list(cell_rows[0]), cell_rows)

    model_metrics = _global_metrics_rows(global_cases)
    economy_metrics = _economy_metrics_rows(economy_cases)
    category_metrics = _category_metrics_rows(cell_cases)
    _write_csv(output / "model_metrics.csv", list(model_metrics[0]), model_metrics)
    _write_csv(output / "error_by_economy.csv", list(economy_metrics[0]), economy_metrics)
    _write_csv(output / "error_by_category.csv", list(category_metrics[0]), category_metrics)
    paired_metrics = _paired_global_metrics_rows(global_cases)
    _write_csv(
        output / "paired_model_comparisons.csv",
        list(paired_metrics[0]),
        paired_metrics,
    )
    ranking_stability = _ranking_stability_payload(global_cases)
    _atomic_write(
        output / "ranking_stability.json",
        _canonical_json(_serialise(ranking_stability)),
    )
    focus_diagnostics = _focus_diagnostics_payload(
        model_metrics, economy_metrics, category_metrics
    )
    _atomic_write(
        output / "focus_diagnostics.json",
        _canonical_json(_serialise(focus_diagnostics)),
    )

    holdout_by_model: MutableMapping[str, list[Decimal]] = defaultdict(list)
    for case in global_cases:
        if case.split == "HOLDOUT":
            holdout_by_model[case.model].append(case.absolute_error_bps)
    ranking = sorted(
        (
            {
                "model": model,
                **_aggregate_errors(holdout_by_model[model]),
            }
            for model in MODELS
        ),
        key=lambda item: (item["mean_absolute_error_bps"], item["model"]),
    )
    holdout_payload = {
        "holdout_target_start": policy.holdout_target_start,
        "holdout_target_end": policy.holdout_target_end,
        "holdout_data_used_for_model_selection": False,
        "model_ranking": ranking,
        "p4_vs_p1": _comparison(holdout_by_model[P4], holdout_by_model[P1]),
        "p4_vs_p2": _comparison(holdout_by_model[P4], holdout_by_model[P2]),
        "p4_vs_p3": _comparison(holdout_by_model[P4], holdout_by_model[P3]),
        "model_promotion_allowed": False,
    }
    _atomic_write(
        output / "holdout_evaluation.json", _canonical_json(_serialise(holdout_payload))
    )

    summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "status": "PRE_RELEASE_FORECAST_BACKTEST_COMPLETED_WITH_INITIAL_RELEASE_HISTORY_LIMITATION",
        "forecast_mode": FORECAST_MODE,
        "truth_definition": TRUTH_DEFINITION,
        "as_of_definition": AS_OF_DEFINITION,
        "universe_id": policy.universe_id,
        "history_start": policy.history_start,
        "history_end": policy.history_end,
        "evaluation_target_start": policy.evaluation_target_start,
        "evaluation_target_end": policy.evaluation_target_end,
        "global_case_count_per_model": expected_global_per_model,
        "common_global_case_id_count": len(common_case_ids),
        "common_global_sample_verified": True,
        "global_case_row_count": len(global_cases),
        "economy_case_row_count": len(economy_cases),
        "cell_case_row_count": len(cell_cases),
        "model_count": len(MODELS),
        "paired_comparison_count": len(PAIRWISE_COMPARISONS),
        "paired_comparison_row_count": len(paired_metrics),
        "development_holdout_ranking_changed": ranking_stability["ranking_changed"],
        "development_holdout_winner_changed": ranking_stability["winner_changed"],
        "pre_release_forecast": True,
        "pre_release_forecast_comparison_allowed": True,
        "target_period_values_used_for_prediction": False,
        "target_period_donors_used": False,
        "future_period_source_values_used": False,
        "target_release_date_used_for_prediction": False,
        "truth_uses_first_published_values": True,
        "historical_inputs_use_first_published_values": True,
        "historical_as_of_revisions_available": False,
        "historical_revision_limitation": "INPUT_HISTORY_USES_INITIAL_RELEASES_NOT_FULL_AS_OF_REVISION_VINTAGES",
        "development_data_used_for_model_selection": False,
        "holdout_data_used_for_model_selection": False,
        "first_published_input_manifest_sha256": panel.input_manifest_sha256,
        "first_published_snapshot_manifest_sha256": panel.input_summary.get(
            "snapshot_manifest_sha256"
        ),
        "rejected_v089_experiment_reused": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "run_summary.json", _canonical_json(summary))

    all_metrics = {
        row["model"]: row
        for row in model_metrics
        if row["split"] == "ALL" and row["horizon_months"] == "ALL"
    }
    holdout_metrics = {
        row["model"]: row
        for row in model_metrics
        if row["split"] == "HOLDOUT" and row["horizon_months"] == "ALL"
    }
    italy_rows = [
        row
        for row in economy_metrics
        if row["split"] == "HOLDOUT" and row["economy_code"] == "ITA"
    ]
    cp04_rows = [
        row
        for row in category_metrics
        if row["split"] == "HOLDOUT" and row["source_category"] == "CP04"
    ]
    holdout_pair_rows = [
        row
        for row in paired_metrics
        if row["split"] == "HOLDOUT" and row["horizon_months"] == "ALL"
    ]
    report_lines = [
        "# Armilar v0.9.4 pre-publication forecast backtest",
        "",
        "## Interpretation",
        "",
        "Every forecast is generated as of the official full-data release date of the origin month. No target-month value or target-month donor is used.",
        "",
        "Historical inputs use values as first published. Later revisions that may have been known at each origin are not reconstructed, so this is a target-leakage-free pre-publication test with an explicit historical-vintage limitation.",
        "",
        "## Global results",
        "",
        "| Model | All mean (bps) | All p95 (bps) | Holdout bias (bps) | Holdout mean (bps) | Holdout p95 (bps) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        report_lines.append(
            f"| {model} | {all_metrics[model]['mean_absolute_error_bps']} | "
            f"{all_metrics[model]['p95_absolute_error_bps']} | "
            f"{holdout_metrics[model]['mean_signed_error_bps']} | "
            f"{holdout_metrics[model]['mean_absolute_error_bps']} | "
            f"{holdout_metrics[model]['p95_absolute_error_bps']} |"
        )
    report_lines.extend(
        [
            "",
            "## Ranking stability",
            "",
            f"Development ranking: {', '.join(ranking_stability['development_ranking'])}",
            "",
            f"Holdout ranking: {', '.join(ranking_stability['holdout_ranking'])}",
            "",
            f"Ranking changed: {str(ranking_stability['ranking_changed']).lower()}",
            "",
            f"Winner changed: {str(ranking_stability['winner_changed']).lower()}",
            "",
            "## Holdout paired comparisons",
            "",
            "Negative mean deltas indicate that the challenger reduced absolute error.",
            "",
            "| Challenger | Baseline | Mean delta (bps) | Improvement rate | Regression rate | Worst regression (bps) |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in holdout_pair_rows:
        report_lines.append(
            f"| {row['challenger']} | {row['baseline']} | "
            f"{row['mean_delta_absolute_bps']} | {row['improvement_rate']} | "
            f"{row['regression_rate']} | {row['worst_regression_bps']} |"
        )
    report_lines.extend(
        [
            "",
            "## Focus diagnostics",
            "",
            "### Italy, holdout",
            "",
            "| Model | Mean (bps) | p95 (bps) |",
            "|---|---:|---:|",
        ]
    )
    for row in italy_rows:
        report_lines.append(
            f"| {row['model']} | {row['mean_absolute_error_bps']} | {row['p95_absolute_error_bps']} |"
        )
    report_lines.extend(
        [
            "",
            "### CP04, holdout",
            "",
            "| Model | Mean (bps) | p95 (bps) |",
            "|---|---:|---:|",
        ]
    )
    for row in cp04_rows:
        report_lines.append(
            f"| {row['model']} | {row['mean_absolute_error_bps']} | {row['p95_absolute_error_bps']} |"
        )
    report_lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "The backtest authorises comparison of these pre-publication baselines. It does not authorise model promotion, research release or monetary use.",
            "",
            "`pre_release_forecast_comparison_allowed=true`",
            "",
            "`model_promotion_allowed=false`",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
        ]
    )
    _atomic_write(
        output / "PRE_RELEASE_BACKTEST_REPORT.md",
        ("\n".join(report_lines) + "\n").encode("utf-8"),
    )
    _write_manifest(output)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Armilar v0.9.4 target-leakage-free pre-publication forecast backtest"
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
        result = build_pre_release_backtest(
            args.policy, args.first_published_dir, args.output_dir
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
