import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.hybrid_matrix import build_hybrid_matrix
from armilar_pipeline.measures import MeasureSelection
from armilar_pipeline.supplemental import NominalObservation
from armilar_pipeline.worldbank import DimensionRoles, Observation, Variable

ROOT = Path(__file__).resolve().parents[1]


def obs(country, heading, measure, value):
    return Observation(
        variables={"Country": (country, country), "Classification": (measure, measure), "Series": (heading, heading), "Time": ("YR2021", "2021")},
        value=Decimal(value), source_file=Path(f"raw/{heading}.json"), source_url="https://api.worldbank.org", retrieved_at="2026-06-28T00:00:00Z", source_hash="a"*64,
    )


class HybridMatrixTests(unittest.TestCase):
    def _fixture(self, participants=176, imputed=19):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles("Country", "Series", "Classification", "Time", ("Country","Classification","Series","Time"), "YR2021")
        participant_codes = {f"P{i:03d}": f"Participant {i:03d}" for i in range(1, participants+1)}
        imputed_codes = [f"I{i:03d}" for i in range(1, imputed+1)]
        headings = set(config.required_heading_codes)
        inventories = {
            "Country": [Variable("Country", c, n) for c,n in participant_codes.items()] + [Variable("Country", c, f"Imputed {c}") for c in imputed_codes],
            "Classification": [
                Variable("Classification", "PPP", "Purchasing power parity (PPP) (US$ = 1)"),
                Variable("Classification", "CN", "Expenditure (local currency units, billions)"),
                Variable("Classification", "REAL", "Expenditure, PPP-based (US$, billions)"),
            ],
            "Series": [Variable("Series", h, h) for h in headings],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        observations=[]
        direct_nominals = {
            "1101000":"10", "1102100":"2", "1102200":"3", "1103000":"4", "1105000":"5", "1107000":"7", "1108000":"8", "1111000":"11",
        }
        proxy_ppps = {"9060000":"2", "9080000":"2", "9110000":"2", "9120000":"2", "9140000":"2"}
        controls = {"1000000":"100", "9020000":"80", "9100000":"70"}
        for country in participant_codes:
            for heading, nominal in direct_nominals.items():
                observations += [obs(country, heading, "PPP", "2"), obs(country, heading, "CN", nominal), obs(country, heading, "REAL", Decimal(nominal)/Decimal("2"))]
            for heading, ppp in proxy_ppps.items():
                observations += [obs(country, heading, "PPP", ppp), obs(country, heading, "CN", "10"), obs(country, heading, "REAL", "5")]
            for heading, nominal in controls.items():
                observations += [obs(country, heading, "PPP", "2"), obs(country, heading, "CN", nominal), obs(country, heading, "REAL", Decimal(nominal)/Decimal("2"))]
            observations += [obs(country, "1102000", "PPP", "2"), obs(country, "1102000", "CN", "6"), obs(country, "1102000", "REAL", "3")]
            observations += [obs(country, "1113000", "PPP", "2"), obs(country, "1113000", "CN", "0"), obs(country, "1113000", "REAL", "0")]
        for country in imputed_codes:
            for heading, nominal in controls.items():
                observations += [obs(country, heading, "PPP", "2"), obs(country, heading, "CN", nominal), obs(country, heading, "REAL", Decimal(nominal)/Decimal("2"))]
        supplemental=[]
        for country, name in participant_codes.items():
            for category, value_billion in {
                "CP01":"10", "CP03":"4", "CP04":"40", "CP05":"5", "CP06":"60", "CP07":"7", "CP08":"8", "CP09":"90", "CP10":"100", "CP11":"11", "CP12":"120"
            }.items():
                supplemental.append(NominalObservation(
                    economy_code=country, economy_name=name, armilar_category=category,
                    value_lcu=Decimal(value_billion)*Decimal("1000000000"), currency="LCU",
                    source_id="OECD_TABLE5_T501", source_file="oecd.csv", source_url="https://oecd.example",
                    retrieved_at="2026-06-28T00:00:00Z", source_hash="b"*64,
                    concept="HOUSEHOLDS_S14_DOMESTIC_HFCE_P31DC_CURRENT_PRICES", classification="COICOP1999",
                    quality_flags=("OFFICIAL_OECD",), source_priority=10,
                ))
        return config, roles, observations, inventories, MeasureSelection("PPP","CN","REAL", diagnostics=[]), participant_codes, supplemental

    def test_full_participant_research_matrix_and_imputed_separation(self):
        result = build_hybrid_matrix(*self._fixture())
        self.assertEqual(result.summary["participating_economies_mapped"], 176)
        self.assertEqual(result.summary["officially_imputed_aggregate_only_economies"], 19)
        self.assertEqual(result.summary["complete_participating_economies"], 176)
        self.assertEqual(result.summary["observed_universe_weight_cells"], 176*12)
        self.assertEqual(Decimal(result.summary["observed_universe_weight_sum"]), Decimal("1"))
        self.assertTrue(result.summary["research_release_allowed"])
        self.assertFalse(result.summary["global_12_category_matrix_complete"])
        cp02 = next(row for row in result.category_rows if row["economy_code"] == "P001" and row["armilar_category"] == "CP02")
        self.assertEqual(cp02["nominal_household_expenditure_lcu"], Decimal("5000000000"))
        self.assertIn("NARCOTICS_EXCLUDED", cp02["quality_flags"])
        cp04 = next(row for row in result.category_rows if row["economy_code"] == "P001" and row["armilar_category"] == "CP04")
        self.assertEqual(cp04["ppp_source_heading"], "9060000")
        self.assertEqual(cp04["numerator_source_id"], "OECD_TABLE5_T501")
        self.assertEqual(cp04["real_expenditure_ppp"], Decimal("20000000000"))

    def test_missing_proxy_numerator_excludes_whole_economy_without_partial_weights(self):
        fixture=list(self._fixture(participants=1, imputed=0))
        fixture[-1] = [row for row in fixture[-1] if row.armilar_category != "CP04"]
        config=fixture[0]
        object.__setattr__(config, "expected_participating_economies", 1)
        object.__setattr__(config, "expected_officially_imputed_economies", 0)
        result=build_hybrid_matrix(*fixture)
        self.assertEqual(result.summary["complete_participating_economies"], 0)
        self.assertEqual(result.weight_rows, [])
        self.assertEqual(len(result.category_rows), 0)
        self.assertEqual(len(result.all_category_rows), 7)
        self.assertTrue(any(row["armilar_category"] == "CP04" for row in result.missing_rows))

    def test_duplicate_source90_key_is_rejected(self):
        fixture=list(self._fixture(participants=1, imputed=0))
        object.__setattr__(fixture[0], "expected_participating_economies", 1)
        object.__setattr__(fixture[0], "expected_officially_imputed_economies", 0)
        fixture[2].append(fixture[2][0])
        with self.assertRaisesRegex(ValueError, "Duplicate Source 90"):
            build_hybrid_matrix(*fixture)


if __name__ == "__main__":
    unittest.main()
