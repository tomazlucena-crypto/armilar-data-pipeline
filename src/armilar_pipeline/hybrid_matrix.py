from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Iterable

from .config import Step2Config
from .measures import MeasureSelection
from .supplemental import NominalObservation, select_nominal_sources
from .worldbank import DimensionRoles, Observation, Variable


CATEGORIES = [f"CP{i:02d}" for i in range(1, 13)]
DIRECT_CATEGORIES = {"CP01", "CP02", "CP03", "CP05", "CP07", "CP08", "CP11"}
PROXY_CATEGORIES = {"CP04", "CP06", "CP09", "CP10", "CP12"}


@dataclass
class HybridMatrixResult:
    normalized_source90_rows: list[dict[str, Any]]
    supplemental_nominal_rows: list[dict[str, Any]]
    nominal_selection_audit_rows: list[dict[str, Any]]
    unit_reconciliation_rows: list[dict[str, Any]]
    category_rows: list[dict[str, Any]]
    all_category_rows: list[dict[str, Any]]
    missing_rows: list[dict[str, Any]]
    exclusion_rows: list[dict[str, Any]]
    economy_registry_rows: list[dict[str, Any]]
    weight_rows: list[dict[str, Any]]
    economy_weight_rows: list[dict[str, Any]]
    category_weight_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def build_hybrid_matrix(
    config: Step2Config,
    roles: DimensionRoles,
    observations: list[Observation],
    inventories: dict[str, list[Variable]],
    measures: MeasureSelection,
    participant_codes: dict[str, str],
    supplemental_observations: Iterable[NominalObservation],
) -> HybridMatrixResult:
    country_vars = {item.variable_id: item for item in inventories[roles.country]}
    heading_vars = {item.variable_id: item for item in inventories[roles.heading]}
    measure_vars = {item.variable_id: item for item in inventories[roles.measure]}
    selected_measures = {measures.ppp_id: "PPP", measures.nominal_id: "NOMINAL", measures.real_id: "REAL"}

    raw: dict[tuple[str, str, str], Observation] = {}
    duplicate_keys: list[tuple[str, str, str]] = []
    relevant_headings = set(config.required_heading_codes)
    for obs in observations:
        try:
            country = obs.variables[roles.country][0]
            heading = obs.variables[roles.heading][0]
            measure = obs.variables[roles.measure][0]
        except (KeyError, IndexError):
            continue
        if heading not in relevant_headings or measure not in selected_measures:
            continue
        key = (country, heading, measure)
        if key in raw:
            duplicate_keys.append(key)
        else:
            raw[key] = obs
    if duplicate_keys:
        raise ValueError(f"Duplicate Source 90 economy-heading-measure observations: {duplicate_keys[:10]}")

    nominal_multiplier = _unit_multiplier(measure_vars[measures.nominal_id].value)
    source90_rows = _source90_normalized_rows(raw, country_vars, heading_vars, measure_vars, roles, selected_measures)

    supplemental = list(supplemental_observations)
    selected_nominal, selection_audit = select_nominal_sources(
        supplemental,
        priority_order=config.nominal_source_priority,
        relative_tolerance=config.source_conflict_relative_tolerance,
    )
    unit_reconciliation, invalid_source_economies = _unit_reconciliation(
        raw, participant_codes, measures, config, supplemental, nominal_multiplier
    )

    status_by_country = _country_statuses(config, raw, country_vars, participant_codes, measures)
    category_rows: list[dict[str, Any]] = []
    all_category_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    complete_economies: list[str] = []

    for country in sorted(participant_codes):
        economy_name = country_vars.get(country, Variable(roles.country, country, participant_codes[country])).value
        country_rows: list[dict[str, Any]] = []
        country_complete = True
        for category in CATEGORIES:
            if category in DIRECT_CATEGORIES:
                built, reason = _build_direct_category(
                    country, economy_name, category, config, raw, measures, nominal_multiplier
                )
            else:
                supplemental_obs = selected_nominal.get((country, category))
                if supplemental_obs and (country, supplemental_obs.source_id) in invalid_source_economies:
                    supplemental_obs = None
                    reason = "SUPPLEMENTAL_NOMINAL_SOURCE_FAILED_UNIT_RECONCILIATION"
                    built = None
                else:
                    built, reason = _build_proxy_category(
                        country, economy_name, category, config, raw, measures, supplemental_obs
                    )
            if built is None:
                country_complete = False
                missing_rows.append({
                    "economy_code": country,
                    "economy_name": economy_name,
                    "icp_participation_status": "PARTICIPATING",
                    "armilar_category": category,
                    "data_status": "UNAVAILABLE",
                    "reason": reason,
                })
            else:
                country_rows.append(built)
                all_category_rows.append(built)
        if country_complete and len(country_rows) == 12:
            complete_economies.append(country)
            category_rows.extend(country_rows)
        else:
            exclusion_rows.extend({
                "economy_code": country,
                "economy_name": economy_name,
                "armilar_category": row["armilar_category"],
                "reason": "ECONOMY_EXCLUDED_BECAUSE_12_CATEGORY_MATRIX_INCOMPLETE",
                "real_expenditure_ppp": row["real_expenditure_ppp"],
            } for row in country_rows)

    imputed_codes = [code for code, status in status_by_country.items() if status == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY"]
    for country in sorted(imputed_codes):
        economy_name = country_vars[country].value
        for category in CATEGORIES:
            missing_rows.append({
                "economy_code": country,
                "economy_name": economy_name,
                "icp_participation_status": "OFFICIALLY_IMPUTED_AGGREGATE_ONLY",
                "armilar_category": category,
                "data_status": "OFFICIALLY_IMPUTED_AGGREGATE_ONLY",
                "reason": "ICP_PUBLICATION_HAS_NO_OFFICIAL_12_CATEGORY_ALLOCATION_FOR_NONPARTICIPANT_IMPUTATION",
            })

    weight_rows = _normalise_weights(category_rows, config)
    economy_weights = _aggregate_weights(weight_rows, "economy_code")
    category_weights = _aggregate_weights(weight_rows, "armilar_category")
    weight_sum = sum((row["weight"] for row in weight_rows), Decimal("0"))
    weights_valid = bool(weight_rows) and abs(weight_sum - Decimal("1")) <= config.weight_sum_tolerance

    registry_rows: list[dict[str, Any]] = []
    complete_set = set(complete_economies)
    for code, variable in sorted(country_vars.items()):
        status = status_by_country.get(code, "UNAVAILABLE_OR_NONPUBLISHED")
        registry_rows.append({
            "economy_code": code,
            "economy_name": variable.value,
            "icp_participation_status": status,
            "eligible_complete_12_category_matrix": code in complete_set,
            "included_in_observed_universe_weights": code in complete_set,
            "official_imputation_category_detail_available": False if status == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" else "",
            "participation_status_basis": (
                "OFFICIAL_ICP_2021_PARTICIPATION_LIST" if status == "PARTICIPATING" else
                "SOURCE90_AGGREGATE_ONLY_NONPARTICIPANT" if status == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" else
                "SOURCE90_AGGREGATE" if status == "AGGREGATE" else "NO_ADMISSIBLE_PUBLISHED_RESULT"
            ),
        })

    participant_mapping_complete = len(participant_codes) == config.expected_participating_economies
    imputed_count_valid = len(imputed_codes) == config.expected_officially_imputed_economies
    research_release_allowed = (
        weights_valid
        and len(complete_economies) >= config.minimum_complete_participating_economies
        and participant_mapping_complete
        and imputed_count_valid
    )
    global_matrix_complete = len(complete_economies) == config.expected_participating_economies and not imputed_codes
    blocking: list[str] = []
    if not participant_mapping_complete:
        blocking.append(f"PARTICIPATION_MAPPING_COUNT:{len(participant_codes)}/{config.expected_participating_economies}")
    if not imputed_count_valid:
        blocking.append(f"OFFICIAL_IMPUTED_COUNT:{len(imputed_codes)}/{config.expected_officially_imputed_economies}")
    if not weights_valid:
        blocking.append("OBSERVED_WEIGHT_SUM_INVALID_OR_EMPTY")
    if len(complete_economies) < config.expected_participating_economies:
        blocking.append(f"PARTICIPATING_ECONOMIES_WITH_INCOMPLETE_12_CATEGORY_DATA:{config.expected_participating_economies-len(complete_economies)}")
    if imputed_codes:
        blocking.append(f"OFFICIALLY_IMPUTED_NONPARTICIPANTS_EXCLUDED_NO_CATEGORY_DETAIL:{len(imputed_codes)}")

    status = "RESEARCH_MATRIX_AVAILABLE" if research_release_allowed else "BLOCKED_NO_RESEARCH_MATRIX"
    if research_release_allowed and not global_matrix_complete:
        status = "RESEARCH_MATRIX_AVAILABLE_GLOBAL_SCOPE_INCOMPLETE"
    summary = {
        "schema_version": "4.0",
        "pipeline_version": config.pipeline_version,
        "reference_year": config.reference_year,
        "methodology": "RATIFIED_OPTION_B_STRICT_HFCE_NUMERATOR_WITH_ACTUAL_CONSUMPTION_PPP_PROXY_FOR_FIVE_CATEGORIES",
        "participating_economies_expected": config.expected_participating_economies,
        "participating_economies_mapped": len(participant_codes),
        "officially_imputed_economies_expected": config.expected_officially_imputed_economies,
        "officially_imputed_aggregate_only_economies": len(imputed_codes),
        "complete_participating_economies": len(complete_economies),
        "incomplete_participating_economies": config.expected_participating_economies - len(complete_economies),
        "admissible_observed_category_cells": len(all_category_rows),
        "observed_universe_weight_cells": len(weight_rows),
        "observed_universe_weight_sum": format(weight_sum, "f"),
        "weight_sum_tolerance": format(config.weight_sum_tolerance, "E"),
        "observed_universe_weights_valid": weights_valid,
        "research_release_allowed": research_release_allowed,
        "global_12_category_matrix_complete": global_matrix_complete,
        "monetary_release_allowed": False,
        "status": status,
        "blocking_reasons": blocking,
        "supplemental_nominal_observations": len(supplemental),
        "selected_supplemental_nominal_cells": len(selected_nominal),
        "unit_reconciliation_failed_source_economies": len(invalid_source_economies),
        "direct_ppp_categories": sorted(DIRECT_CATEGORIES),
        "proxy_ppp_categories": sorted(PROXY_CATEGORIES),
        "officially_imputed_policy": "EXCLUDED_AND_REPORTED_SEPARATELY_NO_MODELLED_ALLOCATION",
    }
    return HybridMatrixResult(
        normalized_source90_rows=source90_rows,
        supplemental_nominal_rows=[row.as_dict() for row in supplemental],
        nominal_selection_audit_rows=selection_audit,
        unit_reconciliation_rows=unit_reconciliation,
        category_rows=category_rows,
        all_category_rows=all_category_rows,
        missing_rows=missing_rows,
        exclusion_rows=exclusion_rows,
        economy_registry_rows=registry_rows,
        weight_rows=weight_rows,
        economy_weight_rows=economy_weights,
        category_weight_rows=category_weights,
        summary=summary,
    )


def _build_direct_category(country, economy_name, category, config, raw, measures, nominal_multiplier):
    if category == "CP02":
        components = ["1102100", "1102200"]
        nominal_parts: list[Decimal] = []
        real_parts: list[Decimal] = []
        source_files: list[str] = []
        source_hashes: list[str] = []
        for heading in components:
            nominal_obs = raw.get((country, heading, measures.nominal_id))
            ppp_obs = raw.get((country, heading, measures.ppp_id))
            if nominal_obs is None or ppp_obs is None or ppp_obs.value <= 0:
                return None, f"MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:{heading}"
            nominal = nominal_obs.value * nominal_multiplier
            nominal_parts.append(nominal)
            real_parts.append(nominal / ppp_obs.value)
            source_files.append(nominal_obs.source_file.as_posix())
            source_hashes.append(nominal_obs.source_hash)
        nominal_total = sum(nominal_parts, Decimal("0"))
        real_total = sum(real_parts, Decimal("0"))
        if real_total <= 0:
            return None, "NONPOSITIVE_CP02_REAL_EXPENDITURE"
        composite_ppp = nominal_total / real_total
        return {
            "economy_code": country, "economy_name": economy_name, "armilar_category": category,
            "nominal_household_expenditure_lcu": nominal_total,
            "ppp_lcu_per_international_dollar": composite_ppp,
            "real_expenditure_ppp": real_total,
            "numerator_source_id": "WORLD_BANK_ICP_2021_SOURCE90",
            "numerator_source_file": "|".join(source_files),
            "numerator_source_hash": "|".join(source_hashes),
            "ppp_source_heading": "1102100+1102200",
            "ppp_scope": "STRICT_HFCE_COMPOSITE",
            "derivation": "ALCOHOL_PLUS_TOBACCO_EXCLUDING_NARCOTICS",
            "quality_flags": "OBSERVED_PARTICIPANT|STRICT_HFCE|NARCOTICS_EXCLUDED|NO_DOUBLE_COUNTING",
        }, ""
    heading = config.direct_ppp_heading_by_category[category]
    nominal_obs = raw.get((country, heading, measures.nominal_id))
    ppp_obs = raw.get((country, heading, measures.ppp_id))
    if nominal_obs is None or ppp_obs is None:
        return None, f"MISSING_SOURCE90_DIRECT_NOMINAL_OR_PPP:{heading}"
    if ppp_obs.value <= 0:
        return None, f"NONPOSITIVE_SOURCE90_PPP:{heading}"
    nominal = nominal_obs.value * nominal_multiplier
    return {
        "economy_code": country, "economy_name": economy_name, "armilar_category": category,
        "nominal_household_expenditure_lcu": nominal,
        "ppp_lcu_per_international_dollar": ppp_obs.value,
        "real_expenditure_ppp": nominal / ppp_obs.value,
        "numerator_source_id": "WORLD_BANK_ICP_2021_SOURCE90",
        "numerator_source_file": nominal_obs.source_file.as_posix(),
        "numerator_source_hash": nominal_obs.source_hash,
        "ppp_source_heading": heading,
        "ppp_scope": "STRICT_HFCE",
        "derivation": "DIRECT_SOURCE90_HFCE",
        "quality_flags": "OBSERVED_PARTICIPANT|STRICT_HFCE|NO_DOUBLE_COUNTING",
    }, ""


def _build_proxy_category(country, economy_name, category, config, raw, measures, supplemental_obs):
    if supplemental_obs is None:
        return None, "MISSING_STRICT_HOUSEHOLD_NOMINAL_EXPENDITURE_FROM_OECD_UNSD_OR_EUROSTAT"
    heading = config.proxy_ppp_heading_by_category[category]
    ppp_obs = raw.get((country, heading, measures.ppp_id))
    if ppp_obs is None:
        return None, f"MISSING_SOURCE90_ACTUAL_CONSUMPTION_PPP_PROXY:{heading}"
    if ppp_obs.value <= 0:
        return None, f"NONPOSITIVE_SOURCE90_PPP_PROXY:{heading}"
    return {
        "economy_code": country, "economy_name": economy_name, "armilar_category": category,
        "nominal_household_expenditure_lcu": supplemental_obs.value_lcu,
        "ppp_lcu_per_international_dollar": ppp_obs.value,
        "real_expenditure_ppp": supplemental_obs.value_lcu / ppp_obs.value,
        "numerator_source_id": supplemental_obs.source_id,
        "numerator_source_file": supplemental_obs.source_file,
        "numerator_source_hash": supplemental_obs.source_hash,
        "ppp_source_heading": heading,
        "ppp_scope": "ACTUAL_CONSUMPTION_PROXY_RATIFIED_OPTION_B",
        "derivation": "STRICT_S14_P31DC_NUMERATOR_DIVIDED_BY_ACTUAL_CONSUMPTION_PPP",
        "quality_flags": "OBSERVED_PARTICIPANT|STRICT_HOUSEHOLD_NUMERATOR|PROXY_PPP_ACTUAL_CONSUMPTION_RATIFIED|NO_GOVERNMENT_OR_NPISH_IN_NUMERATOR|NATIONAL_ACCOUNTS_CURRENT_VINTAGE_MAY_DIFFER_FROM_ICP_2021_VINTAGE",
    }, ""


def _country_statuses(config, raw, country_vars, participant_codes, measures):
    result: dict[str, str] = {}
    for code, variable in country_vars.items():
        if code in participant_codes:
            result[code] = "PARTICIPATING"
        elif code in config.aggregate_country_codes or _is_aggregate(variable.value, config.aggregate_country_name_tokens):
            result[code] = "AGGREGATE"
        else:
            controls = sum(1 for heading in config.imputation_detection_heading_codes if (code, heading, measures.ppp_id) in raw)
            detailed = sum(1 for category, heading in config.direct_ppp_heading_by_category.items() if category != "CP02" and (code, heading, measures.ppp_id) in raw)
            result[code] = "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" if controls and detailed == 0 else "UNAVAILABLE_OR_NONPUBLISHED"
    return result


def _unit_reconciliation(raw, participant_codes, measures, config, supplemental, nominal_multiplier):
    direct_headings = {k: v for k, v in config.direct_ppp_heading_by_category.items() if k != "CP02"}
    grouped: dict[tuple[str, str], list[NominalObservation]] = defaultdict(list)
    for obs in supplemental:
        grouped[(obs.economy_code, obs.source_id)].append(obs)
    rows: list[dict[str, Any]] = []
    invalid: set[tuple[str, str]] = set()
    for (country, source_id), candidates in sorted(grouped.items()):
        ratios: list[Decimal] = []
        compared: list[str] = []
        for obs in candidates:
            heading = direct_headings.get(obs.armilar_category)
            if not heading:
                continue
            official = raw.get((country, heading, measures.nominal_id))
            if official is None or official.value == 0 or obs.value_lcu == 0:
                continue
            source90_lcu = official.value * nominal_multiplier
            ratios.append(obs.value_lcu / source90_lcu)
            compared.append(obs.armilar_category)
        if ratios:
            ordered = sorted(ratios)
            median = ordered[len(ordered)//2]
            status = "PASS_COMPATIBLE_SCALE" if Decimal("0.5") <= median <= Decimal("2") else "FAIL_INCOMPATIBLE_SCALE"
            if status.startswith("FAIL"):
                invalid.add((country, source_id))
        else:
            median = Decimal("0")
            status = "NOT_TESTABLE_NO_DIRECT_OVERLAP"
        rows.append({
            "economy_code": country,
            "source_id": source_id,
            "direct_categories_compared": "|".join(sorted(set(compared))),
            "comparison_count": len(ratios),
            "median_supplemental_to_source90_nominal_ratio": median,
            "status": status,
        })
    return rows, invalid


def _source90_normalized_rows(raw, country_vars, heading_vars, measure_vars, roles, selected_measures):
    rows: list[dict[str, Any]] = []
    for (country, heading, measure), obs in sorted(raw.items()):
        rows.append({
            "economy_code": country,
            "economy_name": country_vars.get(country, Variable(roles.country, country, country)).value,
            "heading_code": heading,
            "heading_name": heading_vars.get(heading, Variable(roles.heading, heading, heading)).value,
            "expenditure_measure": selected_measures[measure],
            "value": obs.value,
            "unit": measure_vars[measure].value,
            "source_file": obs.source_file.as_posix(),
            "source_url": obs.source_url,
            "retrieved_at": obs.retrieved_at,
            "source_hash": obs.source_hash,
            "quality_flags": "OFFICIAL_WORLD_BANK_ICP_2021_SOURCE90",
        })
    return rows


def _normalise_weights(category_rows, config):
    total = sum((row["real_expenditure_ppp"] for row in category_rows), Decimal("0"))
    if total <= 0:
        return []
    quantum = Decimal(1).scaleb(-config.weight_decimal_places)
    rows: list[dict[str, Any]] = []
    with localcontext() as ctx:
        ctx.prec = max(50, config.weight_decimal_places + 20)
        for row in sorted(category_rows, key=lambda item: (item["economy_code"], item["armilar_category"])):
            output = dict(row)
            output["weight"] = (row["real_expenditure_ppp"] / total).quantize(quantum, rounding=ROUND_HALF_EVEN)
            rows.append(output)
    residual = Decimal("1") - sum((row["weight"] for row in rows), Decimal("0"))
    rows[-1]["weight"] += residual
    rows[-1]["rounding_residual_applied"] = residual
    for row in rows[:-1]:
        row["rounding_residual_applied"] = Decimal("0")
    return rows


def _aggregate_weights(rows, key):
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        totals[str(row[key])] += row["weight"]
    return [{key: code, "weight": value} for code, value in sorted(totals.items())]


def _unit_multiplier(label: str) -> Decimal:
    low = label.lower()
    if "billion" in low:
        return Decimal("1000000000")
    if "million" in low:
        return Decimal("1000000")
    if "thousand" in low:
        return Decimal("1000")
    return Decimal("1")


def _is_aggregate(name: str, tokens: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(token in low for token in tokens)
