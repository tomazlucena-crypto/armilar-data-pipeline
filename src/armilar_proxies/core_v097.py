"""Closed source-registry primitives for ARMILAR v0.9.7."""
from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

REGISTRY_VERSION = "0.9.7"
PARSER_VERSION = "0.9.7"
LEDGER_VERSION = "1.0"
UTF8_BOM = b"\xef\xbb\xbf"
MAX_XLSX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
ALLOWED_FREQUENCIES = {"WEEKLY", "MONTHLY", "QUARTERLY"}
ALLOWED_PUBLICATION_STATUSES = {
    "EXACT_TIMESTAMP",
    "RELEASE_DATE_ONLY",
    "SNAPSHOT_PAGE_DATE_ONLY",
    "UNRESOLVED",
}
ALLOWED_SOURCE_STATUSES = {
    "ACTIVE_RESEARCH_PROXY",
    "ACTIVE_SENSITIVITY_ONLY",
    "DEFERRED",
    "REJECTED",
}
ALLOWED_LICENSE_STATUSES = {
    "COMMERCIAL_REUSE_ALLOWED_WITH_ATTRIBUTION",
    "REUSE_ALLOWED_WITH_ATTRIBUTION",
    "REVIEW_REQUIRED",
}


class ProxyRegistryError(RuntimeError):
    """Raised when a registry, source or snapshot violates the v0.9.7 contract."""


