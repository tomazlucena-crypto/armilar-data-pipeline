"""Deterministic point-in-time feature construction for ARMILAR v0.9.9."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from itertools import combinations
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Iterable, Mapping

from .archive_builder_v098 import verify_information_set_bundle
from .archive_core_v098 import parse_utc
from .core_v097 import canonical_json_bytes, sha256_bytes, sha256_file, utc_timestamp
from .feature_core_v099 import (
    CELL_COVERAGE_COLUMNS,
    CELL_DIAGNOSTIC_COLUMNS,
    CELL_PERIOD_COLUMNS,
    CONCORDANCE_COLUMNS,
    CONTRACT_VERSION,
    FEATURE_COLUMNS,
    FEATURE_PANEL_STATUS,
    FALSE_GATES,
    MAPPING_AUDIT_COLUMNS,
    STREAM_HISTORY_COLUMNS,
    UNMAPPED_COLUMNS,
    ProxyFeatureError,
    component_hash,
    csv_bytes,
    decimal_text,
    decimal_value,
    false_text,
    feature_id,
    load_policy,
    mapping_for_row,
    month_index,
    month_range,
    months_inclusive,
    month_key,
    percent_change,
    policy_hash,
    read_csv,
    resolve_geography,
    shift_month,
    stream_id,
    target_month_not_after_cutoff,
    target_period_metadata,
    write_manifest,
)
from .feature_diagnostics_v099 import (
    AVAILABILITY_PROFILE_COLUMNS,
    PROVENANCE_CONCENTRATION_COLUMNS,
    RISK_FLAG_COLUMNS,
    build_availability_profiles,
    build_cell_risk_flags,
    build_provenance_concentration,
)


def _manifest_entries(bundle: Path) -> dict[str, str]:
    manifest = bundle / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ProxyFeatureError("feature bundle manifest is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ProxyFeatureError(f"invalid feature manifest line {line_number}")
        digest, relative = parts
        if relative in entries:
            raise ProxyFeatureError(f"duplicate feature manifest path: {relative}")
        path = (bundle / relative).resolve()
        if bundle.resolve() not in path.parents:
            raise ProxyFeatureError(f"feature manifest path escapes bundle: {relative}")
        if not path.is_file() or sha256_file(path) != digest:
            raise ProxyFeatureError(f"feature manifest hash mismatch: {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != actual:
        raise ProxyFeatureError(
            f"feature manifest file set mismatch; missing={sorted(actual - set(entries))}, "
            f"extra={sorted(set(entries) - actual)}"
        )
    return entries


def _basket_rows(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    required = {
        "research_core_id",
        "economy_code",
        "economy_name",
        "category_code",
        "fixed_universe_weight",
    }
    if not rows:
        raise ProxyFeatureError("Research Core basket is empty")
    if not required.issubset(rows[0]):
        raise ProxyFeatureError("Research Core basket is missing required columns")
    identities: set[tuple[str, str]] = set()
    total = Decimal(0)
    for row in rows:
        if row["research_core_id"] != "ARMILAR_RESEARCH_CORE_V1":
            raise ProxyFeatureError("unexpected research_core_id")
        economy = row["economy_code"]
        category = row["category_code"]
        if not re.fullmatch(r"[A-Z0-9]{3}", economy) or not re.fullmatch(r"CP(0[1-9]|1[0-2])", category):
            raise ProxyFeatureError("invalid Research Core basket identity")
        identity = (economy, category)
        if identity in identities:
            raise ProxyFeatureError(f"duplicate Research Core basket cell: {identity}")
        identities.add(identity)
        weight = decimal_value(row["fixed_universe_weight"])
        if weight <= 0:
            raise ProxyFeatureError("Research Core fixed weight must be positive")
        total += weight
    if len(rows) != 60 or total != Decimal(1):
        raise ProxyFeatureError(f"Research Core basket must contain 60 cells summing exactly to 1; rows={len(rows)}, sum={total}")
    economy_categories: dict[str, set[str]] = defaultdict(set)
    for economy, category in identities:
        economy_categories[economy].add(category)
    if len(economy_categories) != 5 or any(len(categories) != 12 for categories in economy_categories.values()):
        raise ProxyFeatureError("Research Core basket must contain five complete 12-category economies")
    return sorted(rows, key=lambda item: (item["economy_code"], item["category_code"]))


def _atomic_directory(target: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if target.exists():
        raise ProxyFeatureError(f"output directory already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))
    return target, temp


def _finalise_directory(temp: Path, target: Path) -> Path:
    temp.replace(target)
    try:
        parent_fd = os.open(str(target.parent), os.O_RDONLY)
    except OSError:
        return target
    try:
        os.fsync(parent_fd)
    except OSError:
        pass
    finally:
        os.close(parent_fd)
    return target


def _source_status_map(information_set_dir: Path, cutoff: str) -> dict[str, dict[str, str]]:
    rows = read_csv(information_set_dir / "source_cutoff_status.csv")
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        source_id = row.get("source_id", "")
        if not source_id or source_id in result:
            raise ProxyFeatureError("source cutoff status contains a missing or duplicate source_id")
        if row.get("cutoff") != cutoff:
            raise ProxyFeatureError("source cutoff status does not match information-set cutoff")
        result[source_id] = row
    return result


def _unmapped_key(row: Mapping[str, str], reason: str) -> tuple[str, ...]:
    return (
        row.get("source_id", ""),
        row.get("series_id", ""),
        row.get("proxy_domain", ""),
        row.get("geography", ""),
        row.get("frequency", ""),
        reason,
    )


def _source_unit_for_transformation(unit: str, transformation: str) -> str:
    return unit if transformation == "LEVEL" else "PERCENT"


def _build_level_rows(
    *,
    panel_rows: list[dict[str, str]],
    source_status: Mapping[str, Mapping[str, str]],
    policy: Mapping[str, Any],
    basket_rows: list[dict[str, str]],
    cutoff: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    basket_economies = sorted({row["economy_code"] for row in basket_rows})
    basket_cells = {(row["economy_code"], row["category_code"]) for row in basket_rows}
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    unmapped_counts: dict[tuple[str, ...], int] = defaultdict(int)
    audit_state: dict[str, dict[str, Any]] = {}
    for mapping in policy["category_mappings"]:
        audit_state[mapping["mapping_id"]] = {
            "mapping": mapping,
            "matched_input_observation_count": 0,
            "mapped_target_observation_count": 0,
            "source_geographies": set(),
            "periods": [],
        }

    for row in panel_rows:
        if row.get("cutoff") != cutoff:
            raise ProxyFeatureError("panel row cutoff does not match information-set summary")
        if parse_utc(row["available_at"]) > parse_utc(cutoff):
            raise ProxyFeatureError("panel row was observed after cutoff")
        for gate in ("direct_index_use_allowed", "arm_l_use_allowed", "model_training_allowed"):
            if row.get(gate) != "false":
                raise ProxyFeatureError(f"upstream panel gate opened: {gate}")
        mapping = mapping_for_row(policy, row)
        if mapping is None:
            reason = "UNMAPPED_SERIES"
            # Domain mismatch deserves a separate audit reason when a series rule exists.
            for candidate in policy["category_mappings"]:
                match = candidate["series_match"]
                series_matches = (
                    row.get("series_id") == match["value"]
                    if match["type"] == "EXACT"
                    else row.get("series_id", "").startswith(match["value"])
                )
                if candidate["source_id"] == row.get("source_id") and series_matches:
                    reason = "PROXY_DOMAIN_MISMATCH"
                    break
            unmapped_counts[_unmapped_key(row, reason)] += 1
            continue
        if row.get("frequency") != mapping["allowed_frequency"]:
            unmapped_counts[_unmapped_key(row, "FREQUENCY_MISMATCH")] += 1
            continue
        target_period = month_key(row["period"], row["frequency"])
        if not target_month_not_after_cutoff(target_period, cutoff):
            raise ProxyFeatureError("mapped feature period is after cutoff")
        if mapping["target_scope"] == "GLOBAL_BROADCAST":
            target_economies = basket_economies
        else:
            resolved = resolve_geography(policy, row.get("geography", ""))
            if resolved is None:
                unmapped_counts[_unmapped_key(row, "UNRESOLVED_GEOGRAPHY")] += 1
                continue
            if resolved not in basket_economies:
                unmapped_counts[_unmapped_key(row, "OUTSIDE_RESEARCH_CORE")] += 1
                continue
            target_economies = [resolved]
        category = mapping["target_category_code"]
        audit = audit_state[mapping["mapping_id"]]
        audit["matched_input_observation_count"] += 1
        audit["source_geographies"].add(row["geography"])
        audit["periods"].append(row["period"])
        for economy in target_economies:
            if (economy, category) not in basket_cells:
                raise ProxyFeatureError(f"mapping targets a cell outside the Research Core: {(economy, category)}")
            audit["mapped_target_observation_count"] += 1
            group_key = (
                mapping["mapping_id"],
                row["source_id"],
                row["series_id"],
                row["proxy_domain"],
                row["geography"],
                economy,
                category,
                mapping["target_armilar_category"],
                mapping["feature_role"],
                mapping["mapping_evidence"],
                row["frequency"],
                target_period,
                row["unit"],
                mapping["aggregation_method"],
            )
            grouped[group_key].append(row)

    places = int(policy["transformation_policy"]["output_decimal_places"])
    levels: list[dict[str, Any]] = []
    for key in sorted(grouped):
        (
            mapping_id,
            source_id,
            series_id,
            proxy_domain,
            source_geography,
            economy,
            category,
            armilar_category,
            role,
            evidence,
            native_frequency,
            target_period,
            unit,
            aggregation,
        ) = key
        components = grouped[key]
        if aggregation in {"MONTHLY_DIRECT", "QUARTER_END_DIRECT"} and len(components) != 1:
            raise ProxyFeatureError(f"non-weekly aggregation has duplicate components: {key}")
        values = [decimal_value(row["value"]) for row in components]
        with localcontext() as context:
            context.prec = 28
            value = sum(values, Decimal(0)) / Decimal(len(values))
        source_state = source_status.get(source_id)
        if source_state is None:
            raise ProxyFeatureError(f"source status is missing for mapped source: {source_id}")
        freshness = source_state.get("freshness_status", "")
        if freshness not in {
            "CURRENT_WITHIN_EXPECTED_WINDOW",
            "STALE_BEYOND_EXPECTED_WINDOW",
            "NO_SNAPSHOT_BY_CUTOFF",
        }:
            raise ProxyFeatureError(f"invalid source freshness status: {source_id}")
        if freshness == "NO_SNAPSHOT_BY_CUTOFF":
            raise ProxyFeatureError(f"mapped panel rows exist for source with no snapshot by cutoff: {source_id}")
        target_period_end, feature_age_days, period_completeness_status = target_period_metadata(target_period, cutoff)
        row: dict[str, Any] = {
            "cutoff": cutoff,
            "mapping_id": mapping_id,
            "source_id": source_id,
            "series_id": series_id,
            "source_proxy_domain": proxy_domain,
            "source_geography": source_geography,
            "target_economy_code": economy,
            "target_category_code": category,
            "target_armilar_category": armilar_category,
            "feature_role": role,
            "mapping_evidence": evidence,
            "native_frequency": native_frequency,
            "target_frequency": "MONTHLY",
            "target_period": target_period,
            "target_period_end": target_period_end,
            "feature_age_days": feature_age_days,
            "period_completeness_status": period_completeness_status,
            "transformation": "LEVEL",
            "value": decimal_text(value, places),
            "unit": unit,
            "aggregation_method": aggregation,
            "component_count": len(components),
            "component_observation_keys_sha256": component_hash(row_["observation_key"] for row_ in components),
            "latest_available_at": max(row_["available_at"] for row_ in components),
            "source_freshness_status": freshness,
            "direct_index_use_allowed": false_text(),
            "arm_l_use_allowed": false_text(),
            "model_training_allowed": false_text(),
        }
        row["feature_id"] = feature_id(row)
        levels.append(row)

    mapping_audit: list[dict[str, Any]] = []
    for mapping_id in sorted(audit_state):
        state = audit_state[mapping_id]
        mapping = state["mapping"]
        periods = state["periods"]
        mapping_audit.append(
            {
                "mapping_id": mapping_id,
                "source_id": mapping["source_id"],
                "series_match_type": mapping["series_match"]["type"],
                "series_match_value": mapping["series_match"]["value"],
                "target_scope": mapping["target_scope"],
                "target_category_code": mapping["target_category_code"],
                "target_armilar_category": mapping["target_armilar_category"],
                "feature_role": mapping["feature_role"],
                "matched_input_observation_count": state["matched_input_observation_count"],
                "mapped_target_observation_count": state["mapped_target_observation_count"],
                "distinct_source_geography_count": len(state["source_geographies"]),
                "first_source_period": min(periods) if periods else "",
                "last_source_period": max(periods) if periods else "",
            }
        )
    unmapped: list[dict[str, Any]] = []
    for key, count in sorted(unmapped_counts.items()):
        source_id, series_id, domain, geography, frequency, reason = key
        unmapped.append(
            {
                "source_id": source_id,
                "series_id": series_id,
                "proxy_domain": domain,
                "geography": geography,
                "frequency": frequency,
                "reason": reason,
                "observation_count": count,
            }
        )
    return levels, mapping_audit, unmapped


def _transformed_rows(levels: list[dict[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    places = int(policy["transformation_policy"]["output_decimal_places"])
    grouped: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in levels:
        identity = (
            row["mapping_id"],
            row["source_id"],
            row["series_id"],
            row["source_geography"],
            row["target_economy_code"],
            row["target_category_code"],
            row["unit"],
        )
        period = row["target_period"]
        if period in grouped[identity]:
            raise ProxyFeatureError(f"duplicate level feature period: {identity}:{period}")
        grouped[identity][period] = row
    output = list(levels)
    for identity in sorted(grouped):
        by_period = grouped[identity]
        for period in sorted(by_period):
            current = by_period[period]
            current_value = decimal_value(current["value"])
            lags = (
                ("PERIOD_CHANGE_PCT", shift_month(period, -3 if current["native_frequency"] == "QUARTERLY" else -1)),
                ("YEAR_OVER_YEAR_PCT", shift_month(period, -12)),
            )
            for transformation, previous_period in lags:
                previous = by_period.get(previous_period)
                if previous is None:
                    continue
                value = percent_change(current_value, decimal_value(previous["value"]), places)
                if value is None:
                    continue
                row = dict(current)
                row["transformation"] = transformation
                row["value"] = value
                row["unit"] = "PERCENT"
                row["aggregation_method"] = f"{current['aggregation_method']}+EXACT_CALENDAR_LAG"
                row["component_count"] = int(current["component_count"]) + int(previous["component_count"])
                row["component_observation_keys_sha256"] = sha256_bytes(
                    canonical_json_bytes(
                        sorted(
                            [
                                current["component_observation_keys_sha256"],
                                previous["component_observation_keys_sha256"],
                            ]
                        )
                    )
                )
                row["latest_available_at"] = max(current["latest_available_at"], previous["latest_available_at"])
                row["feature_id"] = feature_id(row)
                output.append(row)
    return sorted(
        output,
        key=lambda row: (
            row["target_economy_code"],
            row["target_category_code"],
            row["target_period"],
            row["source_id"],
            row["series_id"],
            row["source_geography"],
            row["transformation"],
        ),
    )


def _stream_identity(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row["mapping_id"]),
        str(row["source_id"]),
        str(row["series_id"]),
        str(row["source_geography"]),
        str(row["target_economy_code"]),
        str(row["target_category_code"]),
    )


def _coverage_rows(features: list[dict[str, Any]], basket_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        if row["transformation"] == "LEVEL":
            by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)
    output: list[dict[str, Any]] = []
    for basket in basket_rows:
        key = (basket["economy_code"], basket["category_code"])
        cell_features = by_cell.get(key, [])
        primary = [row for row in cell_features if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER"]
        sensitivity = [row for row in cell_features if row["feature_role"] == "SENSITIVITY_ONLY"]
        primary_streams = {_stream_identity(row) for row in primary}
        sensitivity_streams = {_stream_identity(row) for row in sensitivity}
        current_sources = sorted({
            row["source_id"] for row in primary
            if row["source_freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW"
        })
        stale_sources = sorted({
            row["source_id"] for row in primary
            if row["source_freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW"
        })
        primary_sources = sorted({row["source_id"] for row in primary})
        sensitivity_sources = sorted({row["source_id"] for row in sensitivity})
        primary_periods = sorted({row["target_period"] for row in primary})
        sensitivity_periods = sorted({row["target_period"] for row in sensitivity})
        primary_ages = [int(row["feature_age_days"]) for row in primary]
        if current_sources:
            status = "PRIMARY_FEATURE_FROM_CURRENT_SOURCE"
        elif stale_sources:
            status = "PRIMARY_FEATURE_FROM_STALE_SOURCE"
        elif sensitivity_streams:
            status = "SENSITIVITY_ONLY"
        else:
            status = "NO_MAPPED_FEATURE"
        output.append({
            "economy_code": basket["economy_code"],
            "economy_name": basket["economy_name"],
            "category_code": basket["category_code"],
            "fixed_universe_weight": basket["fixed_universe_weight"],
            "primary_feature_count": len(primary_streams),
            "sensitivity_feature_count": len(sensitivity_streams),
            "current_primary_source_count": len(current_sources),
            "stale_primary_source_count": len(stale_sources),
            "primary_source_ids": "|".join(primary_sources),
            "sensitivity_source_ids": "|".join(sensitivity_sources),
            "latest_primary_target_period": primary_periods[-1] if primary_periods else "",
            "latest_sensitivity_target_period": sensitivity_periods[-1] if sensitivity_periods else "",
            "minimum_primary_feature_age_days": min(primary_ages) if primary_ages else "",
            "maximum_primary_feature_age_days": max(primary_ages) if primary_ages else "",
            "coverage_status": status,
            "price_coverage_claim_allowed": false_text(),
        })
    return output

def _build_stream_history(features: list[dict[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        grouped[stream_id(row)].append(row)
    minimum_long = int(policy["diagnostic_policy"]["long_history_min_complete_periods"])
    output: list[dict[str, Any]] = []
    for identifier in sorted(grouped):
        rows = grouped[identifier]
        levels = sorted((row for row in rows if row["transformation"] == "LEVEL"), key=lambda row: row["target_period"])
        if not levels:
            raise ProxyFeatureError(f"feature stream has no level rows: {identifier}")
        frequencies = {row["native_frequency"] for row in levels}
        roles = {row["feature_role"] for row in levels}
        freshness = {row["source_freshness_status"] for row in levels}
        if len(frequencies) != 1 or len(roles) != 1 or len(freshness) != 1:
            raise ProxyFeatureError(f"feature stream metadata changes within bundle: {identifier}")
        frequency = next(iter(frequencies))
        step = 3 if frequency == "QUARTERLY" else 1
        periods = [row["target_period"] for row in levels]
        indices = [month_index(period) for period in periods]
        if len(indices) != len(set(indices)):
            raise ProxyFeatureError(f"duplicate level period in stream history: {identifier}")
        expected = set(range(indices[0], indices[-1] + 1, step))
        observed = set(indices)
        missing = len(expected - observed)
        longest_gap = max((right - left - step for left, right in zip(indices, indices[1:])), default=0)
        complete = [row for row in levels if row["period_completeness_status"] == "COMPLETE_PERIOD"]
        partial = [row for row in levels if row["period_completeness_status"] == "PARTIAL_PERIOD_AS_OF_CUTOFF"]
        period_changes = sum(row["transformation"] == "PERIOD_CHANGE_PCT" for row in rows)
        yoy = sum(row["transformation"] == "YEAR_OVER_YEAR_PCT" for row in rows)
        role = next(iter(roles))
        if role == "SENSITIVITY_ONLY":
            status = "SENSITIVITY_HISTORY"
        elif not complete:
            status = "NO_COMPLETE_HISTORY"
        elif len(complete) >= minimum_long and missing == 0 and period_changes > 0:
            status = "LONG_CONTIGUOUS_HISTORY_WITH_CHANGES"
        elif len(complete) >= minimum_long:
            status = "LONG_HISTORY_WITH_GAPS_OR_NO_CHANGES"
        else:
            status = "SHORT_HISTORY"
        first = levels[0]
        output.append({
            "stream_id": identifier,
            "mapping_id": first["mapping_id"],
            "source_id": first["source_id"],
            "series_id": first["series_id"],
            "source_geography": first["source_geography"],
            "target_economy_code": first["target_economy_code"],
            "target_category_code": first["target_category_code"],
            "feature_role": role,
            "native_frequency": frequency,
            "source_freshness_status": next(iter(freshness)),
            "expected_period_step_months": step,
            "first_target_period": periods[0],
            "last_target_period": periods[-1],
            "observed_level_period_count": len(levels),
            "complete_level_period_count": len(complete),
            "partial_level_period_count": len(partial),
            "missing_expected_period_count": missing,
            "longest_gap_months_beyond_expected": longest_gap,
            "history_span_months": months_inclusive(periods[0], periods[-1]),
            "period_change_count": period_changes,
            "year_over_year_count": yoy,
            "latest_feature_age_days": int(levels[-1]["feature_age_days"]),
            "research_diagnostic_status": status,
            "backtest_eligibility_claim_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def _build_cell_period_coverage(
    features: list[dict[str, Any]], basket_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    levels = [row for row in features if row["transformation"] == "LEVEL"]
    if not levels:
        raise ProxyFeatureError("cannot build cell-period coverage without level features")
    periods = month_range(
        min(row["target_period"] for row in levels),
        max(row["target_period"] for row in levels),
    )
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in levels:
        grouped[(row["target_economy_code"], row["target_category_code"], row["target_period"])].append(row)
    output: list[dict[str, Any]] = []
    for basket in basket_rows:
        cell = (basket["economy_code"], basket["category_code"])
        for period in periods:
            rows = grouped.get((*cell, period), [])
            primary = [row for row in rows if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER"]
            sensitivity = [row for row in rows if row["feature_role"] == "SENSITIVITY_ONLY"]
            current = sorted({row["source_id"] for row in primary if row["source_freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW"})
            stale = sorted({row["source_id"] for row in primary if row["source_freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW"})
            complete = [row for row in primary if row["period_completeness_status"] == "COMPLETE_PERIOD"]
            partial = [row for row in primary if row["period_completeness_status"] == "PARTIAL_PERIOD_AS_OF_CUTOFF"]
            complete_current = [row for row in complete if row["source_freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW"]
            complete_stale = [row for row in complete if row["source_freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW"]
            if complete_current:
                status = "PRIMARY_COMPLETE_FROM_CURRENT_SOURCE"
            elif complete_stale:
                status = "PRIMARY_COMPLETE_FROM_STALE_SOURCE"
            elif partial:
                status = "PRIMARY_PARTIAL_ONLY"
            elif sensitivity:
                status = "SENSITIVITY_ONLY"
            else:
                status = "NO_FEATURE"
            output.append({
                "economy_code": basket["economy_code"],
                "economy_name": basket["economy_name"],
                "category_code": basket["category_code"],
                "target_period": period,
                "fixed_universe_weight": basket["fixed_universe_weight"],
                "primary_stream_count": len({stream_id(row) for row in primary}),
                "sensitivity_stream_count": len({stream_id(row) for row in sensitivity}),
                "current_primary_source_count": len(current),
                "stale_primary_source_count": len(stale),
                "complete_primary_stream_count": len({stream_id(row) for row in complete}),
                "partial_primary_stream_count": len({stream_id(row) for row in partial}),
                "primary_source_ids": "|".join(sorted({row["source_id"] for row in primary})),
                "sensitivity_source_ids": "|".join(sorted({row["source_id"] for row in sensitivity})),
                "period_status": status,
                "price_coverage_claim_allowed": false_text(),
            })
    return output


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _pearson(values: list[tuple[Decimal, Decimal]], places: int) -> str:
    if len(values) < 2:
        return ""
    with localcontext() as context:
        context.prec = 28
        count = Decimal(len(values))
        mean_left = sum((left for left, _ in values), Decimal(0)) / count
        mean_right = sum((right for _, right in values), Decimal(0)) / count
        covariance = sum(((left - mean_left) * (right - mean_right) for left, right in values), Decimal(0))
        variance_left = sum(((left - mean_left) ** 2 for left, _ in values), Decimal(0))
        variance_right = sum(((right - mean_right) ** 2 for _, right in values), Decimal(0))
        if variance_left == 0 or variance_right == 0:
            return ""
        correlation = covariance / (variance_left * variance_right).sqrt()
    return decimal_text(correlation, places)


def _build_concordance(features: list[dict[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    complete_only = bool(policy["diagnostic_policy"]["concordance_complete_periods_only"])
    minimum_overlap = int(policy["diagnostic_policy"]["concordance_min_overlap_periods"])
    places = int(policy["transformation_policy"]["output_decimal_places"])
    grouped: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in features:
        if row["feature_role"] != "PRIMARY_RESEARCH_DRIVER" or row["transformation"] == "LEVEL":
            continue
        if complete_only and row["period_completeness_status"] != "COMPLETE_PERIOD":
            continue
        grouped[(row["target_economy_code"], row["target_category_code"], row["transformation"])][stream_id(row)].append(row)
    output: list[dict[str, Any]] = []
    for (economy, category, transformation), streams in sorted(grouped.items()):
        for left_id, right_id in combinations(sorted(streams), 2):
            left_rows = {row["target_period"]: row for row in streams[left_id]}
            right_rows = {row["target_period"]: row for row in streams[right_id]}
            overlap = sorted(set(left_rows) & set(right_rows))
            if not overlap:
                continue
            pairs = [(decimal_value(left_rows[period]["value"]), decimal_value(right_rows[period]["value"])) for period in overlap]
            agreements = sum(_sign(left) == _sign(right) for left, right in pairs)
            disagreements = len(pairs) - agreements
            spreads = [abs(left - right) for left, right in pairs]
            with localcontext() as context:
                context.prec = 28
                agreement_ratio = Decimal(agreements) / Decimal(len(pairs))
                mean_spread = sum(spreads, Decimal(0)) / Decimal(len(spreads))
            correlation = _pearson(pairs, places)
            status = (
                "INSUFFICIENT_OVERLAP"
                if len(overlap) < minimum_overlap
                else "NO_VARIATION"
                if not correlation
                else "DESCRIPTIVE_ONLY"
            )
            left = streams[left_id][0]
            right = streams[right_id][0]
            output.append({
                "target_economy_code": economy,
                "target_category_code": category,
                "transformation": transformation,
                "left_stream_id": left_id,
                "right_stream_id": right_id,
                "left_source_id": left["source_id"],
                "left_series_id": left["series_id"],
                "right_source_id": right["source_id"],
                "right_series_id": right["series_id"],
                "overlap_period_count": len(overlap),
                "first_overlap_period": overlap[0],
                "last_overlap_period": overlap[-1],
                "direction_agreement_count": agreements,
                "direction_disagreement_count": disagreements,
                "direction_agreement_ratio": decimal_text(agreement_ratio, places),
                "mean_absolute_spread": decimal_text(mean_spread, places),
                "maximum_absolute_spread": decimal_text(max(spreads), places),
                "pearson_correlation": correlation,
                "concordance_status": status,
                "concordance_approval_claim_allowed": false_text(),
                "model_ready_claim_allowed": false_text(),
            })
    return output


def _longest_contiguous_periods(periods: list[str]) -> int:
    if not periods:
        return 0
    indices = sorted({month_index(period) for period in periods})
    longest = current = 1
    for left, right in zip(indices, indices[1:]):
        if right == left + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def _build_cell_diagnostics(
    features: list[dict[str, Any]],
    cell_periods: list[dict[str, Any]],
    basket_rows: list[dict[str, str]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    levels_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    transformations_by_cell: dict[tuple[str, str], set[str]] = defaultdict(set)
    periods_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        key = (row["target_economy_code"], row["target_category_code"])
        if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER":
            transformations_by_cell[key].add(row["transformation"])
            if row["transformation"] == "LEVEL":
                levels_by_cell[key].append(row)
    for row in cell_periods:
        periods_by_cell[(row["economy_code"], row["category_code"])].append(row)
    long_min = int(policy["diagnostic_policy"]["long_history_min_complete_periods"])
    multi_min = int(policy["diagnostic_policy"]["multi_source_min_complete_periods"])
    output: list[dict[str, Any]] = []
    complete_statuses = {"PRIMARY_COMPLETE_FROM_CURRENT_SOURCE", "PRIMARY_COMPLETE_FROM_STALE_SOURCE"}
    for basket in basket_rows:
        key = (basket["economy_code"], basket["category_code"])
        levels = levels_by_cell.get(key, [])
        period_rows = periods_by_cell.get(key, [])
        complete_periods = [row["target_period"] for row in period_rows if row["period_status"] in complete_statuses]
        multi_periods = [row["target_period"] for row in period_rows if int(row["complete_primary_stream_count"]) >= 2]
        current = any(row["source_freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW" for row in levels)
        stale = any(row["source_freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW" for row in levels)
        distinct_streams = {stream_id(row) for row in levels}
        distinct_sources = {row["source_id"] for row in levels}
        if not levels:
            diagnostic = "NO_PRIMARY_FEATURE"
        elif not complete_periods:
            diagnostic = "PRIMARY_PARTIAL_ONLY"
        elif stale and not current:
            diagnostic = "PRIMARY_STALE_HISTORY"
        elif len(complete_periods) >= long_min and len(multi_periods) >= multi_min and len(distinct_sources) >= 2:
            diagnostic = "PRIMARY_LONG_MULTI_SOURCE_HISTORY"
        elif len(complete_periods) >= long_min:
            diagnostic = "PRIMARY_LONG_HISTORY"
        else:
            diagnostic = "PRIMARY_SHORT_HISTORY"
        transforms = transformations_by_cell.get(key, set())
        output.append({
            "economy_code": basket["economy_code"],
            "economy_name": basket["economy_name"],
            "category_code": basket["category_code"],
            "fixed_universe_weight": basket["fixed_universe_weight"],
            "distinct_primary_stream_count": len(distinct_streams),
            "distinct_primary_source_count": len(distinct_sources),
            "first_complete_primary_period": min(complete_periods) if complete_periods else "",
            "last_complete_primary_period": max(complete_periods) if complete_periods else "",
            "complete_primary_period_count": len(complete_periods),
            "complete_multi_source_period_count": len(multi_periods),
            "longest_contiguous_primary_months": _longest_contiguous_periods(complete_periods),
            "period_change_available": "true" if "PERIOD_CHANGE_PCT" in transforms else "false",
            "year_over_year_available": "true" if "YEAR_OVER_YEAR_PCT" in transforms else "false",
            "current_source_present": "true" if current else "false",
            "stale_source_only": "true" if stale and not current else "false",
            "diagnostic_class": diagnostic,
            "backtest_eligibility_claim_allowed": false_text(),
            "model_ready_claim_allowed": false_text(),
        })
    return output


def _coverage_weight(rows: Iterable[Mapping[str, Any]], statuses: set[str]) -> str:
    total = sum(
        (decimal_value(row["fixed_universe_weight"]) for row in rows if row["coverage_status"] in statuses),
        Decimal(0),
    )
    return format(total, "f")


def build_feature_panel(
    *,
    information_set_dir: Path,
    policy_path: Path,
    basket_path: Path,
    output_dir: Path,
) -> Path:
    upstream_summary = verify_information_set_bundle(information_set_dir)
    policy = load_policy(policy_path)
    basket_rows = _basket_rows(basket_path)
    cutoff = utc_timestamp(upstream_summary["cutoff"])
    panel_rows = read_csv(information_set_dir / "panel.csv")
    source_status = _source_status_map(information_set_dir, cutoff)
    levels, mapping_audit, unmapped = _build_level_rows(
        panel_rows=panel_rows,
        source_status=source_status,
        policy=policy,
        basket_rows=basket_rows,
        cutoff=cutoff,
    )
    if not levels:
        raise ProxyFeatureError("v0.9.9 mapping produced no feature levels")
    features = _transformed_rows(levels, policy)
    coverage = _coverage_rows(features, basket_rows)
    stream_history = _build_stream_history(features, policy)
    cell_period_coverage = _build_cell_period_coverage(features, basket_rows)
    concordance = _build_concordance(features, policy)
    cell_diagnostics = _build_cell_diagnostics(features, cell_period_coverage, basket_rows, policy)
    availability_profiles = build_availability_profiles(
        features,
        lag_diagnostic_days=int(policy["diagnostic_policy"]["availability_lag_diagnostic_days"]),
    )
    provenance_concentration = build_provenance_concentration(
        features,
        coverage,
        places=int(policy["transformation_policy"]["output_decimal_places"]),
        dominant_source_percent=int(policy["diagnostic_policy"]["provenance_concentration_diagnostic_percent"]),
    )
    risk_flags = build_cell_risk_flags(
        coverage_rows=coverage,
        stream_history_rows=stream_history,
        cell_diagnostic_rows=cell_diagnostics,
        availability_rows=availability_profiles,
        provenance_rows=provenance_concentration,
    )
    target, temp = _atomic_directory(output_dir)
    try:
        (temp / "feature_values.csv").write_bytes(csv_bytes(features, FEATURE_COLUMNS))
        (temp / "cell_coverage.csv").write_bytes(csv_bytes(coverage, CELL_COVERAGE_COLUMNS))
        (temp / "mapping_audit.csv").write_bytes(csv_bytes(mapping_audit, MAPPING_AUDIT_COLUMNS))
        (temp / "unmapped_observations.csv").write_bytes(csv_bytes(unmapped, UNMAPPED_COLUMNS))
        (temp / "feature_stream_history.csv").write_bytes(csv_bytes(stream_history, STREAM_HISTORY_COLUMNS))
        (temp / "cell_period_coverage.csv").write_bytes(csv_bytes(cell_period_coverage, CELL_PERIOD_COLUMNS))
        (temp / "feature_concordance.csv").write_bytes(csv_bytes(concordance, CONCORDANCE_COLUMNS))
        (temp / "cell_research_diagnostics.csv").write_bytes(csv_bytes(cell_diagnostics, CELL_DIAGNOSTIC_COLUMNS))
        (temp / "feature_availability_profile.csv").write_bytes(csv_bytes(availability_profiles, AVAILABILITY_PROFILE_COLUMNS))
        (temp / "cell_provenance_concentration.csv").write_bytes(csv_bytes(provenance_concentration, PROVENANCE_CONCENTRATION_COLUMNS))
        (temp / "cell_research_risk_flags.csv").write_bytes(csv_bytes(risk_flags, RISK_FLAG_COLUMNS))
        summary = {
            "schema_version": "1.0",
            "contract_version": CONTRACT_VERSION,
            "status": FEATURE_PANEL_STATUS,
            "cutoff": cutoff,
            "upstream_information_set_manifest_sha256": sha256_file(information_set_dir / "MANIFEST.sha256"),
            "feature_mapping_policy_sha256": policy_hash(policy_path),
            "research_core_basket_sha256": sha256_file(basket_path),
            "output_decimal_places": int(policy["transformation_policy"]["output_decimal_places"]),
            "diagnostic_long_history_min_complete_periods": int(policy["diagnostic_policy"]["long_history_min_complete_periods"]),
            "diagnostic_multi_source_min_complete_periods": int(policy["diagnostic_policy"]["multi_source_min_complete_periods"]),
            "diagnostic_concordance_min_overlap_periods": int(policy["diagnostic_policy"]["concordance_min_overlap_periods"]),
            "diagnostic_concordance_complete_periods_only": bool(policy["diagnostic_policy"]["concordance_complete_periods_only"]),
            "diagnostic_availability_lag_days": int(policy["diagnostic_policy"]["availability_lag_diagnostic_days"]),
            "diagnostic_provenance_concentration_percent": int(policy["diagnostic_policy"]["provenance_concentration_diagnostic_percent"]),
            "input_observation_count": len(panel_rows),
            "mapped_input_observation_count": sum(int(row["matched_input_observation_count"]) for row in mapping_audit),
            "unmapped_input_observation_count": sum(int(row["observation_count"]) for row in unmapped),
            "feature_value_count": len(features),
            "level_feature_count": sum(row["transformation"] == "LEVEL" for row in features),
            "period_change_feature_count": sum(row["transformation"] == "PERIOD_CHANGE_PCT" for row in features),
            "year_over_year_feature_count": sum(row["transformation"] == "YEAR_OVER_YEAR_PCT" for row in features),
            "primary_feature_value_count": sum(row["feature_role"] == "PRIMARY_RESEARCH_DRIVER" for row in features),
            "sensitivity_feature_value_count": sum(row["feature_role"] == "SENSITIVITY_ONLY" for row in features),
            "mapping_rule_count": len(mapping_audit),
            "mapping_rule_with_matches_count": sum(int(row["matched_input_observation_count"]) > 0 for row in mapping_audit),
            "unmapped_group_count": len(unmapped),
            "feature_stream_count": len(stream_history),
            "feature_stream_with_long_history_count": sum(
                row["research_diagnostic_status"] in {
                    "LONG_CONTIGUOUS_HISTORY_WITH_CHANGES",
                    "LONG_HISTORY_WITH_GAPS_OR_NO_CHANGES",
                }
                for row in stream_history
            ),
            "cell_period_coverage_row_count": len(cell_period_coverage),
            "cell_period_with_complete_primary_count": sum(
                row["period_status"] in {
                    "PRIMARY_COMPLETE_FROM_CURRENT_SOURCE",
                    "PRIMARY_COMPLETE_FROM_STALE_SOURCE",
                }
                for row in cell_period_coverage
            ),
            "concordance_pair_count": len(concordance),
            "concordance_pair_with_sufficient_overlap_count": sum(
                row["concordance_status"] != "INSUFFICIENT_OVERLAP" for row in concordance
            ),
            "cell_research_diagnostic_count": len(cell_diagnostics),
            "availability_profile_count": len(availability_profiles),
            "availability_profile_with_negative_lag_count": sum(
                int(row["negative_first_seen_lag_count"]) > 0 for row in availability_profiles
            ),
            "availability_profile_beyond_diagnostic_window_count": sum(
                int(row["beyond_diagnostic_window_count"]) > 0 for row in availability_profiles
            ),
            "provenance_concentration_cell_count": len(provenance_concentration),
            "single_source_dependency_cell_count": sum(
                row["single_source_dependency"] == "true" for row in provenance_concentration
            ),
            "dominant_source_concentration_cell_count": sum(
                row["dominant_source_above_diagnostic_threshold"] == "true" for row in provenance_concentration
            ),
            "research_risk_flag_cell_count": len(risk_flags),
            "cell_with_descriptive_risk_flags_count": sum(
                int(row["descriptive_flag_count"]) > 0 for row in risk_flags
            ),
            "long_history_cell_count": sum(
                row["diagnostic_class"] in {
                    "PRIMARY_LONG_HISTORY",
                    "PRIMARY_LONG_MULTI_SOURCE_HISTORY",
                }
                for row in cell_diagnostics
            ),
            "multi_source_long_history_cell_count": sum(
                row["diagnostic_class"] == "PRIMARY_LONG_MULTI_SOURCE_HISTORY" for row in cell_diagnostics
            ),
            "research_core_cell_count": len(coverage),
            "primary_source_current_cell_count": sum(row["coverage_status"] == "PRIMARY_FEATURE_FROM_CURRENT_SOURCE" for row in coverage),
            "primary_source_stale_cell_count": sum(row["coverage_status"] == "PRIMARY_FEATURE_FROM_STALE_SOURCE" for row in coverage),
            "sensitivity_only_cell_count": sum(row["coverage_status"] == "SENSITIVITY_ONLY" for row in coverage),
            "no_mapped_feature_cell_count": sum(row["coverage_status"] == "NO_MAPPED_FEATURE" for row in coverage),
            "primary_any_weight_coverage": _coverage_weight(
                coverage,
                {"PRIMARY_FEATURE_FROM_CURRENT_SOURCE", "PRIMARY_FEATURE_FROM_STALE_SOURCE"},
            ),
            "primary_source_current_weight_coverage": _coverage_weight(coverage, {"PRIMARY_FEATURE_FROM_CURRENT_SOURCE"}),
            "primary_source_stale_weight_coverage": _coverage_weight(coverage, {"PRIMARY_FEATURE_FROM_STALE_SOURCE"}),
            "sensitivity_only_weight_coverage": _coverage_weight(coverage, {"SENSITIVITY_ONLY"}),
            "direct_index_use_allowed": False,
            "arm_l_use_allowed": False,
            "model_training_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
            "price_coverage_claim_allowed": False,
            "model_ready_claim_allowed": False,
            "backtest_eligibility_claim_allowed": False,
            "concordance_approval_claim_allowed": False,
        }
        (temp / "feature_summary.json").write_bytes(canonical_json_bytes(summary))
        names = [
            "feature_values.csv",
            "cell_coverage.csv",
            "mapping_audit.csv",
            "unmapped_observations.csv",
            "feature_stream_history.csv",
            "cell_period_coverage.csv",
            "feature_concordance.csv",
            "cell_research_diagnostics.csv",
            "feature_availability_profile.csv",
            "cell_provenance_concentration.csv",
            "cell_research_risk_flags.csv",
            "feature_summary.json",
        ]
        write_manifest(temp, names)
        verify_feature_bundle(temp)
        return _finalise_directory(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _split_ids(value: str) -> list[str]:
    if not value:
        return []
    items = value.split("|")
    if any(not item for item in items) or items != sorted(set(items)):
        raise ProxyFeatureError("coverage source ids must be sorted and unique")
    return items


def verify_feature_bundle(path: Path) -> dict[str, Any]:
    entries = _manifest_entries(path)
    required = {
        "feature_values.csv",
        "cell_coverage.csv",
        "mapping_audit.csv",
        "unmapped_observations.csv",
        "feature_stream_history.csv",
        "cell_period_coverage.csv",
        "feature_concordance.csv",
        "cell_research_diagnostics.csv",
        "feature_availability_profile.csv",
        "cell_provenance_concentration.csv",
        "cell_research_risk_flags.csv",
        "feature_summary.json",
    }
    if set(entries) != required:
        raise ProxyFeatureError("feature bundle file set does not match v0.9.9")
    try:
        summary = json.loads((path / "feature_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxyFeatureError("invalid feature summary") from exc
    if summary.get("schema_version") != "1.0":
        raise ProxyFeatureError("feature summary schema version mismatch")
    if summary.get("status") != FEATURE_PANEL_STATUS or summary.get("contract_version") != CONTRACT_VERSION:
        raise ProxyFeatureError("feature summary status/version mismatch")
    for digest_key in (
        "upstream_information_set_manifest_sha256",
        "feature_mapping_policy_sha256",
        "research_core_basket_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(summary.get(digest_key, ""))):
            raise ProxyFeatureError(f"invalid summary digest: {digest_key}")
    for gate in FALSE_GATES:
        if summary.get(gate) is not False:
            raise ProxyFeatureError(f"feature summary gate opened: {gate}")

    features = read_csv(path / "feature_values.csv")
    coverage = read_csv(path / "cell_coverage.csv")
    mapping_audit = read_csv(path / "mapping_audit.csv")
    unmapped = read_csv(path / "unmapped_observations.csv")
    stream_history = read_csv(path / "feature_stream_history.csv")
    cell_period_coverage = read_csv(path / "cell_period_coverage.csv")
    concordance = read_csv(path / "feature_concordance.csv")
    cell_diagnostics = read_csv(path / "cell_research_diagnostics.csv")
    availability_profiles = read_csv(path / "feature_availability_profile.csv")
    provenance_concentration = read_csv(path / "cell_provenance_concentration.csv")
    risk_flags = read_csv(path / "cell_research_risk_flags.csv")
    if not features:
        raise ProxyFeatureError("feature bundle contains no features")
    if len(features) != summary.get("feature_value_count"):
        raise ProxyFeatureError("feature row count mismatch")
    if len(coverage) != summary.get("research_core_cell_count") or len(coverage) != 60:
        raise ProxyFeatureError("feature coverage must contain exactly 60 Research Core cells")
    if len(mapping_audit) != summary.get("mapping_rule_count"):
        raise ProxyFeatureError("mapping audit count mismatch")
    if len(unmapped) != summary.get("unmapped_group_count"):
        raise ProxyFeatureError("unmapped audit count mismatch")
    if len(stream_history) != summary.get("feature_stream_count"):
        raise ProxyFeatureError("feature stream history count mismatch")
    if len(cell_period_coverage) != summary.get("cell_period_coverage_row_count"):
        raise ProxyFeatureError("cell-period coverage count mismatch")
    if len(concordance) != summary.get("concordance_pair_count"):
        raise ProxyFeatureError("feature concordance count mismatch")
    if len(cell_diagnostics) != summary.get("cell_research_diagnostic_count") or len(cell_diagnostics) != 60:
        raise ProxyFeatureError("cell research diagnostics must contain exactly 60 rows")
    if len(availability_profiles) != summary.get("availability_profile_count"):
        raise ProxyFeatureError("feature availability profile count mismatch")
    if len(provenance_concentration) != summary.get("provenance_concentration_cell_count") or len(provenance_concentration) != 60:
        raise ProxyFeatureError("provenance concentration must contain exactly 60 rows")
    if len(risk_flags) != summary.get("research_risk_flag_cell_count") or len(risk_flags) != 60:
        raise ProxyFeatureError("research risk flags must contain exactly 60 rows")

    cutoff = parse_utc(summary["cutoff"])
    feature_ids: set[str] = set()
    identities: set[tuple[str, ...]] = set()
    level_by_cell: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    transformation_counts = {"LEVEL": 0, "PERIOD_CHANGE_PCT": 0, "YEAR_OVER_YEAR_PCT": 0}
    role_counts = {"PRIMARY_RESEARCH_DRIVER": 0, "SENSITIVITY_ONLY": 0}
    for row in features:
        if set(row) != set(FEATURE_COLUMNS):
            raise ProxyFeatureError("feature CSV columns changed")
        if row["feature_id"] != feature_id(row):
            raise ProxyFeatureError("feature_id does not match canonical identity")
        if row["feature_id"] in feature_ids:
            raise ProxyFeatureError("duplicate feature_id")
        feature_ids.add(row["feature_id"])
        identity = tuple(row[column] for column in (
            "mapping_id", "source_id", "series_id", "source_geography",
            "target_economy_code", "target_category_code", "target_period",
            "transformation", "unit",
        ))
        if identity in identities:
            raise ProxyFeatureError("duplicate feature identity")
        identities.add(identity)
        if parse_utc(row["latest_available_at"]) > cutoff:
            raise ProxyFeatureError("feature contains data observed after cutoff")
        if row["target_frequency"] != "MONTHLY":
            raise ProxyFeatureError("feature target frequency changed")
        if not target_month_not_after_cutoff(row["target_period"], summary["cutoff"]):
            raise ProxyFeatureError("feature target period is after cutoff")
        expected_end, expected_age, expected_completeness = target_period_metadata(row["target_period"], summary["cutoff"])
        if row["target_period_end"] != expected_end:
            raise ProxyFeatureError("feature target period end does not reconcile")
        if int(row["feature_age_days"]) != expected_age:
            raise ProxyFeatureError("feature age does not reconcile")
        if row["period_completeness_status"] != expected_completeness:
            raise ProxyFeatureError("feature period completeness does not reconcile")
        transformation = row["transformation"]
        role = row["feature_role"]
        if transformation not in transformation_counts:
            raise ProxyFeatureError("invalid feature transformation")
        if role not in role_counts:
            raise ProxyFeatureError("invalid feature role")
        transformation_counts[transformation] += 1
        role_counts[role] += 1
        if row["source_freshness_status"] not in {
            "CURRENT_WITHIN_EXPECTED_WINDOW", "STALE_BEYOND_EXPECTED_WINDOW"
        }:
            raise ProxyFeatureError("invalid mapped source freshness status")
        for gate in ("direct_index_use_allowed", "arm_l_use_allowed", "model_training_allowed"):
            if row.get(gate) != "false":
                raise ProxyFeatureError(f"feature row gate opened: {gate}")
        decimal_value(row["value"])
        if int(row["component_count"]) < 1 or not re.fullmatch(r"[0-9a-f]{64}", row["component_observation_keys_sha256"]):
            raise ProxyFeatureError("feature component provenance is invalid")
        if transformation == "LEVEL":
            level_by_cell[(row["target_economy_code"], row["target_category_code"])].append(row)

    cell_ids: set[tuple[str, str]] = set()
    weight_total = Decimal(0)
    allowed_statuses = {
        "PRIMARY_FEATURE_FROM_CURRENT_SOURCE",
        "PRIMARY_FEATURE_FROM_STALE_SOURCE",
        "SENSITIVITY_ONLY",
        "NO_MAPPED_FEATURE",
    }
    for row in coverage:
        if set(row) != set(CELL_COVERAGE_COLUMNS):
            raise ProxyFeatureError("coverage CSV columns changed")
        identity = (row["economy_code"], row["category_code"])
        if identity in cell_ids:
            raise ProxyFeatureError("duplicate feature coverage cell")
        cell_ids.add(identity)
        weight_total += decimal_value(row["fixed_universe_weight"])
        if row["coverage_status"] not in allowed_statuses:
            raise ProxyFeatureError("invalid feature coverage status")
        if row["price_coverage_claim_allowed"] != "false":
            raise ProxyFeatureError("price coverage claim opened")

        level_rows = level_by_cell.get(identity, [])
        primary_rows = [item for item in level_rows if item["feature_role"] == "PRIMARY_RESEARCH_DRIVER"]
        sensitivity_rows = [item for item in level_rows if item["feature_role"] == "SENSITIVITY_ONLY"]
        primary_streams = {_stream_identity(item) for item in primary_rows}
        sensitivity_streams = {_stream_identity(item) for item in sensitivity_rows}
        current_sources = sorted({
            item["source_id"] for item in primary_rows
            if item["source_freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW"
        })
        stale_sources = sorted({
            item["source_id"] for item in primary_rows
            if item["source_freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW"
        })
        primary_sources = sorted({item["source_id"] for item in primary_rows})
        sensitivity_sources = sorted({item["source_id"] for item in sensitivity_rows})
        primary_periods = sorted({item["target_period"] for item in primary_rows})
        sensitivity_periods = sorted({item["target_period"] for item in sensitivity_rows})
        ages = [int(item["feature_age_days"]) for item in primary_rows]
        expected_values = {
            "primary_feature_count": str(len(primary_streams)),
            "sensitivity_feature_count": str(len(sensitivity_streams)),
            "current_primary_source_count": str(len(current_sources)),
            "stale_primary_source_count": str(len(stale_sources)),
            "primary_source_ids": "|".join(primary_sources),
            "sensitivity_source_ids": "|".join(sensitivity_sources),
            "latest_primary_target_period": primary_periods[-1] if primary_periods else "",
            "latest_sensitivity_target_period": sensitivity_periods[-1] if sensitivity_periods else "",
            "minimum_primary_feature_age_days": str(min(ages)) if ages else "",
            "maximum_primary_feature_age_days": str(max(ages)) if ages else "",
        }
        for key, expected in expected_values.items():
            if row[key] != expected:
                raise ProxyFeatureError(f"coverage field does not reconcile: {identity}:{key}")
        _split_ids(row["primary_source_ids"])
        _split_ids(row["sensitivity_source_ids"])
        expected_status = (
            "PRIMARY_FEATURE_FROM_CURRENT_SOURCE" if current_sources
            else "PRIMARY_FEATURE_FROM_STALE_SOURCE" if stale_sources
            else "SENSITIVITY_ONLY" if sensitivity_streams
            else "NO_MAPPED_FEATURE"
        )
        if row["coverage_status"] != expected_status:
            raise ProxyFeatureError("feature coverage status does not reconcile")
    if weight_total != Decimal(1):
        raise ProxyFeatureError(f"feature coverage weights sum to {weight_total}, expected exactly 1")

    mapping_ids: set[str] = set()
    mapped_count = 0
    mapping_with_matches = 0
    for row in mapping_audit:
        if set(row) != set(MAPPING_AUDIT_COLUMNS):
            raise ProxyFeatureError("mapping audit CSV columns changed")
        if row["mapping_id"] in mapping_ids:
            raise ProxyFeatureError("duplicate mapping audit mapping_id")
        mapping_ids.add(row["mapping_id"])
        matched = int(row["matched_input_observation_count"])
        targets = int(row["mapped_target_observation_count"])
        if min(matched, targets, int(row["distinct_source_geography_count"])) < 0:
            raise ProxyFeatureError("negative mapping audit count")
        if matched == 0 and (row["first_source_period"] or row["last_source_period"] or targets):
            raise ProxyFeatureError("unmatched mapping audit contains match metadata")
        if matched > 0:
            if not row["first_source_period"] or not row["last_source_period"]:
                raise ProxyFeatureError("matched mapping audit lacks period bounds")
            mapping_with_matches += 1
        mapped_count += matched

    allowed_unmapped_reasons = {
        "UNMAPPED_SERIES", "PROXY_DOMAIN_MISMATCH", "FREQUENCY_MISMATCH",
        "UNRESOLVED_GEOGRAPHY", "OUTSIDE_RESEARCH_CORE",
    }
    unmapped_count = 0
    unmapped_keys: set[tuple[str, ...]] = set()
    for row in unmapped:
        if set(row) != set(UNMAPPED_COLUMNS):
            raise ProxyFeatureError("unmapped audit CSV columns changed")
        key = tuple(row[column] for column in UNMAPPED_COLUMNS[:-1])
        if key in unmapped_keys:
            raise ProxyFeatureError("duplicate unmapped audit group")
        unmapped_keys.add(key)
        if row["reason"] not in allowed_unmapped_reasons:
            raise ProxyFeatureError("invalid unmapped audit reason")
        count = int(row["observation_count"])
        if count < 1:
            raise ProxyFeatureError("unmapped observation count must be positive")
        unmapped_count += count

    expected_counts = {
        "input_observation_count": mapped_count + unmapped_count,
        "mapped_input_observation_count": mapped_count,
        "unmapped_input_observation_count": unmapped_count,
        "feature_value_count": len(features),
        "level_feature_count": transformation_counts["LEVEL"],
        "period_change_feature_count": transformation_counts["PERIOD_CHANGE_PCT"],
        "year_over_year_feature_count": transformation_counts["YEAR_OVER_YEAR_PCT"],
        "primary_feature_value_count": role_counts["PRIMARY_RESEARCH_DRIVER"],
        "sensitivity_feature_value_count": role_counts["SENSITIVITY_ONLY"],
        "mapping_rule_count": len(mapping_audit),
        "mapping_rule_with_matches_count": mapping_with_matches,
        "unmapped_group_count": len(unmapped),
        "research_core_cell_count": len(coverage),
        "primary_source_current_cell_count": sum(row["coverage_status"] == "PRIMARY_FEATURE_FROM_CURRENT_SOURCE" for row in coverage),
        "primary_source_stale_cell_count": sum(row["coverage_status"] == "PRIMARY_FEATURE_FROM_STALE_SOURCE" for row in coverage),
        "sensitivity_only_cell_count": sum(row["coverage_status"] == "SENSITIVITY_ONLY" for row in coverage),
        "no_mapped_feature_cell_count": sum(row["coverage_status"] == "NO_MAPPED_FEATURE" for row in coverage),
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise ProxyFeatureError(f"feature summary count mismatch: {key}")
    if summary["primary_feature_value_count"] + summary["sensitivity_feature_value_count"] != len(features):
        raise ProxyFeatureError("feature role counts do not sum to total")
    if sum(summary[key] for key in (
        "primary_source_current_cell_count", "primary_source_stale_cell_count",
        "sensitivity_only_cell_count", "no_mapped_feature_cell_count",
    )) != 60:
        raise ProxyFeatureError("coverage status counts do not sum to 60")
    expected_weights = {
        "primary_any_weight_coverage": _coverage_weight(
            coverage, {"PRIMARY_FEATURE_FROM_CURRENT_SOURCE", "PRIMARY_FEATURE_FROM_STALE_SOURCE"}
        ),
        "primary_source_current_weight_coverage": _coverage_weight(coverage, {"PRIMARY_FEATURE_FROM_CURRENT_SOURCE"}),
        "primary_source_stale_weight_coverage": _coverage_weight(coverage, {"PRIMARY_FEATURE_FROM_STALE_SOURCE"}),
        "sensitivity_only_weight_coverage": _coverage_weight(coverage, {"SENSITIVITY_ONLY"}),
    }
    for key, value in expected_weights.items():
        if summary.get(key) != value:
            raise ProxyFeatureError(f"feature summary weight mismatch: {key}")

    diagnostic_policy = {
        "diagnostic_policy": {
            "long_history_min_complete_periods": int(summary.get("diagnostic_long_history_min_complete_periods", 0)),
            "multi_source_min_complete_periods": int(summary.get("diagnostic_multi_source_min_complete_periods", 0)),
            "concordance_min_overlap_periods": int(summary.get("diagnostic_concordance_min_overlap_periods", 0)),
            "concordance_complete_periods_only": summary.get("diagnostic_concordance_complete_periods_only"),
            "availability_lag_diagnostic_days": int(summary.get("diagnostic_availability_lag_days", 0)),
            "provenance_concentration_diagnostic_percent": int(summary.get("diagnostic_provenance_concentration_percent", 0)),
        },
        "transformation_policy": {
            "output_decimal_places": int(summary.get("output_decimal_places", 0)),
        },
    }
    if diagnostic_policy["diagnostic_policy"]["concordance_complete_periods_only"] is not True:
        raise ProxyFeatureError("feature summary diagnostic policy changed")
    if not 1 <= diagnostic_policy["diagnostic_policy"]["availability_lag_diagnostic_days"] <= 3650:
        raise ProxyFeatureError("feature summary availability lag threshold changed")
    if not 50 <= diagnostic_policy["diagnostic_policy"]["provenance_concentration_diagnostic_percent"] <= 100:
        raise ProxyFeatureError("feature summary provenance concentration threshold changed")
    basket_rows = [
        {
            "economy_code": row["economy_code"],
            "economy_name": row["economy_name"],
            "category_code": row["category_code"],
            "fixed_universe_weight": row["fixed_universe_weight"],
        }
        for row in coverage
    ]
    expected_stream_history = _build_stream_history(features, diagnostic_policy)
    expected_cell_period = _build_cell_period_coverage(features, basket_rows)
    expected_concordance = _build_concordance(features, diagnostic_policy)
    expected_cell_diagnostics = _build_cell_diagnostics(features, expected_cell_period, basket_rows, diagnostic_policy)
    expected_availability_profiles = build_availability_profiles(
        features,
        lag_diagnostic_days=diagnostic_policy["diagnostic_policy"]["availability_lag_diagnostic_days"],
    )
    expected_provenance_concentration = build_provenance_concentration(
        features,
        coverage,
        places=diagnostic_policy["transformation_policy"]["output_decimal_places"],
        dominant_source_percent=diagnostic_policy["diagnostic_policy"]["provenance_concentration_diagnostic_percent"],
    )
    expected_risk_flags = build_cell_risk_flags(
        coverage_rows=coverage,
        stream_history_rows=expected_stream_history,
        cell_diagnostic_rows=expected_cell_diagnostics,
        availability_rows=expected_availability_profiles,
        provenance_rows=expected_provenance_concentration,
    )
    comparisons = (
        (stream_history, expected_stream_history, STREAM_HISTORY_COLUMNS, "feature stream history"),
        (cell_period_coverage, expected_cell_period, CELL_PERIOD_COLUMNS, "cell-period coverage"),
        (concordance, expected_concordance, CONCORDANCE_COLUMNS, "feature concordance"),
        (cell_diagnostics, expected_cell_diagnostics, CELL_DIAGNOSTIC_COLUMNS, "cell research diagnostics"),
        (availability_profiles, expected_availability_profiles, AVAILABILITY_PROFILE_COLUMNS, "feature availability profiles"),
        (provenance_concentration, expected_provenance_concentration, PROVENANCE_CONCENTRATION_COLUMNS, "cell provenance concentration"),
        (risk_flags, expected_risk_flags, RISK_FLAG_COLUMNS, "cell research risk flags"),
    )
    for actual_rows, expected_rows, columns, label in comparisons:
        if csv_bytes(actual_rows, columns) != csv_bytes(expected_rows, columns):
            raise ProxyFeatureError(f"{label} does not reconcile with canonical feature rows")

    extended_counts = {
        "availability_profile_with_negative_lag_count": sum(
            int(row["negative_first_seen_lag_count"]) > 0 for row in expected_availability_profiles
        ),
        "availability_profile_beyond_diagnostic_window_count": sum(
            int(row["beyond_diagnostic_window_count"]) > 0 for row in expected_availability_profiles
        ),
        "single_source_dependency_cell_count": sum(
            row["single_source_dependency"] == "true" for row in expected_provenance_concentration
        ),
        "dominant_source_concentration_cell_count": sum(
            row["dominant_source_above_diagnostic_threshold"] == "true" for row in expected_provenance_concentration
        ),
        "cell_with_descriptive_risk_flags_count": sum(
            int(row["descriptive_flag_count"]) > 0 for row in expected_risk_flags
        ),
        "feature_stream_with_long_history_count": sum(
            row["research_diagnostic_status"] in {
                "LONG_CONTIGUOUS_HISTORY_WITH_CHANGES",
                "LONG_HISTORY_WITH_GAPS_OR_NO_CHANGES",
            }
            for row in expected_stream_history
        ),
        "cell_period_with_complete_primary_count": sum(
            row["period_status"] in {
                "PRIMARY_COMPLETE_FROM_CURRENT_SOURCE",
                "PRIMARY_COMPLETE_FROM_STALE_SOURCE",
            }
            for row in expected_cell_period
        ),
        "concordance_pair_with_sufficient_overlap_count": sum(
            row["concordance_status"] != "INSUFFICIENT_OVERLAP" for row in expected_concordance
        ),
        "long_history_cell_count": sum(
            row["diagnostic_class"] in {
                "PRIMARY_LONG_HISTORY",
                "PRIMARY_LONG_MULTI_SOURCE_HISTORY",
            }
            for row in expected_cell_diagnostics
        ),
        "multi_source_long_history_cell_count": sum(
            row["diagnostic_class"] == "PRIMARY_LONG_MULTI_SOURCE_HISTORY" for row in expected_cell_diagnostics
        ),
    }
    for key, expected in extended_counts.items():
        if summary.get(key) != expected:
            raise ProxyFeatureError(f"feature summary extended diagnostic mismatch: {key}")
    return summary

