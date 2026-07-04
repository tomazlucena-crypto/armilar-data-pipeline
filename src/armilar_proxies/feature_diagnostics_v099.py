"""Descriptive research diagnostics for ARMILAR v0.9.9 proxy features."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Iterable, Mapping

from .archive_core_v098 import parse_utc
from .core_v097 import canonical_json_bytes, sha256_bytes
from .feature_core_v099 import decimal_text, decimal_value, false_text, stream_id

AVAILABILITY_PROFILE_COLUMNS = [
    "stream_id",
    "mapping_id",
    "source_id",
    "series_id",
    "source_geography",
    "target_economy_code",
    "target_category_code",
    "feature_role",
    "complete_level_period_count",
    "partial_level_period_count",
    "first_complete_target_period",
    "last_complete_target_period",
    "minimum_first_seen_lag_days",
    "median_first_seen_lag_days",
    "maximum_first_seen_lag_days",
    "negative_first_seen_lag_count",
    "beyond_diagnostic_window_count",
    "availability_profile_status",
    "backtest_eligibility_claim_allowed",
    "model_ready_claim_allowed",
]

PROVENANCE_CONCENTRATION_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "primary_level_observation_count",
    "sensitivity_level_observation_count",
    "distinct_primary_source_count",
    "distinct_primary_stream_count",
    "largest_source_observation_share",
    "source_observation_hhi",
    "largest_stream_observation_share",
    "stream_observation_hhi",
    "single_source_dependency",
    "single_stream_dependency",
    "dominant_source_above_diagnostic_threshold",
    "provenance_concentration_status",
    "quality_weighting_allowed",
    "model_ready_claim_allowed",
]

RISK_FLAG_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "no_primary_feature",
    "stale_source_only",
    "single_source_dependency",
    "single_stream_dependency",
    "dominant_source_concentration",
    "short_history",
    "history_gaps_present",
    "period_change_unavailable",
    "year_over_year_unavailable",
    "no_multi_source_overlap",
    "negative_first_seen_lag_present",
    "long_first_seen_lag_present",
    "descriptive_flag_count",
    "risk_profile_status",
    "backtest_eligibility_claim_allowed",
    "model_ready_claim_allowed",
]


def _median_text(values: list[int]) -> str:
    if not values:
        return ""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        value = Decimal(ordered[middle])
    else:
        value = (Decimal(ordered[middle - 1]) + Decimal(ordered[middle])) / Decimal(2)
    return decimal_text(value, 1)


def _share(numerator: int, denominator: int, places: int) -> str:
    if denominator <= 0:
        return ""
    with localcontext() as context:
        context.prec = 28
        value = Decimal(numerator) / Decimal(denominator)
    return decimal_text(value, places)


def _hhi(counts: Iterable[int], total: int, places: int) -> str:
    if total <= 0:
        return ""
    with localcontext() as context:
        context.prec = 28
        value = sum((Decimal(count) / Decimal(total)) ** 2 for count in counts)
    return decimal_text(value, places)


def build_availability_profiles(
    features: list[dict[str, Any]],
    *,
    lag_diagnostic_days: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        if row.get("transformation") == "LEVEL":
            grouped[stream_id(row)].append(row)
    output: list[dict[str, Any]] = []
    for identifier in sorted(grouped):
        rows = grouped[identifier]
        first = rows[0]
        complete = [row for row in rows if row["period_completeness_status"] == "COMPLETE_PERIOD"]
        partial = [row for row in rows if row["period_completeness_status"] == "PARTIAL_PERIOD_AS_OF_CUTOFF"]
        lags: list[int] = []
        for row in complete:
            lag = (parse_utc(row["latest_available_at"]).date() - date.fromisoformat(row["target_period_end"])).days
            lags.append(lag)
        negative = sum(value < 0 for value in lags)
        beyond = sum(value > lag_diagnostic_days for value in lags)
        if not complete:
            status = "NO_COMPLETE_PERIOD"
        elif negative:
            status = "NEGATIVE_FIRST_SEEN_LAG_PRESENT"
        elif beyond:
            status = "SOME_FIRST_SEEN_LAGS_BEYOND_DIAGNOSTIC_WINDOW"
        else:
            status = "ALL_FIRST_SEEN_LAGS_WITHIN_DIAGNOSTIC_WINDOW"
        output.append({
            "stream_id": identifier,
            "mapping_id": first["mapping_id"],
            "source_id": first["source_id"],
            "series_id": first["series_id"],
            "source_geography": first["source_geography"],
            "target_economy_code": first["target_economy_code"],
            "target_category_code": first["target_category_code"],
            "feature_role": first["feature_role"],
            "complete_level_period_count": len(complete),
            "partial_level_period_count": len(partial),
            "first_complete_target_period": min((row["target_period"] for row in complete), default=""),
            "last_complete_target_period": max((row["target_period"] for row in complete), default=""),
            "minimum_first_seen_lag_days": min(lags) if lags else "",
            "median_first_seen_lag_days": _median_text(lags),
            "maximum_first_seen_lag_days": max(lags) if lags else "",
            "negative_first_seen_lag_count": negative,
            "beyond_diagnostic_window_count": beyond,
            "availability_profile_status": status,
            "backtest_eligibility_claim_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def build_provenance_concentration(
    features: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    *,
    places: int,
    dominant_source_percent: int,
) -> list[dict[str, Any]]:
    levels_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        if row.get("transformation") == "LEVEL":
            levels_by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)
    threshold = Decimal(dominant_source_percent) / Decimal(100)
    output: list[dict[str, Any]] = []
    for cell in sorted(coverage_rows, key=lambda item: (item["economy_code"], item["category_code"])):
        key = (cell["economy_code"], cell["category_code"])
        levels = levels_by_cell.get(key, [])
        primary = [row for row in levels if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER"]
        sensitivity = [row for row in levels if row["feature_role"] == "SENSITIVITY_ONLY"]
        source_counts = Counter(row["source_id"] for row in primary)
        stream_counts = Counter(stream_id(row) for row in primary)
        total = len(primary)
        largest_source_count = max(source_counts.values(), default=0)
        largest_stream_count = max(stream_counts.values(), default=0)
        largest_source_share = _share(largest_source_count, total, places)
        dominant = bool(total and decimal_value(largest_source_share) >= threshold)
        single_source = len(source_counts) == 1 and total > 0
        single_stream = len(stream_counts) == 1 and total > 0
        if not total:
            status = "NO_PRIMARY_LEVEL_OBSERVATION"
        elif single_source and single_stream:
            status = "SINGLE_SOURCE_AND_STREAM_DEPENDENCY"
        elif single_source:
            status = "SINGLE_SOURCE_MULTIPLE_STREAMS"
        elif dominant:
            status = "MULTI_SOURCE_WITH_DOMINANT_SOURCE"
        else:
            status = "MULTI_SOURCE_DISTRIBUTED_OBSERVATIONS"
        output.append({
            "economy_code": cell["economy_code"],
            "economy_name": cell["economy_name"],
            "category_code": cell["category_code"],
            "fixed_universe_weight": cell["fixed_universe_weight"],
            "primary_level_observation_count": total,
            "sensitivity_level_observation_count": len(sensitivity),
            "distinct_primary_source_count": len(source_counts),
            "distinct_primary_stream_count": len(stream_counts),
            "largest_source_observation_share": largest_source_share,
            "source_observation_hhi": _hhi(source_counts.values(), total, places),
            "largest_stream_observation_share": _share(largest_stream_count, total, places),
            "stream_observation_hhi": _hhi(stream_counts.values(), total, places),
            "single_source_dependency": "true" if single_source else "false",
            "single_stream_dependency": "true" if single_stream else "false",
            "dominant_source_above_diagnostic_threshold": "true" if dominant else "false",
            "provenance_concentration_status": status,
            "quality_weighting_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def build_cell_risk_flags(
    *,
    coverage_rows: list[dict[str, Any]],
    stream_history_rows: list[dict[str, Any]],
    cell_diagnostic_rows: list[dict[str, Any]],
    availability_rows: list[dict[str, Any]],
    provenance_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    history_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in stream_history_rows:
        if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER":
            history_by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)
    availability_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in availability_rows:
        if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER":
            availability_by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)
    diagnostic_by_cell = {(row["economy_code"], row["category_code"]): row for row in cell_diagnostic_rows}
    provenance_by_cell = {(row["economy_code"], row["category_code"]): row for row in provenance_rows}
    output: list[dict[str, Any]] = []
    for cell in sorted(coverage_rows, key=lambda item: (item["economy_code"], item["category_code"])):
        key = (cell["economy_code"], cell["category_code"])
        diagnostic = diagnostic_by_cell[key]
        provenance = provenance_by_cell[key]
        histories = history_by_cell.get(key, [])
        availability = availability_by_cell.get(key, [])
        flags = {
            "no_primary_feature": diagnostic["diagnostic_class"] == "NO_PRIMARY_FEATURE",
            "stale_source_only": diagnostic["stale_source_only"] == "true",
            "single_source_dependency": provenance["single_source_dependency"] == "true",
            "single_stream_dependency": provenance["single_stream_dependency"] == "true",
            "dominant_source_concentration": provenance["dominant_source_above_diagnostic_threshold"] == "true",
            "short_history": diagnostic["diagnostic_class"] == "PRIMARY_SHORT_HISTORY",
            "history_gaps_present": any(int(row["missing_expected_period_count"]) > 0 for row in histories),
            "period_change_unavailable": diagnostic["period_change_available"] != "true",
            "year_over_year_unavailable": diagnostic["year_over_year_available"] != "true",
            "no_multi_source_overlap": int(diagnostic["complete_multi_source_period_count"]) == 0,
            "negative_first_seen_lag_present": any(int(row["negative_first_seen_lag_count"]) > 0 for row in availability),
            "long_first_seen_lag_present": any(int(row["beyond_diagnostic_window_count"]) > 0 for row in availability),
        }
        count = sum(flags.values())
        if flags["no_primary_feature"]:
            status = "NO_PRIMARY_FEATURE"
        elif count:
            status = "DESCRIPTIVE_FLAGS_PRESENT"
        else:
            status = "DESCRIPTIVE_FLAGS_ABSENT_IN_CURRENT_PANEL"
        output.append({
            "economy_code": cell["economy_code"],
            "economy_name": cell["economy_name"],
            "category_code": cell["category_code"],
            "fixed_universe_weight": cell["fixed_universe_weight"],
            **{key_: "true" if value else "false" for key_, value in flags.items()},
            "descriptive_flag_count": count,
            "risk_profile_status": status,
            "backtest_eligibility_claim_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def risk_flags_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Canonical fingerprint for deterministic test and audit receipts."""
    return sha256_bytes(canonical_json_bytes(rows))
