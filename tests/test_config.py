import unittest
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.matrix import NORMALIZED_FIELDS
from armilar_pipeline.util import read_csv


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_pinned_to_icp_2021_source_90(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        self.assertEqual(config.source_id, "90")
        self.assertEqual(config.reference_year, 2021)

    def test_crosswalk_is_strict_hfce(self):
        rows = read_csv(ROOT / "config" / "icp_headings_to_armilar.csv")
        included = [row for row in rows if row["include_in_category"] == "true"]
        self.assertTrue(all(row["heading_code"].startswith("11") for row in included))
        self.assertNotIn("1102000", {row["heading_code"] for row in included})
        self.assertNotIn("1102300", {row["heading_code"] for row in included})
        cp02 = {row["heading_code"] for row in included if row["armilar_category"] == "CP02"}
        self.assertEqual(cp02, {"1102100", "1102200"})
        self.assertEqual({row["armilar_category"] for row in included}, {f"CP{i:02d}" for i in range(1, 13)})

    def test_normalized_output_contract_contains_required_provenance_fields(self):
        required = {
            "economy_code", "economy_name", "icp_participation_status", "heading_code",
            "heading_name", "armilar_category", "expenditure_measure", "value", "unit",
            "currency_or_ppp_basis", "source_file", "source_url", "retrieved_at",
            "source_hash", "quality_flags",
        }
        self.assertTrue(required.issubset(set(NORMALIZED_FIELDS)))

    def test_source_registry_contains_all_authoritative_routes(self):
        rows = read_csv(ROOT / "config" / "source_registry.csv")
        source_ids = {row["source_id"] for row in rows}
        self.assertTrue({
            "WB_SOURCE_90_METADATA", "WB_SOURCE_90_CONCEPTS", "WB_SOURCE_90_VARIABLES",
            "WB_SOURCE_90_DATA", "ICP_2021_CLASSIFICATION", "ICP_2021_GOVERNANCE",
            "ICP_2021_DATA_PAGE", "ICP_FAQ", "ICP_2021_PUBLISHED_TABLE",
        }.issubset(source_ids))
        self.assertTrue(all(row["authority"] == "World Bank" for row in rows))

    def test_publication_scope_rules_never_accept_aic_or_npish_surrogates(self):
        from armilar_pipeline.pipeline import _publication_scope_audit
        rules = ROOT / "config" / "publication_scope_rules.csv"
        available = {"9100000", "9060000", "9080000", "9110000", "9120000", "9140000"}
        rows = _publication_scope_audit(rules, available)
        self.assertTrue(all(not row["admissible_for_armilar"] for row in rows))



if __name__ == "__main__":
    unittest.main()
