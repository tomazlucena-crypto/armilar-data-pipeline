import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.matrix import _blocking_reasons, _weights
from armilar_pipeline.worldbank import Variable


ROOT = Path(__file__).resolve().parents[1]


class WeightTests(unittest.TestCase):
    def test_emitted_weights_sum_exactly_one(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        countries = ["AAA", "BBB"]
        categories = ["CP01", "CP02"]
        values = {
            ("AAA", "CP01"): Decimal("1"),
            ("AAA", "CP02"): Decimal("2"),
            ("BBB", "CP01"): Decimal("3"),
            ("BBB", "CP02"): Decimal("4"),
        }
        country_vars = {code: Variable("Country", code, code) for code in countries}
        rows, _, _, total = _weights(config, values, countries, categories, country_vars)
        self.assertEqual(total, Decimal("1"))
        self.assertEqual(sum((row["weight"] for row in rows), Decimal("0")), Decimal("1"))
        self.assertLessEqual(abs(total - Decimal("1")), config.weight_sum_tolerance)
        self.assertTrue(all(row["weight_status"].startswith("DIAGNOSTIC_PARTIAL_PARTICIPANT_UNIVERSE") for row in rows))

    def test_missing_official_imputation_registry_blocks_global_release(self):
        reasons = _blocking_reasons(
            176, 176, 176, 0, 19, set(), set(), Decimal("1"), Decimal("1E-20")
        )
        self.assertIn("OFFICIAL_IMPUTATION_REGISTRY_COUNT_MISMATCH:0/19", reasons)


if __name__ == "__main__":
    unittest.main()
