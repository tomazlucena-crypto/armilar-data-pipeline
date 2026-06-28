from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any

from .config import Step2Config
from .measures import MeasureSelection
from .util import normalize_text, read_csv
from .worldbank import DimensionRoles, Observation, Variable


NORMALIZED_FIELDS = [
    "economy_code", "economy_name", "icp_participation_status", "heading_code",
    "heading_name", "armilar_category", "expenditure_measure", "value", "unit",
    "currency_or_ppp_basis", "source_file", "source_url", "retrieved_at", "source_hash",
    "quality_flags",
]


@dataclass
class MatrixResult:
    normalized_rows: list[dict[str, Any]]
    heading_matrix_rows: list[dict[str, Any]]
    category_rows: list[dict[str, Any]]
    country_registry_rows: list[dict[str, Any]]
    coverage_rows: list[dict[str, Any]]
    exclusion_rows: list[dict[str, Any]]
    missing_rows: list[dict[str, Any]]
    identity_rows: list[dict[str, Any]]
    hierarchy_rows: list[dict[str, Any]]
    weight_rows: list[dict[str, Any]]
    economy_weight_rows: list[dict[str, Any]]
    category_weight_rows: list[dict[str, Any]]
    experimental_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def build_matrix(
    config: Step2Config,
    roles: DimensionRoles,
    observations: list[Observation],
    inventories: dict[str, list[Variable]],
    measures: MeasureSelection,
    participant_codes: dict[str, str],
) -> MatrixResult:
    mapping_rows = read_csv(config.headings_path)
    _validate_crosswalk(mapping_rows, config.forbidden_scope_prefixes)
    mapping = {row["heading_code"]: row for row in mapping_rows}
    categories = [row["armilar_category"] for row in read_csv(config.categories_path)]
    country_vars = {item.variable_id: item for item in inventories[roles.country]}
    measure_vars = {item.variable_id: item for item in inventories[roles.measure]}
    heading_vars = {item.variable_id: item for item in inventories[roles.heading]}

    selected_measure_kind = {
        measures.ppp_id: "PPP",
        measures.nominal_id: "NOMINAL_EXPENDITURE",
        measures.real_id: "REAL_EXPENDITURE_PPP",
    }

    raw: dict[tuple[str, str, str], Observation] = {}
    duplicate_keys: list[tuple[str, str, str]] = []
    for obs in observations:
        try:
            country = obs.variables[roles.country][0]
            heading = obs.variables[roles.heading][0]
            measure = obs.variables[roles.measure][0]
        except KeyError:
            continue
        if heading not in mapping or measure not in selected_measure_kind:
            continue
        key = (country, heading, measure)
        if key in raw:
            duplicate_keys.append(key)
        else:
            raw[key] = obs
    if duplicate_keys:
        raise ValueError(f"Duplicate economy-heading-measure observations: {duplicate_keys[:10]}")

    country_status: dict[str, str] = {}
    country_detail_counts: dict[str, int] = defaultdict(int)
    for country, heading, measure in raw:
        if measure == measures.real_id and mapping[heading]["include_in_category"].lower() == "true":
            country_detail_counts[country] += 1
    for code, variable in country_vars.items():
        if code in participant_codes:
            country_status[code] = "PARTICIPATING"
        elif _is_aggregate(variable.value, config.aggregate_country_name_tokens):
            country_status[code] = "AGGREGATE"
        elif (
            any((code, heading, measures.real_id) in raw for heading in config.imputation_detection_heading_codes)
            and country_detail_counts.get(code, 0) == 0
        ):
            country_status[code] = "OFFICIALLY_IMPUTED_AGGREGATE_ONLY"
        else:
            country_status[code] = "UNAVAILABLE_OR_NONPUBLISHED"

    registry_rows: list[dict[str, Any]] = []
    for code, variable in sorted(country_vars.items()):
        registry_rows.append(
            {
                "economy_code": code,
                "economy_name": variable.value,
                "icp_participation_status": country_status[code],
                "official_participation_source": config.urls["participation_page"] if code in participant_codes else "",
                "detailed_hfce_observation_count": country_detail_counts.get(code, 0),
                "hfce_aggregate_available": (code, "1100000", measures.real_id) in raw,
                "aggregate_imputation_observation_count": sum(
                    1 for heading in config.imputation_detection_heading_codes
                    if (code, heading, measures.real_id) in raw
                ),
                "imputation_detection_heading_codes": "|".join(
                    heading for heading in config.imputation_detection_heading_codes
                    if (code, heading, measures.real_id) in raw
                ),
                "participation_status_basis": (
                    "OFFICIAL_176_PARTICIPATION_LIST" if code in participant_codes else
                    "SOURCE90_AGGREGATE_ONLY_NONPARTICIPANT_MATCHED_TO_OFFICIAL_19_COUNT"
                    if country_status[code] == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" else
                    "SOURCE90_AGGREGATE_LABEL" if country_status[code] == "AGGREGATE" else
                    "NO_ADMISSIBLE_PUBLISHED_RESULT"
                ),
                "eligible_for_12_category_matrix": False,
                "quality_flags": (
                    "OFFICIAL_IMPUTATION_STATUS_INFERRED_FROM_SOURCE90_RELEASE_STRUCTURE"
                    if country_status[code] == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" else ""
                ),
            }
        )

    normalized_rows: list[dict[str, Any]] = []
    heading_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    for (country, heading, measure), obs in sorted(raw.items()):
        country_var = country_vars.get(country, Variable(roles.country, country, country))
        heading_var = heading_vars.get(heading, Variable(roles.heading, heading, mapping[heading]["heading_name"]))
        measure_var = measure_vars[measure]
        map_row = mapping[heading]
        quality_flags = ["OFFICIAL_WORLD_BANK_ICP_2021"]
        if country_status.get(country) == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY":
            quality_flags.append("OFFICIALLY_IMPUTED_ICP")
        elif country_status.get(country) == "PARTICIPATING":
            quality_flags.append("PARTICIPATING_ECONOMY_RESULT")
        if map_row["include_in_category"].lower() != "true":
            quality_flags.append("EXCLUDED_FROM_FINAL_CATEGORY_MATRIX")
            if map_row["economic_scope"] != "HFCE":
                quality_flags.append("NON_HFCE_CONTROL_OR_SURROGATE")
            exclusion_rows.append(
                {
                    "economy_code": country,
                    "heading_code": heading,
                    "heading_name": heading_var.value,
                    "reason": map_row["exclusion_reason"] or "CONTROL_OR_FORBIDDEN_HEADING",
                    "value": obs.value,
                    "measure": selected_measure_kind[measure],
                    "source_file": obs.source_file,
                }
            )
        basis = {
            "PPP": "LOCAL_CURRENCY_UNITS_PER_PPP_US_DOLLAR",
            "NOMINAL_EXPENDITURE": "LOCAL_CURRENCY_CURRENT_PRICES",
            "REAL_EXPENDITURE_PPP": "PPP_BASED_COMMON_CURRENCY",
        }[selected_measure_kind[measure]]
        row = {
            "economy_code": country,
            "economy_name": country_var.value,
            "icp_participation_status": country_status.get(country, "UNKNOWN"),
            "heading_code": heading,
            "heading_name": heading_var.value,
            "armilar_category": map_row["armilar_category"],
            "expenditure_measure": selected_measure_kind[measure],
            "value": obs.value,
            "unit": measure_var.value,
            "currency_or_ppp_basis": basis,
            "source_file": obs.source_file,
            "source_url": obs.source_url,
            "retrieved_at": obs.retrieved_at,
            "source_hash": obs.source_hash,
            "quality_flags": "|".join(quality_flags),
        }
        normalized_rows.append(row)
        heading_rows.append(dict(row))

    identity_rows, identity_failures = _identity_checks(
        raw, country_vars, heading_vars, measures, config.identity_relative_tolerance
    )
    hierarchy_rows, hierarchy_failures = _hierarchy_checks(
        raw, country_vars, participant_codes, measures, config.hierarchy_relative_tolerance
    )

    category_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for code, status in sorted(country_status.items()):
        if status == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY":
            economy_name = country_vars.get(code, Variable(roles.country, code, code)).value
            for category in categories:
                row = _missing(
                    code, economy_name, category, "",
                    "OFFICIAL_ICP_IMPUTATION_AVAILABLE_ONLY_AT_HFCE_AGGREGATE_NO_PUBLIC_CATEGORY_ALLOCATION",
                )
                row["data_status"] = "OFFICIALLY_IMPUTED_AGGREGATE_ONLY"
                missing_rows.append(row)
    eligible_countries: list[str] = []
    by_country_category: dict[tuple[str, str], Decimal] = {}
    required_direct = {
        row["armilar_category"]: row["heading_code"]
        for row in mapping_rows
        if row["include_in_category"].lower() == "true" and row["component_role"] == "DIRECT"
    }
    for country in sorted(participant_codes):
        economy_name = country_vars.get(country, Variable(roles.country, country, country)).value
        complete = True
        country_rows: list[dict[str, Any]] = []
        for category in categories:
            if category == "CP02":
                components = ["1102100", "1102200"]
                real_components = [raw.get((country, code, measures.real_id)) for code in components]
                nominal_components = [raw.get((country, code, measures.nominal_id)) for code in components]
                if any(item is None for item in real_components):
                    complete = False
                    for code, item in zip(components, real_components):
                        if item is None:
                            missing_rows.append(_missing(country, economy_name, category, code, "MISSING_REQUIRED_CP02_REAL_COMPONENT"))
                    continue
                if any(item is None for item in nominal_components):
                    complete = False
                    for code, item in zip(components, nominal_components):
                        if item is None:
                            missing_rows.append(_missing(country, economy_name, category, code, "MISSING_REQUIRED_CP02_NOMINAL_COMPONENT"))
                    continue
                real_value = sum((item.value for item in real_components if item), Decimal("0"))
                nominal_value = sum((item.value for item in nominal_components if item), Decimal("0"))
                source_files = "|".join(sorted({
                    str(item.source_file) for item in [*real_components, *nominal_components] if item
                }))
                derivation = "SUM_1102100_1102200_EXCLUDING_1102300"
            else:
                heading = required_direct.get(category)
                real_item = raw.get((country, heading, measures.real_id)) if heading else None
                nominal_item = raw.get((country, heading, measures.nominal_id)) if heading else None
                if real_item is None:
                    complete = False
                    missing_rows.append(_missing(country, economy_name, category, heading or "", "MISSING_REQUIRED_DIRECT_REAL_HEADING"))
                    continue
                if nominal_item is None:
                    complete = False
                    missing_rows.append(_missing(country, economy_name, category, heading or "", "MISSING_REQUIRED_DIRECT_NOMINAL_HEADING"))
                    continue
                real_value = real_item.value
                nominal_value = nominal_item.value
                source_files = "|".join(sorted({str(real_item.source_file), str(nominal_item.source_file)}))
                derivation = f"DIRECT_{heading}"
            if real_value < 0 or nominal_value < 0:
                complete = False
                missing_rows.append(_missing(country, economy_name, category, "", "NEGATIVE_CATEGORY_EXPENDITURE_VALUE"))
                continue
            country_rows.append(
                {
                    "economy_code": country,
                    "economy_name": economy_name,
                    "icp_participation_status": "PARTICIPATING",
                    "armilar_category": category,
                    "real_expenditure_ppp": real_value,
                    "nominal_expenditure_lcu": nominal_value,
                    "derivation": derivation,
                    "source_files": source_files,
                    "data_status": "OBSERVED_PARTICIPATING_ICP_RESULT",
                    "included_in_candidate_weights": True,
                    "quality_flags": "NARCOTICS_EXCLUDED_EXACTLY" if category == "CP02" else "",
                }
            )
        if country in identity_failures:
            complete = False
            missing_rows.append(_missing(country, economy_name, "", "", "PPP_NOMINAL_REAL_IDENTITY_FAILED"))
        if country in hierarchy_failures:
            complete = False
            missing_rows.append(_missing(country, economy_name, "", "", "ICP_NOMINAL_HIERARCHY_RECONCILIATION_FAILED"))
        hfce_nominal = raw.get((country, "1100000", measures.nominal_id))
        narcotics_nominal = raw.get((country, "1102300", measures.nominal_id))
        net_abroad_nominal = raw.get((country, "1113000", measures.nominal_id))
        if complete and hfce_nominal is not None:
            nominal_category_sum = sum((row["nominal_expenditure_lcu"] for row in country_rows), Decimal("0"))
            nominal_residual = hfce_nominal.value - nominal_category_sum
            expected_adjustments = (
                narcotics_nominal.value + net_abroad_nominal.value
                if narcotics_nominal is not None and net_abroad_nominal is not None
                else None
            )
            for row in country_rows:
                row["nominal_hfce_control_value"] = hfce_nominal.value
                row["nominal_armilar_category_total"] = nominal_category_sum
                row["nominal_hfce_less_armilar_categories"] = nominal_residual
                row["nominal_expected_excluded_adjustments"] = (
                    expected_adjustments if expected_adjustments is not None else ""
                )
                row["quality_flags"] = _join_flags(
                    row["quality_flags"],
                    "NOMINAL_HFCE_RESIDUAL_EXPECTED_NARCOTICS_PLUS_NET_PURCHASES_ABROAD",
                )
        elif complete and hfce_nominal is None:
            complete = False
            missing_rows.append(_missing(country, economy_name, "", "1100000", "MISSING_NOMINAL_HFCE_CONTROL_AGGREGATE"))
        if complete and len(country_rows) == 12:
            eligible_countries.append(country)
            for row in country_rows:
                category_rows.append(row)
                by_country_category[(country, row["armilar_category"])] = row["real_expenditure_ppp"]
        else:
            for row in country_rows:
                row["included_in_candidate_weights"] = False
                row["quality_flags"] = _join_flags(row["quality_flags"], "ECONOMY_INCOMPLETE_EXCLUDED")
                category_rows.append(row)

    eligible_set = set(eligible_countries)
    for row in registry_rows:
        if row["economy_code"] in eligible_set:
            row["eligible_for_12_category_matrix"] = True
        elif row["icp_participation_status"] == "PARTICIPATING":
            row["quality_flags"] = "INCOMPLETE_12_CATEGORY_COVERAGE"

    weight_rows, economy_weights, category_weights, sum_weights = _weights(
        config, by_country_category, eligible_countries, categories, country_vars
    )

    status_counts: dict[str, int] = defaultdict(int)
    for row in registry_rows:
        status_counts[row["icp_participation_status"]] += 1
    coverage_rows = [
        {"metric": "source_country_dimension_count", "value": len(country_vars), "unit": "economies_or_aggregates"},
        {"metric": "official_participating_economies_mapped", "value": len(participant_codes), "unit": "economies"},
        {"metric": "eligible_complete_economies", "value": len(eligible_countries), "unit": "economies"},
        {"metric": "candidate_weight_cells", "value": len(weight_rows), "unit": "economy_category_cells"},
        {"metric": "officially_imputed_aggregate_only", "value": status_counts.get("OFFICIALLY_IMPUTED_AGGREGATE_ONLY", 0), "unit": "economies"},
        {"metric": "missing_required_records", "value": len(missing_rows), "unit": "records"},
        {"metric": "weight_sum", "value": sum_weights, "unit": "share"},
    ]

    expected_participants = config.expected_participating_economies
    expected_imputed = config.expected_officially_imputed_economies
    release_allowed = (
        len(participant_codes) == expected_participants
        and len(eligible_countries) == expected_participants
        and abs(sum_weights - Decimal("1")) <= config.weight_sum_tolerance
        and not identity_failures
        and not hierarchy_failures
    )
    # Even with all 176 detailed participants, the 19 officially imputed economies have no
    # public category allocation. Their omission remains an explicit methodological gate.
    detected_imputed = status_counts.get("OFFICIALLY_IMPUTED_AGGREGATE_ONLY", 0)
    global_complete = release_allowed and expected_imputed == 0 and detected_imputed == 0
    summary = {
        "pipeline_version": config.pipeline_version,
        "reference_year": config.reference_year,
        "participating_economies_expected": expected_participants,
        "participating_economies_mapped": len(participant_codes),
        "eligible_complete_economies": len(eligible_countries),
        "officially_imputed_economies_expected": expected_imputed,
        "officially_imputed_aggregate_only_economies": detected_imputed,
        "candidate_weight_cells": len(weight_rows),
        "candidate_weight_sum": format(sum_weights, "f"),
        "candidate_weights_valid_for_observed_participant_universe": release_allowed,
        "global_12_category_matrix_complete": global_complete,
        "release_allowed": global_complete,
        "status": "COMPLETE" if global_complete else "BLOCKED_WITH_CANDIDATE_MATRIX",
        "blocking_reasons": _blocking_reasons(
            len(participant_codes), len(eligible_countries), expected_participants, detected_imputed, expected_imputed,
            identity_failures, hierarchy_failures, sum_weights, config.weight_sum_tolerance,
        ),
    }
    experimental_rows = [
        {
            "record_type": "EXPERIMENTAL_APPROXIMATION",
            "status": "NONE_USED",
            "included_in_candidate_weights": False,
            "description": "No population, GDP, income or model-based allocation was used.",
        }
    ]
    return MatrixResult(
        normalized_rows=normalized_rows,
        heading_matrix_rows=heading_rows,
        category_rows=category_rows,
        country_registry_rows=registry_rows,
        coverage_rows=coverage_rows,
        exclusion_rows=exclusion_rows,
        missing_rows=missing_rows,
        identity_rows=identity_rows,
        hierarchy_rows=hierarchy_rows,
        weight_rows=weight_rows,
        economy_weight_rows=economy_weights,
        category_weight_rows=category_weights,
        experimental_rows=experimental_rows,
        summary=summary,
    )



