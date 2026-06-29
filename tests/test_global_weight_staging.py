from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.builder import BuildError, load_cells
from armilar_global_weights.cli import main as global_weights_main
from armilar_global_weights.models import EvidenceClass, WeightCell
from armilar_global_weights.staging import (
    EvidenceCell,
    evidence_coverage_rows,
    strict_matrix_row_to_evidence_cell,
    write_evidence_cells,
)


def strict_row(category: str, value: str, *, source90: bool = True, flags: str = "") -> dict[str, str]:
    quality = flags or (
        "OBSERVED_PARTICIPANT|STRICT_HFCE|OFFICIAL_WORLD_BANK_ICP_2021_SOURCE90"
        if source90 else
        "OBSERVED_PARTICIPANT|STRICT_HOUSEHOLD_NUMERATOR|PROXY_PPP_ACTUAL_CONSUMPTION_RATIFIED|NO_GOVERNMENT_OR_NPISH_IN_NUMERATOR"
    )
    return {
        "economy_code": "AAA",
        "economy_name": "Alpha",
        "armilar_category": category,
        "nominal_household_expenditure_lcu": value,
        "ppp_lcu_per_international_dollar": "1",
        "real_expenditure_ppp": value,
        "numerator_source_id": "SRC90" if source90 else "NATIONAL_ACCOUNTS",
        "numerator_source_file": "source.csv",
        "numerator_source_hash": "a" * 64,
        "ppp_source_heading": "ICP-PPP",
        "ppp_scope": "HFCE" if source90 else "AIC_PROXY",
        "derivation": "DIRECT_SOURCE90_HFCE" if source90 else "OPTION_B_DETERMINISTIC_PROXY",
        "quality_flags": quality,
    }


class GlobalWeightStagingTests(unittest.TestCase):
    def test_strict_rows_convert_to_a_or_b_without_changing_values(self) -> None:
        direct = strict_matrix_row_to_evidence_cell(strict_row("CP01", "12.5", source90=True))
        derived = strict_matrix_row_to_evidence_cell(strict_row("CP04", "7.25", source90=False))

        self.assertEqual(direct.weight_cell.evidence_class, EvidenceClass.A_OFFICIAL_EXACT)
        self.assertEqual(derived.weight_cell.evidence_class, EvidenceClass.B_OFFICIAL_DETERMINISTIC)
        self.assertEqual(direct.weight_cell.real_expenditure_central, 12.5)
        self.assertEqual(direct.weight_cell.real_expenditure_lower, 12.5)
        self.assertEqual(derived.weight_cell.real_expenditure_upper, 7.25)
        self.assertTrue(direct.core_eligible)
        self.assertTrue(derived.core_eligible)

    def test_experimental_allocation_is_not_promoted_to_strict_evidence(self) -> None:
        row = strict_row("CP01", "10", flags="EXPERIMENTAL_ALLOCATION")
        with self.assertRaisesRegex(BuildError, "experimental allocations"):
            strict_matrix_row_to_evidence_cell(row)

    def test_staged_evidence_cells_are_builder_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            staged = [
                strict_matrix_row_to_evidence_cell(strict_row("CP01", "10", source90=True)),
                strict_matrix_row_to_evidence_cell(strict_row("CP02", "20", source90=False)),
            ]
            rows = write_evidence_cells(staged, output)
            self.assertEqual(len(rows), 2)
            loaded = load_cells(output / "evidence_cells.csv")
            self.assertEqual([cell.real_expenditure_central for cell in loaded], [10.0, 20.0])
            with (output / "evidence_class_coverage.csv").open(encoding="utf-8", newline="") as handle:
                coverage = list(csv.DictReader(handle))
            self.assertTrue(any(row["scope"] == "global" and row["evidence_class"] == "A_OFFICIAL_EXACT" for row in coverage))
            self.assertTrue(any(row["scope"] == "global" and row["evidence_class"] == "B_OFFICIAL_DETERMINISTIC" for row in coverage))

    def test_c_evidence_is_global_only_not_core(self) -> None:
        estimated = EvidenceCell(
            weight_cell=WeightCell(
                economy_code="BBB",
                category_code="CP01",
                real_expenditure_central=8,
                real_expenditure_lower=7,
                real_expenditure_upper=9,
                evidence_class=EvidenceClass.C_OWN_ECONOMY_ESTIMATE,
                method_id="own-economy-allocation",
                model_version="test",
                source_ids=("PARTIAL",),
            ),
            economy_name="Beta",
            source_state="PARTIAL_EVIDENCE",
            transformation_method="STATISTICAL_ALLOCATION",
            core_eligible=False,
            global_eligible=True,
        )
        rows = [estimated.as_row()]
        coverage = evidence_coverage_rows(rows)
        global_row = next(row for row in coverage if row["scope"] == "global")
        self.assertEqual(global_row["core_eligible_cells"], "0")
        self.assertEqual(global_row["global_eligible_cells"], "1")
        with self.assertRaisesRegex(BuildError, "non-core evidence"):
            EvidenceCell(
                weight_cell=estimated.weight_cell,
                economy_name="Beta",
                source_state="PARTIAL_EVIDENCE",
                transformation_method="STATISTICAL_ALLOCATION",
                core_eligible=True,
                global_eligible=True,
            ).validate()

    def test_stage_strict_cli_writes_evidence_and_coverage(self) -> None:
        fields = list(strict_row("CP01", "1").keys())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix = root / "matrix.csv"
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerow(strict_row("CP01", "1"))
            output = root / "stage"
            self.assertEqual(global_weights_main(["stage-strict", "--matrix", str(matrix), "--output", str(output)]), 0)
            self.assertTrue((output / "evidence_cells.csv").exists())
            self.assertTrue((output / "evidence_class_coverage.csv").exists())


if __name__ == "__main__":
    unittest.main()
