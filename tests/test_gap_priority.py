from __future__ import annotations

import unittest
from decimal import Decimal

from armilar_pipeline.gap_priority import build_gap_priority
from armilar_pipeline.hybrid_matrix import HybridMatrixResult


def matrix_fixture() -> HybridMatrixResult:
    registry = [
        {"economy_code": "CHN", "economy_name": "China", "icp_participation_status": "PARTICIPATING", "eligible_complete_12_category_matrix": False},
        {"economy_code": "IND", "economy_name": "India", "icp_participation_status": "PARTICIPATING", "eligible_complete_12_category_matrix": False},
        {"economy_code": "AAA", "economy_name": "Complete", "icp_participation_status": "PARTICIPATING", "eligible_complete_12_category_matrix": True},
    ]
    rows = []
    for code, value in (("CHN", "100"), ("IND", "50"), ("AAA", "25")):
        for category in ("CP01", "CP02", "CP03", "CP05", "CP07", "CP08", "CP11"):
            rows.append({"economy_code": code, "armilar_category": category, "real_expenditure_ppp": Decimal(value)})
        if code == "AAA":
            for category in ("CP04", "CP06", "CP09", "CP10", "CP12"):
                rows.append({"economy_code": code, "armilar_category": category, "real_expenditure_ppp": Decimal("25")})
    return HybridMatrixResult([], [], [], [], [], rows, [], [], registry, [], [], [], {})


class GapPriorityTests(unittest.TestCase):
    def test_economic_and_source_adjusted_ranks_are_distinct(self) -> None:
        probes = [
            {"economy_code": "CHN", "best_runtime_candidate_class": "C_ONLY", "best_source_id": "CHN_SURVEY", "retrieval_status": "ACCESSIBLE", "integration_cost": "HIGH", "blocking_reason": "SURVEY"},
            {"economy_code": "IND", "best_runtime_candidate_class": "B_CANDIDATE", "best_source_id": "IND_NA", "retrieval_status": "ACCESSIBLE", "integration_cost": "LOW", "blocking_reason": "MAPPING"},
        ]
        rows, summary = build_gap_priority(matrix_fixture(), probes)
        by_code = {row["economy_code"]: row for row in rows}
        self.assertEqual(by_code["CHN"]["economic_gap_rank"], 1)
        self.assertEqual(by_code["IND"]["economic_gap_rank"], 2)
        self.assertEqual(by_code["IND"]["source_adjusted_priority_rank"], 1)
        self.assertGreater(summary["top10_direct_expenditure_share"], Decimal("0"))
        self.assertIn("not a final Armilar weight", summary["indicator_warning"])


if __name__ == "__main__":
    unittest.main()
