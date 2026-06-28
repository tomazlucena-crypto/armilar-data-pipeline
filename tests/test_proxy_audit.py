from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.hybrid_matrix import HybridMatrixResult
from armilar_pipeline.measures import MeasureSelection
from armilar_pipeline.proxy_audit import build_proxy_audit
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


if __name__ == "__main__":
    unittest.main()
