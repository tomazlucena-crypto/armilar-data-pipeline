from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import Step2Config
from .util import atomic_write_bytes, sha256_bytes, utc_now, write_json


class AcquisitionError(RuntimeError):
    """Structured acquisition failure preserving every technical attempt."""

    def __init__(self, *, source_id: str, url: str, attempt_errors: tuple[str, ...], retrieved_at: str):
        self.source_id = source_id
        self.url = url
        self.attempt_errors = attempt_errors
        self.retrieved_at = retrieved_at
        super().__init__(f"Acquisition failed for {source_id}: {'; '.join(attempt_errors)}")


@dataclass(frozen=True)
class AcquisitionRecord:
    source_id: str
    url: str
    final_url: str
    path: Path
    status: str
    status_code: int | None
    content_type: str | None
    bytes: int
    sha256: str
    retrieved_at: str
    attempt_errors: tuple[str, ...]

    def as_dict(self, root: Path) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "final_url": self.final_url,
            "filename": self.path.relative_to(root).as_posix(),
            "status": self.status,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "attempt_errors": list(self.attempt_errors),
        }


def add_query(url: str, **params: Any) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items() if value is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_url(
    config: Step2Config,
    *,
    source_id: str,
    url: str,
    destination: Path,
    cache_path: Path | None = None,
    accept: str = "*/*",
) -> AcquisitionRecord:
    errors: list[str] = []
    headers = {"User-Agent": config.user_agent, "Accept": accept}
    for attempt in range(1, config.retries + 1):
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                payload = response.read(config.max_response_bytes + 1)
                if len(payload) > config.max_response_bytes:
                    raise ValueError(
                        f"Response exceeds max_response_bytes={config.max_response_bytes}"
                    )
                atomic_write_bytes(destination, payload)
                if cache_path is not None:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, cache_path)
                record = AcquisitionRecord(
                    source_id=source_id,
                    url=url,
                    final_url=response.geturl(),
                    path=destination,
                    status="fresh",
                    status_code=getattr(response, "status", None),
                    content_type=response.headers.get("Content-Type"),
                    bytes=len(payload),
                    sha256=sha256_bytes(payload),
                    retrieved_at=utc_now(),
                    attempt_errors=tuple(errors),
                )
                write_json(destination.with_suffix(destination.suffix + ".meta.json"), record.as_dict(destination.parent.parent.parent))
                return record
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < config.retries:
                time.sleep(config.backoff_seconds * attempt)
    if cache_path is not None and cache_path.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_path, destination)
        payload = destination.read_bytes()
        record = AcquisitionRecord(
            source_id=source_id,
            url=url,
            final_url=url,
            path=destination,
            status="stale_cache",
            status_code=None,
            content_type=None,
            bytes=len(payload),
            sha256=sha256_bytes(payload),
            retrieved_at=utc_now(),
            attempt_errors=tuple(errors),
        )
        write_json(destination.with_suffix(destination.suffix + ".meta.json"), record.as_dict(destination.parent.parent.parent))
        return record
    raise AcquisitionError(
        source_id=source_id,
        url=url,
        attempt_errors=tuple(errors),
        retrieved_at=utc_now(),
    )


def fetch_json_pages(
    config: Step2Config,
    *,
    source_id: str,
    base_url: str,
    destination_dir: Path,
    cache_dir: Path,
) -> list[AcquisitionRecord]:
    records: list[AcquisitionRecord] = []
    page = 1
    pages = 1
    while page <= pages:
        url = add_query(base_url, format="json", per_page=config.per_page, page=page)
        destination = destination_dir / f"page_{page:04d}.json"
        cache_path = cache_dir / source_id / f"page_{page:04d}.json"
        record = fetch_url(
            config,
            source_id=f"{source_id}_page_{page}",
            url=url,
            destination=destination,
            cache_path=cache_path,
            accept="application/json,text/json,*/*;q=0.1",
        )
        records.append(record)
        try:
            parsed = json.loads(destination.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {destination}: {exc}") from exc
        metadata = _page_metadata(parsed)
        pages = max(1, int(metadata.get("pages", 1)))
        page += 1
    return records


def _page_metadata(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}