def _validate_crosswalk(rows, forbidden_prefixes):
    included = [row for row in rows if row["include_in_category"].lower() == "true"]
    if any(any(row["heading_code"].startswith(prefix) for prefix in forbidden_prefixes) for row in included):
        raise ValueError("Crosswalk attempts to include AIC, NPISH or government scope")
    cp02 = {row["heading_code"] for row in included if row["armilar_category"] == "CP02"}
    if cp02 != {"1102100", "1102200"}:
        raise ValueError(f"CP02 must use exactly alcohol and tobacco components, found {sorted(cp02)}")
    included_codes = {row["heading_code"] for row in included}
    if "1102000" in included_codes or "1102300" in included_codes:
        raise ValueError("CP02 parent or narcotics cannot enter the category matrix")
    categories = {row["armilar_category"] for row in included}
    if categories != {f"CP{i:02d}" for i in range(1, 13)}:
        raise ValueError("Crosswalk must cover exactly twelve Armilar categories")


def _identity_checks(raw, country_vars, heading_vars, measures, tolerance):
    rows: list[dict[str, Any]] = []
    failures: set[str] = set()
    keys = {(country, heading) for country, heading, _ in raw}
    for country, heading in sorted(keys):
        p = raw.get((country, heading, measures.ppp_id))
        n = raw.get((country, heading, measures.nominal_id))
        r = raw.get((country, heading, measures.real_id))
        if not p or not n or not r or p.value <= 0 or r.value == 0:
            continue
        derived = n.value / p.value
        error = abs(derived - r.value) / abs(r.value)
        status = "PASS" if error <= tolerance else "FAIL"
        if status == "FAIL":
            failures.add(country)
        rows.append({
            "economy_code": country,
            "economy_name": country_vars.get(country, Variable("", country, country)).value,
            "heading_code": heading,
            "heading_name": heading_vars.get(heading, Variable("", heading, heading)).value,
            "ppp": p.value,
            "nominal_expenditure": n.value,
            "reported_real_expenditure": r.value,
            "derived_real_expenditure": derived,
            "relative_error": error,
            "tolerance": tolerance,
            "status": status,
        })
    return rows, failures