def canonical_text_bytes(payload: bytes) -> bytes:
    if payload.startswith(UTF8_BOM):
        raise ProxyRegistryError("UTF-8 BOM is forbidden for canonical ARMILAR files")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProxyRegistryError("canonical file is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, *, canonical_text: bool = False) -> str:
    payload = path.read_bytes()
    if canonical_text:
        payload = canonical_text_bytes(payload)
    return sha256_bytes(payload)


def utc_timestamp(value: str) -> str:
    text = value.strip()
    if not text:
        raise ProxyRegistryError("timestamp cannot be empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProxyRegistryError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ProxyRegistryError("timestamps must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def optional_utc_timestamp(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return utc_timestamp(str(value))


def slug_timestamp(value: str) -> str:
    return utc_timestamp(value).replace("-", "").replace(":", "").replace("Z", "Z")


def _timestamp_value(value: str) -> datetime:
    text = utc_timestamp(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _period_not_after_retrieval(period: str, frequency: str, retrieved_at: str) -> bool:
    retrieved = _timestamp_value(retrieved_at)
    if frequency == "WEEKLY":
        return date.fromisoformat(period) <= retrieved.date()
    if frequency == "MONTHLY":
        return period <= retrieved.strftime("%Y-%m")
    if frequency == "QUARTERLY":
        quarter = (retrieved.month - 1) // 3 + 1
        return period <= f"{retrieved.year}-Q{quarter}"
    raise ProxyRegistryError(f"unsupported frequency: {frequency}")


def decimal_text(value: Any) -> str:
    if value is None:
        raise ProxyRegistryError("numeric value is missing")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, bool):
        raise ProxyRegistryError("boolean is not a numeric observation")
    else:
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if not text or text in {"..", ":", "-", "—", "NA", "N/A", "nan", "None"}:
            raise ProxyRegistryError("numeric value is missing")
        if text.count(",") == 1 and "." not in text:
            text = text.replace(",", ".")
        text = text.replace(",", "")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ProxyRegistryError(f"invalid numeric value: {value!r}") from exc
    if not number.is_finite():
        raise ProxyRegistryError("non-finite numeric value")
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def normalise_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def parse_month(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    text = str(value or "").strip()
    candidates = [
        "%Y-%m",
        "%Y/%m",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b-%y",
        "%b %Y",
        "%B %Y",
        "%Y %b",
        "%Y %B",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{4})M(0[1-9]|1[0-2])", text, flags=re.I)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    raise ProxyRegistryError(f"cannot parse monthly period: {value!r}")


def parse_week(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ProxyRegistryError(f"cannot parse weekly date: {value!r}")


def parse_quarter(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "")
    for pattern in (r"(\d{4})Q([1-4])", r"(\d{4})-Q([1-4])", r"Q([1-4])(\d{4})"):
        match = re.fullmatch(pattern, text)
        if match:
            if pattern.startswith("Q"):
                return f"{match.group(2)}-Q{match.group(1)}"
            return f"{match.group(1)}-Q{match.group(2)}"
    raise ProxyRegistryError(f"cannot parse quarterly period: {value!r}")


def safe_child(root: Path, relative: str | Path) -> Path:
    candidate = (root / relative).resolve()
    resolved = root.resolve()
    if candidate != resolved and resolved not in candidate.parents:
        raise ProxyRegistryError(f"path escapes root: {relative}")
    return candidate


def _required_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProxyRegistryError(f"{label} must be an object")
    return value


def _required_string(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProxyRegistryError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def load_registry(path: Path) -> dict[str, Any]:
    try:
        payload = canonical_text_bytes(path.read_bytes())
        registry = json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxyRegistryError(f"cannot load registry: {path}") from exc
    validate_registry(registry)
    return registry


def validate_registry(registry: Any) -> None:
    root = _required_mapping(registry, "registry")
    if set(root) != {
        "registry_id",
        "registry_version",
        "constitutional_scope",
        "global_invariants",
        "sources",
    }:
        raise ProxyRegistryError("registry root keys do not match the closed v0.9.7 contract")
    if _required_string(root, "registry_version", "registry") != REGISTRY_VERSION:
        raise ProxyRegistryError("unexpected proxy registry version")
    invariants = _required_mapping(root.get("global_invariants"), "global_invariants")
    required_false = {
        "direct_index_use_allowed",
        "arm_l_use_allowed",
        "model_training_allowed",
        "shadow_production_allowed",
        "monetary_use_allowed",
        "live_acquisition_in_ci_allowed",
    }
    if set(invariants) != required_false | {"raw_snapshot_required", "replay_required"}:
        raise ProxyRegistryError("global invariant keys do not match the closed contract")
    for key in required_false:
        if invariants.get(key) is not False:
            raise ProxyRegistryError(f"global invariant {key} must remain false")
    for key in ("raw_snapshot_required", "replay_required"):
        if invariants.get(key) is not True:
            raise ProxyRegistryError(f"global invariant {key} must remain true")
    sources = root.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ProxyRegistryError("registry must contain at least one source")
    source_ids: set[str] = set()
    domains_seen: set[str] = set()
    for index, raw_source in enumerate(sources):
        source = _required_mapping(raw_source, f"sources[{index}]")
        required_keys = {
            "source_id",
            "authority",
            "dataset_name",
            "official_page_url",
            "data_url",
            "allowed_hosts",
            "transport",
            "raw_extension",
            "parser_id",
            "frequency",
            "proxy_domains",
            "source_status",
            "purpose",
            "geographic_scope",
            "publication_time_status",
            "historical_vintage_support",
            "expected_lag_days",
            "license",
            "attribution",
            "max_download_bytes",
            "content_type_allowlist",
            "series_selection",
            "direct_index_use_allowed",
            "arm_l_use_allowed",
            "model_training_allowed",
            "shadow_production_allowed",
            "monetary_use_allowed",
            "conceptual_limitations",
        }
        if set(source) != required_keys:
            missing = sorted(required_keys - set(source))
            extra = sorted(set(source) - required_keys)
            raise ProxyRegistryError(f"source keys mismatch for entry {index}; missing={missing}, extra={extra}")
        source_id = _required_string(source, "source_id", f"source[{index}]")
        if not re.fullmatch(r"[A-Z0-9_]+", source_id):
            raise ProxyRegistryError(f"invalid source_id: {source_id}")
        if source_id in source_ids:
            raise ProxyRegistryError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        for url_key in ("official_page_url", "data_url"):
            parsed = urllib.parse.urlparse(_required_string(source, url_key, source_id))
            if parsed.scheme != "https" or not parsed.hostname:
                raise ProxyRegistryError(f"{source_id}.{url_key} must be HTTPS")
        hosts = source.get("allowed_hosts")
        if not isinstance(hosts, list) or not hosts or any(not isinstance(item, str) or not item for item in hosts):
            raise ProxyRegistryError(f"{source_id}.allowed_hosts must be a non-empty string list")
        data_host = urllib.parse.urlparse(source["data_url"]).hostname
        if data_host not in hosts:
            raise ProxyRegistryError(f"{source_id} data host is absent from allowed_hosts")
        if source.get("transport") not in {"HTTP_CSV", "HTTP_XLSX", "EUROSTAT_JSONSTAT"}:
            raise ProxyRegistryError(f"unsupported transport for {source_id}")
        if source.get("raw_extension") not in {".csv", ".xlsx", ".json"}:
            raise ProxyRegistryError(f"unsupported raw extension for {source_id}")
        if source.get("frequency") not in ALLOWED_FREQUENCIES:
            raise ProxyRegistryError(f"unsupported frequency for {source_id}")
        domains = source.get("proxy_domains")
        if not isinstance(domains, list) or not domains or any(not isinstance(item, str) or not item for item in domains):
            raise ProxyRegistryError(f"{source_id}.proxy_domains must be a non-empty string list")
        domains_seen.update(domains)
        if source.get("source_status") not in ALLOWED_SOURCE_STATUSES:
            raise ProxyRegistryError(f"unsupported source_status for {source_id}")
        if source.get("publication_time_status") not in ALLOWED_PUBLICATION_STATUSES:
            raise ProxyRegistryError(f"unsupported publication_time_status for {source_id}")
        if not isinstance(source.get("historical_vintage_support"), bool):
            raise ProxyRegistryError(f"historical_vintage_support must be boolean for {source_id}")
        lag = source.get("expected_lag_days")
        if lag is not None and (not isinstance(lag, int) or lag < 0 or lag > 366):
            raise ProxyRegistryError(f"invalid expected_lag_days for {source_id}")
        license_info = _required_mapping(source.get("license"), f"{source_id}.license")
        if set(license_info) != {"name", "url", "commercial_reuse_status", "notes"}:
            raise ProxyRegistryError(f"closed license keys violated for {source_id}")
        if license_info.get("commercial_reuse_status") not in ALLOWED_LICENSE_STATUSES:
            raise ProxyRegistryError(f"invalid license status for {source_id}")
        max_bytes = source.get("max_download_bytes")
        if not isinstance(max_bytes, int) or max_bytes < 1024 or max_bytes > 256 * 1024 * 1024:
            raise ProxyRegistryError(f"invalid max_download_bytes for {source_id}")
        content_types = source.get("content_type_allowlist")
        if not isinstance(content_types, list) or not content_types:
            raise ProxyRegistryError(f"content_type_allowlist must be non-empty for {source_id}")
        if not isinstance(source.get("series_selection"), dict):
            raise ProxyRegistryError(f"series_selection must be an object for {source_id}")
        for gate in (
            "direct_index_use_allowed",
            "arm_l_use_allowed",
            "model_training_allowed",
            "shadow_production_allowed",
            "monetary_use_allowed",
        ):
            if source.get(gate) is not False:
                raise ProxyRegistryError(f"{source_id}.{gate} must remain false")
        limitations = source.get("conceptual_limitations")
        if not isinstance(limitations, list) or not limitations or any(not isinstance(item, str) or not item for item in limitations):
            raise ProxyRegistryError(f"{source_id}.conceptual_limitations must be a non-empty string list")
    mandatory_domains = {"ENERGY", "FUELS", "FOOD", "TRANSPORT", "HOUSING_OOH_SENSITIVITY"}
    if not mandatory_domains.issubset(domains_seen):
        raise ProxyRegistryError(f"mandatory proxy domains missing: {sorted(mandatory_domains - domains_seen)}")


def registry_hash(path: Path) -> str:
    return sha256_bytes(canonical_text_bytes(path.read_bytes()))


def source_by_id(registry: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    for source in registry["sources"]:
        if source["source_id"] == source_id:
            return dict(source)
    raise ProxyRegistryError(f"unknown source_id: {source_id}")


@dataclass(frozen=True)
class FetchResponse:
    body: bytes
    status: int
    final_url: str
    headers: dict[str, str]


class UrlLibFetcher:
    def fetch(self, source: Mapping[str, Any], *, timeout_seconds: int = 60) -> FetchResponse:
        request = urllib.request.Request(
            source["data_url"],
            headers={
                "User-Agent": "ARMILAR-Research-Proxy-Acquirer/0.9.7 (+https://github.com/tomazlucena-crypto/armilar-data-pipeline)",
                "Accept": ", ".join(source["content_type_allowlist"]),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is registry-validated HTTPS
                final_url = response.geturl()
                host = urllib.parse.urlparse(final_url).hostname
                if host not in source["allowed_hosts"]:
                    raise ProxyRegistryError(f"redirected to unapproved host: {host}")
                status = int(getattr(response, "status", 200))
                if status != 200:
                    raise ProxyRegistryError(f"unexpected HTTP status: {status}")
                limit = int(source["max_download_bytes"])
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise ProxyRegistryError(f"download exceeds max_download_bytes for {source['source_id']}")
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
        except urllib.error.URLError as exc:
            raise ProxyRegistryError(f"HTTP acquisition failed for {source['source_id']}: {exc}") from exc
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        allowlist = {item.lower() for item in source["content_type_allowlist"]}
        if content_type and content_type not in allowlist and "application/octet-stream" not in allowlist:
            raise ProxyRegistryError(f"unexpected content type {content_type!r} for {source['source_id']}")
        return FetchResponse(body=body, status=status, final_url=final_url, headers=headers)


def validate_raw_magic(source: Mapping[str, Any], payload: bytes) -> None:
    extension = source["raw_extension"]
    if extension == ".xlsx":
        if not payload.startswith(b"PK"):
            raise ProxyRegistryError("XLSX payload does not have ZIP magic")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                total = sum(info.file_size for info in archive.infolist())
                if total > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ProxyRegistryError("XLSX uncompressed size exceeds safety limit")
                if "[Content_Types].xml" not in archive.namelist():
                    raise ProxyRegistryError("XLSX package is missing [Content_Types].xml")
        except zipfile.BadZipFile as exc:
            raise ProxyRegistryError("invalid XLSX ZIP package") from exc
    elif extension == ".json":
        try:
            json.loads(payload.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProxyRegistryError("invalid JSON payload") from exc
    elif extension == ".csv":
        try:
            payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ProxyRegistryError("CSV payload is not UTF-8") from exc

