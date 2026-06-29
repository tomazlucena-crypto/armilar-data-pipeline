from __future__ import annotations

from decimal import Decimal
from typing import Any

from .hybrid_matrix import DIRECT_CATEGORIES, HybridMatrixResult


CLASS_PROBABILITY = {
    "A_CANDIDATE": Decimal("0.95"),
    "B_CANDIDATE": Decimal("0.65"),
    "C_ONLY": Decimal("0.10"),
    "D_UNAVAILABLE": Decimal("0.01"),
}

COST_DIVISOR = {
    "LOW": Decimal("1"),
    "MEDIUM": Decimal("2"),
    "HIGH": Decimal("4"),
    "VERY_HIGH": Decimal("8"),
}


def build_gap_priority(
    matrix: HybridMatrixResult,
    source_probe_economies: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    participant_registry = {
        str(row["economy_code"]): row
        for row in matrix.economy_registry_rows
        if row["icp_participation_status"] == "PARTICIPATING"
    }
    categories: dict[str, set[str]] = {}
    direct_real: dict[str, Decimal] = {}
    all_real: dict[str, Decimal] = {}
    for row in matrix.all_category_rows:
        code = str(row["economy_code"])
        category = str(row["armilar_category"])
        value = Decimal(str(row["real_expenditure_ppp"]))
        categories.setdefault(code, set()).add(category)
        all_real[code] = all_real.get(code, Decimal("0")) + value
        if category in DIRECT_CATEGORIES:
            direct_real[code] = direct_real.get(code, Decimal("0")) + value

    total_direct = sum((direct_real.get(code, Decimal("0")) for code in sorted(participant_registry)), Decimal("0"))
    complete_codes = {
        str(row["economy_code"])
        for row in matrix.economy_registry_rows
        if row["icp_participation_status"] == "PARTICIPATING"
        and str(row["eligible_complete_12_category_matrix"]).lower() in {"true", "1"}
    }
    complete_direct = sum((direct_real.get(code, Decimal("0")) for code in sorted(complete_codes)), Decimal("0"))
    probe_by_code = {str(row["economy_code"]): row for row in source_probe_economies}

    rows: list[dict[str, Any]] = []
    for code, registry in participant_registry.items():
        present = categories.get(code, set())
        if len(present) == 12:
            continue
        direct_value = direct_real.get(code, Decimal("0"))
        direct_share = direct_value / total_direct if total_direct > 0 else Decimal("0")
        probe = probe_by_code.get(code, {})
        candidate_class = str(probe.get("best_runtime_candidate_class") or "NOT_PROBED")
        probability = CLASS_PROBABILITY.get(candidate_class, Decimal("0"))
        cost = str(probe.get("integration_cost") or "NOT_ESTIMATED").upper()
        divisor = COST_DIVISOR.get(cost, Decimal("10"))
        score = direct_share * probability / divisor
        rows.append({
            "economy_code": code,
            "economy_name": registry["economy_name"],
            "categories_available": len(present),
            "missing_categories": "|".join(sorted({f"CP{i:02d}" for i in range(1, 13)} - present)),
            "direct_categories_available": len(present & DIRECT_CATEGORIES),
            "direct_real_expenditure_ppp_indicator": direct_value,
            "direct_expenditure_share_of_participant_indicator": direct_share,
            "source_probe_class": candidate_class,
            "source_probe_best_source_id": probe.get("best_source_id", ""),
            "source_probe_retrieval_status": probe.get("retrieval_status", "NOT_PROBED"),
            "candidate_success_probability_assumption": probability if candidate_class in CLASS_PROBABILITY else "",
            "integration_cost_assumption": cost,
            "development_priority_score": score,
            "blocking_reason": probe.get("blocking_reason", "NOT_INCLUDED_IN_TOP10_SOURCE_PROBE"),
        })

    rows.sort(
        key=lambda row: (
            Decimal(str(row["direct_real_expenditure_ppp_indicator"])),
            str(row["economy_code"]),
        ),
        reverse=True,
    )
    cumulative = Decimal("0")
    for rank, row in enumerate(rows, start=1):
        cumulative += Decimal(str(row["direct_expenditure_share_of_participant_indicator"]))
        row["economic_gap_rank"] = rank
        row["cumulative_direct_expenditure_share_of_incomplete_economies"] = cumulative
        row["source_adjusted_priority_rank"] = ""

    source_ranked = sorted(
        (row for row in rows if row["source_probe_class"] != "NOT_PROBED"),
        key=lambda row: (
            Decimal(str(row["development_priority_score"])),
            Decimal(str(row["direct_real_expenditure_ppp_indicator"])),
        ),
        reverse=True,
    )
    for rank, row in enumerate(source_ranked, start=1):
        row["source_adjusted_priority_rank"] = rank

    summary = {
        "participant_direct_expenditure_indicator_total": total_direct,
        "complete_economy_direct_expenditure_indicator_total": complete_direct,
        "complete_economy_indicator_coverage_ratio": complete_direct / total_direct if total_direct else Decimal("0"),
        "incomplete_economies_ranked": len(rows),
        "top10_direct_expenditure_share": sum(
            (Decimal(str(row["direct_expenditure_share_of_participant_indicator"])) for row in rows[:10]),
            Decimal("0"),
        ),
        "top20_direct_expenditure_share": sum(
            (Decimal(str(row["direct_expenditure_share_of_participant_indicator"])) for row in rows[:20]),
            Decimal("0"),
        ),
        "indicator_warning": "This priority indicator uses only seven direct ICP categories. It is not a final Armilar weight or a world-coverage estimate.",
    }
    return rows, summary
