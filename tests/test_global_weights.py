import csv
import hashlib
import json
from pathlib import Path

import pytest

from armilar_global_weights.builder import BuildError, build_release, load_cells
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
    cells = []
    for economy in ("AAA", "BBB"):
        for number in range(1, 13):
            evidence = EvidenceClass.A_OFFICIAL_EXACT if economy == "AAA" else EvidenceClass.C_OWN_ECONOMY_ESTIMATE
            cells.append(cell(economy, f"CP{number:02d}", evidence, value=number + (5 if economy == "BBB" else 0)))
    return cells


def test_complete_release_sums_to_one_and_separates_core(tmp_path: Path) -> None:
    summary = build_release(complete_cells(), tmp_path)
    assert summary["complete_grid"] is True
    assert summary["cell_count"] == 24
    assert summary["weight_sum"] == pytest.approx(1.0)
    assert summary["core_global_weight_share"] < 1.0
    assert summary["estimated_global_weight_share"] > 0.0

    with (tmp_path / "weights_global.csv").open(encoding="utf-8") as handle:
        global_rows = list(csv.DictReader(handle))
    assert sum(float(row["weight"]) for row in global_rows) == pytest.approx(1.0)

    with (tmp_path / "weights_core.csv").open(encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    assert {row["economy_code"] for row in core_rows} == {"AAA"}
    assert sum(float(row["observed_universe_weight"]) for row in core_rows) == pytest.approx(1.0)
    assert sum(float(row["global_weight"]) for row in core_rows) == pytest.approx(summary["core_global_weight_share"])


def test_incomplete_world_grid_fails_closed(tmp_path: Path) -> None:
    cells = complete_cells()[:-1]
    with pytest.raises(BuildError, match="incomplete"):
        build_release(cells, tmp_path)


def test_duplicate_cell_fails_closed(tmp_path: Path) -> None:
    cells = complete_cells()
    cells.append(cells[0])
    with pytest.raises(BuildError, match="duplicate"):
        build_release(cells, tmp_path)


def test_estimated_cell_requires_uncertainty() -> None:
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
    with pytest.raises(ValueError, match="non-zero uncertainty"):
        invalid.validate()


def test_donor_imputation_requires_donors() -> None:
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
    with pytest.raises(ValueError, match="donor_economies"):
        invalid.validate()


def test_uncertainty_contains_central_for_every_cell(tmp_path: Path) -> None:
    build_release(complete_cells(), tmp_path)
    with (tmp_path / "weights_uncertainty.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(float(row["weight_lower"]) <= float(row["weight_central"]) <= float(row["weight_upper"]) for row in rows)


def test_outputs_are_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_release(complete_cells(), first)
    build_release(reversed(complete_cells()), second)
    names = sorted(path.name for path in first.iterdir())
    assert names == sorted(path.name for path in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_release_remains_research_only(tmp_path: Path) -> None:
    build_release(complete_cells(), tmp_path)
    release = json.loads((tmp_path / "global_weight_release.json").read_text(encoding="utf-8"))
    assert release["monetary_release_allowed"] is False


def test_release_manifest_hash_matches_published_manifest(tmp_path: Path) -> None:
    build_release(complete_cells(), tmp_path)
    release = json.loads((tmp_path / "global_weight_release.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256((tmp_path / "MANIFEST.sha256").read_bytes()).hexdigest()
    assert release["manifest_sha256"] == actual
    assert "global_weight_release.json" not in (tmp_path / "MANIFEST.sha256").read_text(encoding="utf-8")