def _hierarchy_checks(raw, country_vars, participant_codes, measures, tolerance):
    rows: list[dict[str, Any]] = []
    failures: set[str] = set()
    division_codes = ["1101000", "1102000", *[f"11{i:02d}000" for i in range(3, 14)]]
    armilar_codes = ["1101000", "1102100", "1102200", *[f"11{i:02d}000" for i in range(3, 13)]]

    def value(country: str, heading: str):
        item = raw.get((country, heading, measures.nominal_id))
        return item.value if item is not None else None

    def add_check(country: str, check: str, reported, components: list[Decimal], required_codes: list[str]):
        economy_name = country_vars.get(country, Variable("", country, country)).value
        missing = [code for code in required_codes if value(country, code) is None]
        if reported is None or missing:
            rows.append({
                "economy_code": country,
                "economy_name": economy_name,
                "check": check,
                "measure_basis": "NOMINAL_EXPENDITURE_LCU",
                "reported_value": reported if reported is not None else "",
                "derived_value": "",
                "difference": "",
                "relative_error": "",
                "tolerance": tolerance,
                "status": "NOT_TESTED_MISSING_INPUT",
                "missing_heading_codes": "|".join(missing),
            })
            return
        derived = sum(components, Decimal("0"))
        difference = reported - derived
        denominator = max(abs(reported), abs(derived), Decimal("1E-30"))
        relative_error = abs(difference) / denominator
        status = "PASS" if relative_error <= tolerance else "FAIL"
        if status == "FAIL":
            failures.add(country)
        rows.append({
            "economy_code": country,
            "economy_name": economy_name,
            "check": check,
            "measure_basis": "NOMINAL_EXPENDITURE_LCU",
            "reported_value": reported,
            "derived_value": derived,
            "difference": difference,
            "relative_error": relative_error,
            "tolerance": tolerance,
            "status": status,
            "missing_heading_codes": "",
        })

    for country in sorted(participant_codes):
        cp02_codes = ["1102100", "1102200", "1102300"]
        cp02_values = [value(country, code) for code in cp02_codes]
        add_check(
            country,
            "NOMINAL_CP02_PARENT_EQUALS_ALCOHOL_TOBACCO_NARCOTICS",
            value(country, "1102000"),
            [item for item in cp02_values if item is not None],
            cp02_codes,
        )
        division_values = [value(country, code) for code in division_codes]
        add_check(
            country,
            "NOMINAL_HFCE_EQUALS_SUM_OF_13_PUBLISHED_CATEGORIES_INCLUDING_NET_PURCHASES_ABROAD",
            value(country, "1100000"),
            [item for item in division_values if item is not None],
            division_codes,
        )
        armilar_values = [value(country, code) for code in armilar_codes]
        hfce = value(country, "1100000")
        narcotics = value(country, "1102300")
        net_purchases_abroad = value(country, "1113000")
        if (
            hfce is None
            or narcotics is None
            or net_purchases_abroad is None
            or any(item is None for item in armilar_values)
        ):
            missing = [
                code for code in ["1100000", "1102300", "1113000", *armilar_codes]
                if value(country, code) is None
            ]
            rows.append({
                "economy_code": country,
                "economy_name": country_vars.get(country, Variable("", country, country)).value,
                "check": "NOMINAL_HFCE_MINUS_ARMILAR_EQUALS_NARCOTICS_PLUS_NET_PURCHASES_ABROAD",
                "measure_basis": "NOMINAL_EXPENDITURE_LCU",
                "reported_value": "",
                "derived_value": "",
                "difference": "",
                "relative_error": "",
                "tolerance": tolerance,
                "status": "NOT_TESTED_MISSING_INPUT",
                "missing_heading_codes": "|".join(missing),
            })
        else:
            reported_adjustments = narcotics + net_purchases_abroad
            derived_adjustments = hfce - sum(
                (item for item in armilar_values if item is not None), Decimal("0")
            )
            difference = reported_adjustments - derived_adjustments
            denominator = max(abs(reported_adjustments), abs(derived_adjustments), Decimal("1E-30"))
            relative_error = abs(difference) / denominator
            status = "PASS" if relative_error <= tolerance else "FAIL"
            if status == "FAIL":
                failures.add(country)
            rows.append({
                "economy_code": country,
                "economy_name": country_vars.get(country, Variable("", country, country)).value,
                "check": "NOMINAL_HFCE_MINUS_ARMILAR_EQUALS_NARCOTICS_PLUS_NET_PURCHASES_ABROAD",
                "measure_basis": "NOMINAL_EXPENDITURE_LCU",
                "reported_value": reported_adjustments,
                "derived_value": derived_adjustments,
                "difference": difference,
                "relative_error": relative_error,
                "tolerance": tolerance,
                "status": status,
                "missing_heading_codes": "",
            })
    return rows, failures

