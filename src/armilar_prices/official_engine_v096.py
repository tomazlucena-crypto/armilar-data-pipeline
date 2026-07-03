"""ARMILAR v0.9.6 deterministic official engine and temporal ledger.

This module implements the ratified Research Core development contract only.
It does not open any research, model-promotion, shadow-production or monetary gate.
All economic arithmetic uses :class:`decimal.Decimal` with precision 28 and
ROUND_HALF_EVEN. Input vintages are selected strictly by publication cutoff.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

DECIMAL_PRECISION = 28
DECIMAL_ROUNDING = ROUND_HALF_EVEN
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
WEIGHT_TOLERANCE = Decimal("1e-24")
CONTRIBUTION_TOLERANCE = Decimal("1e-20")
INDEX_DECIMAL_PLACES = 12
PRICE_RELATIVE_DECIMAL_PLACES = 12
CONTRIBUTION_DECIMAL_PLACES = 12
PERCENTAGE_DECIMAL_PLACES = 8
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")
CANONICAL_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
CATEGORY_FORMULA = "ARITHMETIC_LASPEYRES_FIXED_REAL_HFCE_PPP_WEIGHTS"
HEADLINE_FORMULA = "ARITHMETIC_HEADLINE_CP00_WITH_DERIVED_ECONOMY_WEIGHTS"
PROHIBITED_PRICE_EVIDENCE_TOKENS = (
    "PROXY", "IMPUT", "MODEL", "FORECAST", "NOWCAST", "CARRY_FORWARD", "SYNTHETIC"
)


class OfficialEngineError(RuntimeError):
    """Raised when a run would violate the ratified engine contract."""


class SeriesKind(StrEnum):
    ARM_O = "ARM-O"
    ARM_R = "ARM-R"
    ARM_H = "ARM-H"


class RunStatus(StrEnum):
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise OfficialEngineError(f"{field} must be an exact decimal string, integer or Decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OfficialEngineError(f"invalid decimal for {field}: {value!r}") from exc
    if not result.is_finite():
        raise OfficialEngineError(f"{field} must be finite")
    return result


def _quantize(value: Decimal, decimal_places: int) -> Decimal:
    quantum = Decimal(1).scaleb(-decimal_places)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ctx.rounding = DECIMAL_ROUNDING
        return value.quantize(quantum)


def _fixed_decimal_text(value: Decimal, decimal_places: int) -> str:
    return format(_quantize(value, decimal_places), f".{decimal_places}f")


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _validate_month(value: str, field: str = "period") -> str:
    if not MONTH_RE.fullmatch(value):
        raise OfficialEngineError(f"invalid {field}: {value!r}")
    return value


def _parse_utc(value: str, field: str) -> datetime:
    if not UTC_RE.fullmatch(value):
        raise OfficialEngineError(f"{field} must be an explicit UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OfficialEngineError(f"invalid {field}: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise OfficialEngineError(f"{field} must be UTC")
    return parsed


def _month_range(start: str, end: str) -> tuple[str, ...]:
    _validate_month(start, "start_period")
    _validate_month(end, "end_period")
    sy, sm = (int(part) for part in start.split("-"))
    ey, em = (int(part) for part in end.split("-"))
    if (sy, sm) > (ey, em):
        raise OfficialEngineError("start_period must not be after end_period")
    result: list[str] = []
    year, month = sy, sm
    while (year, month) <= (ey, em):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(result)


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise OfficialEngineError(f"path escapes root: {relative!r}")
    return candidate


@dataclass(frozen=True, slots=True)
class EnginePolicy:
    policy_id: str
    policy_version: str
    constitution_id: str
    constitution_version: str
    constitution_sha256: str
    ratification_record_sha256: str
    reference_year: int
    reference_average: Decimal
    categories: tuple[str, ...]
    start_period: str
    end_period: str
    precision: int
    rounding: str
    fixed_weight_column: str
    research_release_allowed: bool
    model_promotion_allowed: bool
    shadow_production_allowed: bool
    monetary_release_allowed: bool
    world_claim_allowed: bool
    ooh_sensitivity_required: bool

    @classmethod
    def load(cls, path: Path) -> "EnginePolicy":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OfficialEngineError(f"cannot load engine policy: {path}") from exc
        required = {
            "policy_id",
            "policy_version",
            "constitution_id",
            "constitution_version",
            "constitution_sha256",
            "ratification_record_sha256",
            "reference_year",
            "reference_average",
            "categories",
            "start_period",
            "end_period",
            "precision",
            "rounding",
            "fixed_weight_column",
            "release_gates",
            "ooh_sensitivity_required",
        }
        if set(payload) != required:
            missing = sorted(required - set(payload))
            extra = sorted(set(payload) - required)
            raise OfficialEngineError(f"policy keys mismatch; missing={missing}, extra={extra}")
        gates = payload["release_gates"]
        gate_keys = {
            "research_release_allowed",
            "model_promotion_allowed",
            "shadow_production_allowed",
            "monetary_release_allowed",
            "world_claim_allowed",
        }
        if not isinstance(gates, dict) or set(gates) != gate_keys:
            raise OfficialEngineError("release_gates must contain the closed canonical gate set")
        categories = tuple(payload["categories"])
        if categories != CANONICAL_CATEGORIES:
            raise OfficialEngineError("policy categories must be exactly CP01-CP12 in canonical order")
        if any(bool(gates[key]) for key in gate_keys):
            raise OfficialEngineError("all v0.9.6 release gates must remain false")
        if payload["constitution_version"] != "1.0.0-research":
            raise OfficialEngineError("v0.9.6 requires the ratified 1.0.0-research constitution")
        for field in ("constitution_sha256", "ratification_record_sha256"):
            if not SHA256_RE.fullmatch(str(payload[field])):
                raise OfficialEngineError(f"invalid {field}")
        if int(payload["reference_year"]) != 2021:
            raise OfficialEngineError("reference_year must remain 2021")
        reference_average = _decimal(payload["reference_average"], "reference_average")
        if reference_average != HUNDRED:
            raise OfficialEngineError("reference_average must be exactly 100")
        if int(payload["precision"]) != DECIMAL_PRECISION:
            raise OfficialEngineError("precision must be 28")
        if payload["rounding"] != "ROUND_HALF_EVEN":
            raise OfficialEngineError("rounding must be ROUND_HALF_EVEN")
        periods = _month_range(payload["start_period"], payload["end_period"])
        if not all(period.startswith("2021-") for period in periods[:12]):
            raise OfficialEngineError("declared interval must include the full 2021 base year")
        if not bool(payload["ooh_sensitivity_required"]):
            raise OfficialEngineError("OOH sensitivity must remain required")
        return cls(
            policy_id=str(payload["policy_id"]),
            policy_version=str(payload["policy_version"]),
            constitution_id=str(payload["constitution_id"]),
            constitution_version=str(payload["constitution_version"]),
            constitution_sha256=str(payload["constitution_sha256"]),
            ratification_record_sha256=str(payload["ratification_record_sha256"]),
            reference_year=2021,
            reference_average=reference_average,
            categories=categories,
            start_period=str(payload["start_period"]),
            end_period=str(payload["end_period"]),
            precision=DECIMAL_PRECISION,
            rounding="ROUND_HALF_EVEN",
            fixed_weight_column=str(payload["fixed_weight_column"]),
            research_release_allowed=False,
            model_promotion_allowed=False,
            shadow_production_allowed=False,
            monetary_release_allowed=False,
            world_claim_allowed=False,
            ooh_sensitivity_required=True,
        )

    @property
    def periods(self) -> tuple[str, ...]:
        return _month_range(self.start_period, self.end_period)


@dataclass(frozen=True, slots=True)
class WeightCell:
    economy_code: str
    category_code: str
    weight: Decimal
    evidence_class: str
    source_id: str

    def validate(self, categories: Sequence[str]) -> None:
        if len(self.economy_code) != 3 or self.economy_code.upper() != self.economy_code:
            raise OfficialEngineError(f"invalid economy_code: {self.economy_code!r}")
        if self.category_code not in categories:
            raise OfficialEngineError(f"invalid category_code: {self.category_code!r}")
        if self.weight <= ZERO:
            raise OfficialEngineError("fixed weights must be positive")
        if not self.evidence_class or not self.source_id:
            raise OfficialEngineError("weight evidence_class and source_id are required")


@dataclass(frozen=True, slots=True)
class PriceVintageObservation:
    series_id: str
    economy_code: str
    category_code: str
    period: str
    value: Decimal
    published_at: str
    retrieved_at: str
    vintage_id: str
    revision_sequence: int
    raw_snapshot_id: str
    source_sha256: str
    evidence_class: str

    def validate(self, categories: Sequence[str], *, headline: bool = False) -> None:
        if not self.series_id or not self.vintage_id or not self.evidence_class or not self.raw_snapshot_id:
            raise OfficialEngineError(
                "series_id, vintage_id, raw_snapshot_id and evidence_class are required"
            )
        if len(self.economy_code) != 3 or self.economy_code.upper() != self.economy_code:
            raise OfficialEngineError(f"invalid economy_code: {self.economy_code!r}")
        expected = "CP00" if headline else None
        if headline and self.category_code != expected:
            raise OfficialEngineError("headline observations must use CP00")
        if not headline and self.category_code not in categories:
            raise OfficialEngineError(f"invalid category_code: {self.category_code!r}")
        _validate_month(self.period)
        _parse_utc(self.published_at, "published_at")
        _parse_utc(self.retrieved_at, "retrieved_at")
        if self.value <= ZERO:
            raise OfficialEngineError("price indices must be positive")
        if self.revision_sequence < 0:
            raise OfficialEngineError("revision_sequence must be non-negative")
        if not SHA256_RE.fullmatch(self.source_sha256):
            raise OfficialEngineError("source_sha256 must be lowercase SHA-256")
        evidence = self.evidence_class.upper()
        if any(token in evidence for token in PROHIBITED_PRICE_EVIDENCE_TOKENS):
            raise OfficialEngineError(
                f"official series cannot use proxy or model evidence: {self.evidence_class!r}"
            )


@dataclass(frozen=True, slots=True)
class BuildRequest:
    run_id: str
    series_kind: SeriesKind
    vintage_id: str
    cutoff_at: str
    created_at: str

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", self.run_id):
            raise OfficialEngineError("invalid run_id")
        if not self.vintage_id:
            raise OfficialEngineError("vintage_id is required")
        _parse_utc(self.cutoff_at, "cutoff_at")
        _parse_utc(self.created_at, "created_at")
        if _parse_utc(self.created_at, "created_at") < _parse_utc(self.cutoff_at, "cutoff_at"):
            raise OfficialEngineError("created_at cannot precede cutoff_at")


def load_weights(path: Path, policy: EnginePolicy) -> list[WeightCell]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise OfficialEngineError("weight input is empty")
    required = {"economy_code", "category_code", policy.fixed_weight_column}
    if not required.issubset(rows[0]):
        raise OfficialEngineError(f"weight input missing columns: {sorted(required - set(rows[0]))}")
    result: list[WeightCell] = []
    seen: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):
        cell = WeightCell(
            economy_code=str(row["economy_code"]).strip().upper(),
            category_code=str(row["category_code"]).strip().upper(),
            weight=_decimal(row[policy.fixed_weight_column], f"weight line {line}"),
            evidence_class=str(row.get("weight_evidence_class") or row.get("evidence_class") or row.get("quality_flags") or "UNDISCLOSED").strip(),
            source_id=str(row.get("source_id") or row.get("numerator_source_id") or "UNDISCLOSED").strip(),
        )
        cell.validate(policy.categories)
        key = (cell.economy_code, cell.category_code)
        if key in seen:
            raise OfficialEngineError(f"duplicate weight cell: {key}")
        seen.add(key)
        result.append(cell)
    economies = sorted({row.economy_code for row in result})
    expected = {(economy, category) for economy in economies for category in policy.categories}
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise OfficialEngineError(f"weight grid incomplete; missing={missing[:10]}, extra={extra[:10]}")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ctx.rounding = DECIMAL_ROUNDING
        total = sum((row.weight for row in result), ZERO)
    if abs(total - ONE) > WEIGHT_TOLERANCE:
        raise OfficialEngineError(f"fixed weights must sum exactly to 1 within tolerance, got {_decimal_text(total)}")
    return sorted(result, key=lambda row: (row.economy_code, row.category_code))


def load_observations(path: Path, policy: EnginePolicy, *, headline: bool = False) -> list[PriceVintageObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise OfficialEngineError(f"observation input is empty: {path}")
    required = {
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
    }
    if not required.issubset(rows[0]):
        raise OfficialEngineError(f"observation input missing columns: {sorted(required - set(rows[0]))}")
    result: list[PriceVintageObservation] = []
    seen: set[tuple[str, str, str, str, int]] = set()
    for line, row in enumerate(rows, start=2):
        try:
            sequence = int(row["revision_sequence"])
        except (TypeError, ValueError) as exc:
            raise OfficialEngineError(f"invalid revision_sequence at line {line}") from exc
        item = PriceVintageObservation(
            series_id=str(row["series_id"]).strip(),
            economy_code=str(row["economy_code"]).strip().upper(),
            category_code=str(row["category_code"]).strip().upper(),
            period=str(row["period"]).strip(),
            value=_decimal(row["value"], f"value line {line}"),
            published_at=str(row["published_at"]).strip(),
            retrieved_at=str(row["retrieved_at"]).strip(),
            vintage_id=str(row["vintage_id"]).strip(),
            revision_sequence=sequence,
            raw_snapshot_id=str(row["raw_snapshot_id"]).strip(),
            source_sha256=str(row["source_sha256"]).strip(),
            evidence_class=str(row["evidence_class"]).strip(),
        )
        item.validate(policy.categories, headline=headline)
        key = (
            item.economy_code,
            item.category_code,
            item.period,
            item.published_at,
            item.retrieved_at,
            item.revision_sequence,
            item.raw_snapshot_id,
        )
        if key in seen:
            raise OfficialEngineError(f"duplicate observation vintage at line {line}")
        seen.add(key)
        result.append(item)
    return sorted(
        result,
        key=lambda row: (
            row.economy_code,
            row.category_code,
            row.period,
            _parse_utc(row.published_at, "published_at"),
            row.revision_sequence,
            _parse_utc(row.retrieved_at, "retrieved_at"),
            row.raw_snapshot_id,
            row.series_id,
        ),
    )


def select_as_of(
    observations: Iterable[PriceVintageObservation],
    cutoff_at: str,
    series_kind: SeriesKind,
) -> list[PriceVintageObservation]:
    """Select the constitutionally permitted vintage for each cell-period.

    ARM-O and ARM-H preserve the earliest official publication that is visible
    by the information cutoff. ARM-R selects the latest official revision that
    is visible by the cutoff. A later cutoff therefore never mutates ARM-O.
    """
    cutoff = _parse_utc(cutoff_at, "cutoff_at")
    candidates: dict[tuple[str, str, str], list[PriceVintageObservation]] = defaultdict(list)
    for row in observations:
        published = _parse_utc(row.published_at, "published_at")
        retrieved = _parse_utc(row.retrieved_at, "retrieved_at")
        if published <= cutoff and retrieved <= cutoff:
            candidates[(row.economy_code, row.category_code, row.period)].append(row)
    selected: list[PriceVintageObservation] = []
    for key, rows in sorted(candidates.items()):
        rows.sort(
            key=lambda row: (
                _parse_utc(row.published_at, "published_at"),
                row.revision_sequence,
                _parse_utc(row.retrieved_at, "retrieved_at"),
                row.vintage_id,
                row.raw_snapshot_id,
                row.series_id,
            )
        )
        selected.append(rows[-1] if series_kind is SeriesKind.ARM_R else rows[0])
    return selected


def _normalise_panel(
    selected: Iterable[PriceVintageObservation],
    policy: EnginePolicy,
    expected_cells: set[tuple[str, str]],
) -> tuple[list[dict[str, str]], dict[tuple[str, str, str], Decimal]]:
    by_cell: dict[tuple[str, str], dict[str, PriceVintageObservation]] = defaultdict(dict)
    for row in selected:
        if row.period not in policy.periods:
            continue
        key = (row.economy_code, row.category_code)
        if row.period in by_cell[key]:
            raise OfficialEngineError(f"duplicate selected period for {key} {row.period}")
        by_cell[key][row.period] = row
    if set(by_cell) != expected_cells:
        missing_cells = sorted(expected_cells - set(by_cell))
        extra_cells = sorted(set(by_cell) - expected_cells)
        raise OfficialEngineError(
            f"selected panel cell universe mismatch; missing={missing_cells[:10]}, extra={extra_cells[:10]}"
        )
    base_periods = tuple(f"{policy.reference_year}-{month:02d}" for month in range(1, 13))
    normalised_rows: list[dict[str, str]] = []
    relative_by_key: dict[tuple[str, str, str], Decimal] = {}
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ctx.rounding = DECIMAL_ROUNDING
        for cell in sorted(expected_cells):
            periods = by_cell[cell]
            missing = [period for period in policy.periods if period not in periods]
            if missing:
                raise OfficialEngineError(f"incomplete selected panel for {cell}; missing={missing[:12]}")
            base_missing = [period for period in base_periods if period not in periods]
            if base_missing:
                raise OfficialEngineError(f"base year incomplete for {cell}; missing={base_missing}")
            base_average = sum((periods[period].value for period in base_periods), ZERO) / Decimal(12)
            if base_average <= ZERO:
                raise OfficialEngineError(f"non-positive base average for {cell}")
            check = ZERO
            for period in policy.periods:
                source = periods[period]
                relative = source.value / base_average * policy.reference_average
                relative_by_key[(cell[0], cell[1], period)] = relative
                if period in base_periods:
                    check += relative
                normalised_rows.append(
                    {
                        "economy_code": cell[0],
                        "category_code": cell[1],
                        "period": period,
                        "source_value": _decimal_text(source.value),
                        "base_year_average": _decimal_text(base_average),
                        "price_relative": _fixed_decimal_text(relative, PRICE_RELATIVE_DECIMAL_PLACES),
                        "price_relative_unrounded": _decimal_text(relative),
                        "series_id": source.series_id,
                        "source_vintage_id": source.vintage_id,
                        "published_at": source.published_at,
                        "retrieved_at": source.retrieved_at,
                        "revision_sequence": str(source.revision_sequence),
                        "raw_snapshot_id": source.raw_snapshot_id,
                        "source_sha256": source.source_sha256,
                        "evidence_class": source.evidence_class,
                    }
                )
            annual_average = check / Decimal(12)
            if abs(annual_average - policy.reference_average) > WEIGHT_TOLERANCE:
                raise OfficialEngineError(
                    f"base-year normalisation is not exact for {cell}: {_decimal_text(annual_average)}"
                )
    return normalised_rows, relative_by_key


def _formula_for(series_kind: SeriesKind) -> str:
    return HEADLINE_FORMULA if series_kind is SeriesKind.ARM_H else CATEGORY_FORMULA


def _aggregate_index(
    weights: Sequence[WeightCell],
    relative_by_key: Mapping[tuple[str, str, str], Decimal],
    policy: EnginePolicy,
    series_kind: SeriesKind,
    run_id: str,
    vintage_id: str,
    cutoff_at: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    index_rows: list[dict[str, str]] = []
    cell_rows: list[dict[str, str]] = []
    economy_rows: list[dict[str, str]] = []
    category_rows: list[dict[str, str]] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ctx.rounding = DECIMAL_ROUNDING
        for period in policy.periods:
            total = ZERO
            economy_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
            category_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
            period_cells: list[dict[str, str]] = []
            for weight in weights:
                key = (weight.economy_code, weight.category_code, period)
                relative = relative_by_key.get(key)
                if relative is None:
                    raise OfficialEngineError(f"missing normalised price for {key}")
                contribution = weight.weight * relative
                total += contribution
                economy_totals[weight.economy_code] += contribution
                category_totals[weight.category_code] += contribution
                period_cells.append(
                    {
                        "run_id": run_id,
                        "series_kind": series_kind.value,
                        "vintage_id": vintage_id,
                        "cutoff_at": cutoff_at,
                        "period": period,
                        "economy_code": weight.economy_code,
                        "category_code": weight.category_code,
                        "fixed_universe_weight": _decimal_text(weight.weight),
                        "price_relative": _fixed_decimal_text(relative, PRICE_RELATIVE_DECIMAL_PLACES),
                        "price_relative_unrounded": _decimal_text(relative),
                        "index_level_contribution": _fixed_decimal_text(
                            contribution, CONTRIBUTION_DECIMAL_PLACES
                        ),
                        "index_level_contribution_unrounded": _decimal_text(contribution),
                        "contribution_since_base": _fixed_decimal_text(
                            weight.weight * (relative - HUNDRED), CONTRIBUTION_DECIMAL_PLACES
                        ),
                        "contribution_since_base_unrounded": _decimal_text(
                            weight.weight * (relative - HUNDRED)
                        ),
                        "weight_evidence_class": weight.evidence_class,
                        "weight_source_id": weight.source_id,
                    }
                )
            if abs(sum(economy_totals.values(), ZERO) - total) > CONTRIBUTION_TOLERANCE:
                raise OfficialEngineError("economy contributions do not sum to the index")
            if abs(sum(category_totals.values(), ZERO) - total) > CONTRIBUTION_TOLERANCE:
                raise OfficialEngineError("category contributions do not sum to the index")
            canonical_total = _quantize(total, INDEX_DECIMAL_PLACES)
            canonical_cell_sum = sum(
                (_quantize(_decimal(row["index_level_contribution_unrounded"], "cell contribution"), CONTRIBUTION_DECIMAL_PLACES) for row in period_cells),
                ZERO,
            )
            canonical_economy_sum = sum(
                (_quantize(value, CONTRIBUTION_DECIMAL_PLACES) for value in economy_totals.values()), ZERO
            )
            canonical_category_sum = sum(
                (_quantize(value, CONTRIBUTION_DECIMAL_PLACES) for value in category_totals.values()), ZERO
            )
            index_rows.append(
                {
                    "run_id": run_id,
                    "series_kind": series_kind.value,
                    "vintage_id": vintage_id,
                    "cutoff_at": cutoff_at,
                    "period": period,
                    "index_value": _fixed_decimal_text(total, INDEX_DECIMAL_PLACES),
                    "index_value_unrounded": _decimal_text(total),
                    "index_quantization_residual": _decimal_text(total - canonical_total),
                    "cell_contribution_rounding_residual": _fixed_decimal_text(
                        canonical_total - canonical_cell_sum, CONTRIBUTION_DECIMAL_PLACES
                    ),
                    "economy_contribution_rounding_residual": _fixed_decimal_text(
                        canonical_total - canonical_economy_sum, CONTRIBUTION_DECIMAL_PLACES
                    ),
                    "category_contribution_rounding_residual": _fixed_decimal_text(
                        canonical_total - canonical_category_sum, CONTRIBUTION_DECIMAL_PLACES
                    ),
                    "status": RunStatus.COMPLETE.value,
                    "reference_year": str(policy.reference_year),
                    "reference_average": _decimal_text(policy.reference_average),
                    "formula": _formula_for(series_kind),
                    "precision": str(policy.precision),
                    "rounding": policy.rounding,
                    "fx_treatment": "EXCLUDED_FROM_PRIMARY_INDEX",
                    "research_release_allowed": "false",
                    "model_promotion_allowed": "false",
                    "shadow_production_allowed": "false",
                    "monetary_release_allowed": "false",
                    "world_claim_allowed": "false",
                }
            )
            cell_rows.extend(period_cells)
            for economy, value in sorted(economy_totals.items()):
                economy_rows.append(
                    {
                        "run_id": run_id,
                        "series_kind": series_kind.value,
                        "period": period,
                        "economy_code": economy,
                        "index_level_contribution": _fixed_decimal_text(
                            value, CONTRIBUTION_DECIMAL_PLACES
                        ),
                        "index_level_contribution_unrounded": _decimal_text(value),
                    }
                )
            for category, value in sorted(category_totals.items()):
                category_rows.append(
                    {
                        "run_id": run_id,
                        "series_kind": series_kind.value,
                        "period": period,
                        "category_code": category,
                        "index_level_contribution": _fixed_decimal_text(
                            value, CONTRIBUTION_DECIMAL_PLACES
                        ),
                        "index_level_contribution_unrounded": _decimal_text(value),
                    }
                )
    base_values = [
        _decimal(row["index_value_unrounded"], "index_value_unrounded")
        for row in index_rows
        if row["period"].startswith(f"{policy.reference_year}-")
    ]
    if len(base_values) != 12:
        raise OfficialEngineError("index output lacks the twelve base-year months")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ctx.rounding = DECIMAL_ROUNDING
        average = sum(base_values, ZERO) / Decimal(12)
    if abs(average - policy.reference_average) > WEIGHT_TOLERANCE:
        raise OfficialEngineError(f"aggregate base-year average is not exactly 100: {_decimal_text(average)}")
    return index_rows, cell_rows, economy_rows, category_rows


def _weight_evidence_summary(weights: Sequence[WeightCell]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in weights:
        counts[row.evidence_class] += 1
        totals[row.evidence_class] += row.weight
    experimental_classes = {
        evidence for evidence in counts
        if "EXPERIMENTAL" in evidence.upper() or "PROXY" in evidence.upper()
    }
    experimental_count = sum(counts[evidence] for evidence in experimental_classes)
    experimental_total = sum((totals[evidence] for evidence in experimental_classes), ZERO)
    return {
        "weight_evidence_class_counts": dict(sorted(counts.items())),
        "weight_evidence_class_totals": {
            evidence: _decimal_text(total) for evidence, total in sorted(totals.items())
        },
        "experimental_proxy_cell_count": experimental_count,
        "experimental_proxy_weight_total": _decimal_text(experimental_total),
        "experimental_proxy_disclosure_required": True,
    }


def _headline_weights(weights: Sequence[WeightCell]) -> list[WeightCell]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    evidence: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    for row in weights:
        totals[row.economy_code] += row.weight
        evidence[row.economy_code].add(row.evidence_class)
        sources[row.economy_code].add(row.source_id)
    result = [
        WeightCell(
            economy_code=economy,
            category_code="CP00",
            weight=weight,
            evidence_class="|".join(sorted(evidence[economy])),
            source_id="|".join(sorted(sources[economy])),
        )
        for economy, weight in sorted(totals.items())
    ]
    if abs(sum((row.weight for row in result), ZERO) - ONE) > WEIGHT_TOLERANCE:
        raise OfficialEngineError("derived headline economy weights do not sum to 1")
    return result


def _build_headline_panel(
    weights: Sequence[WeightCell],
    observations: Sequence[PriceVintageObservation],
    policy: EnginePolicy,
    request: BuildRequest,
) -> tuple[list[dict[str, str]], dict[tuple[str, str, str], Decimal], list[WeightCell]]:
    headline_weights = _headline_weights(weights)
    selected = select_as_of(observations, request.cutoff_at, request.series_kind)
    expected = {(row.economy_code, "CP00") for row in headline_weights}
    normalised, relatives = _normalise_panel(selected, policy, expected)
    return normalised, relatives, headline_weights


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_manifest(root: Path) -> dict[str, str]:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
    )
    entries: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        entries[relative] = _sha256_path(path)
    (root / "MANIFEST.sha256").write_text(
        "".join(f"{digest} {relative}\n" for relative, digest in entries.items()),
        encoding="utf-8",
    )
    return entries


def verify_manifest(root: Path) -> dict[str, str]:
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise OfficialEngineError("MANIFEST.sha256 is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            digest, relative = line.split(" ", 1)
        except ValueError as exc:
            raise OfficialEngineError(f"invalid manifest line {line_number}") from exc
        if not SHA256_RE.fullmatch(digest):
            raise OfficialEngineError(f"invalid manifest digest at line {line_number}")
        if relative in entries:
            raise OfficialEngineError(f"duplicate manifest target: {relative}")
        target = _safe_child(root, relative)
        if not target.is_file():
            raise OfficialEngineError(f"manifest target missing: {relative}")
        actual = _sha256_path(target)
        if actual != digest:
            raise OfficialEngineError(f"MANIFEST_HASH_MISMATCH: {relative}")
        entries[relative] = digest
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != actual_files:
        raise OfficialEngineError(
            f"manifest file set mismatch; missing={sorted(actual_files - set(entries))}, "
            f"extra={sorted(set(entries) - actual_files)}"
        )
    return entries


def _copy_input(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def build_run(
    *,
    policy_path: Path,
    weights_path: Path,
    category_observations_path: Path,
    headline_observations_path: Path | None,
    output_dir: Path,
    ledger_path: Path,
    request: BuildRequest,
) -> dict[str, Any]:
    request.validate()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise OfficialEngineError("OUTPUT_DIRECTORY_NOT_EMPTY")
    policy = EnginePolicy.load(policy_path)
    weights = load_weights(weights_path, policy)
    category_observations = load_observations(category_observations_path, policy)
    if request.series_kind is SeriesKind.ARM_H:
        if headline_observations_path is None:
            raise OfficialEngineError("ARM-H requires headline observations")
        headline_observations = load_observations(headline_observations_path, policy, headline=True)
    else:
        headline_observations = []
    staging_parent = output_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=staging_parent))
    try:
        assert staging is not None
        inputs = staging / "inputs"
        outputs = staging / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        _copy_input(policy_path, inputs / "official_engine_policy.json")
        _copy_input(weights_path, inputs / "fixed_weights.csv")
        _copy_input(category_observations_path, inputs / "category_observations.csv")
        if headline_observations_path is not None:
            _copy_input(headline_observations_path, inputs / "headline_observations.csv")
        if request.series_kind is SeriesKind.ARM_H:
            normalised_rows, relatives, active_weights = _build_headline_panel(
                weights, headline_observations, policy, request
            )
        else:
            selected = select_as_of(category_observations, request.cutoff_at, request.series_kind)
            expected = {(row.economy_code, row.category_code) for row in weights}
            normalised_rows, relatives = _normalise_panel(selected, policy, expected)
            active_weights = weights
        index_rows, cell_rows, economy_rows, category_rows = _aggregate_index(
            active_weights,
            relatives,
            policy,
            request.series_kind,
            request.run_id,
            request.vintage_id,
            request.cutoff_at,
        )
        _write_csv(
            outputs / "normalised_price_observations.csv",
            normalised_rows,
            (
                "economy_code",
                "category_code",
                "period",
                "source_value",
                "base_year_average",
                "price_relative",
                "price_relative_unrounded",
                "series_id",
                "source_vintage_id",
                "published_at",
                "retrieved_at",
                "revision_sequence",
                "raw_snapshot_id",
                "source_sha256",
                "evidence_class",
            ),
        )
        _write_csv(outputs / "index_series.csv", index_rows, tuple(index_rows[0]))
        _write_csv(outputs / "cell_contributions.csv", cell_rows, tuple(cell_rows[0]))
        _write_csv(outputs / "economy_contributions.csv", economy_rows, tuple(economy_rows[0]))
        _write_csv(outputs / "category_contributions.csv", category_rows, tuple(category_rows[0]))
        input_hashes = {
            "policy_sha256": _sha256_path(inputs / "official_engine_policy.json"),
            "weights_sha256": _sha256_path(inputs / "fixed_weights.csv"),
            "category_observations_sha256": _sha256_path(inputs / "category_observations.csv"),
            "headline_observations_sha256": (
                _sha256_path(inputs / "headline_observations.csv")
                if (inputs / "headline_observations.csv").is_file()
                else None
            ),
        }
        summary: dict[str, Any] = {
            "schema_version": "1.0",
            "engine_version": "0.9.6",
            "run_id": request.run_id,
            "series_kind": request.series_kind.value,
            "vintage_id": request.vintage_id,
            "cutoff_at": request.cutoff_at,
            "created_at": request.created_at,
            "status": RunStatus.COMPLETE.value,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "constitution_id": policy.constitution_id,
            "constitution_version": policy.constitution_version,
            "constitution_sha256": policy.constitution_sha256,
            "ratification_record_sha256": policy.ratification_record_sha256,
            "reference_year": policy.reference_year,
            "reference_average": _decimal_text(policy.reference_average),
            "precision": policy.precision,
            "rounding": policy.rounding,
            "period_count": len(policy.periods),
            "economy_count": len({row.economy_code for row in active_weights}),
            "category_count": len({row.category_code for row in active_weights}),
            "weight_cell_count": len(active_weights),
            "research_core_weight_cell_count": len(weights),
            "index_row_count": len(index_rows),
            "normalised_observation_count": len(normalised_rows),
            **_weight_evidence_summary(weights),
            "formula": _formula_for(request.series_kind),
            "fx_treatment": "EXCLUDED_FROM_PRIMARY_INDEX",
            "input_hashes": input_hashes,
            "ooh_sensitivity_required": policy.ooh_sensitivity_required,
            "ooh_sensitivity_completed": False,
            "release_gates": {
                "research_release_allowed": False,
                "model_promotion_allowed": False,
                "shadow_production_allowed": False,
                "monetary_release_allowed": False,
                "world_claim_allowed": False,
            },
        }
        (outputs / "run_summary.json").write_bytes(_canonical_json_bytes(summary))
        (outputs / "ECONOMIC_REPORT.md").write_text(_economic_report(summary), encoding="utf-8")
        _write_manifest(staging)
        verify_manifest(staging)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)
        staging = None
        try:
            ledger_entry = append_ledger(ledger_path, output_dir)
        except Exception:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise
        summary["ledger_sequence"] = ledger_entry["sequence"]
        summary["ledger_entry_hash"] = ledger_entry["entry_hash"]
        return summary
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _economic_report(summary: Mapping[str, Any]) -> str:
    return (
        "# ARMILAR v0.9.6 official engine run\n\n"
        f"- Run: `{summary['run_id']}`\n"
        f"- Series: `{summary['series_kind']}`\n"
        f"- Vintage: `{summary['vintage_id']}`\n"
        f"- Cutoff: `{summary['cutoff_at']}`\n"
        f"- Periods: {summary['period_count']}\n"
        f"- Economies: {summary['economy_count']}\n"
        f"- Active weight cells: {summary['weight_cell_count']}\n"
        f"- Research Core weight cells: {summary['research_core_weight_cell_count']}\n"
        f"- Experimental AIC-PPP proxy cells: {summary['experimental_proxy_cell_count']}\n"
        f"- Experimental AIC-PPP proxy weight: {summary['experimental_proxy_weight_total']}\n"
        "- Base: average of the twelve months of 2021 equals exactly 100.\n"
        "- Arithmetic: Decimal precision 28, ROUND_HALF_EVEN, no intermediate rounding.\n"
        "- Current FX: excluded from the primary index.\n"
        "- OOH sensitivity: required before any external or shadow release.\n"
        "- All release, promotion, shadow, monetary and world-claim gates remain closed.\n"
    )


def _ledger_payload(run_dir: Path) -> dict[str, Any]:
    verify_manifest(run_dir)
    summary_path = run_dir / "outputs" / "run_summary.json"
    if not summary_path.is_file():
        raise OfficialEngineError("run summary missing")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "run_id": summary["run_id"],
        "series_kind": summary["series_kind"],
        "vintage_id": summary["vintage_id"],
        "cutoff_at": summary["cutoff_at"],
        "created_at": summary["created_at"],
        "run_manifest_sha256": _sha256_path(run_dir / "MANIFEST.sha256"),
        "run_summary_sha256": _sha256_path(summary_path),
        "constitution_sha256": summary["constitution_sha256"],
        "ratification_record_sha256": summary["ratification_record_sha256"],
    }


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    previous = "0" * 64
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OfficialEngineError(f"invalid ledger JSON at line {line_number}") from exc
        expected_keys = {"sequence", "previous_hash", "payload", "entry_hash"}
        if set(entry) != expected_keys:
            raise OfficialEngineError(f"ledger entry keys mismatch at line {line_number}")
        if entry["sequence"] != line_number:
            raise OfficialEngineError(f"ledger sequence mismatch at line {line_number}")
        if entry["previous_hash"] != previous:
            raise OfficialEngineError(f"ledger chain broken at line {line_number}")
        unsigned = {
            "sequence": entry["sequence"],
            "previous_hash": entry["previous_hash"],
            "payload": entry["payload"],
        }
        actual = _sha256_bytes(_canonical_json_bytes(unsigned))
        if actual != entry["entry_hash"]:
            raise OfficialEngineError(f"ledger hash mismatch at line {line_number}")
        previous = entry["entry_hash"]
        entries.append(entry)
    return entries


def append_ledger(path: Path, run_dir: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise OfficialEngineError("ledger is locked by another writer") from exc
    try:
        os.close(descriptor)
        entries = _read_ledger(path)
        payload = _ledger_payload(run_dir)
        for entry in entries:
            if entry["payload"]["run_id"] == payload["run_id"]:
                if entry["payload"] == payload:
                    return entry
                raise OfficialEngineError("immutable run_id already exists with different content")
        previous = entries[-1]["entry_hash"] if entries else "0" * 64
        unsigned = {
            "sequence": len(entries) + 1,
            "previous_hash": previous,
            "payload": payload,
        }
        entry = dict(unsigned)
        entry["entry_hash"] = _sha256_bytes(_canonical_json_bytes(unsigned))
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(_canonical_json_bytes(entry).decode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        _read_ledger(path)
        return entry
    finally:
        lock.unlink(missing_ok=True)


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    return _read_ledger(path)


def replay_run(run_dir: Path) -> dict[str, Any]:
    verify_manifest(run_dir)
    summary = json.loads((run_dir / "outputs" / "run_summary.json").read_text(encoding="utf-8"))
    request = BuildRequest(
        run_id=summary["run_id"] + ".replay",
        series_kind=SeriesKind(summary["series_kind"]),
        vintage_id=summary["vintage_id"],
        cutoff_at=summary["cutoff_at"],
        created_at=summary["created_at"],
    )
    with tempfile.TemporaryDirectory(prefix="armilar-v096-replay-") as temporary:
        temp = Path(temporary)
        output = temp / "run"
        ledger = temp / "ledger.jsonl"
        replay_summary = build_run(
            policy_path=run_dir / "inputs" / "official_engine_policy.json",
            weights_path=run_dir / "inputs" / "fixed_weights.csv",
            category_observations_path=run_dir / "inputs" / "category_observations.csv",
            headline_observations_path=(
                run_dir / "inputs" / "headline_observations.csv"
                if (run_dir / "inputs" / "headline_observations.csv").is_file()
                else None
            ),
            output_dir=output,
            ledger_path=ledger,
            request=request,
        )
        comparisons = (
            "outputs/normalised_price_observations.csv",
            "outputs/index_series.csv",
            "outputs/cell_contributions.csv",
            "outputs/economy_contributions.csv",
            "outputs/category_contributions.csv",
        )
        for relative in comparisons:
            original = (run_dir / relative).read_text(encoding="utf-8")
            replay = (output / relative).read_text(encoding="utf-8")
            original = original.replace(summary["run_id"], request.run_id)
            if original != replay:
                raise OfficialEngineError(f"REPLAY_OUTPUT_MISMATCH: {relative}")
        return {
            "status": "REPLAY_VERIFIED",
            "original_run_id": summary["run_id"],
            "replay_run_id": replay_summary["run_id"],
            "verified_files": list(comparisons),
        }


def _read_csv_decimal(path: Path, key_fields: Sequence[str], value_field: str) -> dict[tuple[str, ...], Decimal]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[tuple[str, ...], Decimal] = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in result:
            raise OfficialEngineError(f"duplicate reconciliation key: {key}")
        result[key] = _decimal(row[value_field], value_field)
    return result


def reconcile_runs(old_run: Path, new_run: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise OfficialEngineError("OUTPUT_DIRECTORY_NOT_EMPTY")
    verify_manifest(old_run)
    verify_manifest(new_run)
    old_summary = json.loads((old_run / "outputs" / "run_summary.json").read_text(encoding="utf-8"))
    new_summary = json.loads((new_run / "outputs" / "run_summary.json").read_text(encoding="utf-8"))
    if old_summary["policy_id"] != new_summary["policy_id"]:
        raise OfficialEngineError("cannot reconcile runs under different policies")
    old_index = _read_csv_decimal(
        old_run / "outputs" / "index_series.csv", ("period",), "index_value_unrounded"
    )
    new_index = _read_csv_decimal(
        new_run / "outputs" / "index_series.csv", ("period",), "index_value_unrounded"
    )
    if set(old_index) != set(new_index):
        raise OfficialEngineError("cannot reconcile different period sets")
    old_cells = _read_csv_decimal(
        old_run / "outputs" / "cell_contributions.csv",
        ("period", "economy_code", "category_code"),
        "index_level_contribution_unrounded",
    )
    new_cells = _read_csv_decimal(
        new_run / "outputs" / "cell_contributions.csv",
        ("period", "economy_code", "category_code"),
        "index_level_contribution_unrounded",
    )
    if set(old_cells) != set(new_cells):
        raise OfficialEngineError("cannot reconcile different cell grids")
    index_rows: list[dict[str, str]] = []
    cell_rows: list[dict[str, str]] = []
    for key in sorted(old_index):
        revision = new_index[key] - old_index[key]
        index_rows.append(
            {
                "period": key[0],
                "old_run_id": old_summary["run_id"],
                "new_run_id": new_summary["run_id"],
                "old_vintage_id": old_summary["vintage_id"],
                "new_vintage_id": new_summary["vintage_id"],
                "old_index_value": _fixed_decimal_text(old_index[key], INDEX_DECIMAL_PLACES),
                "old_index_value_unrounded": _decimal_text(old_index[key]),
                "new_index_value": _fixed_decimal_text(new_index[key], INDEX_DECIMAL_PLACES),
                "new_index_value_unrounded": _decimal_text(new_index[key]),
                "revision_index_points": _fixed_decimal_text(revision, INDEX_DECIMAL_PLACES),
                "revision_index_points_unrounded": _decimal_text(revision),
                "revision_percent": _fixed_decimal_text(
                    revision / old_index[key] * HUNDRED, PERCENTAGE_DECIMAL_PLACES
                ),
                "revision_percent_unrounded": _decimal_text(revision / old_index[key] * HUNDRED),
            }
        )
    by_period: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for key in sorted(old_cells):
        revision = new_cells[key] - old_cells[key]
        by_period[key[0]] += revision
        cell_rows.append(
            {
                "period": key[0],
                "economy_code": key[1],
                "category_code": key[2],
                "old_index_level_contribution": _fixed_decimal_text(
                    old_cells[key], CONTRIBUTION_DECIMAL_PLACES
                ),
                "old_index_level_contribution_unrounded": _decimal_text(old_cells[key]),
                "new_index_level_contribution": _fixed_decimal_text(
                    new_cells[key], CONTRIBUTION_DECIMAL_PLACES
                ),
                "new_index_level_contribution_unrounded": _decimal_text(new_cells[key]),
                "revision_index_points": _fixed_decimal_text(revision, CONTRIBUTION_DECIMAL_PLACES),
                "revision_index_points_unrounded": _decimal_text(revision),
            }
        )
    for row in index_rows:
        if abs(by_period[row["period"]] - _decimal(row["revision_index_points_unrounded"], "revision")) > CONTRIBUTION_TOLERANCE:
            raise OfficialEngineError("reconciliation cell revisions do not sum to total revision")
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir / "index_reconciliation.csv", index_rows, tuple(index_rows[0]))
    _write_csv(output_dir / "cell_reconciliation.csv", cell_rows, tuple(cell_rows[0]))
    summary = {
        "schema_version": "1.0",
        "status": "RECONCILED",
        "old_run_id": old_summary["run_id"],
        "new_run_id": new_summary["run_id"],
        "period_count": len(index_rows),
        "revised_period_count": sum(
            1 for row in index_rows if _decimal(row["revision_index_points_unrounded"], "revision") != ZERO
        ),
        "cell_row_count": len(cell_rows),
        "cell_revision_count": sum(
            1 for row in cell_rows if _decimal(row["revision_index_points_unrounded"], "revision") != ZERO
        ),
        "max_absolute_revision_index_points": _fixed_decimal_text(
            max((abs(_decimal(row["revision_index_points_unrounded"], "revision")) for row in index_rows), default=ZERO),
            INDEX_DECIMAL_PLACES,
        ),
        "research_release_allowed": False,
        "shadow_production_allowed": False,
        "monetary_release_allowed": False,
        "release_gates": {
            "research_release_allowed": False,
            "model_promotion_allowed": False,
            "shadow_production_allowed": False,
            "monetary_release_allowed": False,
            "world_claim_allowed": False,
        },
    }
    (output_dir / "reconciliation_summary.json").write_bytes(_canonical_json_bytes(summary))
    _write_manifest(output_dir)
    verify_manifest(output_dir)
    return summary


def run_ooh_sensitivity(
    run_dir: Path,
    scenario_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise OfficialEngineError("OUTPUT_DIRECTORY_NOT_EMPTY")
    verify_manifest(run_dir)
    try:
        scenarios_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OfficialEngineError("cannot load OOH scenarios") from exc
    if set(scenarios_payload) != {"schema_version", "scenarios"}:
        raise OfficialEngineError("OOH scenario document keys mismatch")
    scenarios = scenarios_payload["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise OfficialEngineError("OOH scenarios must be a non-empty list")
    scenario_defs: list[tuple[str, Decimal]] = []
    for item in scenarios:
        if set(item) != {"scenario_id", "cp04_multiplier", "interpretation"}:
            raise OfficialEngineError("OOH scenario keys mismatch")
        multiplier = _decimal(item["cp04_multiplier"], "cp04_multiplier")
        if multiplier <= ZERO:
            raise OfficialEngineError("cp04_multiplier must be positive")
        scenario_defs.append((str(item["scenario_id"]), multiplier))
    index = _read_csv_decimal(
        run_dir / "outputs" / "index_series.csv", ("period",), "index_value_unrounded"
    )
    cells = _read_csv_decimal(
        run_dir / "outputs" / "cell_contributions.csv",
        ("period", "economy_code", "category_code"),
        "index_level_contribution_unrounded",
    )
    cp04: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for (period, _economy, category), value in cells.items():
        if category == "CP04":
            cp04[period] += value
    rows: list[dict[str, str]] = []
    for scenario_id, multiplier in scenario_defs:
        for (period,), baseline in sorted(index.items()):
            adjusted = baseline - cp04[period] + cp04[period] * multiplier
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "period": period,
                    "cp04_multiplier": _decimal_text(multiplier),
                    "baseline_index_value": _fixed_decimal_text(baseline, INDEX_DECIMAL_PLACES),
                    "baseline_index_value_unrounded": _decimal_text(baseline),
                    "scenario_index_value": _fixed_decimal_text(adjusted, INDEX_DECIMAL_PLACES),
                    "scenario_index_value_unrounded": _decimal_text(adjusted),
                    "impact_index_points": _fixed_decimal_text(
                        adjusted - baseline, INDEX_DECIMAL_PLACES
                    ),
                    "impact_index_points_unrounded": _decimal_text(adjusted - baseline),
                    "evidence_status": "SCENARIO_NOT_EVIDENCE",
                }
            )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir / "ooh_sensitivity.csv", rows, tuple(rows[0]))
    summary = {
        "schema_version": "1.0",
        "status": "OOH_SCENARIO_HARNESS_COMPLETED",
        "run_id": json.loads((run_dir / "outputs" / "run_summary.json").read_text())["run_id"],
        "scenario_count": len(scenario_defs),
        "period_count": len(index),
        "evidence_status": "SCENARIO_NOT_EVIDENCE",
        "uses_official_oohpi": False,
        "constitutional_ooh_requirement_satisfied": False,
        "external_release_authorised": False,
        "shadow_production_authorised": False,
        "monetary_release_authorised": False,
        "release_gates": {
            "research_release_allowed": False,
            "model_promotion_allowed": False,
            "shadow_production_allowed": False,
            "monetary_release_allowed": False,
            "world_claim_allowed": False,
        },
    }
    (output_dir / "ooh_sensitivity_summary.json").write_bytes(_canonical_json_bytes(summary))
    _write_manifest(output_dir)
    verify_manifest(output_dir)
    return summary


def export_parquet(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Export canonical CSV outputs to Parquet through optional DuckDB.

    DuckDB is deliberately optional in v0.9.6. The deterministic CSV run bundle
    remains the canonical replay artefact; Parquet files are derived storage views.
    """
    verify_manifest(run_dir)
    if importlib.util.find_spec("duckdb") is None:
        raise OfficialEngineError("OPTIONAL_STORAGE_DEPENDENCY_MISSING: install armilar-data-pipeline[temporal]")
    import duckdb  # type: ignore[import-not-found]

    if output_dir.exists() and any(output_dir.iterdir()):
        raise OfficialEngineError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.mkdir(parents=True, exist_ok=False)
    sources = (
        "normalised_price_observations.csv",
        "index_series.csv",
        "cell_contributions.csv",
        "economy_contributions.csv",
        "category_contributions.csv",
    )
    connection = duckdb.connect(database=":memory:")
    try:
        for name in sources:
            source = (run_dir / "outputs" / name).resolve().as_posix().replace("'", "''")
            destination = (output_dir / name.replace(".csv", ".parquet")).resolve().as_posix().replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM read_csv_auto('{source}', header=true, all_varchar=true)) "
                f"TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
    finally:
        connection.close()
    summary = {
        "schema_version": "1.0",
        "status": "PARQUET_DERIVED_VIEW_EXPORTED",
        "canonical_source_manifest_sha256": _sha256_path(run_dir / "MANIFEST.sha256"),
        "file_count": len(sources),
        "canonical_storage": False,
        "release_gates": {
            "research_release_allowed": False,
            "model_promotion_allowed": False,
            "shadow_production_allowed": False,
            "monetary_release_allowed": False,
            "world_claim_allowed": False,
        },
    }
    (output_dir / "parquet_export_summary.json").write_bytes(_canonical_json_bytes(summary))
    _write_manifest(output_dir)
    verify_manifest(output_dir)
    return summary


