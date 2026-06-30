from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from armilar_global_weights.models import CATEGORIES as SOURCE_CATEGORIES

from .classification import (
    ARMILAR_CATEGORY_CODES,
    ClassificationBundle,
    ClassificationError,
    load_classification_bundle,
    mapping_audit_rows,
)
from .models import NormalizedPriceObservation, PriceEvidenceClass, validate_month
from .selector import load_normalized_prices


class PricePilotError(ValueError):
    """Raised when the Eurostat category pilot would violate its contract."""


@dataclass(frozen=True, slots=True)
class WorldWeight:
    economy_code: str
    category_code: str
    world_weight: float

    def validate(self) -> None:
        if (
            len(self.economy_code) != 3
            or self.economy_code != self.economy_code.upper()
            or not self.economy_code.isalpha()
        ):
            raise PricePilotError(f"invalid economy_code: {self.economy_code!r}")
        if self.category_code not in SOURCE_CATEGORIES:
            raise PricePilotError(f"invalid source category_code: {self.category_code!r}")
        if not math.isfinite(self.world_weight) or self.world_weight < 0:
            raise PricePilotError("world_weight must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class PriceUniverseSpec:
    universe_id: str
    economies: tuple[str, ...]
    categories: tuple[str, ...]
    source_categories: tuple[str, ...]
    classification_id: str
    classification_version: str
    classification_sha256: str
    mapping_id: str
    mapping_sha256: str
    source_classification: str
    source_classification_version: str
    covered_world_weight_before_normalization: float
    external_world_weight: float
    normalization_rule: str
    reference_period: str
    allowed_sources: tuple[str, ...]
    experimental: bool
    start_period: str
    end_period: str
    minimum_complete_months: int
    price_concept: str
    weight_concept: str
    concept_alignment_status: str
    raw_source_detail_preserved: bool
    research_release_allowed: bool = False
    monetary_release_allowed: bool = False

    def validate(self) -> None:
        if "EUROSTAT" not in self.universe_id or "PILOT" not in self.universe_id:
            raise PricePilotError("universe_id must identify an explicit Eurostat pilot")
        if "WORLD" in self.universe_id:
            raise PricePilotError("the Eurostat pilot cannot be labelled a world index")
        if not self.economies or len(set(self.economies)) != len(self.economies):
            raise PricePilotError("economies must be non-empty and unique")
        if tuple(sorted(self.economies)) != self.economies:
            raise PricePilotError("economies must be sorted")
        if self.categories != ARMILAR_CATEGORY_CODES:
            raise PricePilotError("categories must be ARM01 to ARM09")
        if self.source_categories != tuple(SOURCE_CATEGORIES):
            raise PricePilotError("source_categories must remain CP01 to CP12")
        if self.classification_id != "ARMILAR_CONSUMPTION_CLASSIFICATION":
            raise PricePilotError("unexpected canonical classification id")
        if self.classification_version != "1.0.0":
            raise PricePilotError("unexpected canonical classification version")
        if len(self.classification_sha256) != 64 or len(self.mapping_sha256) != 64:
            raise PricePilotError("classification hashes must be SHA-256")
        if not self.mapping_id.strip():
            raise PricePilotError("mapping_id is required")
        if self.source_classification != "ECOICOP":
            raise PricePilotError("v0.8.2 requires an ECOICOP source mapping")
        if self.source_classification_version != "V1":
            raise PricePilotError("only the ratified ECOICOP V1 bridge is allowed")
        if not 0 < self.covered_world_weight_before_normalization <= 1:
            raise PricePilotError("covered world weight must be in (0, 1]")
        if not math.isclose(
            self.covered_world_weight_before_normalization + self.external_world_weight,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise PricePilotError("covered and external world weights must sum to 1")
        if self.normalization_rule != "FIXED_UNIVERSE_NORMALISE_ONCE":
            raise PricePilotError("unsupported normalization rule")
        validate_month(self.reference_period)
        validate_month(self.start_period)
        validate_month(self.end_period)
        if self.start_period != self.reference_period:
            raise PricePilotError("pilot must begin at the reference period")
        if self.end_period < self.start_period:
            raise PricePilotError("end period precedes start period")
        if set(self.allowed_sources) != {"EUROSTAT"}:
            raise PricePilotError("the v0.8.2 pilot allows Eurostat only")
        if not self.experimental:
            raise PricePilotError("the pilot must remain experimental")
        if self.minimum_complete_months < 2:
            raise PricePilotError("minimum_complete_months must be at least 2")
        if self.price_concept != "HICP_HOUSEHOLD_FINAL_MONETARY_CONSUMPTION":
            raise PricePilotError("unexpected price concept")
        if self.weight_concept != "ARMILAR_HFCE_PPP_2021":
            raise PricePilotError("unexpected weight concept")
        if self.concept_alignment_status != "PARTIAL_HFMCE_HFCE_SCOPE_MISMATCH":
            raise PricePilotError("concept-alignment limitation must remain explicit")
        if not self.raw_source_detail_preserved:
            raise PricePilotError("raw source detail must be preserved")
        if self.research_release_allowed or self.monetary_release_allowed:
            raise PricePilotError("pilot release flags must remain false")


def load_world_weights(path: Path) -> list[WorldWeight]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise PricePilotError(f"world-weight input is empty: {path}")
    result: list[WorldWeight] = []
    seen: set[tuple[str, str]] = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            item = WorldWeight(
                economy_code=(row.get("economy_code") or "").strip().upper(),
                category_code=(row.get("category_code") or "").strip().upper(),
                world_weight=float(row["world_weight"]),
            )
            item.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise PricePilotError(
                f"invalid world weight at CSV line {line_number}: {exc}"
            ) from exc
        key = (item.economy_code, item.category_code)
        if key in seen:
            raise PricePilotError(f"duplicate world-weight cell: {key}")
        seen.add(key)
        result.append(item)
    total = sum(row.world_weight for row in result)
    if total > 1.0 + 1e-9:
        raise PricePilotError(f"world weights exceed 1: {total}")
    return sorted(result, key=lambda row: (row.economy_code, row.category_code))


def _month_range(start: str, end: str) -> list[str]:
    validate_month(start)
    validate_month(end)
    start_y, start_m = map(int, start.split("-"))
    end_y, end_m = map(int, end.split("-"))
    result: list[str] = []
    year, month = start_y, start_m
    while (year, month) <= (end_y, end_m):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return result


def build_eurostat_category_pilot(
    world_weights: Iterable[WorldWeight],
    selected_prices: Iterable[NormalizedPriceObservation],
    reference_period: str,
    classification_bundle: ClassificationBundle,
    *,
    minimum_complete_months: int = 2,
) -> tuple[
    PriceUniverseSpec,
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
]:
    validate_month(reference_period)
    try:
        classification_bundle.validate_strict_source_grid(SOURCE_CATEGORIES)
        source_mapping = classification_bundle.mapping_by_source()
    except ClassificationError as exc:
        raise PricePilotError(f"invalid canonical classification: {exc}") from exc

    weights = list(world_weights)
    prices = list(selected_prices)
    if not weights:
        raise PricePilotError("world weights are empty")
    if not prices:
        raise PricePilotError("selected prices are empty")
    for row in weights:
        row.validate()
    for row in prices:
        row.validate()
        if row.reference_period != reference_period:
            raise PricePilotError("selected prices use inconsistent reference periods")
        if row.provider.upper() != "EUROSTAT":
            raise PricePilotError(f"non-Eurostat source in pilot: {row.series_id}")
        if row.evidence_class is not PriceEvidenceClass.P1_OFFICIAL_CATEGORY:
            raise PricePilotError(f"non-P1 price in pilot: {row.series_id}")
        if row.source_category_code != row.category_code:
            raise PricePilotError(f"non-exact source category in pilot: {row.series_id}")
        if row.category_code not in source_mapping:
            raise PricePilotError(
                f"unmapped source category in pilot: {row.category_code}"
            )

    price_by_key = {
        (row.economy_code, row.category_code, row.period): row for row in prices
    }
    if len(price_by_key) != len(prices):
        raise PricePilotError("duplicate economy-category-period selected prices")

    weight_by_key = {(row.economy_code, row.category_code): row for row in weights}
    candidate_economies = sorted(
        {
            row.economy_code
            for row in prices
            if row.period == reference_period
            and all(
                (row.economy_code, category, reference_period) in price_by_key
                for category in SOURCE_CATEGORIES
            )
            and all(
                (row.economy_code, category) in weight_by_key
                for category in SOURCE_CATEGORIES
            )
        }
    )
    if not candidate_economies:
        raise PricePilotError("no economy has a complete reference-month P1 Eurostat grid")

    all_periods = sorted({row.period for row in prices if row.period >= reference_period})
    if not all_periods or all_periods[0] != reference_period:
        raise PricePilotError("reference period is absent from selected prices")
    observed_end = all_periods[-1]
    calendar = _month_range(reference_period, observed_end)

    passing: list[str] = []
    economy_complete_periods: dict[str, list[str]] = {}
    for economy in candidate_economies:
        complete = [
            period
            for period in calendar
            if all(
                (economy, category, period) in price_by_key
                for category in SOURCE_CATEGORIES
            )
        ]
        contiguous: list[str] = []
        for period in calendar:
            if period not in complete:
                break
            contiguous.append(period)
        economy_complete_periods[economy] = contiguous
        if len(contiguous) >= minimum_complete_months:
            passing.append(economy)

    if not passing:
        raise PricePilotError("no economy passes the minimum complete-month gate")

    common_month_count = min(
        len(economy_complete_periods[economy]) for economy in passing
    )
    common_periods = calendar[:common_month_count]
    if len(common_periods) < minimum_complete_months:
        raise PricePilotError("common complete interval is shorter than the gate")

    source_universe_cells = {
        (economy, category)
        for economy in passing
        for category in SOURCE_CATEGORIES
    }
    covered_world_weight = sum(
        weight_by_key[key].world_weight for key in sorted(source_universe_cells)
    )
    if covered_world_weight <= 0:
        raise PricePilotError("covered world weight is non-positive")
    external_world_weight = 1.0 - covered_world_weight
    if external_world_weight < -1e-9:
        raise PricePilotError("covered world weight exceeds 1")
    external_world_weight = max(0.0, external_world_weight)

    spec = PriceUniverseSpec(
        universe_id="ARM-EUROSTAT-HICP-ARMILAR-V1-PILOT-V0.8.2",
        economies=tuple(passing),
        categories=classification_bundle.classification.category_codes,
        source_categories=tuple(SOURCE_CATEGORIES),
        classification_id=classification_bundle.classification.classification_id,
        classification_version=classification_bundle.classification.version,
        classification_sha256=classification_bundle.classification_sha256,
        mapping_id=classification_bundle.mapping_id,
        mapping_sha256=classification_bundle.mapping_sha256,
        source_classification=classification_bundle.source_classification,
        source_classification_version=(
            classification_bundle.source_classification_version
        ),
        covered_world_weight_before_normalization=covered_world_weight,
        external_world_weight=external_world_weight,
        normalization_rule="FIXED_UNIVERSE_NORMALISE_ONCE",
        reference_period=reference_period,
        allowed_sources=("EUROSTAT",),
        experimental=True,
        start_period=reference_period,
        end_period=common_periods[-1],
        minimum_complete_months=minimum_complete_months,
        price_concept="HICP_HOUSEHOLD_FINAL_MONETARY_CONSUMPTION",
        weight_concept="ARMILAR_HFCE_PPP_2021",
        concept_alignment_status="PARTIAL_HFMCE_HFCE_SCOPE_MISMATCH",
        raw_source_detail_preserved=True,
        research_release_allowed=False,
        monetary_release_allowed=False,
    )
    spec.validate()

    internal_weight = {
        key: weight_by_key[key].world_weight / covered_world_weight
        for key in source_universe_cells
    }
    if not math.isclose(
        sum(internal_weight.values()), 1.0, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise PricePilotError("fixed-universe weights do not sum to 1")

    index_rows: list[dict[str, object]] = []
    canonical_contribution_rows: list[dict[str, object]] = []
    source_contribution_rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []

    for period in common_periods:
        canonical_accumulator: dict[
            tuple[str, str], dict[str, object]
        ] = defaultdict(
            lambda: {
                "world_weight_before_normalization": 0.0,
                "fixed_universe_weight": 0.0,
                "weighted_index_points": 0.0,
                "contribution_since_reference": 0.0,
                "source_category_codes": [],
                "price_series_ids": [],
            }
        )
        total_value = 0.0
        for economy, source_category in sorted(source_universe_cells):
            price = price_by_key[(economy, source_category, period)]
            source_weight = weight_by_key[(economy, source_category)].world_weight
            fixed_weight = internal_weight[(economy, source_category)]
            points = fixed_weight * price.price_relative
            contribution = fixed_weight * (price.price_relative - 100.0)
            total_value += points
            mapping = source_mapping[source_category]
            source_contribution_rows.append(
                {
                    "index_id": spec.universe_id,
                    "period": period,
                    "economy_code": economy,
                    "source_category_code": source_category,
                    "armilar_category": mapping.armilar_category,
                    "mapping_type": mapping.mapping_type,
                    "world_weight_before_normalization": source_weight,
                    "fixed_universe_weight": fixed_weight,
                    "price_relative": price.price_relative,
                    "weighted_index_points": points,
                    "contribution_since_reference": contribution,
                    "price_series_id": price.series_id,
                    "price_evidence_class": price.evidence_class.value,
                }
            )
            aggregate = canonical_accumulator[(economy, mapping.armilar_category)]
            aggregate["world_weight_before_normalization"] = float(
                aggregate["world_weight_before_normalization"]
            ) + source_weight
            aggregate["fixed_universe_weight"] = float(
                aggregate["fixed_universe_weight"]
            ) + fixed_weight
            aggregate["weighted_index_points"] = float(
                aggregate["weighted_index_points"]
            ) + points
            aggregate["contribution_since_reference"] = float(
                aggregate["contribution_since_reference"]
            ) + contribution
            aggregate["source_category_codes"].append(source_category)  # type: ignore[union-attr]
            aggregate["price_series_ids"].append(price.series_id)  # type: ignore[union-attr]

        for economy in passing:
            for armilar_category in spec.categories:
                aggregate = canonical_accumulator[(economy, armilar_category)]
                fixed_weight = float(aggregate["fixed_universe_weight"])
                if fixed_weight <= 0:
                    raise PricePilotError(
                        f"non-positive canonical weight: {economy}/{armilar_category}"
                    )
                weighted_points = float(aggregate["weighted_index_points"])
                source_codes = tuple(sorted(aggregate["source_category_codes"]))
                mapping_type = (
                    "EXACT_ONE_TO_ONE" if len(source_codes) == 1 else "EXACT_MERGE"
                )
                canonical_contribution_rows.append(
                    {
                        "index_id": spec.universe_id,
                        "period": period,
                        "economy_code": economy,
                        "category_code": armilar_category,
                        "world_weight_before_normalization": float(
                            aggregate["world_weight_before_normalization"]
                        ),
                        "fixed_universe_weight": fixed_weight,
                        "price_relative": weighted_points / fixed_weight,
                        "weighted_index_points": weighted_points,
                        "contribution_since_reference": float(
                            aggregate["contribution_since_reference"]
                        ),
                        "source_category_codes": "|".join(source_codes),
                        "price_series_ids": "|".join(
                            sorted(aggregate["price_series_ids"])
                        ),
                        "mapping_type": mapping_type,
                        "price_evidence_class": (
                            PriceEvidenceClass.P1_OFFICIAL_CATEGORY.value
                        ),
                    }
                )

        canonical_total = sum(
            float(row["weighted_index_points"])
            for row in canonical_contribution_rows
            if row["period"] == period
        )
        if not math.isclose(
            canonical_total, total_value, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise PricePilotError(
                f"canonical aggregation changed the index at {period}"
            )
        index_rows.append(
            {
                "index_id": spec.universe_id,
                "period": period,
                "value": total_value,
                "status": "COMPLETE",
                "reference_period": reference_period,
                "classification_id": spec.classification_id,
                "classification_version": spec.classification_version,
                "mapping_id": spec.mapping_id,
                "covered_world_weight_before_normalization": covered_world_weight,
                "external_world_weight": external_world_weight,
                "normalization_rule": spec.normalization_rule,
                "universe_fixed": True,
                "aggregation_mode": "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES",
                "fx_treatment": "NOT_INCLUDED",
                "experimental": True,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            }
        )
        for evidence in PriceEvidenceClass:
            evidence_rows.append(
                {
                    "index_id": spec.universe_id,
                    "period": period,
                    "price_evidence_class": evidence.value,
                    "fixed_universe_weight_share": (
                        1.0
                        if evidence is PriceEvidenceClass.P1_OFFICIAL_CATEGORY
                        else 0.0
                    ),
                }
            )

    reference_value = float(index_rows[0]["value"])
    if not math.isclose(reference_value, 100.0, rel_tol=1e-9, abs_tol=1e-9):
        raise PricePilotError(f"reference-period index is not 100: {reference_value}")

    rejected_rows: list[dict[str, object]] = []
    common_set = set(common_periods)
    for period in calendar:
        if period in common_set:
            continue
        missing = [
            f"{economy}:{category}"
            for economy in passing
            for category in SOURCE_CATEGORIES
            if (economy, category, period) not in price_by_key
        ]
        rejected_rows.append(
            {
                "period": period,
                "reason": (
                    "OUTSIDE_LARGEST_COMMON_COMPLETE_INTERVAL"
                    if not missing
                    else "INCOMPLETE_FIXED_UNIVERSE_MONTH"
                ),
                "missing_cell_count": len(missing),
                "missing_cells": "|".join(missing),
            }
        )
    for economy in sorted(set(candidate_economies) - set(passing)):
        rejected_rows.append(
            {
                "period": "",
                "reason": "ECONOMY_FAILED_MINIMUM_COMPLETE_MONTH_GATE",
                "missing_cell_count": "",
                "missing_cells": economy,
            }
        )

    mapping_rows = mapping_audit_rows(classification_bundle)
    summary = {
        "universe_id": spec.universe_id,
        "status": "EXPERIMENTAL_EUROSTAT_ARMILAR_CATEGORY_PILOT",
        "economy_count": len(spec.economies),
        "category_count": len(spec.categories),
        "source_category_count": len(spec.source_categories),
        "canonical_cell_count": len(spec.economies) * len(spec.categories),
        "source_cell_count": len(source_universe_cells),
        "period_count": len(common_periods),
        "start_period": spec.start_period,
        "end_period": spec.end_period,
        "reference_period": reference_period,
        "classification_id": spec.classification_id,
        "classification_version": spec.classification_version,
        "classification_sha256": spec.classification_sha256,
        "mapping_id": spec.mapping_id,
        "mapping_sha256": spec.mapping_sha256,
        "source_classification": spec.source_classification,
        "source_classification_version": spec.source_classification_version,
        "covered_world_weight_before_normalization": covered_world_weight,
        "external_world_weight": external_world_weight,
        "normalization_rule": spec.normalization_rule,
        "universe_fixed": True,
        "raw_source_detail_preserved": True,
        "canonical_aggregation_changes_total_index": False,
        "concept_alignment_status": spec.concept_alignment_status,
        "silent_monthly_renormalisation_allowed": False,
        "future_observation_use_allowed": False,
        "rejected_period_count": len(
            [row for row in rejected_rows if row["period"]]
        ),
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    return (
        spec,
        index_rows,
        canonical_contribution_rows,
        source_contribution_rows,
        evidence_rows,
        rejected_rows,
        mapping_rows,
        summary,
    )


def write_eurostat_pilot_outputs(
    spec: PriceUniverseSpec,
    index_rows: list[dict[str, object]],
    contribution_rows: list[dict[str, object]],
    source_contribution_rows: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
    rejected_rows: list[dict[str, object]],
    mapping_rows: list[dict[str, object]],
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    spec.validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    universe_payload = asdict(spec)
    universe_payload["economies"] = list(spec.economies)
    universe_payload["categories"] = list(spec.categories)
    universe_payload["source_categories"] = list(spec.source_categories)
    universe_payload["allowed_sources"] = list(spec.allowed_sources)
    (output_dir / "price_universe.json").write_text(
        json.dumps(universe_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_dir / "monthly_index.csv",
        index_rows,
        [
            "index_id",
            "period",
            "value",
            "status",
            "reference_period",
            "classification_id",
            "classification_version",
            "mapping_id",
            "covered_world_weight_before_normalization",
            "external_world_weight",
            "normalization_rule",
            "universe_fixed",
            "aggregation_mode",
            "fx_treatment",
            "experimental",
            "research_release_allowed",
            "monetary_release_allowed",
        ],
    )
    _write_csv(
        output_dir / "index_contributions.csv",
        contribution_rows,
        [
            "index_id",
            "period",
            "economy_code",
            "category_code",
            "world_weight_before_normalization",
            "fixed_universe_weight",
            "price_relative",
            "weighted_index_points",
            "contribution_since_reference",
            "source_category_codes",
            "price_series_ids",
            "mapping_type",
            "price_evidence_class",
        ],
    )
    _write_csv(
        output_dir / "source_category_contributions.csv",
        source_contribution_rows,
        [
            "index_id",
            "period",
            "economy_code",
            "source_category_code",
            "armilar_category",
            "mapping_type",
            "world_weight_before_normalization",
            "fixed_universe_weight",
            "price_relative",
            "weighted_index_points",
            "contribution_since_reference",
            "price_series_id",
            "price_evidence_class",
        ],
    )
    _write_csv(
        output_dir / "classification_mapping_audit.csv",
        mapping_rows,
        [
            "mapping_id",
            "source_provider",
            "source_classification",
            "source_classification_version",
            "source_code",
            "source_label",
            "armilar_category",
            "mapping_type",
            "effective_from",
            "effective_to",
            "strict_pilot_admissible",
            "bridge_status",
            "classification_id",
            "classification_version",
            "classification_sha256",
            "mapping_sha256",
            "notes",
        ],
    )
    _write_csv(
        output_dir / "price_evidence_coverage.csv",
        evidence_rows,
        [
            "index_id",
            "period",
            "price_evidence_class",
            "fixed_universe_weight_share",
        ],
    )
    _write_csv(
        output_dir / "rejected_periods.csv",
        rejected_rows,
        ["period", "reason", "missing_cell_count", "missing_cells"],
    )
    (output_dir / "monthly_index_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    names = [
        "price_universe.json",
        "monthly_index.csv",
        "index_contributions.csv",
        "source_category_contributions.csv",
        "classification_mapping_audit.csv",
        "price_evidence_coverage.csv",
        "monthly_index_summary.json",
        "rejected_periods.csv",
    ]
    entries = [
        f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()} {name}"
        for name in names
    ]
    (output_dir / "MANIFEST.sha256").write_text(
        "\n".join(entries) + "\n", encoding="utf-8"
    )
    return summary


def build_eurostat_pilot_from_files(
    world_weights_path: Path,
    selected_prices_path: Path,
    reference_period: str,
    output_dir: Path,
    *,
    classification_path: Path,
    mapping_path: Path,
    minimum_complete_months: int = 2,
) -> dict[str, object]:
    try:
        bundle = load_classification_bundle(classification_path, mapping_path)
    except ClassificationError as exc:
        raise PricePilotError(f"invalid canonical classification: {exc}") from exc
    result = build_eurostat_category_pilot(
        load_world_weights(world_weights_path),
        load_normalized_prices(selected_prices_path),
        reference_period,
        bundle,
        minimum_complete_months=minimum_complete_months,
    )
    return write_eurostat_pilot_outputs(*result, output_dir)


def _write_csv(
    path: Path, rows: list[dict[str, object]], fieldnames: list[str]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "" if row.get(key) is None else row.get(key, "")
                    for key in fieldnames
                }
            )
