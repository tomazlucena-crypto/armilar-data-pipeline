import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.matrix import build_matrix
from armilar_pipeline.measures import MeasureSelection
from armilar_pipeline.worldbank import DimensionRoles, Observation, Variable


ROOT = Path(__file__).resolve().parents[1]
DIRECT = {
    "1101000": Decimal("10"),
    "1103000": Decimal("30"),
    "1104000": Decimal("40"),
    "1105000": Decimal("50"),
    "1106000": Decimal("60"),
    "1107000": Decimal("70"),
    "1108000": Decimal("80"),
    "1109000": Decimal("90"),
    "1110000": Decimal("100"),
    "1111000": Decimal("110"),
    "1112000": Decimal("120"),
}
COMPONENTS = {"1102100": Decimal("12"), "1102200": Decimal("8")}
HEADING_VALUES = {**DIRECT, **COMPONENTS}
AUDIT_VALUES = {"1102000": Decimal("21"), "1102300": Decimal("1"), "1113000": Decimal("-5")}
HFCE = (
    sum(HEADING_VALUES.values(), Decimal("0"))
    + AUDIT_VALUES["1102300"]
    + AUDIT_VALUES["1113000"]
)


def observation(country: str, heading: str, measure: str, value: Decimal) -> Observation:
    return Observation(
        variables={
            "Country": (country, country),
            "Classification": (measure, measure),
            "Series": (heading, heading),
            "Time": ("YR2021", "2021"),
        },
        value=value,
        source_file=Path(f"raw/{heading}.json"),
        source_url="https://api.worldbank.org/test",
        retrieved_at="2026-06-28T00:00:00Z",
        source_hash="a" * 64,
    )


