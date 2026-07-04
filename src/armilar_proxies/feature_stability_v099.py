"""Descriptive cutoff-to-cutoff stability diagnostics for ARMILAR v0.9.9."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any, Mapping

from .core_v097 import canonical_json_bytes, sha256_bytes
from .feature_core_v099 import decimal_text, decimal_value, false_text

STREAM_REVISION_STABILITY_COLUMNS = [
    "stream_variant_id",
    "mapping_id",
    "source_id",
    "series_id",
    "source_geography",
    "target_economy_code",
    "target_category_code",
    "transformation",
    "unit",
    "earlier_feature_count",
    "later_feature_count",
    "overlap_feature_count",
    "added_feature_count",
    "removed_feature_count",
    "value_changed_feature_count",
    "provenance_changed_feature_count",
    "metadata_changed_feature_count",
    "unchanged_feature_count",
    "value_revision_ratio_on_overlap",
    "mean_absolute_value_revision",
    "maximum_absolute_value_revision",
    "stability_status",
    "comparison_decision_use_allowed",
    "model_ready_claim_allowed",
]

CELL_REVISION_STABILITY_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "distinct_stream_variant_count",
    "streams_with_value_revisions",
    "earlier_feature_count",
    "later_feature_count",
    "overlap_feature_count",
    "added_feature_count",
    "removed_feature_count",
    "value_changed_feature_count",
    "provenance_changed_feature_count",
    "metadata_changed_feature_count",
    "unchanged_feature_count",
    "stability_status",
    "comparison_decision_use_allowed",
    "model_ready_claim_allowed",
]

_STATUSES = (
    "ADDED",
    "REMOVED",
    "VALUE_CHANGED",
    "PROVENANCE_CHANGED",
    "METADATA_CHANGED",
    "UNCHANGED",
)


def _variant_key(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(row[column] for column in (
        "mapping_id",
        "source_id",
        "series_id",
        "source_geography",
        "target_economy_code",
        "target_category_code",
        "transformation",
        "unit",
    ))


def _variant_id(key: tuple[str, ...]) -> str:
    return sha256_bytes(canonical_json_bytes(list(key)))


def _mean_absolute(rows: list[Mapping[str, str]], places: int) -> str:
    values = [abs(decimal_value(row["value_delta"])) for row in rows if row["delta_status"] == "VALUE_CHANGED"]
    if not values:
        return ""
    with localcontext() as context:
        context.prec = 28
        result = sum(values, Decimal(0)) / Decimal(len(values))
    return decimal_text(result, places)


def _max_absolute(rows: list[Mapping[str, str]], places: int) -> str:
    values = [abs(decimal_value(row["value_delta"])) for row in rows if row["delta_status"] == "VALUE_CHANGED"]
    return decimal_text(max(values), places) if values else ""


def _status(counts: Mapping[str, int], overlap: int) -> str:
    if overlap == 0:
        return "NO_OVERLAPPING_FEATURES"
    if counts["VALUE_CHANGED"]:
        return "VALUE_REVISIONS_OBSERVED"
    if counts["PROVENANCE_CHANGED"] or counts["METADATA_CHANGED"]:
        return "NON_VALUE_CHANGES_OBSERVED"
    if counts["ADDED"] or counts["REMOVED"]:
        return "ADDITIONS_OR_REMOVALS_WITH_STABLE_OVERLAP"
    return "STABLE_ON_OVERLAP"


def build_stream_revision_stability(feature_deltas: list[dict[str, str]], *, places: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in feature_deltas:
        grouped[_variant_key(row)].append(row)
    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        counts = {status: sum(row["delta_status"] == status for row in rows) for status in _STATUSES}
        earlier = sum(bool(row["earlier_feature_id"]) for row in rows)
        later = sum(bool(row["later_feature_id"]) for row in rows)
        overlap = sum(bool(row["earlier_feature_id"] and row["later_feature_id"]) for row in rows)
        ratio = ""
        if overlap:
            ratio = decimal_text(Decimal(counts["VALUE_CHANGED"]) / Decimal(overlap), places)
        mapping_id, source_id, series_id, geography, economy, category, transformation, unit = key
        output.append({
            "stream_variant_id": _variant_id(key),
            "mapping_id": mapping_id,
            "source_id": source_id,
            "series_id": series_id,
            "source_geography": geography,
            "target_economy_code": economy,
            "target_category_code": category,
            "transformation": transformation,
            "unit": unit,
            "earlier_feature_count": earlier,
            "later_feature_count": later,
            "overlap_feature_count": overlap,
            "added_feature_count": counts["ADDED"],
            "removed_feature_count": counts["REMOVED"],
            "value_changed_feature_count": counts["VALUE_CHANGED"],
            "provenance_changed_feature_count": counts["PROVENANCE_CHANGED"],
            "metadata_changed_feature_count": counts["METADATA_CHANGED"],
            "unchanged_feature_count": counts["UNCHANGED"],
            "value_revision_ratio_on_overlap": ratio,
            "mean_absolute_value_revision": _mean_absolute(rows, places),
            "maximum_absolute_value_revision": _max_absolute(rows, places),
            "stability_status": _status(counts, overlap),
            "comparison_decision_use_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def build_cell_revision_stability(
    feature_deltas: list[dict[str, str]],
    coverage_deltas: list[dict[str, str]],
    stream_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in feature_deltas:
        grouped[(row["target_economy_code"], row["target_category_code"])].append(row)
    stream_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in stream_rows:
        stream_by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)
    output: list[dict[str, Any]] = []
    for coverage in sorted(coverage_deltas, key=lambda item: (item["economy_code"], item["category_code"])):
        key = (coverage["economy_code"], coverage["category_code"])
        rows = grouped.get(key, [])
        counts = {status: sum(row["delta_status"] == status for row in rows) for status in _STATUSES}
        earlier = sum(bool(row["earlier_feature_id"]) for row in rows)
        later = sum(bool(row["later_feature_id"]) for row in rows)
        overlap = sum(bool(row["earlier_feature_id"] and row["later_feature_id"]) for row in rows)
        streams = stream_by_cell.get(key, [])
        if not rows:
            status = "NO_FEATURES_IN_EITHER_PANEL"
        else:
            status = _status(counts, overlap)
        output.append({
            "economy_code": coverage["economy_code"],
            "economy_name": coverage["economy_name"],
            "category_code": coverage["category_code"],
            "fixed_universe_weight": coverage["fixed_universe_weight"],
            "distinct_stream_variant_count": len(streams),
            "streams_with_value_revisions": sum(int(row["value_changed_feature_count"]) > 0 for row in streams),
            "earlier_feature_count": earlier,
            "later_feature_count": later,
            "overlap_feature_count": overlap,
            "added_feature_count": counts["ADDED"],
            "removed_feature_count": counts["REMOVED"],
            "value_changed_feature_count": counts["VALUE_CHANGED"],
            "provenance_changed_feature_count": counts["PROVENANCE_CHANGED"],
            "metadata_changed_feature_count": counts["METADATA_CHANGED"],
            "unchanged_feature_count": counts["UNCHANGED"],
            "stability_status": status,
            "comparison_decision_use_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output
