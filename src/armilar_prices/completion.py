from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Iterable, Mapping, Sequence

getcontext().prec = 40

DIRECT_CLASSES = {"P1_OFFICIAL_CATEGORY", "P2_OFFICIAL_COMPATIBLE_AGGREGATE"}
HEADLINE_CLASS = "P3_OFFICIAL_HEADLINE"
FALLBACK_CLASSES = {"P3_OFFICIAL_HEADLINE", "P4_REGIONAL_PATTERN", "P5_WORLD_PATTERN"}
ALL_CLASSES = DIRECT_CLASSES | FALLBACK_CLASSES
HEADLINE_CATEGORY = "HEADLINE"
MODEL_VERSION = "price-completion-v0.8.4"


class PriceCompletionError(ValueError):
    pass


@dataclass(frozen=True)
class WeightCell:
    economy_code: str
    category_code: str
    world_weight: Decimal


@dataclass(frozen=True)
class EconomyProfile:
    economy_code: str
    region: str
    income_group: str
    characteristics: tuple[str, ...]
    covariates: tuple[tuple[str, Decimal], ...] = ()

    @property
    def covariate_map(self) -> dict[str, Decimal]:
        return dict(self.covariates)


@dataclass(frozen=True)
class ObservedPrice:
    economy_code: str
    category_code: str
    period: str
    price_relative: Decimal
    evidence_class: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompletionPolicy:
    policy_version: str
    required_categories: tuple[str, ...]
    minimum_region_donors: int
    minimum_world_donors: int
    maximum_donors: int
    interval_lower_quantile: Decimal
    interval_upper_quantile: Decimal
    p3_default_half_width: Decimal
    validation_horizons: tuple[int, ...]
    research_release_allowed: bool
    monetary_release_allowed: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "CompletionPolicy":
        required = tuple(str(value).strip() for value in payload.get("required_categories", []))
        if not required or len(set(required)) != len(required):
            raise PriceCompletionError("required_categories must be non-empty and unique")
        if any(not code.startswith("ARM") for code in required):
            raise PriceCompletionError("v0.8.4 requires canonical ARM categories")
        try:
            policy = cls(
                policy_version=str(payload["policy_version"]),
                required_categories=required,
                minimum_region_donors=int(payload.get("minimum_region_donors", 2)),
                minimum_world_donors=int(payload.get("minimum_world_donors", 3)),
                maximum_donors=int(payload.get("maximum_donors", 20)),
                interval_lower_quantile=Decimal(str(payload.get("interval_lower_quantile", "0.10"))),
                interval_upper_quantile=Decimal(str(payload.get("interval_upper_quantile", "0.90"))),
                p3_default_half_width=Decimal(str(payload.get("p3_default_half_width", "0.03"))),
                validation_horizons=tuple(int(value) for value in payload.get("validation_horizons", [1, 3, 6, 12])),
                research_release_allowed=bool(payload.get("research_release_allowed", False)),
                monetary_release_allowed=bool(payload.get("monetary_release_allowed", False)),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise PriceCompletionError(f"invalid completion policy: {exc}") from exc
        if policy.minimum_region_donors < 1 or policy.minimum_world_donors < 1:
            raise PriceCompletionError("donor minimums must be positive")
        if policy.maximum_donors < max(policy.minimum_region_donors, policy.minimum_world_donors):
            raise PriceCompletionError("maximum_donors is below a donor minimum")
        if not (Decimal("0") <= policy.interval_lower_quantile < policy.interval_upper_quantile <= Decimal("1")):
            raise PriceCompletionError("invalid uncertainty quantiles")
        if policy.p3_default_half_width <= 0:
            raise PriceCompletionError("p3_default_half_width must be positive")
        if not policy.validation_horizons or any(value < 1 for value in policy.validation_horizons):
            raise PriceCompletionError("validation_horizons must be positive")
        if policy.research_release_allowed or policy.monetary_release_allowed:
            raise PriceCompletionError("v0.8.4 release flags must remain false")
        return policy


@dataclass(frozen=True)
class CompletedCell:
    economy_code: str
    category_code: str
    period: str
    central_index: Decimal
    lower_index: Decimal
    upper_index: Decimal
    monthly_change: Decimal
    lower_monthly_change: Decimal
    upper_monthly_change: Decimal
    evidence_class: str
    method_id: str
    source_ids: tuple[str, ...]
    donor_economies: tuple[str, ...]
    donor_selection_rule: str
    observed: bool


@dataclass(frozen=True)
class Prediction:
    central_rate: Decimal
    lower_rate: Decimal
    upper_rate: Decimal
    evidence_class: str
    method_id: str
    source_ids: tuple[str, ...]
    donor_economies: tuple[str, ...]
    donor_selection_rule: str


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise PriceCompletionError(f"invalid decimal for {label}: {value!r}") from exc
    if not result.is_finite():
        raise PriceCompletionError(f"non-finite decimal for {label}")
    return result


def _validate_period(period: str) -> None:
    if len(period) != 7 or period[4] != "-" or not period[:4].isdigit() or not period[5:].isdigit():
        raise PriceCompletionError(f"invalid monthly period: {period}")
    month = int(period[5:])
    if month < 1 or month > 12:
        raise PriceCompletionError(f"invalid monthly period: {period}")


def _next_period(period: str) -> str:
    year = int(period[:4])
    month = int(period[5:])
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _period_range(start: str, end: str) -> list[str]:
    _validate_period(start)
    _validate_period(end)
    if end < start:
        raise PriceCompletionError("end period precedes reference period")
    result = [start]
    while result[-1] < end:
        result.append(_next_period(result[-1]))
    if result[-1] != end:
        raise PriceCompletionError("period range is not monthly")
    return result


def _split_pipe(value: str) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in value.split("|") if item.strip()}))


