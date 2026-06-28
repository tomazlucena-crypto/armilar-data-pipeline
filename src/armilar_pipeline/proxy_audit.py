from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Any

from .config import Step2Config
from .hybrid_matrix import HybridMatrixResult, PROXY_CATEGORIES, _unit_multiplier
from .measures import MeasureSelection
from .worldbank import DimensionRoles, Observation, Variable


AIC_HEADING = "9020000"


def build_proxy_audit(
    config: Step2Config,
    *,
    roles: DimensionRoles,
    observations: list[Observation],
    inventories: dict[str, list[Variable]],
    measures: MeasureSelection,
    matrix: HybridMatrixResult,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Build the Step 2H0 evidence audit for the ratified AIC-PPP proxy.

    The financing-exposure ratio is diagnostic only. It does not estimate the
    PPP proxy error. The direct PPP comparison remains unavailable where the
    public ICP release omits the strict HFCE PPP for the five proxy categories.
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

    ppp_comparison_rows: list[dict[str, Any]] = []
    for code in complete_codes:
        economy_name = rows_by_country[code][0]["economy_name"]
        for category in sorted(PROXY_CATEGORIES):
            proxy_row = next((row for row in rows_by_country[code] if row["armilar_category"] == category), None)
            ppp_comparison_rows.append({
                "economy_code": code,
                "economy_name": economy_name,
                "armilar_category": category,
                "aic_ppp": proxy_row["ppp_lcu_per_international_dollar"] if proxy_row else "",
                "strict_hfce_ppp": "",
                "ppp_ratio_hfce_to_aic": "",
                "implied_real_expenditure_error_ratio": "",
                "status": "NO_PUBLIC_STRICT_HFCE_PPP_BENCHMARK",
                "evidence_note": "The public ICP 2021 global release does not publish the matching strict HFCE PPP for this category.",
            })

    ordered = sorted(financing_ratios)
    financing_median = Decimal(str(median(ordered))) if ordered else None
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "reference_year": config.reference_year,
        "methodology": "AIC_PPP_PROXY_EVIDENCE_AUDIT",
        "financing_exposure_comparisons": len(financing_ratios),
        "financing_exposure_median": financing_median if financing_median is not None else "",
        "financing_exposure_minimum": min(financing_ratios) if financing_ratios else "",
        "financing_exposure_maximum": max(financing_ratios) if financing_ratios else "",
        "direct_hfce_vs_aic_ppp_comparisons": 0,
        "proxy_categories": sorted(PROXY_CATEGORIES),
        "validation_status": "INSUFFICIENT_DIRECT_EVIDENCE",
        "option_b_monetary_use_allowed": False,
        "option_b_research_use_allowed": True,
        "reason": "No public matched strict-HFCE PPP benchmark exists for the five proxy categories in Source 90. Financing exposure is reported separately and is not treated as an error estimate.",
    }
    return financing_rows, ppp_comparison_rows, summary
