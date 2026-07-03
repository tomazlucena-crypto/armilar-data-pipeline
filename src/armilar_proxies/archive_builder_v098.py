"""Deterministic first-seen archive and point-in-time panels for ARMILAR v0.9.8."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .acquisition_v097 import replay_snapshot, verify_ledger, verify_manifest
from .archive_core_v098 import (
    ARCHIVE_STATUS,
    CONTRACT_VERSION,
    CONTINUITY_COLUMNS,
    FALSE_GATES,
    INFORMATION_SET_STATUS,
    PANEL_COLUMNS,
    REVISION_COLUMNS,
    SNAPSHOT_DELTA_COLUMNS,
    SNAPSHOT_OBSERVATION_COLUMNS,
    SOURCE_CUTOFF_STATUS_COLUMNS,
    VALUE_VERSION_COLUMNS,
    ProxyInformationSetError,
    bundle_manifest_bytes,
    csv_bytes,
    false_text,
    load_policy,
    observation_key,
    parse_utc,
    policy_hash,
    read_csv,
)
from .core_v097 import (
    canonical_json_bytes,
    load_registry,
    registry_hash,
    safe_child,
    sha256_bytes,
    sha256_file,
    source_by_id,
    utc_timestamp,
)

_FREQUENCY_DAYS = {"WEEKLY": 7, "MONTHLY": 31, "QUARTERLY": 92}


def _manifest_entries(bundle: Path) -> dict[str, str]:
    manifest = bundle / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ProxyInformationSetError("bundle manifest is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ProxyInformationSetError(f"invalid bundle manifest line {line_number}")
        digest, relative = parts
        if relative in entries:
            raise ProxyInformationSetError(f"duplicate bundle manifest path: {relative}")
        path = safe_child(bundle, relative)
        if not path.is_file():
            raise ProxyInformationSetError(f"bundle manifest file is missing: {relative}")
        if sha256_file(path) != digest:
            raise ProxyInformationSetError(f"bundle manifest hash mismatch: {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != actual:
        raise ProxyInformationSetError(
            f"bundle manifest file set mismatch; missing={sorted(actual - set(entries))}, extra={sorted(set(entries) - actual)}"
        )
    return entries


def verify_archive_bundle(path: Path) -> dict[str, Any]:
    entries = _manifest_entries(path)
    required = {
        "snapshot_observations.csv",
        "value_versions.csv",
        "revision_events.csv",
        "snapshot_deltas.csv",
        "source_continuity.csv",
        "archive_lineage.json",
        "archive_summary.json",
    }
    if set(entries) != required:
        raise ProxyInformationSetError("archive bundle file set does not match v0.9.8")
    summary = json.loads((path / "archive_summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != ARCHIVE_STATUS or summary.get("contract_version") != CONTRACT_VERSION:
        raise ProxyInformationSetError("archive summary status/version mismatch")
    for gate in FALSE_GATES:
        if summary.get(gate) is not False:
            raise ProxyInformationSetError(f"archive gate opened: {gate}")
    if summary.get("historical_first_published_claim_allowed") is not False:
        raise ProxyInformationSetError("historical first-published claim gate opened")
    snapshots = read_csv(path / "snapshot_observations.csv")
    versions = read_csv(path / "value_versions.csv")
    revisions = read_csv(path / "revision_events.csv")
    deltas = read_csv(path / "snapshot_deltas.csv")
    lineage = json.loads((path / "archive_lineage.json").read_text(encoding="utf-8"))
    if sha256_file(path / "archive_lineage.json") != summary.get("archive_lineage_sha256"):
        raise ProxyInformationSetError("archive lineage hash mismatch")
    if lineage.get("lineage_mode") != summary.get("lineage_mode"):
        raise ProxyInformationSetError("archive lineage mode mismatch")
    if lineage.get("parent_archive_manifest_sha256") != summary.get("parent_archive_manifest_sha256"):
        raise ProxyInformationSetError("archive parent manifest mismatch")
    if lineage.get("appended_snapshot_count") != summary.get("appended_snapshot_count"):
        raise ProxyInformationSetError("archive appended snapshot count mismatch")
    if lineage.get("predecessor_content_preserved") is not True:
        raise ProxyInformationSetError("archive predecessor preservation is not asserted")
    if len(snapshots) != summary.get("snapshot_observation_count"):
        raise ProxyInformationSetError("snapshot observation count mismatch")
    if len(versions) != summary.get("value_version_count"):
        raise ProxyInformationSetError("value version count mismatch")
    if len(revisions) != summary.get("revision_event_count"):
        raise ProxyInformationSetError("revision event count mismatch")
    if len(deltas) != summary.get("snapshot_delta_count") or len(deltas) != summary.get("snapshot_count"):
        raise ProxyInformationSetError("snapshot delta count mismatch")
    allowed_delta_statuses = {"INITIAL_SNAPSHOT", "UNCHANGED_SNAPSHOT", "CONTENT_CHANGED"}
    if any(row.get("delta_status") not in allowed_delta_statuses for row in deltas):
        raise ProxyInformationSetError("snapshot delta status is invalid")
    if lineage.get("lineage_mode") == "ROOT":
        if lineage.get("parent_archive_manifest_sha256") is not None or lineage.get("parent_snapshot_count") != 0:
            raise ProxyInformationSetError("root archive lineage has a parent")
        if lineage.get("appended_snapshot_count") != summary.get("snapshot_count"):
            raise ProxyInformationSetError("root archive appended count mismatch")
    elif lineage.get("lineage_mode") == "SUCCESSOR":
        parent_hash = lineage.get("parent_archive_manifest_sha256")
        parent_summary_hash = lineage.get("parent_archive_summary_sha256")
        if not isinstance(parent_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", parent_hash):
            raise ProxyInformationSetError("successor archive parent hash is invalid")
        if not isinstance(parent_summary_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", parent_summary_hash):
            raise ProxyInformationSetError("successor archive parent summary hash is invalid")
        if int(lineage.get("parent_snapshot_count", 0)) < 1 or int(lineage.get("appended_snapshot_count", 0)) < 1:
            raise ProxyInformationSetError("successor archive lineage counts are invalid")
        if int(lineage["parent_snapshot_count"]) + int(lineage["appended_snapshot_count"]) != int(summary["snapshot_count"]):
            raise ProxyInformationSetError("successor archive lineage counts do not reconcile")
    else:
        raise ProxyInformationSetError("archive lineage mode is invalid")
    keys = {row["observation_key"] for row in snapshots}
    if len(keys) != summary.get("distinct_observation_count"):
        raise ProxyInformationSetError("distinct observation count mismatch")
    previous: dict[str, int] = {}
    for row in sorted(versions, key=lambda item: (item["observation_key"], int(item["version_sequence"]))):
        sequence = int(row["version_sequence"])
        expected = previous.get(row["observation_key"], 0) + 1
        if sequence != expected:
            raise ProxyInformationSetError("value version sequence is not contiguous")
        previous[row["observation_key"]] = sequence
        for gate in ("direct_index_use_allowed", "arm_l_use_allowed", "model_training_allowed"):
            if row.get(gate) != "false":
                raise ProxyInformationSetError(f"value-version gate opened: {gate}")
    return summary


def verify_information_set_bundle(path: Path) -> dict[str, Any]:
    entries = _manifest_entries(path)
    if set(entries) != {"panel.csv", "source_cutoff_status.csv", "information_set_summary.json"}:
        raise ProxyInformationSetError("information-set bundle file set does not match v0.9.8")
    summary = json.loads((path / "information_set_summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != INFORMATION_SET_STATUS or summary.get("contract_version") != CONTRACT_VERSION:
        raise ProxyInformationSetError("information-set summary status/version mismatch")
    for gate in FALSE_GATES:
        if summary.get(gate) is not False:
            raise ProxyInformationSetError(f"information-set gate opened: {gate}")
    if summary.get("historical_first_published_claim_allowed") is not False:
        raise ProxyInformationSetError("historical first-published claim gate opened")
    rows = read_csv(path / "panel.csv")
    source_status = read_csv(path / "source_cutoff_status.csv")
    if len(rows) != summary.get("selected_observation_count"):
        raise ProxyInformationSetError("information-set row count mismatch")
    if len(source_status) != summary.get("archive_source_count"):
        raise ProxyInformationSetError("information-set source-status count mismatch")
    status_counts = {
        "CURRENT_WITHIN_EXPECTED_WINDOW": 0,
        "STALE_BEYOND_EXPECTED_WINDOW": 0,
        "NO_SNAPSHOT_BY_CUTOFF": 0,
    }
    for row in source_status:
        status = row.get("freshness_status")
        if status not in status_counts:
            raise ProxyInformationSetError("information-set freshness status is invalid")
        status_counts[status] += 1
        if status == "NO_SNAPSHOT_BY_CUTOFF":
            if row.get("latest_snapshot_at") or row.get("latest_snapshot_id") or row.get("age_days"):
                raise ProxyInformationSetError("no-snapshot source status contains snapshot data")
        else:
            age = int(row["age_days"])
            allowed = int(row["allowed_age_days"])
            expected = "CURRENT_WITHIN_EXPECTED_WINDOW" if age <= allowed else "STALE_BEYOND_EXPECTED_WINDOW"
            if status != expected:
                raise ProxyInformationSetError("information-set freshness classification mismatch")
    if status_counts["CURRENT_WITHIN_EXPECTED_WINDOW"] != summary.get("current_source_count"):
        raise ProxyInformationSetError("current-source count mismatch")
    if status_counts["STALE_BEYOND_EXPECTED_WINDOW"] != summary.get("stale_source_count"):
        raise ProxyInformationSetError("stale-source count mismatch")
    if status_counts["NO_SNAPSHOT_BY_CUTOFF"] != summary.get("no_snapshot_source_count"):
        raise ProxyInformationSetError("no-snapshot source count mismatch")
    cutoff = parse_utc(summary["cutoff"])
    if any(parse_utc(row["available_at"]) > cutoff for row in rows):
        raise ProxyInformationSetError("information-set contains a value observed after the cutoff")
    if len({row["observation_key"] for row in rows}) != len(rows):
        raise ProxyInformationSetError("information-set contains duplicate observation keys")
    return summary


def _atomic_directory(target: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if target.exists():
        raise ProxyInformationSetError(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
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


def _discover_snapshot_dirs(snapshot_root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for receipt_path in sorted(snapshot_root.glob("*/*/receipt.json")):
        snapshot_dir = receipt_path.parent
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProxyInformationSetError(f"invalid snapshot receipt: {receipt_path}") from exc
        snapshot_id = str(receipt.get("snapshot_id", ""))
        if not snapshot_id:
            raise ProxyInformationSetError(f"snapshot receipt has no snapshot_id: {receipt_path}")
        if snapshot_id in found:
            raise ProxyInformationSetError(f"duplicate snapshot_id in filesystem: {snapshot_id}")
        found[snapshot_id] = snapshot_dir
    return found


def _continuity_rows(
    retrievals: Mapping[str, list[str]],
    registry: Mapping[str, Any],
    multiplier: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_id in sorted(retrievals):
        values = sorted({utc_timestamp(item) for item in retrievals[source_id]})
        source = source_by_id(registry, source_id)
        interval = _FREQUENCY_DAYS[source["frequency"]]
        allowed = interval * multiplier + int(source.get("expected_lag_days") or 0)
        gaps = [int((parse_utc(right) - parse_utc(left)).total_seconds() // 86400) for left, right in zip(values, values[1:])]
        maximum = max(gaps, default=0)
        if len(values) == 1:
            status = "SINGLE_SNAPSHOT"
        elif maximum <= allowed:
            status = "CONTIGUOUS_WITHIN_EXPECTED_LAG"
        else:
            status = "GAPPED_ARCHIVE"
        output.append(
            {
                "source_id": source_id,
                "snapshot_count": len(values),
                "archive_start_at": values[0],
                "archive_end_at": values[-1],
                "maximum_gap_days": maximum,
                "allowed_gap_days": allowed,
                "continuity_status": status,
            }
        )
    return output



def _snapshot_delta_rows(snapshot_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in snapshot_rows:
        group_key = (row["source_id"], row["retrieved_at"], row["snapshot_id"])
        grouped.setdefault(group_key, {})[row["observation_key"]] = row["value"]
    previous_by_source: dict[str, tuple[str, str, dict[str, str]]] = {}
    output: list[dict[str, Any]] = []
    for (source_id, retrieved_at, snapshot_id), current in sorted(grouped.items()):
        prior = previous_by_source.get(source_id)
        if prior is None:
            output.append(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "retrieved_at": retrieved_at,
                    "previous_snapshot_id": "",
                    "previous_retrieved_at": "",
                    "current_observation_count": len(current),
                    "added_count": len(current),
                    "reobserved_count": 0,
                    "revised_count": 0,
                    "missing_from_previous_count": 0,
                    "delta_status": "INITIAL_SNAPSHOT",
                }
            )
        else:
            prior_snapshot_id, prior_retrieved_at, previous = prior
            current_keys = set(current)
            previous_keys = set(previous)
            shared = current_keys & previous_keys
            revised = sum(1 for key in shared if current[key] != previous[key])
            reobserved = len(shared) - revised
            added = len(current_keys - previous_keys)
            missing = len(previous_keys - current_keys)
            status = "UNCHANGED_SNAPSHOT" if added == revised == missing == 0 else "CONTENT_CHANGED"
            output.append(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "retrieved_at": retrieved_at,
                    "previous_snapshot_id": prior_snapshot_id,
                    "previous_retrieved_at": prior_retrieved_at,
                    "current_observation_count": len(current),
                    "added_count": added,
                    "reobserved_count": reobserved,
                    "revised_count": revised,
                    "missing_from_previous_count": missing,
                    "delta_status": status,
                }
            )
        previous_by_source[source_id] = (snapshot_id, retrieved_at, current)
    return output


def _archive_lineage(
    *,
    previous_archive_dir: Path | None,
    snapshot_rows: list[dict[str, str]],
    snapshot_count: int,
    current_policy_sha256: str,
) -> dict[str, Any]:
    if previous_archive_dir is None:
        return {
            "schema_version": "1.0",
            "contract_version": CONTRACT_VERSION,
            "lineage_mode": "ROOT",
            "parent_archive_manifest_sha256": None,
            "parent_archive_summary_sha256": None,
            "parent_snapshot_count": 0,
            "appended_snapshot_count": snapshot_count,
            "predecessor_content_preserved": True,
        }
    previous_archive_dir = previous_archive_dir.resolve()
    previous_summary = verify_archive_bundle(previous_archive_dir)
    if previous_summary.get("policy_sha256") != current_policy_sha256:
        raise ProxyInformationSetError("successor archive policy does not match predecessor policy")
    previous_rows = read_csv(previous_archive_dir / "snapshot_observations.csv")
    previous_ids = {row["snapshot_id"] for row in previous_rows}
    current_ids = {row["snapshot_id"] for row in snapshot_rows}
    if not previous_ids < current_ids:
        raise ProxyInformationSetError("successor archive must contain every predecessor snapshot and at least one new snapshot")
    previous_payloads = {tuple(row[column] for column in SNAPSHOT_OBSERVATION_COLUMNS) for row in previous_rows}
    current_payloads = {tuple(row[column] for column in SNAPSHOT_OBSERVATION_COLUMNS) for row in snapshot_rows}
    if not previous_payloads <= current_payloads:
        raise ProxyInformationSetError("successor archive does not preserve predecessor snapshot observations exactly")
    parent_count = int(previous_summary["snapshot_count"])
    appended = snapshot_count - parent_count
    if appended <= 0:
        raise ProxyInformationSetError("successor archive has no appended snapshot")
    return {
        "schema_version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "lineage_mode": "SUCCESSOR",
        "parent_archive_manifest_sha256": sha256_file(previous_archive_dir / "MANIFEST.sha256"),
        "parent_archive_summary_sha256": sha256_file(previous_archive_dir / "archive_summary.json"),
        "parent_snapshot_count": parent_count,
        "appended_snapshot_count": appended,
        "predecessor_content_preserved": True,
    }


def _source_cutoff_status_rows(
    *,
    archive_dir: Path,
    selected: Mapping[str, Mapping[str, str]],
    cutoff_text: str,
) -> list[dict[str, Any]]:
    cutoff = parse_utc(cutoff_text)
    continuity = read_csv(archive_dir / "source_continuity.csv")
    snapshots = read_csv(archive_dir / "snapshot_observations.csv")
    snapshots_by_source: dict[str, dict[tuple[str, str], None]] = defaultdict(dict)
    for row in snapshots:
        if parse_utc(row["retrieved_at"]) <= cutoff:
            snapshots_by_source[row["source_id"]][(row["retrieved_at"], row["snapshot_id"])] = None
    selected_counts: dict[str, int] = defaultdict(int)
    for row in selected.values():
        selected_counts[str(row["source_id"])] += 1
    output: list[dict[str, Any]] = []
    for row in sorted(continuity, key=lambda item: item["source_id"]):
        source_id = row["source_id"]
        candidates = sorted(snapshots_by_source.get(source_id, {}))
        allowed = int(row["allowed_gap_days"])
        if not candidates:
            latest_at = ""
            latest_id = ""
            age_days: int | str = ""
            status = "NO_SNAPSHOT_BY_CUTOFF"
        else:
            latest_at, latest_id = candidates[-1]
            age_days = int((cutoff - parse_utc(latest_at)).total_seconds() // 86400)
            status = "CURRENT_WITHIN_EXPECTED_WINDOW" if age_days <= allowed else "STALE_BEYOND_EXPECTED_WINDOW"
        output.append(
            {
                "source_id": source_id,
                "cutoff": cutoff_text,
                "selected_observation_count": selected_counts.get(source_id, 0),
                "latest_snapshot_id": latest_id,
                "latest_snapshot_at": latest_at,
                "age_days": age_days,
                "allowed_age_days": allowed,
                "freshness_status": status,
            }
        )
    return output

def build_archive(
    *,
    registry_path: Path,
    policy_path: Path,
    snapshot_root: Path,
    output_dir: Path,
    previous_archive_dir: Path | None = None,
) -> Path:
    registry = load_registry(registry_path)
    policy = load_policy(policy_path)
    snapshot_root = snapshot_root.resolve()
    ledger_path = snapshot_root / "snapshot_ledger.jsonl"
    ledger = verify_ledger(ledger_path)
    if not ledger:
        raise ProxyInformationSetError("snapshot ledger is empty")
    snapshot_dirs = _discover_snapshot_dirs(snapshot_root)
    ledger_ids = [str(entry["snapshot_id"]) for entry in ledger]
    if len(set(ledger_ids)) != len(ledger_ids):
        raise ProxyInformationSetError("snapshot ledger contains duplicate snapshot ids")
    if set(ledger_ids) != set(snapshot_dirs):
        raise ProxyInformationSetError(
            f"snapshot filesystem/ledger mismatch; missing={sorted(set(ledger_ids)-set(snapshot_dirs))}, extra={sorted(set(snapshot_dirs)-set(ledger_ids))}"
        )

    snapshot_rows: list[dict[str, str]] = []
    retrievals: dict[str, list[str]] = defaultdict(list)
    previous_source_clock: dict[str, Any] = {}
    source_ids = {source["source_id"] for source in registry["sources"]}

    sequence_clock: dict[str, Any] = {}
    for entry in ledger:
        source_id = str(entry["source_id"])
        clock = parse_utc(str(entry["retrieved_at"]))
        if source_id in sequence_clock and clock < sequence_clock[source_id]:
            raise ProxyInformationSetError(f"retrieval clock regressed in ledger sequence for source {source_id}")
        sequence_clock[source_id] = clock
    ordered = sorted(ledger, key=lambda item: (parse_utc(str(item["retrieved_at"])), str(item["source_id"]), int(item["sequence"])))
    for entry in ordered:
        snapshot_id = str(entry["snapshot_id"])
        snapshot_dir = snapshot_dirs[snapshot_id]
        verify_manifest(snapshot_dir)
        replay_snapshot(registry_path=registry_path, snapshot_dir=snapshot_dir)
        receipt = json.loads((snapshot_dir / "receipt.json").read_text(encoding="utf-8"))
        source_id = str(receipt["source_id"])
        if source_id not in source_ids:
            raise ProxyInformationSetError(f"snapshot source is not in the v0.9.7 registry: {source_id}")
        if source_id != entry["source_id"] or receipt["retrieved_at"] != entry["retrieved_at"]:
            raise ProxyInformationSetError(f"snapshot receipt does not match ledger: {snapshot_id}")
        if receipt["source_sha256"] != entry["source_sha256"] or receipt["registry_sha256"] != entry["registry_sha256"]:
            raise ProxyInformationSetError(f"snapshot hashes do not match ledger: {snapshot_id}")
        retrieved = utc_timestamp(str(receipt["retrieved_at"]))
        clock = parse_utc(retrieved)
        if source_id in previous_source_clock and clock < previous_source_clock[source_id]:
            raise ProxyInformationSetError(f"retrieval clock regressed for source {source_id}")
        previous_source_clock[source_id] = clock
        retrievals[source_id].append(retrieved)
        rows = read_csv(snapshot_dir / "normalized.csv")
        seen_in_snapshot: dict[str, str] = {}
        for row in rows:
            key = observation_key(row)
            value = row.get("value", "")
            if key in seen_in_snapshot:
                if seen_in_snapshot[key] != value:
                    raise ProxyInformationSetError(f"conflicting duplicate observation in snapshot {snapshot_id}: {key}")
                raise ProxyInformationSetError(f"duplicate observation in snapshot {snapshot_id}: {key}")
            seen_in_snapshot[key] = value
            snapshot_rows.append(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "retrieved_at": retrieved,
                    "observation_key": key,
                    "series_id": row["series_id"],
                    "proxy_domain": row["proxy_domain"],
                    "geography": row["geography"],
                    "period": row["period"],
                    "frequency": row["frequency"],
                    "value": value,
                    "unit": row["unit"],
                    "source_sha256": row["source_sha256"],
                    "registry_sha256": row["registry_sha256"],
                    "row_locator": row["row_locator"],
                }
            )

    snapshot_rows.sort(key=lambda row: (row["retrieved_at"], row["source_id"], row["snapshot_id"], row["observation_key"]))
    versions: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    latest: dict[str, dict[str, Any]] = {}
    sequence_by_key: dict[str, int] = defaultdict(int)
    for row in snapshot_rows:
        key = row["observation_key"]
        prior = latest.get(key)
        if prior is not None and prior["value"] == row["value"]:
            continue
        sequence_by_key[key] += 1
        sequence = sequence_by_key[key]
        basis = "FIRST_VERIFIED_RETRIEVAL" if sequence == 1 else "REVISION_FIRST_VERIFIED_RETRIEVAL"
        version = {
            "observation_key": key,
            "version_sequence": sequence,
            "source_id": row["source_id"],
            "series_id": row["series_id"],
            "proxy_domain": row["proxy_domain"],
            "geography": row["geography"],
            "period": row["period"],
            "frequency": row["frequency"],
            "unit": row["unit"],
            "value": row["value"],
            "available_at": row["retrieved_at"],
            "availability_basis": basis,
            "first_snapshot_id": row["snapshot_id"],
            "first_source_sha256": row["source_sha256"],
            "direct_index_use_allowed": false_text(),
            "arm_l_use_allowed": false_text(),
            "model_training_allowed": false_text(),
        }
        if prior is not None:
            revisions.append(
                {
                    "observation_key": key,
                    "source_id": row["source_id"],
                    "series_id": row["series_id"],
                    "geography": row["geography"],
                    "period": row["period"],
                    "unit": row["unit"],
                    "old_version_sequence": prior["version_sequence"],
                    "new_version_sequence": sequence,
                    "old_value": prior["value"],
                    "new_value": row["value"],
                    "revision_first_seen_at": row["retrieved_at"],
                    "snapshot_id": row["snapshot_id"],
                }
            )
        versions.append(version)
        latest[key] = version

    current_policy_sha256 = policy_hash(policy_path)
    snapshot_deltas = _snapshot_delta_rows(snapshot_rows)
    lineage = _archive_lineage(
        previous_archive_dir=previous_archive_dir,
        snapshot_rows=snapshot_rows,
        snapshot_count=len(ledger_ids),
        current_policy_sha256=current_policy_sha256,
    )
    continuity = _continuity_rows(
        retrievals,
        registry,
        int(policy["quality_policy"]["continuity_gap_multiplier"]),
    )
    archive_start = min(row["retrieved_at"] for row in snapshot_rows)
    archive_end = max(row["retrieved_at"] for row in snapshot_rows)
    target, temp = _atomic_directory(output_dir)
    try:
        (temp / "snapshot_observations.csv").write_bytes(csv_bytes(snapshot_rows, SNAPSHOT_OBSERVATION_COLUMNS))
        (temp / "value_versions.csv").write_bytes(csv_bytes(versions, VALUE_VERSION_COLUMNS))
        (temp / "revision_events.csv").write_bytes(csv_bytes(revisions, REVISION_COLUMNS))
        (temp / "snapshot_deltas.csv").write_bytes(csv_bytes(snapshot_deltas, SNAPSHOT_DELTA_COLUMNS))
        (temp / "source_continuity.csv").write_bytes(csv_bytes(continuity, CONTINUITY_COLUMNS))
        (temp / "archive_lineage.json").write_bytes(canonical_json_bytes(lineage))
        summary = {
            "schema_version": "1.0",
            "contract_version": CONTRACT_VERSION,
            "status": ARCHIVE_STATUS,
            "snapshot_count": len(ledger_ids),
            "snapshot_observation_count": len(snapshot_rows),
            "distinct_observation_count": len(latest),
            "value_version_count": len(versions),
            "revision_event_count": len(revisions),
            "snapshot_delta_count": len(snapshot_deltas),
            "source_count": len(retrievals),
            "archive_start_at": archive_start,
            "archive_end_at": archive_end,
            "input_ledger_sha256": sha256_file(ledger_path),
            "policy_sha256": current_policy_sha256,
            "archive_lineage_sha256": sha256_file(temp / "archive_lineage.json"),
            "lineage_mode": lineage["lineage_mode"],
            "parent_archive_manifest_sha256": lineage["parent_archive_manifest_sha256"],
            "appended_snapshot_count": lineage["appended_snapshot_count"],
            "historical_first_published_claim_allowed": False,
            "direct_index_use_allowed": False,
            "arm_l_use_allowed": False,
            "model_training_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
        }
        (temp / "archive_summary.json").write_bytes(canonical_json_bytes(summary))
        names = [
            "snapshot_observations.csv",
            "value_versions.csv",
            "revision_events.csv",
            "snapshot_deltas.csv",
            "source_continuity.csv",
            "archive_lineage.json",
            "archive_summary.json",
        ]
        entries = {name: sha256_file(temp / name) for name in names}
        (temp / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
        verify_archive_bundle(temp)
        return _finalise_directory(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def build_information_set(*, archive_dir: Path, cutoff: str, output_dir: Path) -> Path:
    verify_archive_bundle(archive_dir)
    cutoff_text = utc_timestamp(cutoff)
    cutoff_value = parse_utc(cutoff_text)
    versions = read_csv(archive_dir / "value_versions.csv")
    selected: dict[str, dict[str, str]] = {}
    for row in sorted(versions, key=lambda item: (item["observation_key"], int(item["version_sequence"]))):
        if parse_utc(row["available_at"]) <= cutoff_value:
            selected[row["observation_key"]] = row
    if not selected:
        raise ProxyInformationSetError("no proxy value was available by the requested cutoff")
    rows: list[dict[str, Any]] = []
    for key in sorted(selected):
        row = selected[key]
        rows.append(
            {
                "observation_key": key,
                "version_sequence": int(row["version_sequence"]),
                "source_id": row["source_id"],
                "series_id": row["series_id"],
                "proxy_domain": row["proxy_domain"],
                "geography": row["geography"],
                "period": row["period"],
                "frequency": row["frequency"],
                "unit": row["unit"],
                "value": row["value"],
                "available_at": row["available_at"],
                "availability_basis": row["availability_basis"],
                "first_snapshot_id": row["first_snapshot_id"],
                "first_source_sha256": row["first_source_sha256"],
                "cutoff": cutoff_text,
                "historical_first_published_claim_allowed": false_text(),
                "direct_index_use_allowed": false_text(),
                "arm_l_use_allowed": false_text(),
                "model_training_allowed": false_text(),
            }
        )
    source_status = _source_cutoff_status_rows(
        archive_dir=archive_dir,
        selected=selected,
        cutoff_text=cutoff_text,
    )
    target, temp = _atomic_directory(output_dir)
    try:
        (temp / "panel.csv").write_bytes(csv_bytes(rows, PANEL_COLUMNS))
        (temp / "source_cutoff_status.csv").write_bytes(csv_bytes(source_status, SOURCE_CUTOFF_STATUS_COLUMNS))
        available = [row["available_at"] for row in rows]
        summary = {
            "schema_version": "1.0",
            "contract_version": CONTRACT_VERSION,
            "status": INFORMATION_SET_STATUS,
            "cutoff": cutoff_text,
            "archive_manifest_sha256": sha256_file(archive_dir / "MANIFEST.sha256"),
            "selected_observation_count": len(rows),
            "source_count": len({row["source_id"] for row in rows}),
            "archive_source_count": len(source_status),
            "current_source_count": sum(row["freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW" for row in source_status),
            "stale_source_count": sum(row["freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW" for row in source_status),
            "no_snapshot_source_count": sum(row["freshness_status"] == "NO_SNAPSHOT_BY_CUTOFF" for row in source_status),
            "first_available_at": min(available),
            "last_available_at": max(available),
            "historical_first_published_claim_allowed": False,
            "direct_index_use_allowed": False,
            "arm_l_use_allowed": False,
            "model_training_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
        }
        (temp / "information_set_summary.json").write_bytes(canonical_json_bytes(summary))
        names = ["panel.csv", "source_cutoff_status.csv", "information_set_summary.json"]
        entries = {name: sha256_file(temp / name) for name in names}
        (temp / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
        verify_information_set_bundle(temp)
        return _finalise_directory(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