def _load_category_mapping(path: Path, required_categories: Sequence[str]) -> dict[str, str]:
    required = {"source_code", "armilar_category", "mapping_type", "strict_pilot_admissible"}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise PriceCompletionError(f"classification mapping missing columns: {sorted(required)}")
        result: dict[str, str] = {}
        for raw in reader:
            source = raw["source_code"].strip().upper()
            target = raw["armilar_category"].strip().upper()
            admissible = raw["strict_pilot_admissible"].strip().lower() == "true"
            mapping_type = raw["mapping_type"].strip().upper()
            if not admissible:
                continue
            if mapping_type not in {"EXACT_ONE_TO_ONE", "EXACT_MERGE"}:
                raise PriceCompletionError(f"non-exact weight mapping is not admissible: {source}")
            if target not in required_categories:
                raise PriceCompletionError(f"mapping target outside completion policy: {target}")
            if source in result and result[source] != target:
                raise PriceCompletionError(f"ambiguous source category mapping: {source}")
            result[source] = target
    if not result:
        raise PriceCompletionError("classification mapping has no admissible rows")
    return result


def load_weights(
    path: Path,
    required_categories: Sequence[str],
    mapping_path: Path | None = None,
) -> list[WeightCell]:
    required = {"economy_code", "category_code"}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise PriceCompletionError(f"weights file missing columns: {sorted(required)}")
        weight_field = next(
            (name for name in ("world_weight", "weight", "weight_central") if name in reader.fieldnames),
            None,
        )
        if weight_field is None:
            raise PriceCompletionError("weights file requires world_weight, weight or weight_central")
        raw_rows = list(reader)
    if not raw_rows:
        raise PriceCompletionError("weights file is empty")

    source_categories = {raw["category_code"].strip().upper() for raw in raw_rows}
    direct_canonical = source_categories.issubset(set(required_categories))
    mapping: dict[str, str] = {}
    if not direct_canonical:
        if mapping_path is None:
            raise PriceCompletionError("source-category weights require a classification mapping")
        mapping = _load_category_mapping(mapping_path, required_categories)

    aggregated: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    seen_source: set[tuple[str, str]] = set()
    for raw in raw_rows:
        economy = raw["economy_code"].strip().upper()
        source_category = raw["category_code"].strip().upper()
        source_key = (economy, source_category)
        if not economy or source_key in seen_source:
            raise PriceCompletionError(f"duplicate or invalid source weight cell: {source_key}")
        seen_source.add(source_key)
        if direct_canonical:
            category = source_category
        else:
            category = mapping.get(source_category, "")
            if not category:
                raise PriceCompletionError(f"unmapped source weight category: {source_category}")
        weight = _decimal(raw[weight_field], f"{weight_field} {source_key}")
        if weight <= 0:
            raise PriceCompletionError(f"non-positive world weight: {source_key}")
        aggregated[(economy, category)] += weight

    rows = [WeightCell(economy, category, value) for (economy, category), value in aggregated.items()]
    economies = sorted({row.economy_code for row in rows})
    expected = {(economy, category) for economy in economies for category in required_categories}
    actual = {(row.economy_code, row.category_code) for row in rows}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        detail = f"missing={missing[:1]} extra={extra[:1]}"
        raise PriceCompletionError(f"incomplete canonical world weight grid: {detail}")
    total = sum((row.world_weight for row in rows), Decimal("0"))
    if abs(total - Decimal("1")) > Decimal("0.000000000001"):
        raise PriceCompletionError(f"world weights must sum to one, found {total}")
    return sorted(rows, key=lambda row: (row.economy_code, row.category_code))


def load_profiles(path: Path, economies: Sequence[str]) -> dict[str, EconomyProfile]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if "economy_code" not in fieldnames or "income_group" not in fieldnames:
            raise PriceCompletionError("profiles file requires economy_code and income_group")
        region_field = "region_code" if "region_code" in fieldnames else "region" if "region" in fieldnames else None
        if region_field is None:
            raise PriceCompletionError("profiles file requires region_code or region")
        reserved = {"economy_code", "region_code", "region", "income_group", "total_real_expenditure", "characteristics"}
        covariate_names = tuple(sorted(name for name in fieldnames if name not in reserved))
        result: dict[str, EconomyProfile] = {}
        for line_number, raw in enumerate(reader, start=2):
            economy = raw["economy_code"].strip().upper()
            if economy in result:
                raise PriceCompletionError(f"duplicate economy profile: {economy}")
            covariates: list[tuple[str, Decimal]] = []
            for name in covariate_names:
                value = (raw.get(name) or "").strip()
                if value:
                    covariates.append((name, _decimal(value, f"profile covariate {economy}/{name}")))
            if raw.get("total_real_expenditure") and raw["total_real_expenditure"].strip():
                total = _decimal(raw["total_real_expenditure"], f"total_real_expenditure {economy}")
                if total <= 0:
                    raise PriceCompletionError(f"total_real_expenditure must be positive: {economy}")
            profile = EconomyProfile(
                economy_code=economy,
                region=raw[region_field].strip().upper(),
                income_group=raw["income_group"].strip().upper(),
                characteristics=_split_pipe(raw.get("characteristics") or ""),
                covariates=tuple(covariates),
            )
            if not profile.economy_code or not profile.region or not profile.income_group:
                raise PriceCompletionError(f"incomplete economy profile at line {line_number}: {economy}")
            result[economy] = profile
    missing = sorted(set(economies) - set(result))
    if missing:
        raise PriceCompletionError(f"missing economy profile: {missing[0]}")
    extra = sorted(set(result) - set(economies))
    if extra:
        raise PriceCompletionError(f"profile has economy outside weights: {extra[0]}")
    return result


