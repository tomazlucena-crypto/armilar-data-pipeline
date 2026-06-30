from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .models import NormalizedPriceObservation, PriceEvidenceClass, parse_list


class PriceSelectionError(ValueError):
    """Raised when normalised prices cannot be selected deterministically."""


def load_normalized_prices(path: Path) -> list[NormalizedPriceObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise PriceSelectionError("normalised price input is empty")
    items: list[NormalizedPriceObservation] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            item = NormalizedPriceObservation(
                series_id=row["series_id"].strip(),
                economy_code=row["economy_code"].strip().upper(),
                category_code=row["category_code"].strip().upper(),
                period=row["period"].strip(),
                price_relative=float(row["price_relative"]),
                evidence_class=PriceEvidenceClass(row["evidence_class"].strip()),
                source_priority=int(row["source_priority"]),
                provider=row["provider"].strip(),
                dataset=row["dataset"].strip(),
                source_category_code=row["source_category_code"].strip(),
                reference_period=row["reference_period"].strip(),
                published_at=(row.get("published_at") or "").strip(),
                retrieved_at=(row.get("retrieved_at") or "").strip(),
                revision_id=(row.get("revision_id") or "").strip(),
                quality_flags=parse_list(row.get("quality_flags")),
            )
            item.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceSelectionError(f"invalid normalised price at CSV line {line_number}: {exc}") from exc
        items.append(item)
    return items


def select_best_prices(
    rows: Iterable[NormalizedPriceObservation],
) -> tuple[list[NormalizedPriceObservation], list[dict[str, object]], dict[str, object]]:
    items = list(rows)
    duplicate_source_keys = sorted(
        key
        for key, count in Counter(
            (row.series_id, row.economy_code, row.category_code, row.period) for row in items
        ).items()
        if count > 1
    )
    if duplicate_source_keys:
        raise PriceSelectionError(f"duplicate normalised source observations: {duplicate_source_keys[:10]}")

    grouped: dict[tuple[str, str, str], list[NormalizedPriceObservation]] = defaultdict(list)
    for row in items:
        grouped[(row.economy_code, row.category_code, row.period)].append(row)

    selected: list[NormalizedPriceObservation] = []
    audit: list[dict[str, object]] = []
    previous_series: dict[tuple[str, str], str] = {}
    for key in sorted(grouped, key=lambda value: (value[0], value[1], value[2])):
        candidates = sorted(
            grouped[key],
            key=lambda row: (row.evidence_class.rank, row.source_priority, row.series_id),
        )
        winner = candidates[0]
        cell = (winner.economy_code, winner.category_code)
        switched = cell in previous_series and previous_series[cell] != winner.series_id
        previous_series[cell] = winner.series_id
        selected.append(winner)
        audit.append({
            "economy_code": winner.economy_code,
            "category_code": winner.category_code,
            "period": winner.period,
            "selected_series_id": winner.series_id,
            "selected_evidence_class": winner.evidence_class.value,
            "selected_source_priority": winner.source_priority,
            "candidate_count": len(candidates),
            "rejected_series_ids": "|".join(row.series_id for row in candidates[1:]),
            "source_switch": switched,
        })

    summary = {
        "input_candidate_count": len(items),
        "selected_observation_count": len(selected),
        "cell_count": len({(row.economy_code, row.category_code) for row in selected}),
        "period_count": len({row.period for row in selected}),
        "source_switch_count": sum(bool(row["source_switch"]) for row in audit),
        "selected_evidence_class_counts": dict(sorted(Counter(row.evidence_class.value for row in selected).items())),
        "monetary_release_allowed": False,
    }
    return selected, audit, summary


def write_selection_outputs(
    selected: Iterable[NormalizedPriceObservation],
    audit: list[dict[str, object]],
    summary: dict[str, object],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(selected)
    with (output_dir / "selected_prices.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "series_id", "economy_code", "category_code", "period", "price_relative",
            "evidence_class", "source_priority", "provider", "dataset",
            "source_category_code", "reference_period", "published_at", "retrieved_at",
            "revision_id", "quality_flags",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
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
    with (output_dir / "price_selection_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(audit[0].keys()) if audit else [
            "economy_code", "category_code", "period", "selected_series_id",
            "selected_evidence_class", "selected_source_priority", "candidate_count",
            "rejected_series_ids", "source_switch",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(audit)
    (output_dir / "price_selection_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
