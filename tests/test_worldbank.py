import tempfile
import unittest
import zipfile
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.worldbank import (
    DimensionRoles, Variable, build_heading_query, extract_concepts, extract_variables, identify_roles,
    validate_classification_workbook, validate_source_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


class WorldBankTests(unittest.TestCase):
    def test_extract_concepts_and_variables(self):
        concepts_payload = {
            "source": [{"id": "90", "concept": [
                {"id": "Country", "value": "Country"},
                {"id": "Classification", "value": "Classification"},
                {"id": "Series", "value": "Series"},
                {"id": "Time", "value": "Time"},
            ]}]
        }
        self.assertEqual(len(extract_concepts(concepts_payload)), 4)
        variables_payload = {"source": [{"concept": {"id": "Series", "variable": [
            {"id": "1101000", "value": "FOOD AND NON-ALCOHOLIC BEVERAGES"}
        ]}}]}
        variables = extract_variables(variables_payload)
        self.assertEqual(variables[0].variable_id, "1101000")

    def test_role_discovery_is_content_based(self):
        concepts = [("Country", "Country"), ("Classification", "Classification"), ("Series", "Series"), ("Time", "Time")]
        inventories = {
            "Country": [Variable("Country", f"A{i:02d}", f"Country {i}") for i in range(101)],
            "Classification": [Variable("Classification", "PPP", "Purchasing power parity")],
            "Series": [Variable("Series", code, code) for code in ["1100000", "1101000", "1102000", "1102100", "1102200", "1103000"]],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        roles = identify_roles(concepts, inventories, 2021)
        self.assertEqual(roles.heading, "Series")
        self.assertEqual(roles.measure, "Classification")
        self.assertEqual(roles.year_id, "YR2021")

    def test_role_discovery_allows_headings_in_classification_dimension(self):
        concepts = [("Country", "Country"), ("Classification", "Classification"), ("Series", "Series"), ("Time", "Time")]
        inventories = {
            "Country": [Variable("Country", f"A{i:02d}", f"Country {i}") for i in range(101)],
            "Classification": [
                Variable("Classification", code, code)
                for code in ["1100000", "1101000", "1102000", "1102100", "1102200", "1103000"]
            ],
            "Series": [Variable("Series", "PPP", "Purchasing power parity")],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        roles = identify_roles(concepts, inventories, 2021)
        self.assertEqual(roles.heading, "Classification")
        self.assertEqual(roles.measure, "Series")

    def test_advanced_query_follows_discovered_order(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles("Country", "Series", "Classification", "Time", ("Country", "Classification", "Series", "Time"), "YR2021")
        url = build_heading_query(config, roles, "1101000")
        self.assertIn("/country/all/classification/all/series/1101000/time/YR2021/data", url)

    def test_validates_exact_icp2021_source_metadata(self):
        payload = [
            {"page": 1, "pages": 1, "total": 1},
            [{"id": "90", "name": "International Comparison Program (ICP) 2021", "code": "IC2"}],
        ]
        result = validate_source_metadata(payload, "90")
        self.assertEqual(result["id"], "90")
        self.assertEqual(result["source_code"], "IC2")
        with self.assertRaises(ValueError):
            validate_source_metadata([{}, [{"id": "90", "name": "Unrelated database"}]], "90")

    def test_classification_workbook_must_contain_required_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "classification.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", "<sheet>1100000 1101000 1102100</sheet>")
            result = validate_classification_workbook(path, ["1100000", "1101000", "1102100"])
            self.assertTrue(result["valid_xlsx"])
            with self.assertRaises(ValueError):
                validate_classification_workbook(path, ["1100000", "1102300"])


if __name__ == "__main__":
    unittest.main()
