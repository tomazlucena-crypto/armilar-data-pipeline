from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.models import CATEGORIES, EvidenceClass, WeightCell
from armilar_global_weights.release_gate import (
    GlobalReleaseGatePolicy,
    ReleaseGateError,
    evaluate_and_optionally_build,
    evaluate_global_release,
)


def cell(economy: str, category: str, evidence: EvidenceClass, value: float = 10.0) -> WeightCell:
    estimated = evidence.is_estimated
    return WeightCell(
        economy_code=economy,
        category_code=category,
        real_expenditure_central=value,
        real_expenditure_lower=value * (0.9 if estimated else 1.0),
        real_expenditure_upper=value * (1.1 if estimated else 1.0),
        evidence_class=evidence,
        method_id="estimate" if estimated else "strict",
        model_version="0.7.3",
        source_ids=("SRC",),
        donor_economies=("AAA", "BBB", "CCC")
        if evidence is EvidenceClass.D_DONOR_IMPUTATION
        else (),
        validation_mae=0.5 if estimated else None,
        validation_bias=0.1 if estimated else None,
    )


def complete_grid(estimated_economies: int = 1, fallback: bool = False) -> list[WeightCell]:
    rows: list[WeightCell] = []
    for index, economy in enumerate(("AAA", "BBB", "CCC", "DDD")):
        estimated = index >= 4 - estimated_economies
        evidence = (
            EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK
            if estimated and fallback
            else EvidenceClass.D_DONOR_IMPUTATION
            if estimated
            else EvidenceClass.A_OFFICIAL_EXACT
        )
        rows.extend(cell(economy, category, evidence) for category in CATEGORIES)
    return rows


def policy(**overrides: object) -> GlobalReleaseGatePolicy:
    values = {
        "policy_version": "test",
        "minimum_validated_economies": 3,
        "minimum_prediction_count": 24,
        "maximum_mape": 0.20,
        "minimum_interval_coverage": 0.80,
        "maximum_estimated_expenditure_share": 0.30,
        "maximum_fallback_e_expenditure_share": 0.05,
        "require_validation_metrics_for_all_estimated_cells": True,
        "require_complete_grid": True,
        "research_release_allowed_when_all_gates_pass": True,
        "monetary_release_allowed": False,
    }
    values.update(overrides)
    return GlobalReleaseGatePolicy(**values)


def validation(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "validated_economy_count": 4,
        "prediction_count": 48,
        "mape": 0.10,
        "interval_coverage": 0.90,
        "leave_one_out": True,
        "result_driven_donor_selection": False,
        "monetary_release_allowed": False,
    }
    values.update(overrides)
    return values


class GlobalReleaseGateTests(unittest.TestCase):
    def test_eligible_research_release_passes_without_monetary_authorisation(self) -> None:
        decision = evaluate_global_release(complete_grid(), validation(), policy())
        self.assertTrue(decision["all_gates_passed"])
        self.assertTrue(decision["global_research_release_allowed"])
        self.assertFalse(decision["monetary_release_allowed"])

    def test_high_estimated_share_fails_closed(self) -> None:
        decision = evaluate_global_release(complete_grid(estimated_economies=2), validation(), policy())
        self.assertFalse(decision["global_research_release_allowed"])
        failed = {row["gate"] for row in decision["checks"] if not row["passed"]}
        self.assertIn("estimated_expenditure_share", failed)

    def test_e_fallback_share_has_independent_gate(self) -> None:
        decision = evaluate_global_release(complete_grid(fallback=True), validation(), policy())
        self.assertFalse(decision["global_research_release_allowed"])
        failed = {row["gate"] for row in decision["checks"] if not row["passed"]}
        self.assertIn("fallback_e_expenditure_share", failed)

    def test_missing_validation_metrics_fails_closed(self) -> None:
        rows = complete_grid()
        estimated = next(row for row in rows if row.evidence_class.is_estimated)
        rows[rows.index(estimated)] = WeightCell(
            economy_code=estimated.economy_code,
            category_code=estimated.category_code,
            real_expenditure_central=estimated.real_expenditure_central,
            real_expenditure_lower=estimated.real_expenditure_lower,
            real_expenditure_upper=estimated.real_expenditure_upper,
            evidence_class=estimated.evidence_class,
            method_id=estimated.method_id,
            model_version=estimated.model_version,
            source_ids=estimated.source_ids,
            donor_economies=estimated.donor_economies,
        )
        decision = evaluate_global_release(rows, validation(), policy())
        self.assertFalse(decision["global_research_release_allowed"])

    def test_result_driven_donor_selection_fails_closed(self) -> None:
        decision = evaluate_global_release(
            complete_grid(), validation(result_driven_donor_selection=True), policy()
        )
        self.assertFalse(decision["global_research_release_allowed"])

    def test_policy_cannot_authorise_monetary_release(self) -> None:
        with self.assertRaisesRegex(ReleaseGateError, "cannot authorise monetary"):
            policy(monetary_release_allowed=True).validate()

    def test_build_occurs_only_after_all_gates_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence.csv"
            summary = root / "validation.json"
            policy_path = root / "policy.json"
            from armilar_global_weights.imputation import write_imputation_outputs

            rows = complete_grid()
            write_imputation_outputs(rows, {"monetary_release_allowed": False}, root / "imputation")
            evidence.write_bytes((root / "imputation" / "completed_evidence_grid_research.csv").read_bytes())
            summary.write_text(json.dumps(validation()), encoding="utf-8")
            policy_path.write_text(json.dumps({
                "policy_version": "test",
                "minimum_validated_economies": 3,
                "minimum_prediction_count": 24,
                "maximum_mape": 0.20,
                "minimum_interval_coverage": 0.80,
                "maximum_estimated_expenditure_share": 0.30,
                "maximum_fallback_e_expenditure_share": 0.05,
                "require_validation_metrics_for_all_estimated_cells": True,
                "require_complete_grid": True,
                "research_release_allowed_when_all_gates_pass": True,
                "monetary_release_allowed": False
            }), encoding="utf-8")
            output = root / "out"
            decision = evaluate_and_optionally_build(
                evidence, summary, policy_path, output, build_when_eligible=True
            )
            self.assertTrue(decision["global_weights_built"])
            self.assertTrue((output / "global_research_release" / "weights_global.csv").exists())
            self.assertFalse((output / "global_research_release" / "weights_final.csv").exists())


if __name__ == "__main__":
    unittest.main()
