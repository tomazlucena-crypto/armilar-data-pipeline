from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from armilar_global_weights.models import CATEGORIES

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class PriceEvidenceClass(StrEnum):
    P1_OFFICIAL_CATEGORY = "P1_OFFICIAL_CATEGORY"
    P2_OFFICIAL_AGGREGATE = "P2_OFFICIAL_AGGREGATE"
    P3_OFFICIAL_HEADLINE = "P3_OFFICIAL_HEADLINE"
    P4_REGIONAL_PROXY = "P4_REGIONAL_PROXY"
    P5_GLOBAL_PROXY = "P5_GLOBAL_PROXY"

    @property
    def rank(self) -> int:
        return {
            PriceEvidenceClass.P1_OFFICIAL_CATEGORY: 1,
            PriceEvidenceClass.P2_OFFICIAL_AGGREGATE: 2,
            PriceEvidenceClass.P3_OFFICIAL_HEADLINE: 3,
            PriceEvidenceClass.P4_REGIONAL_PROXY: 4,
            PriceEvidenceClass.P5_GLOBAL_PROXY: 5,
        }[self]

    @property
    def is_direct_or_official_aggregate(self) -> bool:
        return self in {
            PriceEvidenceClass.P1_OFFICIAL_CATEGORY,
            PriceEvidenceClass.P2_OFFICIAL_AGGREGATE,
        }


@dataclass(frozen=True, slots=True)
class PriceSeriesDefinition:
    series_id: str
    provider: str
    dataset: str
    economy_code: str
    source_category_code: str
    target_categories: tuple[str, ...]
    evidence_class: PriceEvidenceClass
    source_priority: int
    access_method: str
    source_url: str
    frequency: str = "M"
    unit: str = "INDEX"
    seasonal_adjustment: str = "NSA"
    publication_lag_days: int = 0
    revision_policy: str = "REVISABLE"
    fallback_series: tuple[str, ...] = ()
    enabled: bool = True
    provider_code: str = ""
    query_key: str = ""

    def validate(self) -> None:
        if not self.series_id.strip():
            raise ValueError("series_id is required")
        if not self.provider.strip() or not self.dataset.strip():
            raise ValueError(f"provider and dataset are required for {self.series_id}")
        if (
            len(self.economy_code) != 3
            or not self.economy_code.isalnum()
            or self.economy_code != self.economy_code.upper()
        ):
            raise ValueError(f"invalid economy_code for {self.series_id}: {self.economy_code!r}")
        if not self.source_category_code.strip():
            raise ValueError(f"source_category_code is required for {self.series_id}")
        if not self.target_categories:
            raise ValueError(f"target_categories cannot be empty for {self.series_id}")
        if len(set(self.target_categories)) != len(self.target_categories):
            raise ValueError(f"duplicate target_categories for {self.series_id}")
        invalid = sorted(set(self.target_categories) - set(CATEGORIES))
        if invalid:
            raise ValueError(f"invalid target_categories for {self.series_id}: {invalid}")
        if self.frequency != "M":
            raise ValueError(f"only monthly frequency is allowed in v0.8.0: {self.series_id}")
        if self.unit != "INDEX":
            raise ValueError(f"only index-level series are allowed in v0.8.0: {self.series_id}")
        if self.seasonal_adjustment != "NSA":
            raise ValueError(f"only non-seasonally-adjusted series are allowed: {self.series_id}")
        if self.source_priority < 1:
            raise ValueError(f"source_priority must be positive for {self.series_id}")
        if self.publication_lag_days < 0:
            raise ValueError(f"publication_lag_days cannot be negative for {self.series_id}")
        if self.access_method not in {"SDMX", "REST_JSON", "CSV", "FIXTURE"}:
            raise ValueError(f"unsupported access_method for {self.series_id}: {self.access_method}")
        if not self.source_url.strip():
            raise ValueError(f"source_url is required for {self.series_id}")
        if self.evidence_class is PriceEvidenceClass.P1_OFFICIAL_CATEGORY and len(self.target_categories) != 1:
            raise ValueError(f"P1 series must target exactly one category: {self.series_id}")
        if self.evidence_class is PriceEvidenceClass.P3_OFFICIAL_HEADLINE and set(self.target_categories) != set(CATEGORIES):
            raise ValueError(f"P3 headline series must target all 12 categories: {self.series_id}")


@dataclass(frozen=True, slots=True)
class PriceObservation:
    series_id: str
    period: str
    value: float
    published_at: str = ""
    retrieved_at: str = ""
    revision_id: str = ""
    status: str = ""

    def validate(self) -> None:
        if not self.series_id.strip():
            raise ValueError("series_id is required")
        validate_month(self.period)
        if not math.isfinite(self.value) or self.value <= 0:
            raise ValueError(f"price index value must be finite and positive for {self.series_id}/{self.period}")


@dataclass(frozen=True, slots=True)
class NormalizedPriceObservation:
    series_id: str
    economy_code: str
    category_code: str
    period: str
    price_relative: float
    evidence_class: PriceEvidenceClass
    source_priority: int
    provider: str
    dataset: str
    source_category_code: str
    reference_period: str
    published_at: str = ""
    retrieved_at: str = ""
    revision_id: str = ""
    quality_flags: tuple[str, ...] = ()

    def validate(self) -> None:
        validate_month(self.period)
        validate_month(self.reference_period)
        if self.category_code not in CATEGORIES:
            raise ValueError(f"invalid category_code: {self.category_code}")
        if not math.isfinite(self.price_relative) or self.price_relative <= 0:
            raise ValueError("price_relative must be finite and positive")
        if self.source_priority < 1:
            raise ValueError("source_priority must be positive")


def validate_month(value: str) -> None:
    if not _MONTH_RE.fullmatch(value):
        raise ValueError(f"invalid monthly period: {value!r}")


def parse_list(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split("|") if part.strip())
    return tuple(str(part).strip() for part in value if str(part).strip())
