import json
import unittest
from pathlib import Path

from armilar_pipeline.config import load_config

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_pinned_to_icp_2021_source_90_and_option_b(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        self.assertEqual(config.source_id, "90")
        self.assertEqual(config.reference_year, 2021)
        self.assertEqual(config.pipeline_version, "0.6.0")
        self.assertEqual(config.aggregate_country_name_tokens, ("benchmark",))
        self.assertIn("NAB", config.aggregate_country_codes)
        self.assertEqual(set(config.proxy_ppp_heading_by_category), {"CP04", "CP06", "CP09", "CP10", "CP12"})
        policy = json.loads((ROOT / "config" / "methodology_policy.json").read_text())
        self.assertEqual(policy["decision"], "OPTION_B")
        self.assertEqual(policy["status"], "RATIFIED_FOR_RESEARCH_DEVELOPMENT")

    def test_all_official_acquisition_routes_are_declared(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        for key in (
            "advanced_data_base", "oecd_table5_t501", "oecd_table5a_t501",
            "eurostat_nama_10_cp18", "undata_sna_table32",
        ):
            self.assertIn(key, config.urls)
            self.assertTrue(config.urls[key].startswith("https://"))

    def test_external_code_corrections_are_explicit(self):
        text = (ROOT / "config" / "external_economy_codes.csv").read_text()
        self.assertIn("RUS,RUT", text)
        self.assertIn("BES,BON", text)

    def test_step2h0_registry_covers_ten_priority_economies(self):
        import csv
        path = ROOT / "config" / "source_probe_candidates.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 11)
        self.assertEqual(len({row["economy_code"] for row in rows}), 10)
        self.assertTrue(all(None not in row for row in rows))
        self.assertEqual(
            {row["methodological_candidate_class"] for row in rows},
            {"B_CANDIDATE", "C_ONLY", "D_UNAVAILABLE"},
        )


if __name__ == "__main__":
    unittest.main()