class MatrixEndToEndTests(unittest.TestCase):
    def test_complete_participants_and_aggregate_only_imputations_remain_separate(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles(
            country="Country",
            heading="Series",
            measure="Classification",
            time="Time",
            concept_order=("Country", "Classification", "Series", "Time"),
            year_id="YR2021",
        )
        participant_codes = {f"P{i:03d}": f"Participant {i:03d}" for i in range(1, 177)}
        imputed_codes = [f"I{i:03d}" for i in range(1, 20)]
        country_variables = [
            Variable("Country", code, name) for code, name in participant_codes.items()
        ] + [
            Variable("Country", code, f"Imputed {index:03d}")
            for index, code in enumerate(imputed_codes, start=1)
        ]
        heading_codes = ["1000000", "9020000", "9100000", "1100000", *HEADING_VALUES.keys(), *AUDIT_VALUES.keys()]
        inventories = {
            "Country": country_variables,
            "Classification": [
                Variable("Classification", "PPP", "Purchasing power parity (PPP) (US$ = 1)"),
                Variable("Classification", "NOM", "Expenditure (million LCU)"),
                Variable("Classification", "REAL", "Expenditure (million US$), based on PPPs"),
            ],
            "Series": [Variable("Series", code, code) for code in heading_codes],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        measures = MeasureSelection("PPP", "NOM", "REAL", diagnostics=[])
        observations = []
        for country in participant_codes:
            values = {"1100000": HFCE, **HEADING_VALUES, **AUDIT_VALUES}
            for heading, real in values.items():
                observations.extend([
                    observation(country, heading, "PPP", Decimal("2")),
                    observation(country, heading, "NOM", real * Decimal("2")),
                    observation(country, heading, "REAL", real),
                ])
        for country in imputed_codes:
            # Source 90 publishes aggregate imputed results at GDP, household+NPISH
            # consumption and AIC levels, not a strict twelve-category HFCE allocation.
            for heading in ("1000000", "9020000", "9100000"):
                observations.extend([
                    observation(country, heading, "PPP", Decimal("2")),
                    observation(country, heading, "NOM", HFCE * Decimal("2")),
                    observation(country, heading, "REAL", HFCE),
                ])

        result = build_matrix(config, roles, observations, inventories, measures, participant_codes)

        self.assertEqual(result.summary["eligible_complete_economies"], 176)
        self.assertEqual(result.summary["officially_imputed_aggregate_only_economies"], 19)
        self.assertEqual(result.summary["candidate_weight_cells"], 176 * 12)
        self.assertEqual(Decimal(result.summary["candidate_weight_sum"]), Decimal("1"))
        self.assertTrue(result.summary["candidate_weights_valid_for_observed_participant_universe"])
        self.assertFalse(result.summary["global_12_category_matrix_complete"])
        self.assertFalse(result.summary["release_allowed"])
        self.assertEqual(result.summary["status"], "BLOCKED_WITH_CANDIDATE_MATRIX")
        self.assertIn(
            "OFFICIALLY_IMPUTED_ECONOMIES_HAVE_NO_PUBLIC_12_CATEGORY_ALLOCATION:19",
            result.summary["blocking_reasons"],
        )
        cp02 = [row for row in result.category_rows if row["economy_code"] == "P001" and row["armilar_category"] == "CP02"]
        self.assertEqual(len(cp02), 1)
        self.assertEqual(cp02[0]["real_expenditure_ppp"], Decimal("20"))
        self.assertEqual(cp02[0]["derivation"], "SUM_1102100_1102200_EXCLUDING_1102300")
        self.assertEqual(cp02[0]["nominal_hfce_less_armilar_categories"], Decimal("-8"))
        self.assertEqual(
            sum((row["weight"] for row in result.weight_rows), Decimal("0")),
            Decimal("1"),
        )
        p001_hierarchy = [row for row in result.hierarchy_rows if row["economy_code"] == "P001"]
        self.assertEqual(len(p001_hierarchy), 3)
        self.assertTrue(all(row["status"] == "PASS" for row in p001_hierarchy))
        self.assertTrue(all(row["measure_basis"] == "NOMINAL_EXPENDITURE_LCU" for row in p001_hierarchy))
        imputed_missing = [row for row in result.missing_rows if row["economy_code"] == "I001"]
        self.assertEqual(len(imputed_missing), 12)
        self.assertTrue(all(row["data_status"] == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY" for row in imputed_missing))
        imputed_registry = [row for row in result.country_registry_rows if row["economy_code"] == "I001"][0]
        self.assertEqual(imputed_registry["aggregate_imputation_observation_count"], 3)
        self.assertEqual(imputed_registry["imputation_detection_heading_codes"], "1000000|9020000|9100000")
        self.assertIn("SOURCE90_AGGREGATE_ONLY", imputed_registry["participation_status_basis"])


    def test_real_ppp_expenditures_are_not_required_to_be_additive(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles(
            country="Country", heading="Series", measure="Classification", time="Time",
            concept_order=("Country", "Classification", "Series", "Time"), year_id="YR2021",
        )
        country = "AAA"
        inventories = {
            "Country": [Variable("Country", country, "Economy A")],
            "Classification": [
                Variable("Classification", "PPP", "Purchasing power parity (PPP) (US$ = 1)"),
                Variable("Classification", "NOM", "Expenditure (million LCU)"),
                Variable("Classification", "REAL", "Expenditure (million US$), based on PPPs"),
            ],
            "Series": [Variable("Series", code, code) for code in ["1100000", *HEADING_VALUES, *AUDIT_VALUES]],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        nominal = {**HEADING_VALUES, **AUDIT_VALUES, "1100000": HFCE}
        ppps = {heading: Decimal(index + 1) for index, heading in enumerate(nominal)}
        observations = []
        for heading, nominal_value in nominal.items():
            ppp = ppps[heading]
            observations.extend([
                observation(country, heading, "PPP", ppp),
                observation(country, heading, "NOM", nominal_value),
                observation(country, heading, "REAL", nominal_value / ppp),
            ])
        result = build_matrix(
            config, roles, observations, inventories,
            MeasureSelection("PPP", "NOM", "REAL", diagnostics=[]),
            {country: "Economy A"},
        )
        hierarchy = [row for row in result.hierarchy_rows if row["economy_code"] == country]
        self.assertEqual(len(hierarchy), 3)
        self.assertTrue(all(row["status"] == "PASS" for row in hierarchy))
        self.assertNotEqual(
            sum((row["real_expenditure_ppp"] for row in result.category_rows), Decimal("0")),
            nominal["1100000"] / ppps["1100000"],
        )
        self.assertFalse(any("HIERARCHY_RECONCILIATION_FAILED" in row["reason"] for row in result.missing_rows))

    def test_duplicate_economy_heading_measure_is_rejected(self):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        roles = DimensionRoles("Country", "Series", "Classification", "Time", ("Country", "Classification", "Series", "Time"), "YR2021")
        inventories = {
            "Country": [Variable("Country", "AAA", "A")],
            "Classification": [
                Variable("Classification", "PPP", "Purchasing power parity"),
                Variable("Classification", "NOM", "Expenditure (million LCU)"),
                Variable("Classification", "REAL", "Real expenditure based on PPPs"),
            ],
            "Series": [Variable("Series", "1101000", "Food")],
            "Time": [Variable("Time", "YR2021", "2021")],
        }
        duplicate = observation("AAA", "1101000", "REAL", Decimal("1"))
        with self.assertRaisesRegex(ValueError, "Duplicate economy-heading-measure"):
            build_matrix(
                config, roles, [duplicate, duplicate], inventories,
                MeasureSelection("PPP", "NOM", "REAL", diagnostics=[]), {"AAA": "A"}
            )


if __name__ == "__main__":
    unittest.main()
