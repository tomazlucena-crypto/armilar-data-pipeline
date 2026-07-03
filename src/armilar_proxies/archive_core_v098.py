"""Closed policy and canonical primitives for ARMILAR v0.9.8 proxy archives."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core_v097 import (
    ProxyRegistryError,
    canonical_json_bytes,
    canonical_text_bytes,
    sha256_bytes,
    sha256_file,
    utc_timestamp,
)

CONTRACT_VERSION = "0.9.8"
ARCHIVE_STATUS = "FIRST_SEEN_PROXY_ARCHIVE_VALID"
INFORMATION_SET_STATUS = "POINT_IN_TIME_RESEARCH_INPUT_ONLY"
FALSE_GATES = (
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
    "shadow_production_allowed",
    "monetary_use_allowed",
)

SNAPSHOT_OBSERVATION_COLUMNS = [
    "source_id",
    "snapshot_id",
    "retrieved_at",
    "observation_key",
    "series_id",
    "proxy_domain",
    "geography",
    "period",
    "frequency",
    "value",
    "unit",
    "source_sha256",
    "registry_sha256",
    "row_locator",
]

VALUE_VERSION_COLUMNS = [
    "observation_key",
    "version_sequence",
    "source_id",
    "series_id",
    "proxy_domain",
    "geography",
    "period",
    "frequency",
    "unit",
    "value",
    "available_at",
    "availability_basis",
    "first_snapshot_id",
    "first_source_sha256",
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
]

REVISION_COLUMNS = [
    "observation_key",
    "source_id",
    "series_id",
    "geography",
    "period",
    "unit",
    "old_version_sequence",
    "new_version_sequence",
    "old_value",
    "new_value",
    "revision_first_seen_at",
    "snapshot_id",
]

CONTINUITY_COLUMNS = [
    "source_id",
    "snapshot_count",
    "archive_start_at",
    "archive_end_at",
    "maximum_gap_days",
    "allowed_gap_days",
    "continuity_status",
]


SNAPSHOT_DELTA_COLUMNS = [
    "source_id",
    "snapshot_id",
    "retrieved_at",
    "previous_snapshot_id",
    "previous_retrieved_at",
    "current_observation_count",
    "added_count",
    "reobserved_count",
    "revised_count",
    "missing_from_previous_count",
    "delta_status",
]

SOURCE_CUTOFF_STATUS_COLUMNS = [
    "source_id",
    "cutoff",
    "selected_observation_count",
    "latest_snapshot_id",
    "latest_snapshot_at",
    "age_days",
    "allowed_age_days",
    "freshness_status",
]

PANEL_COLUMNS = [
    "observation_key",
    "version_sequence",
    "source_id",
    "series_id",
    "proxy_domain",
    "geography",
    "period",
    "frequency",
    "unit",
    "value",
    "available_at",
    "availability_basis",
    "first_snapshot_id",
    "first_source_sha256",
    "cutoff",
    "historical_first_published_claim_allowed",
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
]


class ProxyInformationSetError(ProxyRegistryError):
    """Raised when the v0.9.8 archive or cutoff contract is violated."""


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProxyInformationSetError(f"{label} must be an object")
    return value


def load_policy(path: Path) -> dict[str, Any]:
    try:
        payload = canonical_text_bytes(path.read_bytes())
        policy = json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxyInformationSetError(f"cannot load v0.9.8 policy: {path}") from exc
    validate_policy(policy)
    return policy


def validate_policy(value: Any) -> None:
    policy = _required_object(value, "policy")
    expected_root = {
        "contract_id",
        "contract_version",
        "upstream_registry_version",
        "constitutional_scope",
        "availability_policy",
        "archive_policy",
        "quality_policy",
        "output_gates",
    }
    if set(policy) != expected_root:
        raise ProxyInformationSetError("policy root keys do not match the closed v0.9.8 contract")
    if policy.get("contract_id") != "ARMILAR_PROXY_INFORMATION_SET_V098":
        raise ProxyInformationSetError("unexpected contract_id")
    if policy.get("contract_version") != CONTRACT_VERSION:
        raise ProxyInformationSetError("unexpected contract_version")
    if policy.get("upstream_registry_version") != "0.9.7":
        raise ProxyInformationSetError("unexpected upstream registry version")
    availability = _required_object(policy.get("availability_policy"), "availability_policy")
    expected_availability = {
        "clock",
        "retroactive_availability_forbidden",
        "snapshot_level_publication_date_is_row_evidence",
        "latest_revised_history_before_archive_start_forbidden",
        "revision_available_only_when_first_seen",
        "same_value_reobservation_is_not_revision",
    }
    if set(availability) != expected_availability:
        raise ProxyInformationSetError("availability policy keys do not match the closed contract")
    if availability.get("clock") != "FIRST_VERIFIED_RETRIEVAL":
        raise ProxyInformationSetError("availability clock must remain FIRST_VERIFIED_RETRIEVAL")
    for key in expected_availability - {"clock", "snapshot_level_publication_date_is_row_evidence"}:
        if availability.get(key) is not True:
            raise ProxyInformationSetError(f"availability policy {key} must remain true")
    if availability.get("snapshot_level_publication_date_is_row_evidence") is not False:
        raise ProxyInformationSetError("snapshot-level publication dates cannot be row evidence")
    archive = _required_object(policy.get("archive_policy"), "archive_policy")
    expected_archive = {
        "verify_snapshot_manifest",
        "deterministic_replay_required",
        "verify_snapshot_ledger",
        "preserve_all_snapshot_observations",
        "preserve_all_distinct_value_versions",
        "preserve_revision_events",
        "append_only_output",
        "preserve_snapshot_deltas",
        "successor_archive_lineage_required_when_extending",
        "predecessor_content_must_be_preserved",
    }
    if set(archive) != expected_archive or any(archive.get(key) is not True for key in expected_archive):
        raise ProxyInformationSetError("all archive-policy invariants must remain true")
    quality = _required_object(policy.get("quality_policy"), "quality_policy")
    expected_quality = {
        "maximum_unexplained_clock_regression_seconds",
        "reject_duplicate_snapshot_ids",
        "reject_conflicting_rows_within_snapshot",
        "reject_unknown_sources",
        "continuity_statuses",
        "continuity_gap_multiplier",
        "snapshot_delta_statuses",
        "cutoff_freshness_statuses",
    }
    if set(quality) != expected_quality:
        raise ProxyInformationSetError("quality policy keys do not match the closed contract")
    if quality.get("maximum_unexplained_clock_regression_seconds") != 0:
        raise ProxyInformationSetError("clock regressions must remain forbidden")
    for key in ("reject_duplicate_snapshot_ids", "reject_conflicting_rows_within_snapshot", "reject_unknown_sources"):
        if quality.get(key) is not True:
            raise ProxyInformationSetError(f"quality policy {key} must remain true")
    if quality.get("continuity_statuses") != [
        "SINGLE_SNAPSHOT",
        "CONTIGUOUS_WITHIN_EXPECTED_LAG",
        "GAPPED_ARCHIVE",
    ]:
        raise ProxyInformationSetError("continuity statuses changed")
    multiplier = quality.get("continuity_gap_multiplier")
    if not isinstance(multiplier, int) or multiplier < 1 or multiplier > 12:
        raise ProxyInformationSetError("continuity_gap_multiplier must be an integer from 1 to 12")
    if quality.get("snapshot_delta_statuses") != [
        "INITIAL_SNAPSHOT",
        "UNCHANGED_SNAPSHOT",
        "CONTENT_CHANGED",
    ]:
        raise ProxyInformationSetError("snapshot delta statuses changed")
    if quality.get("cutoff_freshness_statuses") != [
        "NO_SNAPSHOT_BY_CUTOFF",
        "CURRENT_WITHIN_EXPECTED_WINDOW",
        "STALE_BEYOND_EXPECTED_WINDOW",
    ]:
        raise ProxyInformationSetError("cutoff freshness statuses changed")
    gates = _required_object(policy.get("output_gates"), "output_gates")
    if set(gates) != set(FALSE_GATES) | {"historical_first_published_claim_allowed"}:
        raise ProxyInformationSetError("output-gate keys do not match the closed contract")
    for key, gate in gates.items():
        if gate is not False:
            raise ProxyInformationSetError(f"output gate {key} must remain false")


def policy_hash(path: Path) -> str:
    return sha256_bytes(canonical_text_bytes(path.read_bytes()))


def observation_identity(row: Mapping[str, str]) -> dict[str, str]:
    required = ("source_id", "series_id", "proxy_domain", "geography", "period", "frequency", "unit")
    identity: dict[str, str] = {}
    for key in required:
        value = str(row.get(key, "")).strip()
        if not value:
            raise ProxyInformationSetError(f"observation identity field is empty: {key}")
        identity[key] = value
    return identity


def observation_key(row: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json_bytes(observation_identity(row)))


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        text = canonical_text_bytes(path.read_bytes()).decode("utf-8")
    except OSError as exc:
        raise ProxyInformationSetError(f"cannot read CSV: {path}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ProxyInformationSetError(f"CSV has no header: {path}")
    rows = [{str(k): str(v or "") for k, v in row.items()} for row in reader]
    return rows


def csv_bytes(rows: Iterable[Mapping[str, Any]], columns: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for raw in rows:
        row = {key: raw.get(key, "") for key in columns}
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(utc_timestamp(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def false_text() -> str:
    return "false"


def bundle_manifest_bytes(entries: Mapping[str, str]) -> bytes:
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())).encode("utf-8")


def write_manifest(root: Path, names: Iterable[str]) -> str:
    entries = {name: sha256_file(root / name) for name in names}
    payload = bundle_manifest_bytes(entries)
    (root / "MANIFEST.sha256").write_bytes(payload)
    return sha256_bytes(payload)
