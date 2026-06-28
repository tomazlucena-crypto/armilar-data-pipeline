from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import PipelineConfig, Source
from .util import sha256_file, utc_now, write_json


class DownloadTooLarge(RuntimeError):
    pass


class UnexpectedContentType(RuntimeError):
    pass


def _content_type_matches(actual: str | None, expected: tuple[str, ...]) -> bool:
    if not expected:
        return True
    normalized = (actual or "").split(";", 1)[0].strip().lower()
    return any(normalized == item.lower() for item in expected)


def _download_once(source: Source, user_agent: str, destination: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": user_agent, "Accept": "*/*"},
        method="GET",
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    try:
        with urllib.request.urlopen(request, timeout=source.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type")
            if not _content_type_matches(content_type, source.expected_content_types):
                raise UnexpectedContentType(
                    f"Expected {source.expected_content_types}, received {content_type!r}"
                )

            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > source.max_bytes:
                raise DownloadTooLarge(
                    f"Declared content length {declared_length} exceeds {source.max_bytes}"
                )

            with temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > source.max_bytes:
                        raise DownloadTooLarge(
                            f"Response exceeded maximum of {source.max_bytes} bytes"
                        )
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())

            if bytes_written == 0:
                raise RuntimeError("Downloaded response is empty")
            os.replace(temporary, destination)
            return {
                "status_code": getattr(response, "status", None),
                "final_url": response.geturl(),
                "content_type": content_type,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "bytes": bytes_written,
            }
    finally:
        temporary.unlink(missing_ok=True)


def _cache_paths(cache_root: Path, source: Source) -> tuple[Path, Path]:
    assert source.filename is not None
    data_path = cache_root / "latest" / source.filename
    metadata_path = cache_root / "metadata" / f"{source.source_id}.json"
    return data_path, metadata_path


def _save_cache(cache_root: Path, source: Source, source_file: Path, metadata: dict[str, Any]) -> None:
    cache_file, cache_metadata = _cache_paths(cache_root, source)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, cache_file)
    write_json(cache_metadata, metadata)


def _restore_cache(cache_root: Path, source: Source, destination: Path) -> dict[str, Any] | None:
    cache_file, cache_metadata = _cache_paths(cache_root, source)
    if not cache_file.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_file, destination)
    metadata: dict[str, Any] = {}
    if cache_metadata.is_file():
        try:
            metadata = json.loads(cache_metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    return metadata


def fetch(config: PipelineConfig, run_root: str | Path, cache_root: str | Path) -> dict[str, Any]:
    run_dir = Path(run_root)
    raw_root = run_dir / "raw"
    cache_dir = Path(cache_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    for source in config.sources:
        if source.mode != "download":
            entries.append(
                {
                    "source_id": source.source_id,
                    "provider": source.provider,
                    "required": source.required,
                    "mode": source.mode,
                    "status": "probe_only",
                    "url": source.url,
                    "purpose": source.purpose,
                }
            )
            continue

        assert source.filename is not None
        destination = raw_root / source.filename
        started_at = utc_now()
        attempt_errors: list[dict[str, str]] = []
        response_metadata: dict[str, Any] | None = None

        for attempt in range(1, source.retries + 2):
            try:
                response_metadata = _download_once(source, config.user_agent, destination)
                break
            except Exception as exc:  # captured in manifest; retry policy is deliberate
                attempt_errors.append(
                    {
                        "attempt": str(attempt),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                if attempt <= source.retries:
                    time.sleep(min(2 ** (attempt - 1), 8))

        if response_metadata is not None:
            sha256 = sha256_file(destination)
            fetched_at = utc_now()
            cache_metadata = {
                "source_id": source.source_id,
                "url": source.url,
                "fetched_at": fetched_at,
                "sha256": sha256,
                **response_metadata,
            }
            _save_cache(cache_dir, source, destination, cache_metadata)
            entries.append(
                {
                    "source_id": source.source_id,
                    "provider": source.provider,
                    "required": source.required,
                    "mode": source.mode,
                    "status": "fresh",
                    "url": source.url,
                    "filename": str(Path("raw") / source.filename),
                    "started_at": started_at,
                    "fetched_at": fetched_at,
                    "sha256": sha256,
                    "attempt_errors": attempt_errors,
                    "purpose": source.purpose,
                    **response_metadata,
                }
            )
            continue

        cached_metadata = _restore_cache(cache_dir, source, destination)
        if cached_metadata is not None:
            entries.append(
                {
                    "source_id": source.source_id,
                    "provider": source.provider,
                    "required": source.required,
                    "mode": source.mode,
                    "status": "stale_cache",
                    "url": source.url,
                    "filename": str(Path("raw") / source.filename),
                    "started_at": started_at,
                    "restored_at": utc_now(),
                    "sha256": sha256_file(destination),
                    "bytes": destination.stat().st_size,
                    "cached_fetched_at": cached_metadata.get("fetched_at"),
                    "attempt_errors": attempt_errors,
                    "purpose": source.purpose,
                }
            )
        else:
            entries.append(
                {
                    "source_id": source.source_id,
                    "provider": source.provider,
                    "required": source.required,
                    "mode": source.mode,
                    "status": "failed",
                    "url": source.url,
                    "started_at": started_at,
                    "failed_at": utc_now(),
                    "attempt_errors": attempt_errors,
                    "purpose": source.purpose,
                }
            )

    required_failed = [
        entry["source_id"]
        for entry in entries
        if entry["required"] and entry["status"] == "failed"
    ]
    stale = [entry["source_id"] for entry in entries if entry["status"] == "stale_cache"]
    fresh = [entry["source_id"] for entry in entries if entry["status"] == "fresh"]
    if required_failed:
        operational_status = "FAILED"
    elif stale:
        operational_status = "DEGRADED"
    else:
        operational_status = "NORMAL"

    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "operational_status": operational_status,
        "summary": {
            "fresh": fresh,
            "stale_cache": stale,
            "required_failed": required_failed,
            "total_entries": len(entries),
        },
        "entries": entries,
    }
