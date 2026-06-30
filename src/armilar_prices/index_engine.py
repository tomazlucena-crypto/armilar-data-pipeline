from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from armilar_global_weights.models import CATEGORIES

from .models import NormalizedPriceObservation, PriceEvidenceClass, validate_month
from .selector import load_normalized_prices


class IndexBuildError(ValueError):
    """Raised when a monthly research index would violate its contract."""


class AggregationMode(StrEnum):
    PPP_WEIGHTED_LOCAL_PRICE_RELATIVES = "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES"
    COMMON_CURRENCY_FX_ADJUSTED = "COMMON_CURRENCY_FX_ADJUSTED"


@dataclass(frozen=True, slots=True)
class WeightRecord:
    economy_code: str
    category_code: str
    weight: float

    def validate(self) -> None:
        if len(self.economy_code) != 3 or self.economy_code != self.economy_code.upper():
            raise IndexBuildError(f"invalid weight economy_code: {self.economy_code!r}")
        if self.category_code not in CATEGORIES:
            raise IndexBuildError(f"invalid weight category_code: {self.category_code!r}")
        if not math.isfinite(self.weight) or self.weight < 0:
            raise IndexBuildError("weights must be finite and non-negative")


def load_global_weights(path: Path) -> list[WeightRecord]:
    return _load_weights(path, "weight")


def load_core_weights(path: Path) -> list[WeightRecord]:
    return _load_weights(path, "observed_universe_weight")


def _load_weights(path: Path, weight_column: str) -> list[WeightRecord]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise IndexBuildError(f"weight input is empty: {path}")
    result: list[WeightRecord] = []
    seen: set[tuple[str, str]] = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            item = WeightRecord(
                economy_code=row["economy_code"].strip().upper(),
                category_code=row["category_code"].strip().upper(),
                weight=float(row[weight_column]),
            )
            item.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexBuildError(f"invalid weight at CSV line {line_number}: {exc}") from exc
        key = (item.economy_code, item.category_code)
        if key in seen:
            raise IndexBuildError(f"duplicate weight cell: {key}")
        seen.add(key)
        result.append(item)
    total = sum(row.weight for row in result)
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise IndexBuildError(f"{weight_column} must sum to 1, got {total}")
    return sorted(result, key=lambda row: (row.economy_code, row.category_code))


