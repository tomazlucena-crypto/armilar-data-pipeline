import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.hybrid_matrix import _normalise_weights


ROOT = Path(__file__).resolve().parents[1]


class WeightTests(unittest.TestCase):
    def test_emitted_weights_sum_exactly_one(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        rows = [
            {"economy_code": "AAA", "armilar_category": "CP01", "real_expenditure_ppp": Decimal("1")},
            {"economy_code": "AAA", "armilar_category": "CP02", "real_expenditure_ppp": Decimal("2")},
            {"economy_code": "BBB", "armilar_category": "CP01", "real_expenditure_ppp": Decimal("3")},
            {"economy_code": "BBB", "armilar_category": "CP02", "real_expenditure_ppp": Decimal("4")},
        ]
        weights = _normalise_weights(rows, config)
        total = sum((row["weight"] for row in weights), Decimal("0"))
        self.assertEqual(total, Decimal("1"))
        self.assertLessEqual(abs(total - Decimal("1")), config.weight_sum_tolerance)
        self.assertTrue(all("rounding_residual_applied" in row for row in weights))
        self.assertEqual(sum((row["rounding_residual_applied"] for row in weights), Decimal("0")), Decimal("0"))

    def test_empty_or_nonpositive_matrix_never_emits_weights(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        self.assertEqual(_normalise_weights([], config), [])
        self.assertEqual(_normalise_weights([
            {"economy_code": "AAA", "armilar_category": "CP01", "real_expenditure_ppp": Decimal("0")}
        ], config), [])


if __name__ == "__main__":
    unittest.main()
