from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.hybrid_matrix import HybridMatrixResult
from armilar_pipeline.measures import MeasureSelection
from armilar_pipeline.proxy_audit import build_proxy_audit, build_proxy_error_summaries, normalize_proxy_comparison_rows
from armilar_pipeline.worldbank import DimensionRoles, Observation, Variable

ROOT = Path(__file__).resolve().parents[1]


def observation(heading: str, value: str) -> Observation:
    return Observation(
        variables={"Country": ("AAA", "Alpha"), "Series": (heading, heading), "Classification": ("CN", "Nominal"), "Time": ("YR2021", "2021")},
        value=Decimal(value), source_file=Path("raw.json"), source_url="https://example.test", retrieved_at="2026-06-28T00:00:00Z", source_hash="a" * 64,
    )


class ProxyAuditTests(unittest.TestCase):
    def test_financing_gap_reconstructs_hfce_before_comparison(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles("Country", "Series", "Classification", "Time", ("Country", "Classification", "Series", "Time"), "YR2021")
        inventories = {"Classification": [Variable("Classification", "CN", "Expenditure (local currency units)")]}
        rows = [
            {
                "economy_code": "AAA", "economy_name": "Alpha", "armilar_category": f"CP{i:02d}",
                "nominal_household_expenditure_lcu": Decimal("10"),
                "ppp_lcu_per_international_dollar": Decimal("2"),
            }
            for i in range(1, 13)
        ]
        matrix = HybridMatrixResult([], [], [], [], rows, rows, [], [], [], [], [], [], {})
        observations = [
            observation("9020000", "160"),
            observation("1102000", "10"),
            observation("1102100", "4"),
            observation("1102200", "3"),
            observation("1113000", "-2"),
        ]
        financing, comparisons, summary = build_proxy_audit(
            config, roles=roles, observations=observations, inventories=inventories,
            measures=MeasureSelection("PPP", "CN", "REAL", diagnostics=[]), matrix=matrix,
        )
        self.assertEqual(financing[0]["derived_narcotics_nominal_lcu"], Decimal("3"))
        self.assertEqual(financing[0]["reconstructed_hfce_nominal_lcu"], Decimal("121"))
        self.assertEqual(financing[0]["aic_minus_hfce_lcu"], Decimal("39"))
        self.assertEqual(len(comparisons), 5)
        self.assertEqual(summary["validation_status"], "INSUFFICIENT_DIRECT_EVIDENCE")
        self.assertFalse(summary["option_b_monetary_use_allowed"])


    def test_direct_ppp_proxy_error_uses_hfce_to_aic_ppp_ratio(self) -> None:
        rows = normalize_proxy_comparison_rows([{
            "economy_code": "AAA", "economy_name": "Alpha", "armilar_category": "CP04",
            "aic_ppp": "2", "strict_hfce_ppp": "2.1",
        }])
        self.assertEqual(rows[0]["ppp_ratio_hfce_to_aic"], Decimal("1.05"))
        self.assertEqual(rows[0]["implied_real_expenditure_error_ratio"], Decimal("0.05"))
        self.assertEqual(rows[0]["status"], "DIRECT_OFFICIAL_COMPARISON_AVAILABLE")

    def test_financing_gap_cannot_validate_proxy_without_direct_ppp_pairs(self) -> None:
        categories, economies, summary = build_proxy_error_summaries([])
        self.assertEqual(categories, [])
        self.assertEqual(economies, [])
        self.assertEqual(summary["validation_status"], "INSUFFICIENT_DIRECT_EVIDENCE")
        self.assertEqual(summary["direct_hfce_vs_aic_ppp_comparisons"], 0)

    def test_direct_error_summaries_are_separated_by_category_and_economy(self) -> None:
        rows = [
            {"economy_code": "AAA", "economy_name": "Alpha", "armilar_category": "CP04", "aic_ppp": "2", "strict_hfce_ppp": "2.02"},
            {"economy_code": "AAA", "economy_name": "Alpha", "armilar_category": "CP06", "aic_ppp": "4", "strict_hfce_ppp": "3.96"},
        ]
        categories, economies, summary = build_proxy_error_summaries(rows)
        self.assertEqual(len(categories), 2)
        self.assertEqual(len(economies), 1)
        self.assertEqual(economies[0]["direct_comparison_count"], 2)
        self.assertEqual(summary["validation_status"], "INSUFFICIENT_DIRECT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