def _canonical_evidence_class(value: str) -> str:
    normalized = value.strip().upper()
    if normalized.startswith("P1_"):
        return "P1_OFFICIAL_CATEGORY"
    if normalized.startswith("P2_"):
        return "P2_OFFICIAL_COMPATIBLE_AGGREGATE"
    if normalized.startswith("P3_"):
        return "P3_OFFICIAL_HEADLINE"
    raise PriceCompletionError(f"unsupported input evidence class: {value!r}")


def load_observations(path: Path, categories: Sequence[str], economies: Sequence[str]) -> list[ObservedPrice]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        required = {"economy_code", "category_code", "period"}
        if not required.issubset(fieldnames):
            raise PriceCompletionError(f"observations file missing columns: {sorted(required)}")
        price_field = next((name for name in ("price_relative", "price_index") if name in fieldnames), None)
        evidence_field = next((name for name in ("evidence_class", "price_evidence_class") if name in fieldnames), None)
        source_field = next((name for name in ("source_ids", "price_series_ids", "series_id") if name in fieldnames), None)
        if price_field is None or evidence_field is None or source_field is None:
            raise PriceCompletionError(
                "observations file requires a price field, evidence field and source-id field"
            )
        rows: list[ObservedPrice] = []
        seen: set[tuple[str, str, str]] = set()
        for raw in reader:
            economy = raw["economy_code"].strip().upper()
            category = raw["category_code"].strip().upper()
            period = raw["period"].strip()
            evidence = _canonical_evidence_class(raw[evidence_field])
            key = (economy, category, period)
            _validate_period(period)
            if key in seen:
                raise PriceCompletionError(f"duplicate observed price cell: {key}")
            seen.add(key)
            if economy not in economies:
                raise PriceCompletionError(f"observation economy outside weights: {economy}")
            if category == HEADLINE_CATEGORY:
                if evidence != HEADLINE_CLASS:
                    raise PriceCompletionError(f"headline must use {HEADLINE_CLASS}: {key}")
            elif category in categories:
                if evidence not in DIRECT_CLASSES:
                    raise PriceCompletionError(f"category observation must be P1 or P2: {key}")
            else:
                raise PriceCompletionError(f"unknown observation category: {category}")
            value = _decimal(raw[price_field], f"{price_field} {key}")
            if value <= 0:
                raise PriceCompletionError(f"non-positive price relative: {key}")
            sources = _split_pipe(raw[source_field])
            if not sources:
                raise PriceCompletionError(f"source identifiers required: {key}")
            rows.append(ObservedPrice(economy, category, period, value, evidence, sources))
    if not rows:
        raise PriceCompletionError("observations file is empty")
    return sorted(rows, key=lambda row: (row.period, row.economy_code, row.category_code))


