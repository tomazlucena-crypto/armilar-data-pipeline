import unittest
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.measures import select_measures, semantic_kind
from armilar_pipeline.worldbank import Observation, Variable


class MeasureTests(unittest.TestCase):
    def test_semantic_classification(self):
        self.assertEqual(semantic_kind("Purchasing power parity (PPP) (US$ = 1)"), "PPP")
        self.assertEqual(semantic_kind("Expenditure (million LCU)"), "NOMINAL_EXPENDITURE")
        self.assertEqual(semantic_kind("Expenditure (million US$), based on PPPs"), "REAL_EXPENDITURE")
        self.assertEqual(semantic_kind("Expenditure per capita, based on PPPs"), "OTHER")

    def test_numeric_identity_selects_measure_triple(self):
        measures = [
            Variable("Classification", "P", "Purchasing power parity (PPP) (US$ = 1)"),
            Variable("Classification", "N", "Expenditure (million LCU)"),
            Variable("Classification", "R", "Expenditure (million US$), based on PPPs"),
            Variable("Classification", "X", "Price level index (world = 100)"),
        ]
        observations = []
        for measure, value in [("P", "2"), ("N", "100"), ("R", "50")]:
            observations.append(Observation(
                variables={
                    "Country": ("AAA", "A"), "Series": ("1101000", "Food"),
                    "Classification": (measure, measure), "Time": ("YR2021", "2021"),
                },
                value=Decimal(value), source_file=Path("raw.json"), source_url="u",
                retrieved_at="t", source_hash="h",
            ))
        selected = select_measures(measures, observations, "Classification", "Country", "Series")
        self.assertEqual((selected.ppp_id, selected.nominal_id, selected.real_id), ("P", "N", "R"))


if __name__ == "__main__":
    unittest.main()
