import unittest
from pathlib import Path

from armilar_pipeline.pipeline import _publication_scope_audit


ROOT = Path(__file__).resolve().parents[1]


class PublicationScopeTests(unittest.TestCase):
    def test_current_public_release_aic_surrogates_are_detected_and_rejected(self):
        # Mirrors the official 45-heading publication layout: strict HFCE is
        # available for some divisions, while actual-consumption substitutes
        # appear for housing, health, recreation, education and miscellaneous.
        available = {
            "1000000", "9020000", "9100000",
            "1101000", "1102000", "1102100", "1102200", "1103000",
            "9060000", "1105000", "9080000", "1107000", "1108000",
            "9110000", "9120000", "1111000", "9140000",
        }
        rows = _publication_scope_audit(ROOT / "config" / "publication_scope_rules.csv", available)
        by_category = {row["armilar_category"]: row for row in rows}
        self.assertEqual(
            by_category["HFCE_CONTROL"]["missing_required_heading_codes"], "1100000"
        )
        self.assertEqual(
            by_category["HFCE_CONTROL"]["available_forbidden_alternative_codes"], "9100000"
        )
        for category, strict_code, surrogate in [
            ("CP04", "1104000", "9060000"),
            ("CP06", "1106000", "9080000"),
            ("CP09", "1109000", "9110000"),
            ("CP10", "1110000", "9120000"),
            ("CP12", "1112000", "9140000"),
        ]:
            self.assertEqual(by_category[category]["missing_required_heading_codes"], strict_code)
            self.assertEqual(by_category[category]["available_forbidden_alternative_codes"], surrogate)
            self.assertEqual(by_category[category]["status"], "BLOCKED_REQUIRED_HFCE_HEADING_MISSING")
            self.assertFalse(by_category[category]["admissible_for_armilar"])
        self.assertEqual(by_category["CP02"]["status"], "PASS_STRICT_HFCE_AVAILABLE")
        self.assertEqual(by_category["CP02"]["available_forbidden_alternative_codes"], "1102000")


if __name__ == "__main__":
    unittest.main()
