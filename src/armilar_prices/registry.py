from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from .models import PriceEvidenceClass, PriceSeriesDefinition, parse_list


class RegistryError(ValueError):
    """Raised when the price-series registry violates its contract."""


def load_registry(path: Path) -> list[PriceSeriesDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if bool(payload.get("monetary_release_allowed", False)):
        raise RegistryError("the Armilar price registry cannot authorise monetary release")
    rows = payload.get("series")
    if not isinstance(rows, list) or not rows:
        raise RegistryError("registry must contain a non-empty series list")
    definitions: list[PriceSeriesDefinition] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise RegistryError(f"registry series #{index} is not an object")
        try:
            definition = PriceSeriesDefinition(
                series_id=str(row["series_id"]).strip(),
                provider=str(row["provider"]).strip(),
                dataset=str(row["dataset"]).strip(),
                economy_code=str(row["economy_code"]).strip().upper(),
                source_category_code=str(row["source_category_code"]).strip(),
                target_categories=parse_list(row.get("target_categories")),
                evidence_class=PriceEvidenceClass(str(row["evidence_class"]).strip()),
                source_priority=int(row["source_priority"]),
                access_method=str(row["access_method"]).strip().upper(),
                source_url=str(row["source_url"]).strip(),
                frequency=str(row.get("frequency", "M")).strip().upper(),
                unit=str(row.get("unit", "INDEX")).strip().upper(),
                seasonal_adjustment=str(row.get("seasonal_adjustment", "NSA")).strip().upper(),
                publication_lag_days=int(row.get("publication_lag_days", 0)),
                revision_policy=str(row.get("revision_policy", "REVISABLE")).strip().upper(),
                fallback_series=parse_list(row.get("fallback_series")),
                enabled=bool(row.get("enabled", True)),
                provider_code=str(row.get("provider_code", "")).strip(),
                query_key=str(row.get("query_key", "")).strip(),
            )
            definition.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryError(f"invalid registry series #{index}: {exc}") from exc
        definitions.append(definition)
    validate_registry(definitions)
    return definitions


def validate_registry(definitions: Iterable[PriceSeriesDefinition]) -> None:
    rows = list(definitions)
    ids = [row.series_id for row in rows]
    duplicates = sorted(series_id for series_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise RegistryError(f"duplicate series_id values: {duplicates}")
    by_id = {row.series_id: row for row in rows}
    for row in rows:
        row.validate()
        for fallback in row.fallback_series:
            if fallback not in by_id:
                raise RegistryError(f"unknown fallback {fallback!r} for {row.series_id}")
            target = by_id[fallback]
            if target.economy_code != row.economy_code:
                raise RegistryError(f"cross-economy fallback is forbidden: {row.series_id} -> {fallback}")
            if not set(row.target_categories).intersection(target.target_categories):
                raise RegistryError(f"fallback has no overlapping target category: {row.series_id} -> {fallback}")
    _validate_fallback_cycles(by_id)


def _validate_fallback_cycles(by_id: dict[str, PriceSeriesDefinition]) -> None:
    visited: set[str] = set()
    active: set[str] = set()

    def visit(series_id: str) -> None:
        if series_id in active:
            raise RegistryError(f"fallback cycle detected at {series_id}")
        if series_id in visited:
            return
        active.add(series_id)
        for fallback in by_id[series_id].fallback_series:
            visit(fallback)
        active.remove(series_id)
        visited.add(series_id)

    for series_id in sorted(by_id):
        visit(series_id)


def candidate_series(
    definitions: Iterable[PriceSeriesDefinition], economy_code: str, category_code: str
) -> list[PriceSeriesDefinition]:
    return sorted(
        (
            row
            for row in definitions
            if row.enabled
            and row.economy_code == economy_code
            and category_code in row.target_categories
        ),
        key=lambda row: (row.evidence_class.rank, row.source_priority, row.series_id),
    )


def registry_summary(definitions: Iterable[PriceSeriesDefinition]) -> dict[str, object]:
    rows = list(definitions)
    enabled = [row for row in rows if row.enabled]
    return {
        "series_count": len(rows),
        "enabled_series_count": len(enabled),
        "economy_count": len({row.economy_code for row in enabled}),
        "provider_count": len({row.provider for row in enabled}),
        "evidence_class_counts": dict(sorted(Counter(row.evidence_class.value for row in enabled).items())),
        "monetary_release_allowed": False,
    }
