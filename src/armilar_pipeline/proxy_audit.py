from __future__ import annotations

import csv
import json
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Iterable

from .config import Step2Config
from .hybrid_matrix import HybridMatrixResult, PROXY_CATEGORIES, _unit_multiplier
from .measures import MeasureSelection
from .worldbank import DimensionRoles, Observation, Variable


AIC_HEADING = "9020000"
DEFAULT_PROXY_POLICY = {
    "minimum_direct_comparisons": 50,
    "minimum_distinct_economies": 10,
    "minimum_comparisons_per_category": 5,
    "validated_median_absolute_error_max": "0.02",
    "validated_with_limits_median_absolute_error_max": "0.05",
}


def build_proxy_audit(
    config: Step2Config,
    *,
    roles: DimensionRoles,
    observations: list[Observation],
    inventories: dict[str, list[Variable]],
    measures: MeasureSelection,
    matrix: HybridMatrixResult,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Build separate financing-exposure and direct PPP-error evidence.

    The financing gap is diagnostic only. It never stands in for the PPP error.
    Direct error observations are admitted only from the explicit official
    benchmark registry and only where matched HFCE and AIC PPPs exist for the
    same economy, category and reference year.
    """
    measure_vars = {item.variable_id: item for item in inventories[roles.measure]}
    nominal_multiplier = _unit_multiplier(measure_vars[measures.nominal_id].value)
    raw_nominal: dict[tuple[str, str], Observation] = {}
    for obs in observations:
        try:
            country = obs.variables[roles.country][0]
            heading = obs.variables[roles.heading][0]
            measure = obs.variables[roles.measure][0]
        except (KeyError, IndexError):
            continue
        if measure == measures.nominal_id:
            raw_nominal[(country, heading)] = obs

    complete_codes = sorted({row["economy_code"] for row in matrix.category_rows})
    rows_by_country: dict[str, list[dict[str, Any]]] = {}
    for row in matrix.category_rows:
        rows_by_country.setdefault(str(row["economy_code"]), []).append(row)

    financing_rows: list[dict[str, Any]] = []
    financing_ratios: list[Decimal] = []
    for code in complete_codes:
        rows = rows_by_country.get(code, [])
        armilar_nominal = sum((Decimal(str(row["nominal_household_expenditure_lcu"])) for row in rows), Decimal("0"))
        aic_obs = raw_nominal.get((code, AIC_HEADING))
        cp02_total_obs = raw_nominal.get((code, "1102000"))
        alcohol_obs = raw_nominal.get((code, "1102100"))
        tobacco_obs = raw_nominal.get((code, "1102200"))
        net_abroad_obs = raw_nominal.get((code, "1113000"))
        required = (aic_obs, cp02_total_obs, alcohol_obs, tobacco_obs, net_abroad_obs)
        if any(item is None for item in required) or armilar_nominal <= 0:
            financing_rows.append({
                "economy_code": code,
                "economy_name": rows[0]["economy_name"] if rows else "",
                "armilar_12_category_nominal_lcu": armilar_nominal,
                "derived_narcotics_nominal_lcu": "",
                "net_purchases_abroad_nominal_lcu": "",
                "reconstructed_hfce_nominal_lcu": "",
                "aic_nominal_lcu": "",
                "aic_minus_hfce_lcu": "",
                "aic_hfce_financing_gap_ratio": "",
                "status": "UNAVAILABLE",
                "interpretation": "Financing exposure cannot be calculated because a required public control cell is unavailable.",
            })
            continue
        cp02_total = cp02_total_obs.value * nominal_multiplier
        alcohol = alcohol_obs.value * nominal_multiplier
        tobacco = tobacco_obs.value * nominal_multiplier
        narcotics = cp02_total - alcohol - tobacco
        net_abroad = net_abroad_obs.value * nominal_multiplier
        hfce_nominal = armilar_nominal + narcotics + net_abroad
        aic_nominal = aic_obs.value * nominal_multiplier
        if narcotics < 0 or hfce_nominal <= 0:
            status = "WARN_CONCEPT_OR_UNIT_MISMATCH"
            ratio: Decimal | str = ""
            gap: Decimal | str = ""
        else:
            gap = aic_nominal - hfce_nominal
            ratio = gap / hfce_nominal
            status = "PASS_DIAGNOSTIC_ONLY" if ratio >= Decimal("-0.02") else "WARN_CONCEPT_OR_UNIT_MISMATCH"
            if status == "PASS_DIAGNOSTIC_ONLY":
                financing_ratios.append(ratio)
        financing_rows.append({
            "economy_code": code,
            "economy_name": rows[0]["economy_name"] if rows else "",
            "armilar_12_category_nominal_lcu": armilar_nominal,
            "derived_narcotics_nominal_lcu": narcotics,
            "net_purchases_abroad_nominal_lcu": net_abroad,
            "reconstructed_hfce_nominal_lcu": hfce_nominal,
            "aic_nominal_lcu": aic_nominal,
            "aic_minus_hfce_lcu": gap,
            "aic_hfce_financing_gap_ratio": ratio,
            "status": status,
            "interpretation": "Measures third-party-financed consumption exposure after reconstructing HFCE with narcotics and net purchases abroad; it is not the PPP proxy error.",
        })

    benchmarks = _load_official_benchmarks(config)
    ppp_comparison_rows: list[dict[str, Any]] = []
    for code in complete_codes:
        economy_name = rows_by_country[code][0]["economy_name"]
        for category in sorted(PROXY_CATEGORIES):
            proxy_row = next((row for row in rows_by_country[code] if row["armilar_category"] == category), None)
            benchmark = benchmarks.get((code, category))
            aic_ppp = _decimal_or_blank(benchmark.get("aic_ppp", "")) if benchmark else ""
            if aic_ppp == "" and proxy_row:
                aic_ppp = Decimal(str(proxy_row["ppp_lcu_per_international_dollar"]))
            strict_hfce_ppp = _decimal_or_blank(benchmark.get("strict_hfce_ppp", "")) if benchmark else ""
            comparison = _comparison_values(aic_ppp, strict_hfce_ppp)
            if comparison is None:
                status = "NO_MATCHED_OFFICIAL_HFCE_AIC_PPP_BENCHMARK"
                ratio: Decimal | str = ""
                error: Decimal | str = ""
            else:
                ratio, error = comparison
                status = "DIRECT_OFFICIAL_COMPARISON_AVAILABLE"
            ppp_comparison_rows.append({
                "economy_code": code,
                "economy_name": economy_name,
                "armilar_category": category,
                "aic_ppp": aic_ppp,
                "strict_hfce_ppp": strict_hfce_ppp,
                "ppp_ratio_hfce_to_aic": ratio,
                "implied_real_expenditure_error_ratio": error,
                "status": status,
                "source_authority": benchmark.get("source_authority", "") if benchmark else "",
                "source_url": benchmark.get("source_url", "") if benchmark else "",
                "reference_year": benchmark.get("reference_year", "") if benchmark else "",
                "classification": benchmark.get("classification", "") if benchmark else "",
                "evidence_note": (
                    benchmark.get("notes", "Matched official benchmark supplied in the explicit registry.")
                    if benchmark else
                    "No matched official strict-HFCE and AIC PPP observation is registered for this economy/category."
                ),
            })

    category_errors, economy_errors, direct_summary = build_proxy_error_summaries(
        ppp_comparison_rows, policy=_load_proxy_policy(config)
    )
    ordered = sorted(financing_ratios)
    financing_median = Decimal(str(median(ordered))) if ordered else None
    summary: dict[str, Any] = {
        "schema_version": "2.0",
        "reference_year": config.reference_year,
        "methodology": "SEPARATE_AIC_HFCE_FINANCING_EXPOSURE_AND_MATCHED_PPP_PROXY_ERROR_AUDIT",
        "financing_exposure_comparisons": len(financing_ratios),
        "financing_exposure_median": financing_median if financing_median is not None else "",
        "financing_exposure_minimum": min(financing_ratios) if financing_ratios else "",
        "financing_exposure_maximum": max(financing_ratios) if financing_ratios else "",
        "proxy_categories": sorted(PROXY_CATEGORIES),
        "option_b_monetary_use_allowed": False,
        "option_b_research_use_allowed": True,
        "financing_gap_is_proxy_error": False,
        **direct_summary,
        "reason": direct_summary["reason"],
        # Included so callers that still use the three-value API can emit the
        # additional files without recalculating from raw data.
        "error_by_category_rows": category_errors,
        "error_by_economy_rows": economy_errors,
    }
    return financing_rows, ppp_comparison_rows, summary



def normalize_proxy_comparison_rows(comparison_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and calculate matched HFCE/AIC PPP comparison rows."""
    output: list[dict[str, Any]] = []
    for raw in comparison_rows:
        row = dict(raw)
        aic = _decimal_or_blank(row.get("aic_ppp", ""))
        hfce = _decimal_or_blank(row.get("strict_hfce_ppp", ""))
        values = _comparison_values(aic, hfce)
        row["aic_ppp"] = aic
        row["strict_hfce_ppp"] = hfce
        if values is None:
            row["ppp_ratio_hfce_to_aic"] = ""
            row["implied_real_expenditure_error_ratio"] = ""
            row["status"] = row.get("status") or "NO_MATCHED_OFFICIAL_HFCE_AIC_PPP_BENCHMARK"
        else:
            ratio, error = values
            row["ppp_ratio_hfce_to_aic"] = ratio
            row["implied_real_expenditure_error_ratio"] = error
            row["status"] = "DIRECT_OFFICIAL_COMPARISON_AVAILABLE"
        output.append(row)
    return output

def build_proxy_error_summaries(
    comparison_rows: Iterable[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    effective = {**DEFAULT_PROXY_POLICY, **(policy or {})}
    valid: list[dict[str, Any]] = []
    for row in normalize_proxy_comparison_rows(comparison_rows):
        error = row.get("implied_real_expenditure_error_ratio", "")
        if not isinstance(error, Decimal):
            continue
        valid.append({**row, "absolute_error_ratio": abs(error)})

    category_rows = _group_error_rows(valid, "armilar_category")
    economy_rows = _group_error_rows(valid, "economy_code", include_name=True)
    categories_with_minimum = sum(
        1 for row in category_rows
        if int(row["direct_comparison_count"]) >= int(effective["minimum_comparisons_per_category"])
    )
    economies = {str(row.get("economy_code", "")) for row in valid}
    abs_errors = [Decimal(str(row["absolute_error_ratio"])) for row in valid]
    signed_errors = [Decimal(str(row["implied_real_expenditure_error_ratio"])) for row in valid]
    median_abs = _median_decimal(abs_errors) if abs_errors else ""
    median_signed = _median_decimal(signed_errors) if signed_errors else ""
    mean_abs = (sum(abs_errors, Decimal("0")) / Decimal(len(abs_errors))) if abs_errors else ""
    minimum_evidence = (
        len(valid) >= int(effective["minimum_direct_comparisons"])
        and len(economies) >= int(effective["minimum_distinct_economies"])
        and categories_with_minimum == len(PROXY_CATEGORIES)
    )
    if not minimum_evidence:
        validation_status = "INSUFFICIENT_DIRECT_EVIDENCE"
        reason = (
            "Matched strict-HFCE and AIC PPP evidence does not satisfy the minimum total, economy and per-category coverage gates."
        )
    elif Decimal(str(median_abs)) <= Decimal(str(effective["validated_median_absolute_error_max"])):
        validation_status = "PROXY_VALIDATED"
        reason = "Matched direct evidence satisfies coverage gates and the median absolute PPP proxy error is within the validation threshold."
    elif Decimal(str(median_abs)) <= Decimal(str(effective["validated_with_limits_median_absolute_error_max"])):
        validation_status = "PROXY_VALIDATED_WITH_LIMITS"
        reason = "Matched direct evidence satisfies coverage gates but the median absolute error requires explicit use limits."
    else:
        validation_status = "PROXY_REJECTED"
        reason = "Matched direct evidence satisfies coverage gates and exceeds the rejection threshold."

    summary = {
        "direct_hfce_vs_aic_ppp_comparisons": len(valid),
        "direct_comparison_economies": len(economies),
        "direct_comparison_categories": len({str(row.get("armilar_category", "")) for row in valid}),
        "proxy_categories_meeting_minimum": categories_with_minimum,
        "overall_median_signed_error_ratio": median_signed,
        "overall_median_absolute_error_ratio": median_abs,
        "overall_mean_absolute_error_ratio": mean_abs,
        "validation_status": validation_status,
        "validation_policy": effective,
        "comparison_weighting": "UNWEIGHTED_DIAGNOSTIC",
        "reason": reason,
    }
    return category_rows, economy_rows, summary


def _group_error_rows(rows: list[dict[str, Any]], key: str, *, include_name: bool = False) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "")), []).append(row)
    output: list[dict[str, Any]] = []
    for value, members in sorted(grouped.items()):
        signed = [Decimal(str(row["implied_real_expenditure_error_ratio"])) for row in members]
        absolute = [abs(item) for item in signed]
        result: dict[str, Any] = {
            key: value,
            "direct_comparison_count": len(members),
            "economy_count": len({str(row.get("economy_code", "")) for row in members}),
            "category_count": len({str(row.get("armilar_category", "")) for row in members}),
            "mean_signed_error_ratio": sum(signed, Decimal("0")) / Decimal(len(signed)),
            "median_signed_error_ratio": _median_decimal(signed),
            "mean_absolute_error_ratio": sum(absolute, Decimal("0")) / Decimal(len(absolute)),
            "median_absolute_error_ratio": _median_decimal(absolute),
            "maximum_absolute_error_ratio": max(absolute),
            "status": "DIRECT_EVIDENCE_SUMMARY",
        }
        if include_name:
            result["economy_name"] = str(members[0].get("economy_name", ""))
        output.append(result)
    return output


