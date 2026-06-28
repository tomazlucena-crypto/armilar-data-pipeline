import unittest
from pathlib import Path

from armilar_pipeline.participation import extract_participating_names, map_participants_to_codes
from armilar_pipeline.worldbank import Variable


ROOT = Path(__file__).resolve().parents[1]


def names(start, end):
    return "; ".join(f"C{i:03d}" for i in range(start, end + 1))


class ParticipationTests(unittest.TestCase):
    def test_extracts_176_unique_economies_with_dual_participation(self):
        html = f"""
        <h3>Participating economies in the ICP 2021 cycle, by region</h3>
        <h4>Africa: 52 economies</h4><p>Regional implementing agency: X</p><p>{names(1,52)}.</p>
        <h4>Asia and the Pacific: 21 economies</h4><p>Regional implementing agency: X</p><p>{names(53,73)}.</p>
        <h4>Commonwealth of Independent States: 9 economies</h4><p>Regional implementing agency: X</p><p>{names(74,82)}.</p>
        <h4>Latin America and the Caribbean: 32 economies</h4><p>Regional implementing agency: X</p><p>{names(83,114)}.</p>
        <h4>Western Asia: 16 economies</h4><p>Regional implementing agency: X</p><p>{names(1,5)}; {names(115,125)}.</p>
        <h4>Europe and Organisation for Economic Co-operation and Development (OECD): 51 economies</h4>
        <p>Implementing agencies: Eurostat and OECD</p><p>{names(126,176)}.</p><h3>RELATED</h3>
        """
        result = extract_participating_names(html)
        self.assertEqual(len(result), 176)
        self.assertEqual(len(set(result)), 176)

    def test_parses_preserved_official_participation_section(self):
        html = (ROOT / "tests" / "fixtures" / "icp2021_participation_official_section.html").read_text(encoding="utf-8")
        result = extract_participating_names(html)
        self.assertEqual(len(result), 176)
        self.assertIn("Egypt, Arab Rep.", result)
        self.assertIn("South Africa", result)
        self.assertIn("Anguilla", result)
        self.assertIn("United States", result)
        self.assertEqual(result.count("Mauritania"), 1)
        self.assertEqual(result.count("Morocco"), 1)
        self.assertEqual(result.count("Sudan"), 1)
        self.assertEqual(result.count("Tunisia"), 1)

    def test_source90_special_codes_map_without_false_economies(self):
        variables = [
            Variable("Country", "RUT", "Russian Federation"),
            Variable("Country", "BON", "Bonaire"),
            Variable("Country", "USA", "United States"),
        ]
        mapped, audit = map_participants_to_codes(
            ["Russian Federation", "Bonaire", "United States"],
            variables, ROOT / "config" / "country_name_aliases.csv",
        )
        self.assertEqual(set(mapped), {"RUT", "BON", "USA"})
        self.assertTrue(all(row["status"] == "MAPPED" for row in audit))


if __name__ == "__main__":
    unittest.main()
