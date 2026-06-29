from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.builder import BuildError
from armilar_global_weights.models import EvidenceClass
from armilar_global_weights.staging import strict_matrix_row_to_evidence_cell, write_evidence_cells


class EvidenceStagingTests(unittest.TestCase):
    def test_direct_source_row_becomes_class_a_without_value_change(self) -> None:
        staged = strict_matrix_row_to_evidence_cell({
            "economy_code": "AAA",
            "economy_name": "Economy A",
            "armilar_category": "CP01",
            "real_expenditure_ppp": "123.5",
            "quality_flags": "",
            "derivation": "DIRECT_SOURCE90_HFCE",
            "numerator_source_id": "SOURCE90",
            "ppp_source_heading": "1101000",
        })
        self.assertEqual(staged.weight_cell.evidence_class, EvidenceClass.A_OFFICIAL_EXACT)
        self.assertEqual(staged.weight_cell.real_expenditure_central, 123.5)
        self.assertTrue(staged.core_eligible)

    def test_deterministic_derivation_becomes_class_b(self) -> None:
        staged = strict_matrix_row_to_evidence_cell({
            "economy_code": "AAA",
            "economy_name": "Economy A",
            "armilar_category": "CP04",
            "real_expenditure_ppp": "50",
            "quality_flags": "",
            "derivation": "OFFICIAL_NUMERATOR_DIVIDED_BY_RATIFIED_PROXY",
            "numerator_source_id": "OFFICIAL-HFCE",
            "ppp_source_heading": "9060000",
        })
        self.assertEqual(staged.weight_cell.evidence_class, EvidenceClass.B_OFFICIAL_DETERMINISTIC)
        self.assertTrue(staged.core_eligible)

    def test_experimental_allocation_is_rejected(self) -> None:
        with self.assertRaisesRegex(BuildError, "experimental allocations"):
            strict_matrix_row_to_evidence_cell({
                "economy_code": "AAA",
                "armilar_category": "CP01",
                "real_expenditure_ppp": "10",
                "quality_flags": "EXPERIMENTAL_ALLOCATION",
                "derivation": "DIRECT_SOURCE90_HFCE",
                "numerator_source_id": "SRC",
                "ppp_source_heading": "1101000",
            })

    def test_outputs_include_evidence_and_coverage_files(self) -> None:
        rows = [
            strict_matrix_row_to_evidence_cell({
                "economy_code": "AAA",
                "economy_name": "Economy A",
                "armilar_category": "CP01",
                "real_expenditure_ppp": "10",
                "quality_flags": "",
                "derivation": "DIRECT_SOURCE90_HFCE",
                "numerator_source_id": "SRC",
                "ppp_source_heading": "1101000",
            })
        ]
        with tempfile.TemporaryDirectory() as tmp:
            write_evidence_cells(rows, Path(tmp))
            self.assertTrue((Path(tmp) / "evidence_cells.csv").exists())
            self.assertTrue((Path(tmp) / "evidence_class_coverage.csv").exists())


if __name__ == "__main__":
    unittest.main()
