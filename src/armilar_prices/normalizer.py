from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .models import NormalizedPriceObservation, PriceObservation, PriceSeriesDefinition, validate_month


class PriceNormalizationError(ValueError):
    """Raised when raw price observations cannot be normalised safely."""


def load_observations(path: Path) -> list[PriceObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise PriceNormalizationError("observation input is empty")
    observations: list[PriceObservation] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            observation = PriceObservation(
                series_id=(row.get("series_id") or "").strip(),
                period=(row.get("period") or "").strip(),
                value=float(row["value"]),
                published_at=(row.get("published_at") or "").strip(),
                retrieved_at=(row.get("retrieved_at") or "").strip(),
                revision_id=(row.get("revision_id") or "").strip(),
                status=(row.get("status") or "").strip(),
            )
            observation.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceNormalizationError(f"invalid observation at CSV line {line_number}: {exc}") from exc
        observations.append(observation)
    return observations


def normalize_observations(
    definitions: Iterable[PriceSeriesDefinition],
    observations: Iterable[PriceObservation],
    reference_period: str,
) -> tuple[list[NormalizedPriceObservation], dict[str, object]]:
    validate_month(reference_period)
    registry = {row.series_id: row for row in definitions}
    raw = list(observations)
    duplicates = sorted(
        key for key, count in Counter((row.series_id, row.period) for row in raw).items() if count > 1
    )
    if duplicates:
        raise PriceNormalizationError(f"duplicate series-period observations: {duplicates[:10]}")
    unknown = sorted({row.series_id for row in raw if row.series_id not in registry})
    if unknown:
        raise PriceNormalizationError(f"observations reference unknown series: {unknown}")

    by_series: dict[str, list[PriceObservation]] = defaultdict(list)
    for row in raw:
        if registry[row.series_id].enabled:
            by_series[row.series_id].append(row)

    normalised: list[NormalizedPriceObservation] = []
    missing_reference: list[str] = []
    for series_id in sorted(by_series):
        definition = registry[series_id]
        series_rows = sorted(by_series[series_id], key=lambda row: row.period)
        reference = next((row for row in series_rows if row.period == reference_period), None)
        if reference is None:
            missing_reference.append(series_id)
            continue
        for row in series_rows:
            relative = 100.0 * row.value / reference.value
            for category in definition.target_categories:
                item = NormalizedPriceObservation(
                    series_id=series_id,
                    economy_code=definition.economy_code,
                    category_code=category,
                    period=row.period,
                    price_relative=relative,
                    evidence_class=definition.evidence_class,
                    source_priority=definition.source_priority,
                    provider=definition.provider,
                    dataset=definition.dataset,
                    source_category_code=definition.source_category_code,
                    reference_period=reference_period,
                    published_at=row.published_at,
                    retrieved_at=row.retrieved_at,
                    revision_id=row.revision_id,
                    quality_flags=tuple(filter(None, (row.status,))),
                )
                item.validate()
                normalised.append(item)

    normalised.sort(key=lambda row: (row.economy_code, row.category_code, row.period, row.evidence_class.rank, row.source_priority, row.series_id))
    summary = {
        "reference_period": reference_period,
        "input_observation_count": len(raw),
        "normalised_observation_count": len(normalised),
        "normalised_series_count": len(by_series) - len(missing_reference),
        "series_missing_reference_period": missing_reference,
        "skipped_disabled_observation_count": sum(not registry[row.series_id].enabled for row in raw),
        "monetary_release_allowed": False,
    }
    return normalised, summary


def write_normalized_outputs(
    rows: Iterable[NormalizedPriceObservation], summary: dict[str, object], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    items = list(rows)
    fieldnames = [
        "series_id",
        "economy_code",
        "category_code",
        "period",
        "price_relative",
        "evidence_class",
        "source_priority",
        "provider",
        "dataset",
        "source_category_code",
        "reference_period",
        "published_at",
        "retrieved_at",
        "revision_id",
        "quality_flags",
    ]
    with (output_dir / "normalized_prices.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in items:
            writer.writerow({
                "series_id": row.series_id,
                "economy_code": row.economy_code,
                "category_code": row.category_code,
                "period": row.period,
                "price_relative": format(row.price_relative, ".17g"),
                "evidence_class": row.evidence_class.value,
                "source_priority": row.source_priority,
                "provider": row.provider,
                "dataset": row.dataset,
                "source_category_code": row.source_category_code,
                "reference_period": row.reference_period,
                "published_at": row.published_at,
                "retrieved_at": row.retrieved_at,
                "revision_id": row.revision_id,
                "quality_flags": "|".join(row.quality_flags),
            })
    (output_dir / "price_normalization_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