def load_policy(path: Path) -> CompletionPolicy:
    return CompletionPolicy.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _weighted_quantile(values: Sequence[tuple[Decimal, Decimal]], quantile: Decimal) -> Decimal:
    if not values:
        raise PriceCompletionError("weighted quantile requires values")
    ordered = sorted(values, key=lambda item: (item[0], item[1]))
    total = sum((weight for _, weight in ordered), Decimal("0"))
    if total <= 0:
        raise PriceCompletionError("weighted quantile requires positive weights")
    threshold = total * quantile
    cumulative = Decimal("0")
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _weighted_median(values: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    return _weighted_quantile(values, Decimal("0.5"))


def _covariate_scales(profiles: Mapping[str, EconomyProfile]) -> dict[str, Decimal]:
    values: dict[str, list[Decimal]] = defaultdict(list)
    for profile in profiles.values():
        for name, value in profile.covariates:
            values[name].append(value)
    result: dict[str, Decimal] = {}
    for name, rows in values.items():
        spread = max(rows) - min(rows)
        result[name] = spread if spread > 0 else Decimal("1")
    return result


def _covariate_distance(
    target: EconomyProfile,
    donor: EconomyProfile,
    scales: Mapping[str, Decimal],
) -> Decimal:
    left = target.covariate_map
    right = donor.covariate_map
    names = sorted(set(left) | set(right))
    if not names:
        return Decimal("0")
    distance = Decimal("0")
    for name in names:
        if name not in left or name not in right:
            distance += Decimal("1")
            continue
        distance += abs(left[name] - right[name]) / scales.get(name, Decimal("1"))
    return distance / Decimal(len(names))


def _similarity_weight(
    target: EconomyProfile,
    donor: EconomyProfile,
    donor_world_weight: Decimal,
    scales: Mapping[str, Decimal],
) -> Decimal:
    overlap = len(set(target.characteristics) & set(donor.characteristics))
    multiplier = Decimal("1") + (Decimal("1") if target.income_group == donor.income_group else Decimal("0")) + Decimal(overlap)
    return donor_world_weight * multiplier / (Decimal("1") + _covariate_distance(target, donor, scales))


def _observation_maps(observations: Iterable[ObservedPrice]) -> tuple[dict[tuple[str, str, str], ObservedPrice], dict[tuple[str, str], list[str]]]:
    by_key = {(row.economy_code, row.category_code, row.period): row for row in observations}
    periods: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in observations:
        periods[(row.economy_code, row.category_code)].append(row.period)
    return by_key, {key: sorted(set(values)) for key, values in periods.items()}


def _monthly_rate(by_key: Mapping[tuple[str, str, str], ObservedPrice], economy: str, category: str, period: str) -> Decimal | None:
    previous = _previous_period(period)
    current_row = by_key.get((economy, category, period))
    previous_row = by_key.get((economy, category, previous))
    if current_row is None or previous_row is None:
        return None
    return current_row.price_relative / previous_row.price_relative - Decimal("1")


def _previous_period(period: str) -> str:
    year = int(period[:4])
    month = int(period[5:])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _donor_world_weights(weights: Sequence[WeightCell]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in weights:
        result[row.economy_code] += row.world_weight
    return dict(result)


def _donor_residuals(
    *,
    target_economy: str,
    category: str,
    period: str,
    by_key: Mapping[tuple[str, str, str], ObservedPrice],
    profiles: Mapping[str, EconomyProfile],
    economy_weights: Mapping[str, Decimal],
    same_region_only: bool,
    maximum_donors: int,
) -> list[tuple[str, Decimal, Decimal, tuple[str, ...]]]:
    target_profile = profiles[target_economy]
    scales = _covariate_scales(profiles)
    candidates: list[tuple[int, int, str, Decimal, Decimal, tuple[str, ...]]] = []
    for donor, profile in profiles.items():
        if donor == target_economy:
            continue
        if same_region_only and profile.region != target_profile.region:
            continue
        category_rate = _monthly_rate(by_key, donor, category, period)
        headline_rate = _monthly_rate(by_key, donor, HEADLINE_CATEGORY, period)
        if category_rate is None or headline_rate is None:
            continue
        category_row = by_key[(donor, category, period)]
        if category_row.evidence_class not in DIRECT_CLASSES:
            continue
        overlap = len(set(target_profile.characteristics) & set(profile.characteristics))
        income_match = 1 if target_profile.income_group == profile.income_group else 0
        weight = _similarity_weight(target_profile, profile, economy_weights[donor], scales)
        sources = tuple(sorted(set(category_row.source_ids + by_key[(donor, HEADLINE_CATEGORY, period)].source_ids)))
        candidates.append((-income_match, -overlap, donor, category_rate - headline_rate, weight, sources))
    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    selected = candidates[:maximum_donors]
    return [(donor, residual, weight, sources) for _, _, donor, residual, weight, sources in selected]


def _historical_residuals(
    *,
    target_economy: str,
    category: str,
    period: str,
    by_key: Mapping[tuple[str, str, str], ObservedPrice],
    profiles: Mapping[str, EconomyProfile],
    economy_weights: Mapping[str, Decimal],
) -> list[tuple[Decimal, Decimal]]:
    values: list[tuple[Decimal, Decimal]] = []
    target_profile = profiles[target_economy]
    scales = _covariate_scales(profiles)
    for donor, donor_profile in profiles.items():
        if donor == target_economy:
            continue
        for candidate_period in sorted({key[2] for key in by_key if key[0] == donor and key[1] == category}):
            if candidate_period > period:
                continue
            category_rate = _monthly_rate(by_key, donor, category, candidate_period)
            headline_rate = _monthly_rate(by_key, donor, HEADLINE_CATEGORY, candidate_period)
            if category_rate is None or headline_rate is None:
                continue
            weight = _similarity_weight(target_profile, donor_profile, economy_weights[donor], scales)
            values.append((category_rate - headline_rate, weight))
    return values


def predict_monthly_rate(
    *,
    target_economy: str,
    category: str,
    period: str,
    by_key: Mapping[tuple[str, str, str], ObservedPrice],
    profiles: Mapping[str, EconomyProfile],
    economy_weights: Mapping[str, Decimal],
    policy: CompletionPolicy,
) -> Prediction:
    headline_rate = _monthly_rate(by_key, target_economy, HEADLINE_CATEGORY, period)
    if headline_rate is None:
        raise PriceCompletionError(
            f"target headline missing for {target_economy}/{period}; P3-P5 cannot preserve target headline"
        )
    headline_sources = tuple(sorted(set(
        by_key[(target_economy, HEADLINE_CATEGORY, period)].source_ids
        + by_key[(target_economy, HEADLINE_CATEGORY, _previous_period(period))].source_ids
    )))

    regional = _donor_residuals(
        target_economy=target_economy,
        category=category,
        period=period,
        by_key=by_key,
        profiles=profiles,
        economy_weights=economy_weights,
        same_region_only=True,
        maximum_donors=policy.maximum_donors,
    )
    if len(regional) >= policy.minimum_region_donors:
        residuals = [(residual, weight) for _, residual, weight, _ in regional]
        median = _weighted_median(residuals)
        lower = _weighted_quantile(residuals, policy.interval_lower_quantile)
        upper = _weighted_quantile(residuals, policy.interval_upper_quantile)
        donors = tuple(row[0] for row in regional)
        donor_sources = tuple(sorted({source for row in regional for source in row[3]}))
        return Prediction(
            headline_rate + median,
            headline_rate + min(lower, median),
            headline_rate + max(upper, median),
            "P4_REGIONAL_PATTERN",
            "HEADLINE_PLUS_WEIGHTED_MEDIAN_REGIONAL_DEVIATION_V0.8.4",
            tuple(sorted(set(headline_sources + donor_sources))),
            donors,
            "same_region; rank income_match, characteristic_overlap, economy_code; no target values",
        )

    world = _donor_residuals(
        target_economy=target_economy,
        category=category,
        period=period,
        by_key=by_key,
        profiles=profiles,
        economy_weights=economy_weights,
        same_region_only=False,
        maximum_donors=policy.maximum_donors,
    )
    if len(world) >= policy.minimum_world_donors:
        residuals = [(residual, weight) for _, residual, weight, _ in world]
        median = _weighted_median(residuals)
        lower = _weighted_quantile(residuals, policy.interval_lower_quantile)
        upper = _weighted_quantile(residuals, policy.interval_upper_quantile)
        donors = tuple(row[0] for row in world)
        donor_sources = tuple(sorted({source for row in world for source in row[3]}))
        return Prediction(
            headline_rate + median,
            headline_rate + min(lower, median),
            headline_rate + max(upper, median),
            "P5_WORLD_PATTERN",
            "HEADLINE_PLUS_WEIGHTED_MEDIAN_WORLD_DEVIATION_V0.8.4",
            tuple(sorted(set(headline_sources + donor_sources))),
            donors,
            "world_pool; rank income_match, characteristic_overlap, economy_code; no target values",
        )

    history = _historical_residuals(
        target_economy=target_economy,
        category=category,
        period=period,
        by_key=by_key,
        profiles=profiles,
        economy_weights=economy_weights,
    )
    if history:
        lower_residual = _weighted_quantile(history, policy.interval_lower_quantile)
        upper_residual = _weighted_quantile(history, policy.interval_upper_quantile)
        lower_rate = headline_rate + min(lower_residual, Decimal("0"))
        upper_rate = headline_rate + max(upper_residual, Decimal("0"))
        method = "TARGET_HEADLINE_WITH_HISTORICAL_CATEGORY_RESIDUAL_INTERVAL_V0.8.4"
    else:
        lower_rate = headline_rate - policy.p3_default_half_width
        upper_rate = headline_rate + policy.p3_default_half_width
        method = "TARGET_HEADLINE_WITH_EXPLICIT_UNCALIBRATED_INTERVAL_V0.8.4"
    return Prediction(
        headline_rate,
        lower_rate,
        upper_rate,
        "P3_OFFICIAL_HEADLINE",
        method,
        headline_sources,
        (),
        "no admissible donor pool; target official headline only",
    )


def complete_price_grid(
    weights: Sequence[WeightCell],
    profiles: Mapping[str, EconomyProfile],
    observations: Sequence[ObservedPrice],
    reference_period: str,
    policy: CompletionPolicy,
) -> tuple[list[CompletedCell], list[dict[str, object]], dict[str, object]]:
    _validate_period(reference_period)
    categories = list(policy.required_categories)
    economies = sorted({row.economy_code for row in weights})
    if set(profiles) != set(economies):
        raise PriceCompletionError("profiles and world-weight economies differ")
    by_key, _ = _observation_maps(observations)
    latest_period = max(row.period for row in observations)
    periods = _period_range(reference_period, latest_period)
    economy_weights = _donor_world_weights(weights)
    weight_map = {(row.economy_code, row.category_code): row.world_weight for row in weights}

    for economy in economies:
        if (economy, HEADLINE_CATEGORY, reference_period) not in by_key:
            raise PriceCompletionError(f"reference headline missing: {economy}/{reference_period}")

    completed: list[CompletedCell] = []
    completed_map: dict[tuple[str, str, str], CompletedCell] = {}
    audit: list[dict[str, object]] = []

    for period_index, period in enumerate(periods):
        for economy in economies:
            for category in categories:
                direct = by_key.get((economy, category, period))
                direct_reference = by_key.get((economy, category, reference_period))
                if period == reference_period:
                    if direct is not None:
                        evidence = direct.evidence_class
                        sources = direct.source_ids
                        observed = True
                        method = "OFFICIAL_REFERENCE_REBASE_100"
                    else:
                        headline = by_key[(economy, HEADLINE_CATEGORY, reference_period)]
                        evidence = HEADLINE_CLASS
                        sources = headline.source_ids
                        observed = False
                        method = "REFERENCE_NORMALISATION_100_WITHOUT_CATEGORY_OBSERVATION"
                    cell = CompletedCell(
                        economy, category, period,
                        Decimal("100"), Decimal("100"), Decimal("100"),
                        Decimal("0"), Decimal("0"), Decimal("0"),
                        evidence, method, sources, (), "reference period", observed,
                    )
                elif direct is not None and direct_reference is not None:
                    central = direct.price_relative / direct_reference.price_relative * Decimal("100")
                    previous = completed_map[(economy, category, periods[period_index - 1])]
                    monthly = central / previous.central_index - Decimal("1")
                    cell = CompletedCell(
                        economy, category, period,
                        central, central, central,
                        monthly, monthly, monthly,
                        direct.evidence_class,
                        "DIRECT_OFFICIAL_LEVEL_RELATIVE_TO_REFERENCE_V0.8.4",
                        tuple(sorted(set(direct.source_ids + direct_reference.source_ids))),
                        (), "direct official category or compatible aggregate", True,
                    )
                else:
                    prediction = predict_monthly_rate(
                        target_economy=economy,
                        category=category,
                        period=period,
                        by_key=by_key,
                        profiles=profiles,
                        economy_weights=economy_weights,
                        policy=policy,
                    )
                    if prediction.lower_rate <= Decimal("-1"):
                        raise PriceCompletionError(f"lower monthly price change is <= -100%: {economy}/{category}/{period}")
                    previous = completed_map[(economy, category, periods[period_index - 1])]
                    central = previous.central_index * (Decimal("1") + prediction.central_rate)
                    lower = previous.lower_index * (Decimal("1") + prediction.lower_rate)
                    upper = previous.upper_index * (Decimal("1") + prediction.upper_rate)
                    if lower > upper:
                        lower, upper = upper, lower
                    cell = CompletedCell(
                        economy, category, period,
                        central, lower, upper,
                        prediction.central_rate, prediction.lower_rate, prediction.upper_rate,
                        prediction.evidence_class, prediction.method_id, prediction.source_ids,
                        prediction.donor_economies, prediction.donor_selection_rule, False,
                    )
                completed.append(cell)
                completed_map[(economy, category, period)] = cell
                audit.append({
                    "economy_code": economy,
                    "category_code": category,
                    "period": period,
                    "world_weight": weight_map[(economy, category)],
                    "evidence_class": cell.evidence_class,
                    "observed": cell.observed,
                    "method_id": cell.method_id,
                    "model_version": MODEL_VERSION,
                    "source_ids": "|".join(cell.source_ids),
                    "donor_economies": "|".join(cell.donor_economies),
                    "donor_selection_rule": cell.donor_selection_rule,
                })

    expected_count = len(economies) * len(categories) * len(periods)
    if len(completed) != expected_count:
        raise PriceCompletionError("completed price grid has an unexpected size")
    summary = {
        "methodology_version": "0.8.4",
        "model_version": MODEL_VERSION,
        "reference_period": reference_period,
        "first_period": periods[0],
        "last_period": periods[-1],
        "economy_count": len(economies),
        "category_count": len(categories),
        "period_count": len(periods),
        "completed_cell_count": len(completed),
        "research_release_allowed": False,
        "monetary_release_allowed": False,
        "status": "EXPERIMENTAL_COMPLETE_GRID",
    }
    return completed, audit, summary


def validate_leave_one_out(
    weights: Sequence[WeightCell],
    profiles: Mapping[str, EconomyProfile],
    observations: Sequence[ObservedPrice],
    reference_period: str,
    policy: CompletionPolicy,
) -> list[dict[str, object]]:
    by_key, _ = _observation_maps(observations)
    economy_weights = _donor_world_weights(weights)
    direct_rows = [row for row in observations if row.category_code in policy.required_categories and row.evidence_class in DIRECT_CLASSES]
    periods = sorted({row.period for row in observations if row.period >= reference_period})
    period_position = {period: index for index, period in enumerate(periods)}
    results: list[dict[str, object]] = []

    for target in sorted(direct_rows, key=lambda row: (row.economy_code, row.category_code, row.period)):
        end_position = period_position.get(target.period)
        if end_position is None:
            continue
        for horizon in policy.validation_horizons:
            start_position = end_position - horizon
            if start_position < 0:
                continue
            start_period = periods[start_position]
            start_direct = by_key.get((target.economy_code, target.category_code, start_period))
            if start_direct is None or start_direct.evidence_class not in DIRECT_CLASSES:
                continue
            predicted = Decimal("100")
            lower = Decimal("100")
            upper = Decimal("100")
            fallback_classes: list[str] = []
            donors: set[str] = set()
            valid = True
            for step_position in range(start_position + 1, end_position + 1):
                step_period = periods[step_position]
                try:
                    prediction = predict_monthly_rate(
                        target_economy=target.economy_code,
                        category=target.category_code,
                        period=step_period,
                        by_key=by_key,
                        profiles=profiles,
                        economy_weights=economy_weights,
                        policy=policy,
                    )
                except PriceCompletionError:
                    valid = False
                    break
                if prediction.lower_rate <= Decimal("-1"):
                    valid = False
                    break
                predicted *= Decimal("1") + prediction.central_rate
                lower *= Decimal("1") + prediction.lower_rate
                upper *= Decimal("1") + prediction.upper_rate
                fallback_classes.append(prediction.evidence_class)
                donors.update(prediction.donor_economies)
            if not valid:
                continue
            actual = target.price_relative / start_direct.price_relative * Decimal("100")
            error = predicted - actual
            if lower > upper:
                lower, upper = upper, lower
            fallback_class = max(fallback_classes, key=lambda value: {"P4_REGIONAL_PATTERN": 1, "P5_WORLD_PATTERN": 2, "P3_OFFICIAL_HEADLINE": 3}[value])
            results.append({
                "economy_code": target.economy_code,
                "region": profiles[target.economy_code].region,
                "category_code": target.category_code,
                "end_period": target.period,
                "horizon_months": horizon,
                "hidden_evidence_class": target.evidence_class,
                "fallback_class": fallback_class,
                "actual_index": actual,
                "predicted_index": predicted,
                "lower_index": lower,
                "upper_index": upper,
                "error": error,
                "absolute_error": abs(error),
                "absolute_percentage_error": abs(error) / abs(actual) * Decimal("100"),
                "interval_covered": lower <= actual <= upper,
                "donor_economies": "|".join(sorted(donors)),
            })
    return results


def _metric_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "observation_count": 0,
            "mae": "",
            "mape_percent": "",
            "rmse": "",
            "bias": "",
            "interval_coverage": "",
        }
    count = Decimal(len(rows))
    errors = [Decimal(str(row["error"])) for row in rows]
    abs_errors = [abs(value) for value in errors]
    apes = [Decimal(str(row["absolute_percentage_error"])) for row in rows]
    mean_squared = sum((value * value for value in errors), Decimal("0")) / count
    return {
        "observation_count": len(rows),
        "mae": sum(abs_errors, Decimal("0")) / count,
        "mape_percent": sum(apes, Decimal("0")) / count,
        "rmse": mean_squared.sqrt(),
        "bias": sum(errors, Decimal("0")) / count,
        "interval_coverage": Decimal(sum(1 for row in rows if bool(row["interval_covered"]))) / count,
    }


def _group_metrics(rows: Sequence[Mapping[str, object]], field: str) -> list[dict[str, object]]:
    groups: dict[object, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    result: list[dict[str, object]] = []
    for key in sorted(groups, key=lambda value: str(value)):
        summary = _metric_summary(groups[key])
        result.append({field: key, **summary})
    return result


def build_global_indices(
    completed: Sequence[CompletedCell],
    weights: Sequence[WeightCell],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    weight_map = {(row.economy_code, row.category_code): row.world_weight for row in weights}
    periods = sorted({row.period for row in completed})
    by_period: dict[str, list[CompletedCell]] = defaultdict(list)
    for row in completed:
        by_period[row.period].append(row)
    expected_per_period = len(weight_map)
    index_rows: list[dict[str, object]] = []
    uncertainty_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    for period in periods:
        rows = by_period[period]
        if len(rows) != expected_per_period:
            raise PriceCompletionError(f"period is incomplete; no renormalisation allowed: {period}")
        central = sum((weight_map[(row.economy_code, row.category_code)] * row.central_index for row in rows), Decimal("0"))
        lower = sum((weight_map[(row.economy_code, row.category_code)] * row.lower_index for row in rows), Decimal("0"))
        upper = sum((weight_map[(row.economy_code, row.category_code)] * row.upper_index for row in rows), Decimal("0"))
        index_rows.append({
            "period": period,
            "index_id": "ARM-GLOBAL-EXPERIMENTAL-PRICE-V0.8.4",
            "index_value": central,
            "research_release_allowed": False,
            "monetary_release_allowed": False,
        })
        uncertainty_rows.append({
            "period": period,
            "index_id": "ARM-GLOBAL-EXPERIMENTAL-PRICE-V0.8.4",
            "central_index": central,
            "lower_index": min(lower, central),
            "upper_index": max(upper, central),
            "interval_method": "WEIGHTED_CELL_BOUNDS_NO_RENORMALISATION",
        })
        evidence_weight: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in rows:
            evidence_weight[row.evidence_class] += weight_map[(row.economy_code, row.category_code)]
        for evidence in sorted(ALL_CLASSES):
            coverage_rows.append({
                "period": period,
                "evidence_class": evidence,
                "world_weight": evidence_weight[evidence],
            })
        if abs(sum(evidence_weight.values(), Decimal("0")) - Decimal("1")) > Decimal("0.000000000001"):
            raise PriceCompletionError(f"evidence coverage does not sum to one: {period}")
    return index_rows, uncertainty_rows, coverage_rows


def _format(value: object) -> str:
    if isinstance(value, Decimal):
        text = format(value.quantize(Decimal("0.000000000001")), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format(row.get(field, "")) for field in fieldnames})


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return _format(value)
    raise TypeError(type(value).__name__)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(output_dir: Path, filenames: Sequence[str]) -> None:
    lines = []
    for filename in sorted(filenames):
        content = (output_dir / filename).read_bytes()
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {filename}")
    (output_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_completion_outputs(
    output_dir: Path,
    completed: Sequence[CompletedCell],
    audit: Sequence[Mapping[str, object]],
    validation: Sequence[Mapping[str, object]],
    summary: Mapping[str, object],
    weights: Sequence[WeightCell],
    profiles: Mapping[str, EconomyProfile],
    policy: CompletionPolicy,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    index_rows, global_uncertainty, coverage = build_global_indices(completed, weights)

    cell_rows = [{
        "economy_code": row.economy_code,
        "category_code": row.category_code,
        "period": row.period,
        "price_index": row.central_index,
        "lower_index": row.lower_index,
        "upper_index": row.upper_index,
        "monthly_change": row.monthly_change,
        "evidence_class": row.evidence_class,
        "observed": row.observed,
        "method_id": row.method_id,
        "model_version": MODEL_VERSION,
        "source_ids": "|".join(row.source_ids),
        "donor_economies": "|".join(row.donor_economies),
    } for row in completed]
    uncertainty_rows = [{
        "economy_code": row.economy_code,
        "category_code": row.category_code,
        "period": row.period,
        "central_index": row.central_index,
        "lower_index": row.lower_index,
        "upper_index": row.upper_index,
        "interval_width": row.upper_index - row.lower_index,
        "central_monthly_change": row.monthly_change,
        "lower_monthly_change": row.lower_monthly_change,
        "upper_monthly_change": row.upper_monthly_change,
        "evidence_class": row.evidence_class,
    } for row in completed]

    by_category = _group_metrics(validation, "category_code")
    by_region = _group_metrics(validation, "region")
    by_horizon = _group_metrics(validation, "horizon_months")
    by_fallback = _group_metrics(validation, "fallback_class")
    validation_summary = {
        "methodology_version": "0.8.4",
        "model_version": MODEL_VERSION,
        "validation_method": "LEAVE_ONE_ECONOMY_OUT_HIDE_P1_P2_RECONSTRUCT_P3_P4_P5",
        "overall": _metric_summary(validation),
        "by_category": by_category,
        "by_region": by_region,
        "by_horizon": by_horizon,
        "by_fallback_class": by_fallback,
        "donor_selection_uses_hidden_target_value": False,
        "future_period_observations_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    complete_summary = {
        **summary,
        "policy_version": policy.policy_version,
        "validation_observation_count": len(validation),
        "index_period_count": len(index_rows),
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }

    files: dict[str, tuple[list[str], Iterable[Mapping[str, object]]]] = {
        "monthly_price_cells_complete.csv": (list(cell_rows[0].keys()), cell_rows),
        "monthly_price_uncertainty.csv": (list(uncertainty_rows[0].keys()), uncertainty_rows),
        "price_imputation_audit.csv": (list(audit[0].keys()), audit),
        "price_validation_by_category.csv": (list(by_category[0].keys()) if by_category else ["category_code", "observation_count", "mae", "mape_percent", "rmse", "bias", "interval_coverage"], by_category),
        "price_validation_by_region.csv": (list(by_region[0].keys()) if by_region else ["region", "observation_count", "mae", "mape_percent", "rmse", "bias", "interval_coverage"], by_region),
        "price_validation_by_horizon.csv": (list(by_horizon[0].keys()) if by_horizon else ["horizon_months", "observation_count", "mae", "mape_percent", "rmse", "bias", "interval_coverage"], by_horizon),
        "price_validation_by_fallback.csv": (list(by_fallback[0].keys()) if by_fallback else ["fallback_class", "observation_count", "mae", "mape_percent", "rmse", "bias", "interval_coverage"], by_fallback),
        "monthly_global_experimental_index.csv": (list(index_rows[0].keys()), index_rows),
        "monthly_global_index_uncertainty.csv": (list(global_uncertainty[0].keys()), global_uncertainty),
        "price_evidence_coverage.csv": (list(coverage[0].keys()), coverage),
    }
    written: list[str] = []
    for filename, (fields, rows) in files.items():
        _write_csv(output_dir / filename, fields, rows)
        written.append(filename)

    (output_dir / "price_validation_summary.json").write_text(
        json.dumps(validation_summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written.append("price_validation_summary.json")
    (output_dir / "price_completion_summary.json").write_text(
        json.dumps(complete_summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written.append("price_completion_summary.json")
    _write_manifest(output_dir, written)
    return complete_summary


def build_global_completion_from_files(
    weights_path: Path,
    observations_path: Path,
    profiles_path: Path,
    policy_path: Path,
    reference_period: str,
    output_dir: Path,
    mapping_path: Path | None = None,
) -> dict[str, object]:
    policy = load_policy(policy_path)
    weights = load_weights(weights_path, policy.required_categories, mapping_path)
    economies = sorted({row.economy_code for row in weights})
    profiles = load_profiles(profiles_path, economies)
    observations = load_observations(observations_path, policy.required_categories, economies)
    completed, audit, summary = complete_price_grid(
        weights, profiles, observations, reference_period, policy
    )
    validation = validate_leave_one_out(
        weights, profiles, observations, reference_period, policy
    )
    input_hashes = {
        "weights_global_sha256": _sha256_file(weights_path),
        "observed_prices_sha256": _sha256_file(observations_path),
        "economy_profiles_sha256": _sha256_file(profiles_path),
        "completion_policy_sha256": _sha256_file(policy_path),
    }
    if mapping_path is not None:
        input_hashes["classification_mapping_sha256"] = _sha256_file(mapping_path)
    summary = {
        **summary,
        "input_hashes": input_hashes,
        "input_provenance_complete": True,
        "methodology_changes_allowed_silently": False,
    }
    return write_completion_outputs(
        output_dir, completed, audit, validation, summary, weights, profiles, policy
    )
