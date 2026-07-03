"""Immutable snapshot acquisition, manifests, ledger and replay for ARMILAR v0.9.7."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from .core_v097 import (
    LEDGER_VERSION,
    PARSER_VERSION,
    REGISTRY_VERSION,
    ProxyRegistryError,
    UrlLibFetcher,
    _timestamp_value,
    canonical_json_bytes,
    load_registry,
    optional_utc_timestamp,
    registry_hash,
    safe_child,
    sha256_bytes,
    sha256_file,
    slug_timestamp,
    source_by_id,
    utc_timestamp,
    validate_raw_magic,
)
from .parsers_v097 import PARSERS, csv_bytes, sort_observations

def manifest_bytes(entries: Mapping[str, str]) -> bytes:
    lines = [f"{digest}  {name}\n" for name, digest in sorted(entries.items())]
    return "".join(lines).encode("utf-8")


def verify_manifest(bundle: Path) -> dict[str, str]:
    manifest = bundle / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ProxyRegistryError("snapshot manifest is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ProxyRegistryError(f"invalid manifest line {line_number}")
        digest, relative = parts
        if relative in entries:
            raise ProxyRegistryError(f"duplicate manifest path: {relative}")
        path = safe_child(bundle, relative)
        if not path.is_file():
            raise ProxyRegistryError(f"manifest file missing: {relative}")
        actual = sha256_file(path)
        if actual != digest:
            raise ProxyRegistryError(f"manifest hash mismatch: {relative}")
        entries[relative] = digest
    actual_files = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != actual_files:
        raise ProxyRegistryError(f"manifest file set mismatch; missing={sorted(actual_files - set(entries))}, extra={sorted(set(entries) - actual_files)}")
    return entries


def _ledger_entry_hash(entry_without_hash: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(entry_without_hash))


def append_ledger(ledger_path: Path, receipt: Mapping[str, Any], manifest_sha256: str) -> dict[str, Any]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = "0" * 64
    sequence = 1
    if ledger_path.exists():
        entries = verify_ledger(ledger_path)
        if entries:
            previous_hash = entries[-1]["entry_hash"]
            sequence = entries[-1]["sequence"] + 1
    base = {
        "ledger_version": LEDGER_VERSION,
        "sequence": sequence,
        "source_id": receipt["source_id"],
        "snapshot_id": receipt["snapshot_id"],
        "retrieved_at": receipt["retrieved_at"],
        "published_at": receipt["published_at"],
        "source_sha256": receipt["source_sha256"],
        "registry_sha256": receipt["registry_sha256"],
        "manifest_sha256": manifest_sha256,
        "previous_entry_hash": previous_hash,
    }
    entry = dict(base)
    entry["entry_hash"] = _ledger_entry_hash(base)
    with ledger_path.open("ab") as handle:
        handle.write(canonical_json_bytes(entry))
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    for line_number, line in enumerate(path.read_bytes().splitlines(), start=1):
        try:
            entry = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProxyRegistryError(f"invalid ledger JSON at line {line_number}") from exc
        if not isinstance(entry, dict):
            raise ProxyRegistryError(f"ledger line {line_number} is not an object")
        entry_hash = entry.get("entry_hash")
        base = {key: value for key, value in entry.items() if key != "entry_hash"}
        expected = _ledger_entry_hash(base)
        if entry_hash != expected:
            raise ProxyRegistryError(f"ledger entry hash mismatch at line {line_number}")
        if entry.get("previous_entry_hash") != previous_hash:
            raise ProxyRegistryError(f"ledger chain mismatch at line {line_number}")
        if entry.get("sequence") != line_number:
            raise ProxyRegistryError(f"ledger sequence mismatch at line {line_number}")
        previous_hash = entry_hash
        entries.append(entry)
    return entries


def acquire_source(
    *,
    registry_path: Path,
    source_id: str,
    output_root: Path,
    retrieved_at: str,
    published_at: str | None = None,
    fetcher: Any | None = None,
    raw_payload: bytes | None = None,
    response_headers: Mapping[str, str] | None = None,
    final_url: str | None = None,
) -> Path:
    registry = load_registry(registry_path)
    source = source_by_id(registry, source_id)
    if source["source_status"] not in {"ACTIVE_RESEARCH_PROXY", "ACTIVE_SENSITIVITY_ONLY"}:
        raise ProxyRegistryError(f"source is not acquisition-enabled: {source_id}")
    retrieved = utc_timestamp(retrieved_at)
    published = optional_utc_timestamp(published_at)
    if source["publication_time_status"] == "EXACT_TIMESTAMP" and published is None:
        raise ProxyRegistryError("an exact published_at timestamp is mandatory for this source")
    if raw_payload is None:
        response = (fetcher or UrlLibFetcher()).fetch(source)
        payload = response.body
        status = response.status
        headers = dict(response.headers)
        resolved_url = response.final_url
    else:
        payload = raw_payload
        status = 200
        headers = {str(k).lower(): str(v) for k, v in (response_headers or {}).items()}
        resolved_url = final_url or source["data_url"]
    resolved_host = urllib.parse.urlparse(resolved_url).hostname
    if resolved_host not in source["allowed_hosts"]:
        raise ProxyRegistryError(f"resolved URL host is not approved: {resolved_host}")
    if len(payload) > int(source["max_download_bytes"]):
        raise ProxyRegistryError(f"payload exceeds max_download_bytes for {source_id}")
    if published is not None and _timestamp_value(published) > _timestamp_value(retrieved):
        raise ProxyRegistryError("published_at cannot be after retrieved_at")
    validate_raw_magic(source, payload)
    source_digest = sha256_bytes(payload)
    registry_digest = registry_hash(registry_path)
    snapshot_id = f"{source_id}_{slug_timestamp(retrieved)}_{source_digest[:12]}"
    source_root = safe_child(output_root.resolve(), source_id)
    final_dir = safe_child(source_root, snapshot_id)
    if final_dir.exists():
        raise ProxyRegistryError(f"snapshot already exists: {snapshot_id}")
    source_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}.", dir=source_root))
    try:
        raw_name = f"raw{source['raw_extension']}"
        raw_path = temp_dir / raw_name
        raw_path.write_bytes(payload)
        parser = PARSERS.get(source["parser_id"])
        if parser is None:
            raise ProxyRegistryError(f"unregistered parser: {source['parser_id']}")
        parsed_observations = parser(
            payload,
            source=source,
            published_at=published,
            retrieved_at=retrieved,
            raw_snapshot_id=snapshot_id,
            source_sha256=source_digest,
            registry_sha256=registry_digest,
        )
        allowed_domains = set(source["proxy_domains"])
        for row in parsed_observations:
            if row.get("proxy_domain") not in allowed_domains:
                raise ProxyRegistryError(
                    f"parser emitted undeclared proxy domain {row.get('proxy_domain')!r} for {source_id}"
                )
            if row.get("frequency") != source["frequency"]:
                raise ProxyRegistryError(f"parser frequency mismatch for {source_id}")
        observations = sort_observations(parsed_observations)
        normalised_payload = csv_bytes(observations)
        (temp_dir / "normalized.csv").write_bytes(normalised_payload)
        series = sorted({row["series_id"] for row in observations})
        domains = sorted({row["proxy_domain"] for row in observations})
        geographies = sorted({row["geography"] for row in observations})
        periods = sorted({row["period"] for row in observations})
        information_set_ready = bool(
            published
            and source["historical_vintage_support"]
            and source["publication_time_status"] in {"EXACT_TIMESTAMP", "RELEASE_DATE_ONLY"}
        )
        summary = {
            "schema_version": "1.0",
            "registry_version": REGISTRY_VERSION,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "parser_id": source["parser_id"],
            "parser_version": PARSER_VERSION,
            "frequency": source["frequency"],
            "observation_count": len(observations),
            "series_count": len(series),
            "geography_count": len(geographies),
            "period_count": len(periods),
            "first_period": periods[0],
            "last_period": periods[-1],
            "proxy_domains": domains,
            "published_at": published,
            "publication_time_status": source["publication_time_status"],
            "retrieved_at": retrieved,
            "historical_vintage_support": source["historical_vintage_support"],
            "information_set_ready": information_set_ready,
            "direct_index_use_allowed": False,
            "arm_l_use_allowed": False,
            "model_training_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
            "source_sha256": source_digest,
            "registry_sha256": registry_digest,
            "normalized_sha256": sha256_bytes(normalised_payload),
        }
        (temp_dir / "normalization_summary.json").write_bytes(canonical_json_bytes(summary))
        receipt = {
            "schema_version": "1.0",
            "registry_version": REGISTRY_VERSION,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "official_page_url": source["official_page_url"],
            "requested_url": source["data_url"],
            "final_url": resolved_url,
            "http_status": status,
            "response_headers": {
                key: headers[key]
                for key in sorted(headers)
                if key in {"content-type", "content-length", "etag", "last-modified", "date", "cache-control"}
            },
            "raw_filename": raw_name,
            "raw_size_bytes": len(payload),
            "source_sha256": source_digest,
            "registry_sha256": registry_digest,
            "published_at": published,
            "publication_time_status": source["publication_time_status"],
            "retrieved_at": retrieved,
            "license_name": source["license"]["name"],
            "license_url": source["license"]["url"],
            "attribution": source["attribution"],
            "direct_index_use_allowed": False,
            "arm_l_use_allowed": False,
            "model_training_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
        }
        (temp_dir / "receipt.json").write_bytes(canonical_json_bytes(receipt))
        (temp_dir / "source_registry_entry.json").write_bytes(canonical_json_bytes(source))
        entries = {
            raw_name: sha256_file(raw_path),
            "normalized.csv": sha256_file(temp_dir / "normalized.csv"),
            "normalization_summary.json": sha256_file(temp_dir / "normalization_summary.json"),
            "receipt.json": sha256_file(temp_dir / "receipt.json"),
            "source_registry_entry.json": sha256_file(temp_dir / "source_registry_entry.json"),
        }
        (temp_dir / "MANIFEST.sha256").write_bytes(manifest_bytes(entries))
        verify_manifest(temp_dir)
        temp_dir.replace(final_dir)
        manifest_digest = sha256_file(final_dir / "MANIFEST.sha256")
        try:
            append_ledger(output_root / "snapshot_ledger.jsonl", receipt, manifest_digest)
        except Exception:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return final_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def replay_snapshot(*, registry_path: Path, snapshot_dir: Path) -> dict[str, Any]:
    verify_manifest(snapshot_dir)
    receipt = json.loads((snapshot_dir / "receipt.json").read_text(encoding="utf-8"))
    summary = json.loads((snapshot_dir / "normalization_summary.json").read_text(encoding="utf-8"))
    registry = load_registry(registry_path)
    source = source_by_id(registry, receipt["source_id"])
    current_registry_hash = registry_hash(registry_path)
    if receipt["registry_sha256"] != current_registry_hash:
        raise ProxyRegistryError("snapshot registry hash does not match the supplied registry")
    raw_path = snapshot_dir / receipt["raw_filename"]
    payload = raw_path.read_bytes()
    if sha256_bytes(payload) != receipt["source_sha256"]:
        raise ProxyRegistryError("raw snapshot hash mismatch")
    parser = PARSERS.get(source["parser_id"])
    if parser is None:
        raise ProxyRegistryError("snapshot parser is unavailable")
    observations = sort_observations(
        parser(
            payload,
            source=source,
            published_at=receipt["published_at"],
            retrieved_at=receipt["retrieved_at"],
            raw_snapshot_id=receipt["snapshot_id"],
            source_sha256=receipt["source_sha256"],
            registry_sha256=receipt["registry_sha256"],
        )
    )
    replayed = csv_bytes(observations)
    replay_hash = sha256_bytes(replayed)
    if replay_hash != summary["normalized_sha256"]:
        raise ProxyRegistryError("deterministic replay produced a different normalized hash")
    if replayed != (snapshot_dir / "normalized.csv").read_bytes():
        raise ProxyRegistryError("deterministic replay bytes differ from stored normalized.csv")
    return {
        "status": "PROXY_SNAPSHOT_REPLAY_VALID",
        "source_id": receipt["source_id"],
        "snapshot_id": receipt["snapshot_id"],
        "observation_count": len(observations),
        "normalized_sha256": replay_hash,
        "information_set_ready": summary["information_set_ready"],
        "direct_index_use_allowed": False,
        "arm_l_use_allowed": False,
    }
