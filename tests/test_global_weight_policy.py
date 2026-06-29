from __future__ import annotations

import json
import unittest
from pathlib import Path


class GlobalWeightPolicyTests(unittest.TestCase):
    def test_global_weight_policy_separates_core_and_global(self) -> None:
        root = Path(__file__).resolve().parents[1]
        policy = json.loads((root / "config" / "global_weight_policy.json").read_text(encoding="utf-8"))
        self.assertFalse(policy["core_construction"]["world_claim_allowed"])
        self.assertTrue(policy["global_construction"]["requires_complete_economy_category_grid"])
        self.assertTrue(policy["global_construction"]["requires_uncertainty_for_estimates"])
        self.assertFalse(policy["monetary_release_allowed"])
        self.assertEqual(len(policy["canonical_categories"]), 12)

    def test_reuse_registry_exists_and_has_decisions(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "config" / "component_registry.yaml").read_text(encoding="utf-8")
        for token in (
            "sdmx1",
            "pysdmx",
            "DBnomics",
            "DuckDB",
            "Pandera",
            "Hypothesis",
            "FastAPI",
            "Prefect",
            "MLflow",
        ):
            self.assertIn(token, text)
        self.assertIn("decision:", text)
        self.assertIn("REVIEW_PER_FETCHER", text)


if __name__ == "__main__":
    unittest.main()
