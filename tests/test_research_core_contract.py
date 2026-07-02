from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ResearchCoreContractTests(unittest.TestCase):
    def test_constitution_is_draft_and_blocked(self) -> None:
        constitution = json.loads((ROOT / "constitution" / "ARMILAR_RESEARCH_CORE_V1.json").read_text(encoding="utf-8"))
        self.assertEqual(constitution["constitution_id"], "ARMILAR_RESEARCH_CORE_V1")
        self.assertEqual(constitution["constitution_version"], "0.1.0-draft")
        self.assertEqual(constitution["constitution_status"], "DRAFT")
        self.assertEqual(constitution["research_core_id"], "ARMILAR_RESEARCH_CORE_V1")
        self.assertFalse(constitution["scope"]["world_index_claim_allowed"])
        self.assertFalse(constitution["scope"]["monetary_use_allowed"])
        self.assertFalse(constitution["release_gates"]["research_release_allowed"])
        self.assertFalse(constitution["release_gates"]["model_promotion_allowed"])
        self.assertFalse(constitution["release_gates"]["monetary_release_allowed"])
        self.assertFalse(constitution["release_gates"]["shadow_production_allowed"])
        self.assertEqual(constitution["basket_materialization"]["status"], "BASKET_MATERIALIZATION_BLOCKED")
        self.assertEqual(constitution["basket_materialization"]["expected_cell_count"], 60)
        self.assertEqual(constitution["basket_materialization"]["required_input"], "artifacts/v093/first_published_panel/first_published_observations.csv")

    def test_contract_links_are_present(self) -> None:
        decision = (ROOT / "docs" / "DECISION_RESEARCH_CORE_V1.md").read_text(encoding="utf-8")
        next_actions = (ROOT / "NEXT_ACTIONS.md").read_text(encoding="utf-8")
        self.assertIn("constitution/ARMILAR_RESEARCH_CORE_V1.json", decision)
        self.assertIn("schemas/research_core_constitution.schema.json", decision)
        self.assertIn("BASKET_MATERIALIZATION_BLOCKED", decision)
        self.assertIn("constitution/ARMILAR_RESEARCH_CORE_V1.json", next_actions)
        self.assertIn("BASKET_MATERIALIZATION_BLOCKED", next_actions)

    def test_no_basket_csv_is_materialized(self) -> None:
        self.assertFalse((ROOT / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv").exists())


if __name__ == "__main__":
    unittest.main()