def _weights(config, values, eligible_countries, categories, country_vars):
    ordered_keys = [(country, category) for country in sorted(eligible_countries) for category in categories]
    total = sum((values[key] for key in ordered_keys), Decimal("0"))
    if total <= 0 or not ordered_keys:
        return [], [], [], Decimal("0")
    quant = Decimal(1).scaleb(-config.weight_decimal_places)
    weights: list[Decimal] = []
    with localcontext() as context:
        context.prec = max(50, config.weight_decimal_places + 20)
        for key in ordered_keys[:-1]:
            weights.append((values[key] / total).quantize(quant, rounding=ROUND_HALF_EVEN))
        weights.append(Decimal("1") - sum(weights, Decimal("0")))
    rows: list[dict[str, Any]] = []
    weight_status = (
        "CANDIDATE_COMPLETE_176_PARTICIPANTS"
        if len(eligible_countries) == 176
        else f"DIAGNOSTIC_PARTIAL_PARTICIPANT_UNIVERSE_{len(eligible_countries)}_OF_176"
    )
    for index, (key, weight) in enumerate(zip(ordered_keys, weights)):
        country, category = key
        rows.append({
            "economy_code": country,
            "economy_name": country_vars.get(country, Variable("", country, country)).value,
            "armilar_category": category,
            "real_expenditure_ppp": values[key],
            "global_denominator_real_expenditure_ppp": total,
            "weight": weight,
            "weight_status": weight_status,
            "closure_adjustment": index == len(ordered_keys) - 1,
        })
    economy_totals: dict[str, Decimal] = defaultdict(Decimal)
    category_totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        economy_totals[row["economy_code"]] += row["weight"]
        category_totals[row["armilar_category"]] += row["weight"]
    economy_rows = [
        {"economy_code": code, "economy_name": country_vars[code].value, "weight": value, "weight_status": weight_status}
        for code, value in sorted(economy_totals.items())
    ]
    category_rows = [
        {"armilar_category": code, "weight": value, "weight_status": weight_status}
        for code, value in sorted(category_totals.items())
    ]
    return rows, economy_rows, category_rows, sum(weights, Decimal("0"))


