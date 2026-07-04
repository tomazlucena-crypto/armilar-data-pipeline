"""Deterministic comparison of ARMILAR v0.9.9 point-in-time feature bundles."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .archive_core_v098 import parse_utc
from .core_v097 import canonical_json_bytes, sha256_bytes, sha256_file
from .feature_builder_v099 import verify_feature_bundle
from .feature_core_v099 import ProxyFeatureError, csv_bytes, decimal_text, decimal_value, read_csv, write_manifest
from .feature_stability_v099 import (
    CELL_REVISION_STABILITY_COLUMNS,
    STREAM_REVISION_STABILITY_COLUMNS,
    build_cell_revision_stability,
    build_stream_revision_stability,
)

FEATURE_COMPARISON_STATUS = "POINT_IN_TIME_PROXY_FEATURE_COMPARISON_V099_VALID"

FEATURE_DELTA_COLUMNS = [
    "comparison_key_sha256",
    "delta_status",
    "mapping_id",
    "source_id",
    "series_id",
    "source_geography",
    "target_economy_code",
    "target_category_code",
    "target_period",
    "transformation",
    "unit",
    "earlier_feature_id",
    "later_feature_id",
    "earlier_value",
    "later_value",
    "value_delta",
    "earlier_component_observation_keys_sha256",
    "later_component_observation_keys_sha256",
    "earlier_latest_available_at",
    "later_latest_available_at",
    "earlier_source_freshness_status",
    "later_source_freshness_status",
    "earlier_period_completeness_status",
    "later_period_completeness_status",
    "earlier_feature_age_days",
    "later_feature_age_days",
]

COVERAGE_DELTA_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "earlier_coverage_status",
    "later_coverage_status",
    "earlier_primary_feature_count",
    "later_primary_feature_count",
    "primary_feature_count_delta",
    "earlier_latest_primary_target_period",
    "later_latest_primary_target_period",
    "coverage_status_changed",
]

FALSE_COMPARISON_GATES = (
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
    "shadow_production_allowed",
    "monetary_use_allowed",
    "price_coverage_claim_allowed",
    "model_ready_claim_allowed",
    "backtest_eligibility_claim_allowed",
    "comparison_decision_use_allowed",
)


def _feature_key(row: Mapping[str, str]) -> tuple[str, ...]:
    columns = (
        "mapping_id",
        "source_id",
        "series_id",
        "source_geography",
        "target_economy_code",
        "target_category_code",
        "target_period",
        "transformation",
        "unit",
    )
    values = tuple(str(row.get(column, "")).strip() for column in columns)
    if any(not value for value in values):
        raise ProxyFeatureError("comparison feature identity contains an empty field")
    return values


def _key_hash(key: tuple[str, ...]) -> str:
    return sha256_bytes(canonical_json_bytes(list(key)))


def _atomic_directory(target: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if target.exists():
        raise ProxyFeatureError(f"comparison output directory already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target, Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))


def _finalise(temp: Path, target: Path) -> Path:
    temp.replace(target)
    try:
        fd = os.open(str(target.parent), os.O_RDONLY)
    except OSError:
        return target
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
    return target


def _feature_map(path: Path) -> dict[tuple[str, ...], dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in read_csv(path / "feature_values.csv"):
        key = _feature_key(row)
        if key in result:
            raise ProxyFeatureError(f"duplicate feature comparison identity: {key}")
        result[key] = row
    return result


def _feature_deltas(earlier: Path, later: Path, places: int) -> list[dict[str, Any]]:
    left = _feature_map(earlier)
    right = _feature_map(later)
    output: list[dict[str, Any]] = []
    for key in sorted(set(left) | set(right)):
        old = left.get(key)
        new = right.get(key)
        if old is None:
            status = "ADDED"
        elif new is None:
            status = "REMOVED"
        elif old["value"] != new["value"]:
            status = "VALUE_CHANGED"
        elif old["component_observation_keys_sha256"] != new["component_observation_keys_sha256"]:
            status = "PROVENANCE_CHANGED"
        elif (
            old["latest_available_at"] != new["latest_available_at"]
            or old["source_freshness_status"] != new["source_freshness_status"]
            or old["period_completeness_status"] != new["period_completeness_status"]
        ):
            status = "METADATA_CHANGED"
        else:
            status = "UNCHANGED"
        delta = ""
        if old is not None and new is not None:
            delta = decimal_text(decimal_value(new["value"]) - decimal_value(old["value"]), places)
        mapping_id, source_id, series_id, geography, economy, category, period, transformation, unit = key
        output.append({
            "comparison_key_sha256": _key_hash(key),
            "delta_status": status,
            "mapping_id": mapping_id,
            "source_id": source_id,
            "series_id": series_id,
            "source_geography": geography,
            "target_economy_code": economy,
            "target_category_code": category,
            "target_period": period,
            "transformation": transformation,
            "unit": unit,
            "earlier_feature_id": old["feature_id"] if old else "",
            "later_feature_id": new["feature_id"] if new else "",
            "earlier_value": old["value"] if old else "",
            "later_value": new["value"] if new else "",
            "value_delta": delta,
            "earlier_component_observation_keys_sha256": old["component_observation_keys_sha256"] if old else "",
            "later_component_observation_keys_sha256": new["component_observation_keys_sha256"] if new else "",
            "earlier_latest_available_at": old["latest_available_at"] if old else "",
            "later_latest_available_at": new["latest_available_at"] if new else "",
            "earlier_source_freshness_status": old["source_freshness_status"] if old else "",
            "later_source_freshness_status": new["source_freshness_status"] if new else "",
            "earlier_period_completeness_status": old["period_completeness_status"] if old else "",
            "later_period_completeness_status": new["period_completeness_status"] if new else "",
            "earlier_feature_age_days": old["feature_age_days"] if old else "",
            "later_feature_age_days": new["feature_age_days"] if new else "",
        })
    return output


def _coverage_map(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv(path / "cell_coverage.csv"):
        key = (row["economy_code"], row["category_code"])
        if key in result:
            raise ProxyFeatureError(f"duplicate coverage comparison identity: {key}")
        result[key] = row
    return result


def _coverage_deltas(earlier: Path, later: Path) -> list[dict[str, Any]]:
    left = _coverage_map(earlier)
    right = _coverage_map(later)
    if set(left) != set(right):
        raise ProxyFeatureError("feature bundle Research Core cells differ across comparison")
    output: list[dict[str, Any]] = []
    for key in sorted(left):
        old = left[key]
        new = right[key]
        if old["economy_name"] != new["economy_name"] or old["fixed_universe_weight"] != new["fixed_universe_weight"]:
            raise ProxyFeatureError(f"Research Core metadata changed across comparison: {key}")
        old_count = int(old["primary_feature_count"])
        new_count = int(new["primary_feature_count"])
        output.append({
            "economy_code": key[0],
            "economy_name": old["economy_name"],
            "category_code": key[1],
            "fixed_universe_weight": old["fixed_universe_weight"],
            "earlier_coverage_status": old["coverage_status"],
            "later_coverage_status": new["coverage_status"],
            "earlier_primary_feature_count": old_count,
            "later_primary_feature_count": new_count,
            "primary_feature_count_delta": new_count - old_count,
            "earlier_latest_primary_target_period": old["latest_primary_target_period"],
            "later_latest_primary_target_period": new["latest_primary_target_period"],
            "coverage_status_changed": "true" if old["coverage_status"] != new["coverage_status"] else "false",
        })
    return output


def build_feature_comparison(*, earlier_feature_dir: Path, later_feature_dir: Path, output_dir: Path) -> Path:
    earlier_summary = verify_feature_bundle(earlier_feature_dir)
    later_summary = verify_feature_bundle(later_feature_dir)
    if parse_utc(earlier_summary["cutoff"]) >= parse_utc(later_summary["cutoff"]):
        raise ProxyFeatureError("feature comparison requires an earlier and a later cutoff")
    for key in ("feature_mapping_policy_sha256", "research_core_basket_sha256"):
        if earlier_summary[key] != later_summary[key]:
            raise ProxyFeatureError(f"feature comparison contract changed: {key}")
    places = int(later_summary["output_decimal_places"])
    feature_deltas = _feature_deltas(earlier_feature_dir, later_feature_dir, places)
    coverage_deltas = _coverage_deltas(earlier_feature_dir, later_feature_dir)
    stream_revision_stability = build_stream_revision_stability(feature_deltas, places=places)
    cell_revision_stability = build_cell_revision_stability(
        feature_deltas,
        coverage_deltas,
        stream_revision_stability,
    )
    target, temp = _atomic_directory(output_dir)
    try:
        (temp / "feature_deltas.csv").write_bytes(csv_bytes(feature_deltas, FEATURE_DELTA_COLUMNS))
        (temp / "cell_coverage_deltas.csv").write_bytes(csv_bytes(coverage_deltas, COVERAGE_DELTA_COLUMNS))
        (temp / "stream_revision_stability.csv").write_bytes(csv_bytes(stream_revision_stability, STREAM_REVISION_STABILITY_COLUMNS))
        (temp / "cell_revision_stability.csv").write_bytes(csv_bytes(cell_revision_stability, CELL_REVISION_STABILITY_COLUMNS))
        summary = {
            "schema_version": "1.0",
            "contract_version": "0.9.9",
            "status": FEATURE_COMPARISON_STATUS,
            "earlier_cutoff": earlier_summary["cutoff"],
            "later_cutoff": later_summary["cutoff"],
            "earlier_feature_manifest_sha256": sha256_file(earlier_feature_dir / "MANIFEST.sha256"),
            "later_feature_manifest_sha256": sha256_file(later_feature_dir / "MANIFEST.sha256"),
            "feature_mapping_policy_sha256": earlier_summary["feature_mapping_policy_sha256"],
            "research_core_basket_sha256": earlier_summary["research_core_basket_sha256"],
            "output_decimal_places": places,
            "feature_delta_count": len(feature_deltas),
            "added_feature_count": sum(row["delta_status"] == "ADDED" for row in feature_deltas),
            "removed_feature_count": sum(row["delta_status"] == "REMOVED" for row in feature_deltas),
            "value_changed_feature_count": sum(row["delta_status"] == "VALUE_CHANGED" for row in feature_deltas),
            "provenance_changed_feature_count": sum(row["delta_status"] == "PROVENANCE_CHANGED" for row in feature_deltas),
            "metadata_changed_feature_count": sum(row["delta_status"] == "METADATA_CHANGED" for row in feature_deltas),
            "unchanged_feature_count": sum(row["delta_status"] == "UNCHANGED" for row in feature_deltas),
            "coverage_delta_count": len(coverage_deltas),
            "coverage_status_changed_cell_count": sum(row["coverage_status_changed"] == "true" for row in coverage_deltas),
            "stream_revision_stability_count": len(stream_revision_stability),
            "stream_with_value_revisions_count": sum(
                int(row["value_changed_feature_count"]) > 0 for row in stream_revision_stability
            ),
            "cell_revision_stability_count": len(cell_revision_stability),
            "cell_with_value_revisions_count": sum(
                int(row["value_changed_feature_count"]) > 0 for row in cell_revision_stability
            ),
            **{gate: False for gate in FALSE_COMPARISON_GATES},
        }
        (temp / "comparison_summary.json").write_bytes(canonical_json_bytes(summary))
        write_manifest(temp, [
            "feature_deltas.csv",
            "cell_coverage_deltas.csv",
            "stream_revision_stability.csv",
            "cell_revision_stability.csv",
            "comparison_summary.json",
        ])
        verify_feature_comparison_bundle(temp)
        return _finalise(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _manifest_entries(bundle: Path) -> dict[str, str]:
    manifest = bundle / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ProxyFeatureError("feature comparison manifest is missing")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or relative in entries:
            raise ProxyFeatureError("invalid feature comparison manifest")
        path = (bundle / relative).resolve()
        if bundle.resolve() not in path.parents or not path.is_file() or sha256_file(path) != digest:
            raise ProxyFeatureError(f"feature comparison manifest mismatch: {relative}")
        entries[relative] = digest
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"}
    if set(entries) != actual:
        raise ProxyFeatureError("feature comparison manifest file set mismatch")
    return entries


def verify_feature_comparison_bundle(path: Path) -> dict[str, Any]:
    entries = _manifest_entries(path)
    if set(entries) != {
        "feature_deltas.csv",
        "cell_coverage_deltas.csv",
        "stream_revision_stability.csv",
        "cell_revision_stability.csv",
        "comparison_summary.json",
    }:
        raise ProxyFeatureError("feature comparison file set changed")
    try:
        summary = json.loads((path / "comparison_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxyFeatureError("invalid feature comparison summary") from exc
    if summary.get("status") != FEATURE_COMPARISON_STATUS or summary.get("contract_version") != "0.9.9":
        raise ProxyFeatureError("feature comparison status/version mismatch")
    if parse_utc(summary["earlier_cutoff"]) >= parse_utc(summary["later_cutoff"]):
        raise ProxyFeatureError("feature comparison cutoffs are not ordered")
    for key in ("earlier_feature_manifest_sha256", "later_feature_manifest_sha256", "feature_mapping_policy_sha256", "research_core_basket_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(summary.get(key, ""))):
            raise ProxyFeatureError(f"invalid feature comparison digest: {key}")
    for gate in FALSE_COMPARISON_GATES:
        if summary.get(gate) is not False:
            raise ProxyFeatureError(f"feature comparison gate opened: {gate}")
    places = int(summary.get("output_decimal_places", 0))
    if not 6 <= places <= 18:
        raise ProxyFeatureError("invalid feature comparison output decimal places")
    feature_deltas = read_csv(path / "feature_deltas.csv")
    coverage_deltas = read_csv(path / "cell_coverage_deltas.csv")
    stream_revision_stability = read_csv(path / "stream_revision_stability.csv")
    cell_revision_stability = read_csv(path / "cell_revision_stability.csv")
    identities: set[str] = set()
    statuses = {"ADDED", "REMOVED", "VALUE_CHANGED", "PROVENANCE_CHANGED", "METADATA_CHANGED", "UNCHANGED"}
    counts = {status: 0 for status in statuses}
    for row in feature_deltas:
        if set(row) != set(FEATURE_DELTA_COLUMNS):
            raise ProxyFeatureError("feature comparison delta columns changed")
        key = tuple(row[column] for column in FEATURE_DELTA_COLUMNS[2:11])
        if row["comparison_key_sha256"] != _key_hash(key):
            raise ProxyFeatureError("feature comparison key hash mismatch")
        if row["comparison_key_sha256"] in identities:
            raise ProxyFeatureError("duplicate feature comparison key")
        identities.add(row["comparison_key_sha256"])
        status = row["delta_status"]
        if status not in statuses:
            raise ProxyFeatureError("invalid feature delta status")
        counts[status] += 1
        old = row["earlier_value"]
        new = row["later_value"]
        if status == "ADDED" and (old or not new):
            raise ProxyFeatureError("added feature delta is inconsistent")
        if status == "REMOVED" and (not old or new):
            raise ProxyFeatureError("removed feature delta is inconsistent")
        if old and new:
            expected_delta = decimal_text(decimal_value(new) - decimal_value(old), places)
            if row["value_delta"] != expected_delta:
                raise ProxyFeatureError("feature value delta does not reconcile")
    if len(coverage_deltas) != 60:
        raise ProxyFeatureError("feature comparison must include 60 coverage cells")
    coverage_ids: set[tuple[str, str]] = set()
    changed = 0
    for row in coverage_deltas:
        if set(row) != set(COVERAGE_DELTA_COLUMNS):
            raise ProxyFeatureError("coverage comparison columns changed")
        key = (row["economy_code"], row["category_code"])
        if key in coverage_ids:
            raise ProxyFeatureError("duplicate coverage comparison cell")
        coverage_ids.add(key)
        expected_delta = int(row["later_primary_feature_count"]) - int(row["earlier_primary_feature_count"])
        if int(row["primary_feature_count_delta"]) != expected_delta:
            raise ProxyFeatureError("coverage feature count delta does not reconcile")
        expected_changed = "true" if row["earlier_coverage_status"] != row["later_coverage_status"] else "false"
        if row["coverage_status_changed"] != expected_changed:
            raise ProxyFeatureError("coverage status change flag does not reconcile")
        changed += expected_changed == "true"
    expected_stream_revision_stability = build_stream_revision_stability(feature_deltas, places=places)
    expected_cell_revision_stability = build_cell_revision_stability(
        feature_deltas,
        coverage_deltas,
        expected_stream_revision_stability,
    )
    if csv_bytes(stream_revision_stability, STREAM_REVISION_STABILITY_COLUMNS) != csv_bytes(
        expected_stream_revision_stability, STREAM_REVISION_STABILITY_COLUMNS
    ):
        raise ProxyFeatureError("stream revision stability does not reconcile")
    if csv_bytes(cell_revision_stability, CELL_REVISION_STABILITY_COLUMNS) != csv_bytes(
        expected_cell_revision_stability, CELL_REVISION_STABILITY_COLUMNS
    ):
        raise ProxyFeatureError("cell revision stability does not reconcile")

    expected_counts = {
        "feature_delta_count": len(feature_deltas),
        "added_feature_count": counts["ADDED"],
        "removed_feature_count": counts["REMOVED"],
        "value_changed_feature_count": counts["VALUE_CHANGED"],
        "provenance_changed_feature_count": counts["PROVENANCE_CHANGED"],
        "metadata_changed_feature_count": counts["METADATA_CHANGED"],
        "unchanged_feature_count": counts["UNCHANGED"],
        "coverage_delta_count": len(coverage_deltas),
        "coverage_status_changed_cell_count": changed,
        "stream_revision_stability_count": len(expected_stream_revision_stability),
        "stream_with_value_revisions_count": sum(
            int(row["value_changed_feature_count"]) > 0 for row in expected_stream_revision_stability
        ),
        "cell_revision_stability_count": len(expected_cell_revision_stability),
        "cell_with_value_revisions_count": sum(
            int(row["value_changed_feature_count"]) > 0 for row in expected_cell_revision_stability
        ),
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise ProxyFeatureError(f"feature comparison summary mismatch: {key}")
    return summary
