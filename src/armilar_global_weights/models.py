from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))


class EvidenceClass(StrEnum):
    A_OFFICIAL_EXACT = "A_OFFICIAL_EXACT"
    B_OFFICIAL_DETERMINISTIC = "B_OFFICIAL_DETERMINISTIC"
    C_OWN_ECONOMY_ESTIMATE = "C_OWN_ECONOMY_ESTIMATE"
    D_DONOR_IMPUTATION = "D_DONOR_IMPUTATION"
    E_REGIONAL_GLOBAL_FALLBACK = "E_REGIONAL_GLOBAL_FALLBACK"

    @property
    def is_core(self) -> bool:
        return self in {
            EvidenceClass.A_OFFICIAL_EXACT,
            EvidenceClass.B_OFFICIAL_DETERMINISTIC,
        }

    @property
    def is_estimated(self) -> bool:
        return not self.is_core


@dataclass(frozen=True, slots=True)
class WeightCell:
    economy_code: str
    category_code: str
    real_expenditure_central: float
    real_expenditure_lower: float
    real_expenditure_upper: float
    evidence_class: EvidenceClass
    method_id: str
    model_version: str
    source_ids: tuple[str, ...]
    donor_economies: tuple[str, ...] = ()
    validation_mae: float | None = None
    validation_bias: float | None = None
    notes: str = ""

    def validate(self) -> None:
        if len(self.economy_code) != 3 or not self.economy_code.isalnum() or self.economy_code != self.economy_code.upper():
            raise ValueError(f"invalid economy_code: {self.economy_code!r}")
        if self.category_code not in CATEGORIES:
            raise ValueError(f"invalid category_code: {self.category_code!r}")
        if self.real_expenditure_lower <= 0:
            raise ValueError("real_expenditure_lower must be positive")
        if not self.real_expenditure_lower <= self.real_expenditure_central <= self.real_expenditure_upper:
            raise ValueError("expenditure bounds must contain the central value")
        if not self.method_id.strip() or not self.model_version.strip():
            raise ValueError("method_id and model_version are required")
        if not self.source_ids or any(not source.strip() for source in self.source_ids):
            raise ValueError("at least one non-empty source_id is required")
        if self.validation_mae is not None and self.validation_mae < 0:
            raise ValueError("validation_mae cannot be negative")
        if self.evidence_class.is_core:
            if not _approximately_equal(self.real_expenditure_lower, self.real_expenditure_central):
                raise ValueError("class A/B cells must not invent a lower uncertainty bound")
            if not _approximately_equal(self.real_expenditure_upper, self.real_expenditure_central):
                raise ValueError("class A/B cells must not invent an upper uncertainty bound")
        else:
            if self.real_expenditure_lower == self.real_expenditure_upper:
                raise ValueError("class C/D/E cells require a non-zero uncertainty interval")
        if self.evidence_class is EvidenceClass.D_DONOR_IMPUTATION and not self.donor_economies:
            raise ValueError("class D cells require donor_economies")
        if self.evidence_class is EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK and self.donor_economies:
            raise ValueError("class E fallback must not masquerade as donor imputation")


def _approximately_equal(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def parse_list(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(sorted({part.strip() for part in value.split("|") if part.strip()}))
    return tuple(sorted({str(part).strip() for part in value if str(part).strip()}))