def _missing(country, name, category, heading, reason):
    return {
        "economy_code": country,
        "economy_name": name,
        "armilar_category": category,
        "heading_code": heading,
        "reason": reason,
        "data_status": "UNAVAILABLE",
        "included_in_candidate_weights": False,
    }


def _is_aggregate(name: str, tokens: tuple[str, ...]) -> bool:
    normalized = normalize_text(name)
    return any(token in normalized for token in tokens)


def _join_flags(existing: str, new: str) -> str:
    return f"{existing}|{new}" if existing else new


def _blocking_reasons(mapped, eligible, expected_participants, imputed, expected_imputed, identity_failures, hierarchy_failures, sum_weights, tolerance):
    reasons: list[str] = []
    if mapped != expected_participants:
        reasons.append(f"PARTICIPATION_REGISTRY_NOT_FULLY_MAPPED:{mapped}/{expected_participants}")
    if eligible != expected_participants:
        reasons.append(f"PARTICIPATING_ECONOMIES_INCOMPLETE:{eligible}/{expected_participants}")
    if imputed != expected_imputed:
        reasons.append(f"OFFICIAL_IMPUTATION_REGISTRY_COUNT_MISMATCH:{imputed}/{expected_imputed}")
    if imputed:
        reasons.append(f"OFFICIALLY_IMPUTED_ECONOMIES_HAVE_NO_PUBLIC_12_CATEGORY_ALLOCATION:{imputed}")
    if identity_failures:
        reasons.append(f"PPP_NOMINAL_REAL_IDENTITY_FAILURES:{len(identity_failures)}")
    if hierarchy_failures:
        reasons.append(f"ICP_HIERARCHY_RECONCILIATION_FAILURES:{len(hierarchy_failures)}")
    if abs(sum_weights - Decimal("1")) > tolerance:
        reasons.append(f"WEIGHT_SUM_OUTSIDE_TOLERANCE:{sum_weights}")
    return reasons
