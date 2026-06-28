from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when the source catalogue is invalid."""


@dataclass(frozen=True)
class Source:
    source_id: str
    provider: str
    url: str
    mode: str
    required: bool
    filename: str | None
    timeout_seconds: int
    retries: int
    max_bytes: int
    expected_content_types: tuple[str, ...]
    purpose: str

    @property
    def hostname(self) -> str:
        return urlparse(self.url).hostname or ""


@dataclass(frozen=True)
class PipelineConfig:
    schema_version: str
    user_agent: str
    sources: tuple[Source, ...]


def _require(mapping: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing required field: {key}")
    value = mapping[key]
    if not isinstance(value, expected_type):
        raise ConfigError(f"Field {key!r} must be {expected_type.__name__}")
    return value


def load_config(path: str | Path) -> PipelineConfig:
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read configuration {config_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ConfigError("Configuration root must be an object")

    schema_version = _require(payload, "schema_version", str)
    user_agent = _require(payload, "user_agent", str)
    raw_sources = _require(payload, "sources", list)

    sources: list[Source] = []
    seen_ids: set[str] = set()
    seen_filenames: set[str] = set()

    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ConfigError(f"sources[{index}] must be an object")

        source_id = _require(raw, "id", str)
        if source_id in seen_ids:
            raise ConfigError(f"Duplicate source id: {source_id}")
        seen_ids.add(source_id)

        provider = _require(raw, "provider", str)
        url = _require(raw, "url", str)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ConfigError(f"Source {source_id} must use an absolute HTTPS URL")

        mode = raw.get("mode", "download")
        if mode not in {"download", "probe"}:
            raise ConfigError(f"Source {source_id} has unsupported mode: {mode}")

        required = bool(raw.get("required", False))
        filename = raw.get("filename")
        if mode == "download":
            if not isinstance(filename, str) or not filename.strip():
                raise ConfigError(f"Download source {source_id} requires filename")
            path_obj = Path(filename)
            if path_obj.is_absolute() or ".." in path_obj.parts:
                raise ConfigError(f"Unsafe filename for {source_id}: {filename}")
            if filename in seen_filenames:
                raise ConfigError(f"Duplicate output filename: {filename}")
            seen_filenames.add(filename)
        elif filename is not None and not isinstance(filename, str):
            raise ConfigError(f"filename for {source_id} must be a string or null")

        timeout_seconds = int(raw.get("timeout_seconds", 30))
        retries = int(raw.get("retries", 3))
        max_bytes = int(raw.get("max_bytes", 50_000_000))
        if timeout_seconds < 1 or timeout_seconds > 300:
            raise ConfigError(f"Invalid timeout for {source_id}")
        if retries < 0 or retries > 10:
            raise ConfigError(f"Invalid retries for {source_id}")
        if max_bytes < 1:
            raise ConfigError(f"Invalid max_bytes for {source_id}")

        expected = raw.get("expected_content_types", [])
        if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
            raise ConfigError(f"expected_content_types for {source_id} must be a list of strings")

        purpose = str(raw.get("purpose", ""))
        sources.append(
            Source(
                source_id=source_id,
                provider=provider,
                url=url,
                mode=mode,
                required=required,
                filename=filename,
                timeout_seconds=timeout_seconds,
                retries=retries,
                max_bytes=max_bytes,
                expected_content_types=tuple(expected),
                purpose=purpose,
            )
        )

    if not sources:
        raise ConfigError("At least one source is required")

    return PipelineConfig(
        schema_version=schema_version,
        user_agent=user_agent,
        sources=tuple(sources),
    )
