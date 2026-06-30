from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.builder import BuildError, build_release
from armilar_global_weights.models import EvidenceClass, WeightCell


def cell(economy: str, category: str, evidence: EvidenceClass, value: float = 10.0) -> WeightCell:
    estimated = not evidence.is_core
    return WeightCell(
        economy_code=economy,
        category_code=category,
        real_expenditure_central=value,
        real_expenditure_lower=value * (0.9 if estimated else 1.0),
        real_expenditure_upper=value * (1.1 if estimated else 1.0),
        evidence_class=evidence,
        method_id="official" if not estimated else "test-imputation",
        model_version="1.0.0",
        source_ids=("SRC-1",),
        donor_economies=("AAA",) if evidence is EvidenceClass.D_DONOR_IMPUTATION else (),
    )


def complete_cells() -> list[WeightCell]:
    cells: list[WeightCell] = []
    for economy in ("AAA", "BBB"):
        for number in range(1, 13):
            evidence = (
                EvidenceClass.A_OFFICIAL_EXACT
                if economy == "AAA"
                else EvidenceClass.C_OWN_ECONOMY_ESTIMATE
            )
            cells.append(cell(economy, f"CP{number:02d}", evidence, value=number + (5 if economy == "BBB" else 0)))
    return cells


class GlobalWeightsTests(unittest.TestCase):
    def test_complete_release_sums_to_one_and_separates_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            summary = build_release(complete_cells(), output)
            self.assertTrue(summary["complete_grid"])
            self.assertEqual(summary["cell_count"], 24)
            self.assertAlmostEqual(summary["weight_sum"], 1.0, places=12)
            self.assertLess(summary["core_global_weight_share"], 1.0)
            self.assertGreater(summary["estimated_global_weight_share"], 0.0)

            with (output / "weights_global.csv").open(encoding="utf-8") as handle:
                global_rows = list(csv.DictReader(handle))
            self.assertAlmostEqual(sum(float(row["weight"]) for row in global_rows), 1.0, places=12)

            with (output / "weights_core.csv").open(encoding="utf-8") as handle:
                core_rows = list(csv.DictReader(handle))
            self.assertEqual({row["economy_code"] for row in core_rows}, {"AAA"})
            self.assertAlmostEqual(
                sum(float(row["observed_universe_weight"]) for row in core_rows), 1.0, places=12
            )
            self.assertAlmostEqual(
                sum(float(row["global_weight"]) for row in core_rows),
                summary["core_global_weight_share"],
                places=12,
            )

    def test_incomplete_world_grid_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BuildError, "incomplete"):
                build_release(complete_cells()[:-1], Path(tmp))

    def test_duplicate_cell_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cells = complete_cells()
            cells.append(cells[0])
            with self.assertRaisesRegex(BuildError, "duplicate"):
                build_release(cells, Path(tmp))

    def test_estimated_cell_requires_uncertainty(self) -> None:
        invalid = WeightCell(
            economy_code="AAA",
            category_code="CP01",
            real_expenditure_central=10,
            real_expenditure_lower=10,
            real_expenditure_upper=10,
            evidence_class=EvidenceClass.C_OWN_ECONOMY_ESTIMATE,
            method_id="estimate",
            model_version="1",
            source_ids=("SRC",),
        )
        with self.assertRaisesRegex(ValueError, "non-zero uncertainty"):
            invalid.validate()

    def test_donor_imputation_requires_donors(self) -> None:
        invalid = WeightCell(
            economy_code="AAA",
            category_code="CP01",
            real_expenditure_central=10,
            real_expenditure_lower=9,
            real_expenditure_upper=11,
            evidence_class=EvidenceClass.D_DONOR_IMPUTATION,
            method_id="donor",
            model_version="1",
            source_ids=("SRC",),
        )
        with self.assertRaisesRegex(ValueError, "donor_economies"):
            invalid.validate()

    def test_uncertainty_contains_central_for_every_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            build_release(complete_cells(), output)
            with (output / "weights_uncertainty.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(
                all(
                    float(row["weight_lower"])
                    <= float(row["weight_central"])
                    <= float(row["weight_upper"])
                    for row in rows
                )
            )

    def test_outputs_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            build_release(complete_cells(), first)
            build_release(reversed(complete_cells()), second)
            names = sorted(path.name for path in first.iterdir())
            self.assertEqual(names, sorted(path.name for path in second.iterdir()))
            for name in names:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_release_remains_research_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            build_release(complete_cells(), output)
            release = json.loads((output / "global_weight_release.json").read_text(encoding="utf-8"))
            self.assertFalse(release["monetary_release_allowed"])

    def test_release_manifest_hash_matches_published_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            build_release(complete_cells(), output)
            release = json.loads((output / "global_weight_release.json").read_text(encoding="utf-8"))
            actual = hashlib.sha256((output / "MANIFEST.sha256").read_bytes()).hexdigest()
            self.assertEqual(release["manifest_sha256"], actual)
            self.assertNotIn(
                "global_weight_release.json",
                (output / "MANIFEST.sha256").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