def _request_from_args(args: argparse.Namespace) -> BuildRequest:
    return BuildRequest(
        run_id=args.run_id,
        series_kind=SeriesKind(args.series_kind),
        vintage_id=args.vintage_id,
        cutoff_at=args.cutoff_at,
        created_at=args.created_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build an immutable ARM-O, ARM-R or ARM-H run")
    build.add_argument("--policy", type=Path, required=True)
    build.add_argument("--weights", type=Path, required=True)
    build.add_argument("--category-observations", type=Path, required=True)
    build.add_argument("--headline-observations", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--ledger", type=Path, required=True)
    build.add_argument("--run-id", required=True)
    build.add_argument("--series-kind", choices=[kind.value for kind in SeriesKind], required=True)
    build.add_argument("--vintage-id", required=True)
    build.add_argument("--cutoff-at", required=True)
    build.add_argument("--created-at", required=True)
    replay = sub.add_parser("replay", help="verify and deterministically replay a run bundle")
    replay.add_argument("--run", type=Path, required=True)
    reconcile = sub.add_parser("reconcile", help="reconcile two immutable runs")
    reconcile.add_argument("--old-run", type=Path, required=True)
    reconcile.add_argument("--new-run", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    ledger = sub.add_parser("verify-ledger", help="verify an append-only ledger")
    ledger.add_argument("--ledger", type=Path, required=True)
    ooh = sub.add_parser("ooh-sensitivity", help="run declared CP04 sensitivity scenarios")
    ooh.add_argument("--run", type=Path, required=True)
    ooh.add_argument("--scenarios", type=Path, required=True)
    ooh.add_argument("--output", type=Path, required=True)
    parquet = sub.add_parser("export-parquet", help="derive Parquet views through optional DuckDB")
    parquet.add_argument("--run", type=Path, required=True)
    parquet.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            payload = build_run(
                policy_path=args.policy,
                weights_path=args.weights,
                category_observations_path=args.category_observations,
                headline_observations_path=args.headline_observations,
                output_dir=args.output,
                ledger_path=args.ledger,
                request=_request_from_args(args),
            )
        elif args.command == "replay":
            payload = replay_run(args.run)
        elif args.command == "reconcile":
            payload = reconcile_runs(args.old_run, args.new_run, args.output)
        elif args.command == "verify-ledger":
            entries = verify_ledger(args.ledger)
            payload = {"status": "LEDGER_VERIFIED", "entry_count": len(entries)}
        elif args.command == "ooh-sensitivity":
            payload = run_ooh_sensitivity(args.run, args.scenarios, args.output)
        elif args.command == "export-parquet":
            payload = export_parquet(args.run, args.output)
        else:  # pragma: no cover
            parser.error("unknown command")
            return 2
    except OfficialEngineError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
