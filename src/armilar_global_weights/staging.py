from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .builder import BuildError, _float_text
from .models import EvidenceClass, WeightCell

EVIDENCE_CELL_FIELDS = [
    "economy_code",
    "economy_name",
    "category_code",
    "real_expenditure_central",
    "real_expenditure_lower",
    "real_expenditure_upper",
    "evidence_class",
    "method_id",
    "model_version",
    "source_ids",
    "donor_economies",
    "source_state",
    "transformation_method",
    "core_eligible",
    "global_eligible",
    "validation_mae",
    "validation_bias",
    "notes",
]

COVERAGE_FIELDS = [
    "scope",
    "economy_code",
    "category_code",
    "evidence_class",
    "cell_count",
    "central_expenditure",
    "core_eligible_cells",
    "global_eligible_cells",
]


@dataclass(frozen=True, slots=True)
class EvidenceCell:
    weight_cell: WeightCell
    economy_name: str
    source_state: str
    transformation_method: str
    core_eligible: bool
    global_eligible: bool

    def validate(self) -> None:
        self.weight_cell.validate()
        if self.core_eligible and not self.weight_cell.evidence_class.is_core:
            raise BuildError("non-core evidence cannot be marked core_eligible")
        if not self.source_state:
            raise BuildError("source_state is required")
        if not self.transformation_method:
            raise BuildError("transformation_method is required")

    def as_row(self) -> dict[str, str]:
        self.validate()
        cell = self.weight_cell
        return {
            "economy_code": cell.economy_code,
            "economy_name": self.economy_name,
            "category_code": cell.category_code,
            "real_expenditure_central": _float_text(cell.real_expenditure_central),
            "real_expenditure_lower": _float_text(cell.real_expenditure_lower),
            "real_expenditure_upper": _float_text(cell.real_expenditure_upper),
            "evidence_class": cell.evidence_class.value,
            "method_id": cell.method_id,
            "model_version": cell.model_version,
            "source_ids": "|".join(cell.source_ids),
            "donor_economies": "|".join(cell.donor_economies),
            "source_state": self.source_state,
            "transformation_method": self.transformation_method,
            "core_eligible": str(self.core_eligible).lower(),
            "global_eligible": str(self.global_eligible).lower(),
            "validation_mae": "" if cell.validation_mae is None else _float_text(cell.validation_mae),
            "validation_bias": "" if cell.validation_bias is None else _float_text(cell.validation_bias),
            "notes": cell.notes,
        }


def strict_matrix_row_to_evidence_cell(
    row: dict[str, str], *, model_version: str = "strict-staging-v0.7.1"
) -> EvidenceCell:
    category = str(row.get("armilar_category") or row.get("category_code") or "").strip().upper()
    value = _required_positive_float(row, "real_expenditure_ppp")
    quality_flags = set(str(row.get("quality_flags") or "").split("|"))
    derivation = str(row.get("derivation") or "").strip()
    source_ids = tuple(
        sorted(
            {
                value
                for value in (
                    str(row.get("numerator_source_id") or "").strip(),
                    str(row.get("ppp_source_heading") or "").strip(),
                )
                if value
            }
        )
    )
    if not source_ids:
        raise BuildError("strict row is missing source identifiers")
    if "EXPERIMENTAL_ALLOCATION" in quality_flags:
        raise BuildError("experimental allocations cannot be staged as strict A/B evidence")
    if derivation == "DIRECT_SOURCE90_HFCE":
        evidence = EvidenceClass.A_OFFICIAL_EXACT
        method_id = "strict-source90-direct"
        transformation = derivation
    else:
        evidence = EvidenceClass.B_OFFICIAL_DETERMINISTIC
        method_id = "strict-official-deterministic"
        transformation = derivation or "OFFICIAL_DETERMINISTIC"
    cell = WeightCell(
        economy_code=str(row.get("economy_code") or "").strip().upper(),
        category_code=category,
        real_expenditure_central=value,
        real_expenditure_lower=value,
        real_expenditure_upper=value,
        evidence_class=evidence,
        method_id=method_id,
        model_version=model_version,
        source_ids=source_ids,
        notes="Converted from strict Step 2 matrix without changing value.",
    )
    staged = EvidenceCell(
        weight_cell=cell,
        economy_name=str(row.get("economy_name") or "").strip(),
        source_state="STRICT_MATRIX_ACCEPTED",
        transformation_method=transformation,
        core_eligible=True,
        global_eligible=True,
    )
    staged.validate()
    return staged


def load_strict_matrix(path: Path, *, model_version: str = "strict-staging-v0.7.1") -> list[EvidenceCell]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [strict_matrix_row_to_evidence_cell(row, model_version=model_version) for row in rows]


def write_evidence_cells(cells: Iterable[EvidenceCell], output_dir: Path) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        cell.as_row()
        for cell in sorted(cells, key=lambda item: (item.weight_cell.economy_code, item.weight_cell.category_code))
    ]
    with (output_dir / "evidence_cells.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_CELL_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    coverage_rows = evidence_coverage_rows(rows)
    with (output_dir / "evidence_class_coverage.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(coverage_rows)
    return rows


def evidence_coverage_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Decimal | int]] = defaultdict(
        lambda: {"cell_count": 0, "central_expenditure": Decimal("0"), "core": 0, "global": 0}
    )
    for row in rows:
        central = Decimal(str(row["real_expenditure_central"]))
        keys = [
            ("global", "*", "*", row["evidence_class"]),
            ("economy", row["economy_code"], "*", row["evidence_class"]),
            ("category", "*", row["category_code"], row["evidence_class"]),
        ]
        for key in keys:
            bucket = grouped[key]
            bucket["cell_count"] = int(bucket["cell_count"]) + 1
            bucket["central_expenditure"] = Decimal(bucket["central_expenditure"]) + central
            bucket["core"] = int(bucket["core"]) + (1 if row["core_eligible"] == "true" else 0)
            bucket["global"] = int(bucket["global"]) + (1 if row["global_eligible"] == "true" else 0)
    output: list[dict[str, str]] = []
    for (scope, economy, category, evidence), values in sorted(grouped.items()):
        output.append(
            {
                "scope": scope,
                "economy_code": economy,
                "category_code": category,
                "evidence_class": evidence,
                "cell_count": str(values["cell_count"]),
                "central_expenditure": format(Decimal(values["central_expenditure"]), "f"),
                "core_eligible_cells": str(values["core"]),
                "global_eligible_cells": str(values["global"]),
            }
        )
    return output


def _required_positive_float(row: dict[str, str], field: str) -> float:
    try:
        value = float(str(row[field]).strip())
    except (KeyError, ValueError) as exc:
        raise BuildError(f"strict row has invalid {field}") from exc
    if value <= 0:
        raise BuildError(f"strict row {field} must be positive")
    return value