def calculate_monthly_indices(
    global_weights: Iterable[WeightRecord],
    core_weights: Iterable[WeightRecord],
    selected_prices: Iterable[NormalizedPriceObservation],
    reference_period: str,
    *,
    aggregation_mode: AggregationMode = AggregationMode.PPP_WEIGHTED_LOCAL_PRICE_RELATIVES,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    validate_month(reference_period)
    if aggregation_mode is AggregationMode.COMMON_CURRENCY_FX_ADJUSTED:
        raise IndexBuildError("FX-adjusted common-currency aggregation is not constitutionally ratified")

    global_rows = list(global_weights)
    core_rows = list(core_weights)
    prices = list(selected_prices)
    for row in prices:
        row.validate()
        if row.reference_period != reference_period:
            raise IndexBuildError("selected prices contain inconsistent reference periods")

    price_by_key = {(row.economy_code, row.category_code, row.period): row for row in prices}
    if len(price_by_key) != len(prices):
        raise IndexBuildError("selected price input contains duplicate economy-category-period rows")
    periods = sorted({row.period for row in prices})
    if reference_period not in periods:
        raise IndexBuildError("reference period is absent from selected prices")

    index_rows: list[dict[str, object]] = []
    contribution_rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    for index_id, weights in (
        ("ARM-M-GLOBAL-RESEARCH", global_rows),
        ("ARM-M-CORE-RESEARCH", core_rows),
    ):
        for period in periods:
            covered_weight = 0.0
            weighted_value = 0.0
            evidence_weight: dict[str, float] = defaultdict(float)
            missing: list[str] = []
            period_contributions: list[dict[str, object]] = []
            for weight in weights:
                key = (weight.economy_code, weight.category_code, period)
                price = price_by_key.get(key)
                if price is None:
                    missing.append(f"{weight.economy_code}:{weight.category_code}")
                    continue
                covered_weight += weight.weight
                weighted_value += weight.weight * price.price_relative
                evidence_weight[price.evidence_class.value] += weight.weight
                period_contributions.append({
                    "index_id": index_id,
                    "period": period,
                    "economy_code": weight.economy_code,
                    "category_code": weight.category_code,
                    "weight": weight.weight,
                    "price_relative": price.price_relative,
                    "weighted_index_points": weight.weight * price.price_relative,
                    "contribution_since_reference": weight.weight * (price.price_relative - 100.0),
                    "price_series_id": price.series_id,
                    "price_evidence_class": price.evidence_class.value,
                })
            complete = math.isclose(covered_weight, 1.0, rel_tol=1e-9, abs_tol=1e-9)
            value: float | None = weighted_value if complete else None
            if complete:
                contribution_rows.extend(period_contributions)
            direct_weight = sum(
                share
                for evidence, share in evidence_weight.items()
                if PriceEvidenceClass(evidence).is_direct_or_official_aggregate
            )
            proxy_weight = sum(evidence_weight.values()) - direct_weight
            index_rows.append({
                "index_id": index_id,
                "period": period,
                "value": value,
                "status": "COMPLETE" if complete else "INCOMPLETE",
                "reference_period": reference_period,
                "covered_weight": covered_weight,
                "direct_or_official_aggregate_price_weight": direct_weight,
                "headline_or_proxy_price_weight": proxy_weight,
                "missing_cell_count": len(missing),
                "missing_cells": "|".join(missing),
                "aggregation_mode": aggregation_mode.value,
                "fx_treatment": "NOT_INCLUDED_RESEARCH_BASELINE",
                "monetary_release_allowed": False,
            })
            for evidence in PriceEvidenceClass:
                evidence_rows.append({
                    "index_id": index_id,
                    "period": period,
                    "price_evidence_class": evidence.value,
                    "weight_share": evidence_weight.get(evidence.value, 0.0),
                })

    complete_count = sum(row["status"] == "COMPLETE" for row in index_rows)
    reference_values = [
        row for row in index_rows if row["period"] == reference_period and row["status"] == "COMPLETE"
    ]
    for row in reference_values:
        if not math.isclose(float(row["value"]), 100.0, rel_tol=1e-9, abs_tol=1e-9):
            raise IndexBuildError(f"reference-period index is not 100 for {row['index_id']}")
    summary = {
        "reference_period": reference_period,
        "aggregation_mode": aggregation_mode.value,
        "fx_treatment": "NOT_INCLUDED_RESEARCH_BASELINE",
        "index_row_count": len(index_rows),
        "complete_index_row_count": complete_count,
        "incomplete_index_row_count": len(index_rows) - complete_count,
        "period_count": len(periods),
        "global_weight_cell_count": len(global_rows),
        "core_weight_cell_count": len(core_rows),
        "silent_renormalisation_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    return index_rows, contribution_rows, evidence_rows, summary


def write_index_outputs(
    index_rows: list[dict[str, object]],
    contribution_rows: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "monthly_index.csv",
        index_rows,
        [
            "index_id", "period", "value", "status", "reference_period", "covered_weight",
            "direct_or_official_aggregate_price_weight", "headline_or_proxy_price_weight",
            "missing_cell_count", "missing_cells", "aggregation_mode", "fx_treatment",
            "monetary_release_allowed",
        ],
    )
    _write_csv(
        output_dir / "index_contributions.csv",
        contribution_rows,
        [
            "index_id", "period", "economy_code", "category_code", "weight",
            "price_relative", "weighted_index_points", "contribution_since_reference",
            "price_series_id", "price_evidence_class",
        ],
    )
    _write_csv(
        output_dir / "price_evidence_coverage.csv",
        evidence_rows,
        ["index_id", "period", "price_evidence_class", "weight_share"],
    )
    (output_dir / "monthly_index_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_paths = sorted(path for path in output_dir.iterdir() if path.is_file() and path.name != "MANIFEST.sha256")
    entries = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in manifest_paths]
    (output_dir / "MANIFEST.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")
    return summary


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})
