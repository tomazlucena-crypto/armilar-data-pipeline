from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.imputation import (
    AggregateConstraint,
    EconomyProfile,
    ImputationError,
    ImputationPolicy,
    complete_research_grid,
    select_donors,
    validate_baselines,
    validation_metrics_by_class_category,
    write_imputation_outputs,
)
from armilar_global_weights.models import CATEGORIES, EvidenceClass, WeightCell


def profile(code: str, region: str, income: str, total: float, x: float) -> EconomyProfile:
    return EconomyProfile(code, region, income, total, (("x", x),))


def core_cell(economy: str, category: str, value: float, evidence: EvidenceClass = EvidenceClass.A_OFFICIAL_EXACT) -> WeightCell:
    return WeightCell(
        economy_code=economy,
        category_code=category,
        real_expenditure_central=value,
        real_expenditure_lower=value,
        real_expenditure_upper=value,
        evidence_class=evidence,
        method_id="strict",
        model_version="0.7.1",
        source_ids=("STRICT",),
    )


def complete_core(economy: str, multiplier: float = 1.0) -> list[WeightCell]:
    return [core_cell(economy, category, multiplier * index) for index, category in enumerate(CATEGORIES, start=1)]


def policy(minimum_donors: int = 2, donor_count: int = 3) -> ImputationPolicy:
    return ImputationPolicy(
        donor_count=donor_count,
        minimum_donors=minimum_donors,
        allocation_groups=(("PAIR", ("CP01", "CP02")),),
    )


class ImputationBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profiles = {
            "AAA": profile("AAA", "R1", "H", 78.0, 0.0),
            "BBB": profile("BBB", "R1", "H", 156.0, 0.2),
            "CCC": profile("CCC", "R2", "M", 234.0, 2.0),
            "TGT": profile("TGT", "R1", "H", 100.0, 0.1),
        }
        self.evidence = complete_core("AAA", 1.0) + complete_core("BBB", 2.0) + complete_core("CCC", 3.0)

    def test_donor_selection_is_deterministic_and_profile_only(self) -> None:
        vectors = {
            code: {category: float(index) for index, category in enumerate(CATEGORIES, start=1)}
            for code in ("AAA", "BBB", "CCC")
        }
        first = select_donors("TGT", self.profiles, vectors, policy(), None)
        reversed_outcomes = {
            code: {category: 10_000.0 - value for category, value in vector.items()}
            for code, vector in vectors.items()
        }
        second = select_donors("TGT", self.profiles, reversed_outcomes, policy(), None)
        self.assertEqual(first, second)
        self.assertEqual(first[:2], ["AAA", "BBB"])

    def test_d_imputation_completes_target_and_preserves_core(self) -> None:
        completed, summary = complete_research_grid(self.evidence, self.profiles, [], policy())
        target = [cell for cell in completed if cell.economy_code == "TGT"]
        self.assertEqual(len(target), 12)
        self.assertTrue(all(cell.evidence_class is EvidenceClass.D_DONOR_IMPUTATION for cell in target))
        self.assertAlmostEqual(sum(cell.real_expenditure_central for cell in target), 100.0)
        self.assertEqual(summary["generated_by_evidence_class"]["D_DONOR_IMPUTATION"], 12)
        original = next(cell for cell in self.evidence if cell.economy_code == "AAA" and cell.category_code == "CP01")
        preserved = next(cell for cell in completed if cell.economy_code == "AAA" and cell.category_code == "CP01")
        self.assertEqual(original, preserved)

    def test_c_allocation_uses_own_aggregate_and_fills_residual(self) -> None:
        partial = self.evidence + [core_cell("TGT", "CP01", 30.0)]
        constraint = AggregateConstraint(
            economy_code="TGT",
            aggregate_id="FOOD_COMBINED",
            category_codes=("CP01", "CP02"),
            aggregate_real_expenditure=50.0,
            source_ids=("OWN-OFFICIAL",),
        )
        completed, _ = complete_research_grid(partial, self.profiles, [constraint], policy())
        cp02 = next(cell for cell in completed if cell.economy_code == "TGT" and cell.category_code == "CP02")
        self.assertEqual(cp02.evidence_class, EvidenceClass.C_OWN_ECONOMY_ESTIMATE)
        self.assertAlmostEqual(cp02.real_expenditure_central, 20.0)
        self.assertIn("OWN-OFFICIAL", cp02.source_ids)

    def test_e_fallback_has_no_named_donors(self) -> None:
        limited_profiles = {"AAA": self.profiles["AAA"], "TGT": self.profiles["TGT"]}
        evidence = complete_core("AAA")
        completed, summary = complete_research_grid(evidence, limited_profiles, [], policy(minimum_donors=2, donor_count=2))
        target = [cell for cell in completed if cell.economy_code == "TGT"]
        self.assertTrue(all(cell.evidence_class is EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK for cell in target))
        self.assertTrue(all(not cell.donor_economies for cell in target))
        self.assertEqual(summary["generated_by_evidence_class"]["E_REGIONAL_GLOBAL_FALLBACK"], 12)

    def test_non_positive_residual_fails_closed(self) -> None:
        bad_profiles = dict(self.profiles)
        bad_profiles["TGT"] = profile("TGT", "R1", "H", 5.0, 0.1)
        partial = self.evidence + [core_cell("TGT", "CP01", 10.0)]
        with self.assertRaisesRegex(ImputationError, "non-positive residual"):
            complete_research_grid(partial, bad_profiles, [], policy())

    def test_leave_one_out_excludes_target_and_reports_metrics(self) -> None:
        predictions, summary = validate_baselines(self.evidence, {k: v for k, v in self.profiles.items() if k != "TGT"}, policy())
        self.assertGreater(len(predictions), 0)
        self.assertTrue(all(item.economy_code not in item.donor_economies for item in predictions))
        self.assertIn("mae", summary)
        self.assertIn("interval_coverage", summary)
        self.assertFalse(summary["monetary_release_allowed"])


    def test_validation_metrics_are_attached_to_generated_cells(self) -> None:
        validation_profiles = {k: v for k, v in self.profiles.items() if k != "TGT"}
        predictions, _ = validate_baselines(self.evidence, validation_profiles, policy())
        metrics = validation_metrics_by_class_category(predictions)
        completed, summary = complete_research_grid(
            self.evidence, self.profiles, [], policy(), validation_metrics=metrics
        )
        target = [cell for cell in completed if cell.economy_code == "TGT"]
        self.assertTrue(all(cell.validation_mae is not None for cell in target))
        self.assertEqual(summary["generated_validation_metric_coverage"], 1.0)

    def test_outputs_are_research_only(self) -> None:
        completed, summary = complete_research_grid(self.evidence, self.profiles, [], policy())
        predictions, validation = validate_baselines(
            self.evidence,
            {k: v for k, v in self.profiles.items() if k != "TGT"},
            policy(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_imputation_outputs(completed, summary, output, predictions, validation)
            self.assertTrue((output / "imputed_cells_research.csv").exists())
            self.assertTrue((output / "completed_evidence_grid_research.csv").exists())
            self.assertFalse((output / "weights_global.csv").exists())
            self.assertFalse((output / "weights_final.csv").exists())
            with (output / "imputed_cells_research.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            self.assertTrue(all(row["evidence_class"] in {
                "C_OWN_ECONOMY_ESTIMATE", "D_DONOR_IMPUTATION", "E_REGIONAL_GLOBAL_FALLBACK"
            } for row in rows))


if __name__ == "__main__":
    unittest.main()