def _load_official_benchmarks(config: Step2Config) -> dict[tuple[str, str], dict[str, str]]:
    path = config.proxy_ppp_benchmarks_path
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        code = (row.get("economy_code") or "").strip().upper()
        category = (row.get("armilar_category") or "").strip().upper()
        if not code or category not in PROXY_CATEGORIES:
            continue
        if str(row.get("reference_year", "")).strip() not in {"", str(config.reference_year)}:
            continue
        if (row.get("source_authority") or "").strip() == "":
            continue
        output[(code, category)] = {key: (value or "").strip() for key, value in row.items()}
    return output


def _load_proxy_policy(config: Step2Config) -> dict[str, Any]:
    try:
        payload = json.loads(config.methodology_policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_PROXY_POLICY)
    configured = payload.get("proxy_validation", {})
    return {**DEFAULT_PROXY_POLICY, **configured}


def _comparison_values(aic_ppp: Decimal | str, strict_hfce_ppp: Decimal | str) -> tuple[Decimal, Decimal] | None:
    if not isinstance(aic_ppp, Decimal) or not isinstance(strict_hfce_ppp, Decimal):
        return None
    if aic_ppp <= 0 or strict_hfce_ppp <= 0:
        return None
    ratio = strict_hfce_ppp / aic_ppp
    return ratio, ratio - Decimal("1")


def _decimal_or_blank(value: Any) -> Decimal | str:
    if value in {None, ""}:
        return ""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""


def _median_decimal(values: list[Decimal]) -> Decimal:
    return Decimal(str(median(sorted(values))))
