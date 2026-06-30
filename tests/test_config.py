import csv
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
        self.assertEqual(config.pipeline_version, "0.8.0")
        self.assertEqual(config.source_probe_max_workers, 5)
        self.assertEqual(config.aggregate_country_name_tokens, ("benchmark",))
        self.assertIn("NAB", config.aggregate_country_codes)
        self.assertEqual(set(config.proxy_ppp_heading_by_category), {"CP04", "CP06", "CP09", "CP10", "CP12"})
        policy = json.loads((ROOT / "config" / "methodology_policy.json").read_text())
        self.assertEqual(policy["decision"], "OPTION_B")
        self.assertEqual(policy["status"], "RATIFIED_FOR_RESEARCH_DEVELOPMENT")

    def test_all_official_acquisition_routes_are_declared(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        for key in (
            "advanced_data_base",
            "oecd_table5_t501",
            "oecd_table5a_t501",
            "eurostat_nama_10_cp18",
            "undata_sna_table32",
        ):
            self.assertIn(key, config.urls)
            self.assertTrue(config.urls[key].startswith("https://"))

    def test_external_code_corrections_are_explicit(self):
        text = (ROOT / "config" / "external_economy_codes.csv").read_text()
        self.assertIn("RUS,RUT", text)
        self.assertIn("BES,BON", text)

    def test_step2h0_registry_covers_priority_economies_and_exceptions(self):
        path = ROOT / "config" / "source_probe_candidates.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 20)
        self.assertEqual(len({row["economy_code"] for row in rows}), 15)
        self.assertTrue(all(row["source_family"] for row in rows))
        self.assertTrue(all(row["source_title"] for row in rows))
        self.assertTrue(all(row["resource_type"] for row in rows))
        self.assertTrue(all(None not in row and all(value is not None for value in row.values()) for row in rows))
        classes = {row["methodological_candidate_class"] for row in rows}
        self.assertTrue(classes <= {"B_CANDIDATE", "C_ONLY", "D_UNAVAILABLE"})
        self.assertIn("C_ONLY", classes)
        self.assertIn("D_UNAVAILABLE", classes)

    def test_russia_registry_uses_exact_resources_not_generic_entry_pages(self):
        path = ROOT / "config" / "source_probe_candidates.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row["economy_code"] == "RUT"]
        self.assertEqual(
            {row["source_id"] for row in rows},
            {
                "RUT_FEDSTAT_HFCE_31414",
                "RUT_ROSSTAT_SUT_2021_XLSX",
                "RUT_ROSSTAT_HBS_2021",
                "RUT_ROSSTAT_KIPC_DH_CLASSIFICATION",
                "RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022",
            },
        )
        self.assertTrue(
            all(
                row["source_url"]
                not in {"https://fedstat.ru/", "https://rosstat.gov.ru/statistics/accounts"}
                for row in rows
            )
        )
        self.assertTrue(all("BRICS" not in row["source_title"] for row in rows))


if __name__ == "__main__":
    unittest.main()
