from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

PROVIDER = "EUROSTAT"
DATASET = "prc_hicp_fp"
SNAPSHOT_KIND = "OFFICIAL_FIRST_PUBLISHED_HICP"
TEST_SNAPSHOT_KIND = "TEST_FIRST_PUBLISHED_HICP"
CAPABILITY = "OFFICIAL_FIRST_PUBLISHED_HICP_PANEL"
VINTAGE_CLASS = "FIRST_PUBLISHED_FULL_DATA_RELEASE"
PERIOD_PATTERN = re.compile(r"^\d{4}-\d{2}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CATEGORIES = tuple(f"CP{index:02d}" for index in range(13))


class FirstPublishedError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class Economy:
    armilar_code: str
    eurostat_code: str
    name: str


@dataclass(frozen=True)
class FirstPublishedPolicy:
    policy_version: str
    universe_id: str
    provider: str
    dataset: str
    api_base: str
    frequency: str
    start_period: str
    end_period: str
    categories: tuple[str, ...]
    economies: tuple[Economy, ...]
    preferred_unit_label_tokens: tuple[str, ...]
    preferred_release_label: str
    probe_period: str
    request_timeout_seconds: int
    max_response_bytes: int
    required_information_set_policy_version: str
    required_vertical_policy_version: str
    historical_value_vintages_available: bool
    publication_aware_model_comparison_allowed: bool
    model_promotion_allowed: bool
    research_release_allowed: bool
    monetary_release_allowed: bool
    policy_sha256: str

    @classmethod
    def load(cls, path: Path | str) -> "FirstPublishedPolicy":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FirstPublishedError("POLICY_INVALID", str(source)) from exc
        required = {
            "policy_version",
            "universe_id",
            "provider",
            "dataset",
            "api_base",
            "frequency",
            "start_period",
            "end_period",
            "categories",
            "economies",
            "preferred_unit_label_tokens",
            "preferred_release_label",
            "probe_period",
            "request_timeout_seconds",
            "max_response_bytes",
            "required_information_set_policy_version",
            "required_vertical_policy_version",
            "historical_value_vintages_available",
            "publication_aware_model_comparison_allowed",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise FirstPublishedError("POLICY_FIELD_MISSING", ",".join(missing))
        if payload["provider"] != PROVIDER or payload["dataset"] != DATASET:
            raise FirstPublishedError("SOURCE_CONTRACT_MISMATCH")
        if not str(payload["api_base"]).startswith(
            "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_fp"
        ):
            raise FirstPublishedError("API_BASE_NOT_OFFICIAL")
        for field in ("start_period", "end_period", "probe_period"):
            if not PERIOD_PATTERN.fullmatch(str(payload[field])):
                raise FirstPublishedError("PERIOD_INVALID", f"{field}={payload[field]}")
        if payload["start_period"] > payload["end_period"]:
            raise FirstPublishedError("PERIOD_RANGE_INVALID")
        if not (payload["start_period"] <= payload["probe_period"] <= payload["end_period"]):
            raise FirstPublishedError("PROBE_PERIOD_OUTSIDE_RANGE")
        categories = tuple(str(value) for value in payload["categories"])
        if categories != REQUIRED_CATEGORIES:
            raise FirstPublishedError("CATEGORY_UNIVERSE_MISMATCH", str(categories))
        economies = tuple(
            Economy(
                armilar_code=str(item["armilar_code"]),
                eurostat_code=str(item["eurostat_code"]),
                name=str(item["name"]),
            )
            for item in payload["economies"]
        )
        if tuple(item.armilar_code for item in economies) != ("DEU", "ESP", "FRA", "ITA", "PRT"):
            raise FirstPublishedError("ECONOMY_UNIVERSE_MISMATCH")
        if len({item.eurostat_code for item in economies}) != len(economies):
            raise FirstPublishedError("DUPLICATE_EUROSTAT_GEO")
        tokens = tuple(str(value).strip().lower() for value in payload["preferred_unit_label_tokens"])
        if not tokens or any(not value for value in tokens):
            raise FirstPublishedError("UNIT_LABEL_TOKENS_INVALID")
        if not bool(payload["historical_value_vintages_available"]):
            raise FirstPublishedError("FIRST_PUBLISHED_CAPABILITY_MUST_BE_ENABLED")
        for field in (
            "publication_aware_model_comparison_allowed",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        ):
            if bool(payload[field]):
                raise FirstPublishedError("RELEASE_GATE_MUST_BE_FALSE", field)
        timeout = int(payload["request_timeout_seconds"])
        max_bytes = int(payload["max_response_bytes"])
        if timeout <= 0 or max_bytes <= 0:
            raise FirstPublishedError("REQUEST_LIMIT_INVALID")
        return cls(
            policy_version=str(payload["policy_version"]),
            universe_id=str(payload["universe_id"]),
            provider=str(payload["provider"]),
            dataset=str(payload["dataset"]),
            api_base=str(payload["api_base"]),
            frequency=str(payload["frequency"]),
            start_period=str(payload["start_period"]),
            end_period=str(payload["end_period"]),
            categories=categories,
            economies=economies,
            preferred_unit_label_tokens=tokens,
            preferred_release_label=str(payload["preferred_release_label"]).strip(),
            probe_period=str(payload["probe_period"]),
            request_timeout_seconds=timeout,
            max_response_bytes=max_bytes,
            required_information_set_policy_version=str(payload["required_information_set_policy_version"]),
            required_vertical_policy_version=str(payload["required_vertical_policy_version"]),
            historical_value_vintages_available=True,
            publication_aware_model_comparison_allowed=False,
            model_promotion_allowed=False,
            research_release_allowed=False,
            monetary_release_allowed=False,
            policy_sha256=_sha256(source.read_bytes()),
        )

    @property
    def geo_map(self) -> Mapping[str, Economy]:
        return {item.eurostat_code: item for item in self.economies}


@dataclass(frozen=True)
class Observation:
    economy_code: str
    economy_name: str
    eurostat_geo: str
    source_category: str
    period: str
    value: Decimal
    status: str
    request_id: str
    raw_file: str
    raw_sha256: str


def _installed_version() -> str:
    try:
        return metadata.version("armilar-data-pipeline")
    except metadata.PackageNotFoundError:
        return "0.9.3"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _resolve_inside(root: Path, relative: str, code: str) -> Path:
    candidate = (root / relative).resolve()
    resolved = root.resolve()
    if candidate != resolved and resolved not in candidate.parents:
        raise FirstPublishedError(code, relative)
    return candidate


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    _atomic_write(root / "MANIFEST.sha256", (("\n".join(lines) + "\n") if lines else "").encode("utf-8"))


def verify_manifest(root: Path | str) -> None:
    base = Path(root)
    manifest = base / "MANIFEST.sha256"
    if not manifest.is_file():
        raise FirstPublishedError("MANIFEST_MISSING", str(manifest))
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not HEX64.fullmatch(parts[0].lower()):
            raise FirstPublishedError("MANIFEST_INVALID", raw_line)
        expected, relative = parts[0].lower(), parts[1].strip()
        target = _resolve_inside(base, relative, "MANIFEST_PATH_INVALID")
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise FirstPublishedError("MANIFEST_HASH_MISMATCH", relative)


def iter_periods(start: str, end: str) -> tuple[str, ...]:
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    result: list[str] = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(result)


def _dimension_codes(dimension: Mapping[str, Any], dim_id: str, expected_size: int) -> list[str]:
    try:
        index = dimension[dim_id]["category"]["index"]
    except (KeyError, TypeError) as exc:
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"missing {dim_id} index") from exc
    if isinstance(index, list):
        codes = [str(value) for value in index]
    elif isinstance(index, Mapping):
        codes = [""] * expected_size
        for code, position in index.items():
            pos = int(position)
            if pos < 0 or pos >= expected_size or codes[pos]:
                raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"invalid {dim_id} position")
            codes[pos] = str(code)
    else:
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"unsupported {dim_id} index")
    if len(codes) != expected_size or any(not code for code in codes):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"{dim_id} size mismatch")
    return codes


def _dimension_labels(dimension: Mapping[str, Any], dim_id: str, codes: Sequence[str]) -> Mapping[str, str]:
    try:
        labels = dimension[dim_id]["category"].get("label", {})
    except (KeyError, TypeError) as exc:
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"missing {dim_id} labels") from exc
    if not isinstance(labels, Mapping):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"invalid {dim_id} labels")
    return {code: str(labels.get(code, code)) for code in codes}


def _decode_jsonstat(data: bytes) -> tuple[list[str], list[int], Mapping[str, Any], Any, Any]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", "invalid JSON") from exc
    ids, sizes = payload.get("id"), payload.get("size")
    dimension, values, statuses = payload.get("dimension"), payload.get("value"), payload.get("status", {})
    if not isinstance(ids, list) or not isinstance(sizes, list) or len(ids) != len(sizes):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", "invalid id/size")
    if not isinstance(dimension, Mapping):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", "missing dimension")
    return [str(value) for value in ids], [int(value) for value in sizes], dimension, values, statuses


def discover_codes(data: bytes, policy: FirstPublishedPolicy) -> tuple[str, str, Mapping[str, str]]:
    ids, sizes, dimension, _values, _statuses = _decode_jsonstat(data)
    required = {"freq", "unit", "coicop", "release", "geo", "time"}
    if not required.issubset(ids):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"missing={sorted(required-set(ids))}")
    code_map = {
        dim_id: _dimension_codes(dimension, dim_id, sizes[position])
        for position, dim_id in enumerate(ids)
    }
    unit_labels = _dimension_labels(dimension, "unit", code_map["unit"])
    release_labels = _dimension_labels(dimension, "release", code_map["release"])
    unit_candidates = [
        code for code, label in unit_labels.items()
        if all(token in label.lower().replace(" ", "") for token in (token.replace(" ", "") for token in policy.preferred_unit_label_tokens))
    ]
    if len(unit_candidates) != 1:
        raise FirstPublishedError("UNIT_DISCOVERY_AMBIGUOUS", json.dumps(unit_labels, sort_keys=True))
    preferred_release = policy.preferred_release_label.casefold()
    release_candidates = [
        code for code, label in release_labels.items()
        if label.strip().casefold() == preferred_release
        or preferred_release in label.strip().casefold()
    ]
    if len(release_candidates) != 1:
        raise FirstPublishedError("RELEASE_DISCOVERY_AMBIGUOUS", json.dumps(release_labels, sort_keys=True))
    selected = {
        "unit_code": unit_candidates[0],
        "unit_label": unit_labels[unit_candidates[0]],
        "release_code": release_candidates[0],
        "release_label": release_labels[release_candidates[0]],
    }
    return unit_candidates[0], release_candidates[0], selected


def _url(policy: FirstPublishedPolicy, params: Sequence[tuple[str, str]]) -> str:
    return policy.api_base + "?" + urllib.parse.urlencode(params)


def build_probe_url(policy: FirstPublishedPolicy) -> str:
    economy = policy.economies[0]
    params = [
        ("format", "JSON"),
        ("lang", "EN"),
        ("freq", policy.frequency),
        ("geo", economy.eurostat_code),
        ("coicop", "CP00"),
        ("sinceTimePeriod", policy.probe_period),
        ("untilTimePeriod", policy.probe_period),
    ]
    return _url(policy, params)


def build_data_url(policy: FirstPublishedPolicy, unit_code: str, release_code: str) -> str:
    params: list[tuple[str, str]] = [
        ("format", "JSON"),
        ("lang", "EN"),
        ("freq", policy.frequency),
        ("unit", unit_code),
        ("release", release_code),
    ]
    params.extend(("coicop", category) for category in policy.categories)
    params.extend(("geo", economy.eurostat_code) for economy in policy.economies)
    params.extend((("sinceTimePeriod", policy.start_period), ("untilTimePeriod", policy.end_period)))
    return _url(policy, params)


def _fetch(url: str, policy: FirstPublishedPolicy, opener: Any) -> tuple[bytes, Mapping[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "armilar-data-pipeline/0.9.3"},
        method="GET",
    )
    try:
        with opener(request, timeout=policy.request_timeout_seconds) as response:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            content_type = str(response.headers.get("Content-Type", ""))
            data = response.read(policy.max_response_bytes + 1)
            final_url = str(getattr(response, "url", url))
            headers = {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FirstPublishedError("NETWORK_BLOCKED", str(exc)) from exc
    if status != 200:
        raise FirstPublishedError("PROVIDER_HTTP_ERROR", f"HTTP {status}")
    if not data:
        raise FirstPublishedError("EMPTY_PROVIDER_RESPONSE")
    if len(data) > policy.max_response_bytes:
        raise FirstPublishedError("PROVIDER_RESPONSE_TOO_LARGE")
    if "json" not in content_type.lower() and not data.lstrip().startswith(b"{"):
        raise FirstPublishedError("PROVIDER_CONTENT_TYPE_MISMATCH", content_type)
    return data, {
        "request_url": url,
        "final_url": final_url,
        "http_status": status,
        "content_type": content_type,
        **headers,
    }


def acquire_snapshot(
    policy_path: Path | str,
    snapshot_dir: Path | str,
    *,
    retrieved_at: str | None = None,
    opener: Any = urllib.request.urlopen,
) -> Mapping[str, Any]:
    policy = FirstPublishedPolicy.load(policy_path)
    root = Path(snapshot_dir)
    if root.exists() and any(root.iterdir()):
        raise FirstPublishedError("OUTPUT_DIRECTORY_NOT_EMPTY", str(root))
    root.mkdir(parents=True, exist_ok=True)
    retrieved = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    probe_url = build_probe_url(policy)
    probe_data, probe_receipt = _fetch(probe_url, policy, opener)
    unit_code, release_code, selected = discover_codes(probe_data, policy)
    data_url = build_data_url(policy, unit_code, release_code)
    main_data, main_receipt = _fetch(data_url, policy, opener)
    requests: list[dict[str, Any]] = []
    for request_id, data, receipt in (
        ("structure_probe", probe_data, probe_receipt),
        ("first_published_panel", main_data, main_receipt),
    ):
        digest = _sha256(data)
        relative = Path("raw") / "eurostat" / policy.dataset / f"{request_id}.{digest[:16]}.json"
        _atomic_write(root / relative, data)
        requests.append(
            {
                "request_id": request_id,
                "provider": PROVIDER,
                "dataset": policy.dataset,
                "retrieved_at": retrieved,
                "raw_file": relative.as_posix(),
                "raw_sha256": digest,
                "raw_bytes": len(data),
                **receipt,
            }
        )
    manifest = {
        "snapshot_schema_version": "1.0",
        "provider": PROVIDER,
        "dataset": policy.dataset,
        "snapshot_kind": SNAPSHOT_KIND,
        "policy_version": policy.policy_version,
        "policy_sha256": policy.policy_sha256,
        "universe_id": policy.universe_id,
        "retrieved_at": retrieved,
        "selected_codes": selected,
        "requests": requests,
    }
    _atomic_write(root / "snapshot_manifest.json", _canonical_json(manifest))
    _write_manifest(root)
    return manifest


def parse_observations(data: bytes, request: Mapping[str, Any], policy: FirstPublishedPolicy, *, unit_code: str, release_code: str) -> tuple[Observation, ...]:
    ids, sizes, dimension, values, statuses = _decode_jsonstat(data)
    required = {"freq", "unit", "coicop", "release", "geo", "time"}
    if not required.issubset(ids):
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", f"missing={sorted(required-set(ids))}")
    codes = {
        dim_id: _dimension_codes(dimension, dim_id, sizes[position])
        for position, dim_id in enumerate(ids)
    }
    if isinstance(values, list):
        value_at = lambda index: values[index] if index < len(values) else None
    elif isinstance(values, Mapping):
        value_at = lambda index: values.get(str(index), values.get(index))
    else:
        raise FirstPublishedError("PROVIDER_SCHEMA_UNRESOLVED", "invalid values")
    if isinstance(statuses, list):
        status_at = lambda index: statuses[index] if index < len(statuses) else ""
    elif isinstance(statuses, Mapping):
        status_at = lambda index: statuses.get(str(index), statuses.get(index, ""))
    else:
        status_at = lambda index: ""
    total_size = math.prod(sizes)
    geo_map = policy.geo_map
    rows: list[Observation] = []
    for linear in range(total_size):
        raw_value = value_at(linear)
        if raw_value is None:
            continue
        remainder = linear
        positions = [0] * len(sizes)
        for position in range(len(sizes) - 1, -1, -1):
            positions[position] = remainder % sizes[position]
            remainder //= sizes[position]
        coordinate = {dim_id: codes[dim_id][positions[position]] for position, dim_id in enumerate(ids)}
        if coordinate["freq"] != policy.frequency or coordinate["unit"] != unit_code or coordinate["release"] != release_code:
            continue
        if coordinate["coicop"] not in policy.categories or coordinate["geo"] not in geo_map:
            continue
        period = coordinate["time"]
        if period < policy.start_period or period > policy.end_period:
            continue
        try:
            value = Decimal(str(raw_value))
        except InvalidOperation as exc:
            raise FirstPublishedError("INVALID_PRICE_VALUE", f"{coordinate}") from exc
        if not value.is_finite() or value <= 0:
            raise FirstPublishedError("INVALID_PRICE_VALUE", f"{coordinate}")
        economy = geo_map[coordinate["geo"]]
        rows.append(
            Observation(
                economy_code=economy.armilar_code,
                economy_name=economy.name,
                eurostat_geo=economy.eurostat_code,
                source_category=coordinate["coicop"],
                period=period,
                value=value,
                status=str(status_at(linear) or ""),
                request_id=str(request["request_id"]),
                raw_file=str(request["raw_file"]),
                raw_sha256=str(request["raw_sha256"]),
            )
        )
    expected = {
        (economy.armilar_code, category, period)
        for economy in policy.economies
        for category in policy.categories
        for period in iter_periods(policy.start_period, policy.end_period)
    }
    observed = {(row.economy_code, row.source_category, row.period) for row in rows}
    if len(observed) != len(rows):
        raise FirstPublishedError("DUPLICATE_OBSERVATION")
    missing, extra = sorted(expected - observed), sorted(observed - expected)
    if missing or extra:
        raise FirstPublishedError("FIRST_PUBLISHED_GRID_INCOMPLETE", f"missing={len(missing)} sample={missing[:5]} extra={len(extra)}")
    return tuple(sorted(rows, key=lambda row: (row.period, row.economy_code, row.source_category)))


def load_snapshot(policy: FirstPublishedPolicy, snapshot_dir: Path | str) -> tuple[tuple[Observation, ...], Mapping[str, Any]]:
    root = Path(snapshot_dir)
    verify_manifest(root)
    manifest = json.loads((root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("snapshot_kind") not in {SNAPSHOT_KIND, TEST_SNAPSHOT_KIND}:
        raise FirstPublishedError("SNAPSHOT_KIND_INVALID")
    if manifest.get("policy_sha256") != policy.policy_sha256:
        raise FirstPublishedError("SNAPSHOT_POLICY_MISMATCH")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or len(requests) != 2:
        raise FirstPublishedError("SNAPSHOT_MANIFEST_INVALID")
    request_map = {str(item.get("request_id")): item for item in requests}
    if set(request_map) != {"structure_probe", "first_published_panel"}:
        raise FirstPublishedError("SNAPSHOT_REQUEST_SET_INVALID")
    selected = manifest.get("selected_codes")
    if not isinstance(selected, Mapping):
        raise FirstPublishedError("SELECTED_CODES_MISSING")
    unit_code, release_code = str(selected.get("unit_code", "")), str(selected.get("release_code", ""))
    if not unit_code or not release_code:
        raise FirstPublishedError("SELECTED_CODES_MISSING")
    probe_request = request_map["structure_probe"]
    probe_path = _resolve_inside(root, str(probe_request["raw_file"]), "RAW_PATH_INVALID")
    probe_data = probe_path.read_bytes()
    if _sha256(probe_data) != probe_request.get("raw_sha256"):
        raise FirstPublishedError("REPLAY_HASH_MISMATCH", str(probe_path))
    discovered_unit, discovered_release, _ = discover_codes(probe_data, policy)
    if (unit_code, release_code) != (discovered_unit, discovered_release):
        raise FirstPublishedError("DISCOVERED_CODE_MISMATCH")
    data_request = request_map["first_published_panel"]
    data_path = _resolve_inside(root, str(data_request["raw_file"]), "RAW_PATH_INVALID")
    data = data_path.read_bytes()
    if _sha256(data) != data_request.get("raw_sha256"):
        raise FirstPublishedError("REPLAY_HASH_MISMATCH", str(data_path))
    return parse_observations(data, data_request, policy, unit_code=unit_code, release_code=release_code), manifest


def _load_information_set(policy: FirstPublishedPolicy, root: Path) -> tuple[Mapping[tuple[str, str], Mapping[str, str]], Mapping[str, str], Mapping[str, Any]]:
    verify_manifest(root)
    summary = json.loads((root / "run_summary.json").read_text(encoding="utf-8"))
    if summary.get("policy_version") != policy.required_information_set_policy_version:
        raise FirstPublishedError("INFORMATION_SET_POLICY_MISMATCH")
    if summary.get("universe_id") != policy.universe_id or summary.get("source_category") != "CP00":
        raise FirstPublishedError("INFORMATION_SET_UNIVERSE_MISMATCH")
    if summary.get("research_release_allowed") is not False or summary.get("monetary_release_allowed") is not False:
        raise FirstPublishedError("INPUT_RELEASE_GATE_OPEN")
    path = root / "cp00_publication_availability.csv"
    by_cell: dict[tuple[str, str], Mapping[str, str]] = {}
    by_period: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"economy_code", "reference_period", "available_from_date", "price_relative", "economy_fixed_universe_weight"}
        if not required.issubset(set(reader.fieldnames or ())):
            raise FirstPublishedError("INFORMATION_SET_SCHEMA_INVALID")
        for row in reader:
            key = (str(row["economy_code"]), str(row["reference_period"]))
            if key in by_cell:
                raise FirstPublishedError("DUPLICATE_INFORMATION_SET_CELL", "/".join(key))
            by_cell[key] = row
            period = key[1]
            date_value = str(row["available_from_date"])
            if period in by_period and by_period[period] != date_value:
                raise FirstPublishedError("RELEASE_DATE_INCONSISTENT", period)
            by_period[period] = date_value
    expected = {(economy.armilar_code, period) for economy in policy.economies for period in iter_periods(policy.start_period, policy.end_period)}
    if set(by_cell) != expected:
        raise FirstPublishedError("INFORMATION_SET_GRID_INCOMPLETE")
    return by_cell, by_period, summary


def _load_vertical(policy: FirstPublishedPolicy, root: Path) -> tuple[Mapping[tuple[str, str, str], Mapping[str, str]], Mapping[tuple[str, str], Decimal], Mapping[str, Decimal], Mapping[str, Any]]:
    verify_manifest(root)
    summary = json.loads((root / "run_summary.json").read_text(encoding="utf-8"))
    if summary.get("universe_id") != policy.universe_id:
        raise FirstPublishedError("VERTICAL_UNIVERSE_MISMATCH")
    observations: dict[tuple[str, str, str], Mapping[str, str]] = {}
    with (root / "normalized_price_observations.csv").open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"economy_code", "source_category", "period", "price_relative", "fixed_universe_weight"}
        if not required.issubset(set(reader.fieldnames or ())):
            raise FirstPublishedError("VERTICAL_SCHEMA_INVALID")
        for row in reader:
            category = str(row["source_category"])
            if category not in REQUIRED_CATEGORIES[1:]:
                continue
            key = (str(row["economy_code"]), category, str(row["period"]))
            if key in observations:
                raise FirstPublishedError("DUPLICATE_VERTICAL_CELL", "/".join(key))
            observations[key] = row
    weights: dict[tuple[str, str], Decimal] = {}
    economy_totals: MutableMapping[str, Decimal] = {economy.armilar_code: Decimal("0") for economy in policy.economies}
    with (root / "fixed_universe_weights.csv").open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"economy_code", "source_category", "fixed_universe_weight"}
        if not required.issubset(set(reader.fieldnames or ())):
            raise FirstPublishedError("WEIGHT_SCHEMA_INVALID")
        for row in reader:
            economy, category = str(row["economy_code"]), str(row["source_category"])
            if economy not in economy_totals or category not in REQUIRED_CATEGORIES[1:]:
                continue
            key = (economy, category)
            if key in weights:
                raise FirstPublishedError("DUPLICATE_WEIGHT", "/".join(key))
            try:
                value = Decimal(str(row["fixed_universe_weight"]))
            except InvalidOperation as exc:
                raise FirstPublishedError("INVALID_WEIGHT", "/".join(key)) from exc
            if not value.is_finite() or value <= 0:
                raise FirstPublishedError("INVALID_WEIGHT", "/".join(key))
            weights[key] = value
            economy_totals[economy] += value
    expected_weights = {(economy.armilar_code, category) for economy in policy.economies for category in REQUIRED_CATEGORIES[1:]}
    if set(weights) != expected_weights:
        raise FirstPublishedError("WEIGHT_GRID_INCOMPLETE")
    if abs(sum(weights.values(), Decimal("0")) - Decimal("1")) > Decimal("1e-18"):
        raise FirstPublishedError("WEIGHTS_DO_NOT_SUM_TO_ONE")
    expected_obs = {(economy.armilar_code, category, period) for economy in policy.economies for category in REQUIRED_CATEGORIES[1:] for period in iter_periods(policy.start_period, policy.end_period)}
    if set(observations) != expected_obs:
        raise FirstPublishedError("VERTICAL_GRID_INCOMPLETE", f"observed={len(observations)} expected={len(expected_obs)}")
    return observations, weights, dict(economy_totals), summary


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FirstPublishedError(code, detail) from exc
    if not parsed.is_finite():
        raise FirstPublishedError(code, detail)
    return parsed


def _text(value: Decimal, places: int = 12) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def build_first_published_panel(
    policy_path: Path | str,
    snapshot_dir: Path | str,
    information_set_dir: Path | str,
    vertical_output_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = FirstPublishedPolicy.load(policy_path)
    observations, snapshot = load_snapshot(policy, snapshot_dir)
    info_cells, release_dates, info_summary = _load_information_set(policy, Path(information_set_dir))
    final_categories, weights, economy_weights, vertical_summary = _load_vertical(policy, Path(vertical_output_dir))
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FirstPublishedError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)
    base_periods = tuple(period for period in iter_periods(policy.start_period, policy.end_period) if period.startswith("2021-"))
    if len(base_periods) != 12:
        raise FirstPublishedError("BASE_YEAR_INCOMPLETE")
    by_cell = {(row.economy_code, row.source_category, row.period): row for row in observations}
    base_means: dict[tuple[str, str], Decimal] = {}
    for economy in policy.economies:
        for category in policy.categories:
            values = [by_cell[(economy.armilar_code, category, period)].value for period in base_periods]
            base_means[(economy.armilar_code, category)] = sum(values, Decimal("0")) / Decimal(12)
    panel_rows: list[dict[str, str]] = []
    revision_rows: list[dict[str, str]] = []
    index_accumulator: MutableMapping[str, dict[str, Decimal]] = {
        period: {"b0": Decimal("0"), "b1": Decimal("0"), "category": Decimal("0")}
        for period in iter_periods(policy.start_period, policy.end_period)
    }
    revision_values: list[Decimal] = []
    revised_count = 0
    for row in observations:
        relative = row.value / base_means[(row.economy_code, row.source_category)]
        available = release_dates[row.period]
        if row.source_category == "CP00":
            final_row = info_cells[(row.economy_code, row.period)]
            final_relative = _decimal(str(final_row["price_relative"]), "INVALID_FINAL_RELATIVE", f"{row.economy_code}/{row.period}")
            cell_weight = economy_weights[row.economy_code]
        else:
            final_row = final_categories[(row.economy_code, row.source_category, row.period)]
            final_relative = _decimal(str(final_row["price_relative"]), "INVALID_FINAL_RELATIVE", f"{row.economy_code}/{row.source_category}/{row.period}")
            cell_weight = weights[(row.economy_code, row.source_category)]
        delta_bps = (relative - final_relative) * Decimal("10000")
        revision_values.append(abs(delta_bps))
        if delta_bps != 0:
            revised_count += 1
        panel_rows.append(
            {
                "universe_id": policy.universe_id,
                "economy_code": row.economy_code,
                "economy_name": row.economy_name,
                "eurostat_geo": row.eurostat_geo,
                "source_category": row.source_category,
                "armilar_category": row.source_category,
                "period": row.period,
                "available_from_date": available,
                "price_value_first_published": _text(row.value, 8),
                "reference_period": "2021",
                "reference_price_value_first_published": _text(base_means[(row.economy_code, row.source_category)], 8),
                "price_relative_first_published": _text(relative, 12),
                "fixed_universe_weight": _text(cell_weight, 18),
                "economy_fixed_universe_weight": _text(economy_weights[row.economy_code], 18),
                "price_evidence_class": "P1_OFFICIAL_FIRST_PUBLISHED_HICP",
                "value_vintage_class": VINTAGE_CLASS,
                "provider": PROVIDER,
                "dataset": policy.dataset,
                "status": row.status,
                "request_id": row.request_id,
                "raw_file": row.raw_file,
                "raw_sha256": row.raw_sha256,
            }
        )
        revision_rows.append(
            {
                "economy_code": row.economy_code,
                "source_category": row.source_category,
                "period": row.period,
                "first_published_relative": _text(relative, 12),
                "current_final_relative": _text(final_relative, 12),
                "first_minus_final_relative_bps": _text(delta_bps, 8),
                "absolute_revision_bps": _text(abs(delta_bps), 8),
            }
        )
        if row.source_category == "CP00":
            index_accumulator[row.period]["b0"] += relative / Decimal(len(policy.economies))
            index_accumulator[row.period]["b1"] += relative * economy_weights[row.economy_code]
        else:
            index_accumulator[row.period]["category"] += relative * cell_weight
    index_rows = [
        {
            "period": period,
            "b0_equal_country_first_published_headline": _text(Decimal("100") * values["b0"], 12),
            "b1_armilar_weighted_first_published_headline": _text(Decimal("100") * values["b1"], 12),
            "b2_direct_first_published_category_index": _text(Decimal("100") * values["category"], 12),
            "value_vintage_class": VINTAGE_CLASS,
        }
        for period, values in sorted(index_accumulator.items())
    ]
    revision_sorted = sorted(revision_values)
    p95_index = max(0, math.ceil(Decimal("0.95") * Decimal(len(revision_sorted))) - 1)
    revision_summary = {
        "observation_count": len(panel_rows),
        "revised_observation_count": revised_count,
        "unchanged_observation_count": len(panel_rows) - revised_count,
        "mean_absolute_revision_bps": _text(sum(revision_values, Decimal("0")) / Decimal(len(revision_values)), 8),
        "p95_absolute_revision_bps": _text(revision_sorted[p95_index], 8),
        "maximum_absolute_revision_bps": _text(max(revision_values), 8),
        "interpretation": "Differences compare 2021-normalised first-published values with the current final snapshot. They include genuine revisions and any effects of rounding or historical corrections.",
    }
    _write_csv(
        output / "first_published_observations.csv",
        [
            "universe_id", "economy_code", "economy_name", "eurostat_geo", "source_category", "armilar_category", "period",
            "available_from_date", "price_value_first_published", "reference_period",
            "reference_price_value_first_published", "price_relative_first_published",
            "fixed_universe_weight", "economy_fixed_universe_weight", "price_evidence_class", "value_vintage_class",
            "provider", "dataset", "status", "request_id", "raw_file", "raw_sha256",
        ],
        panel_rows,
    )
    _write_csv(
        output / "first_published_monthly_indices.csv",
        ["period", "b0_equal_country_first_published_headline", "b1_armilar_weighted_first_published_headline", "b2_direct_first_published_category_index", "value_vintage_class"],
        index_rows,
    )
    _write_csv(
        output / "revision_audit.csv",
        ["economy_code", "source_category", "period", "first_published_relative", "current_final_relative", "first_minus_final_relative_bps", "absolute_revision_bps"],
        revision_rows,
    )
    _atomic_write(output / "revision_summary.json", _canonical_json(revision_summary))
    summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "status": "OFFICIAL_FIRST_PUBLISHED_HICP_PANEL_BUILT",
        "capability": CAPABILITY,
        "historical_value_vintages_available": True,
        "value_vintage_class": VINTAGE_CLASS,
        "provider": PROVIDER,
        "dataset": policy.dataset,
        "universe_id": policy.universe_id,
        "economy_count": len(policy.economies),
        "category_count": len(policy.categories),
        "period_count": len(iter_periods(policy.start_period, policy.end_period)),
        "observation_count": len(panel_rows),
        "start_period": policy.start_period,
        "end_period": policy.end_period,
        "release_timing_attached": True,
        "first_published_values_attached": True,
        "snapshot_manifest_sha256": _sha256((Path(snapshot_dir) / "MANIFEST.sha256").read_bytes()),
        "release_information_set_manifest_sha256": _sha256((Path(information_set_dir) / "MANIFEST.sha256").read_bytes()),
        "vertical_input_manifest_sha256": _sha256((Path(vertical_output_dir) / "MANIFEST.sha256").read_bytes()),
        "source_snapshot_retrieved_at": snapshot.get("retrieved_at"),
        "selected_codes": snapshot.get("selected_codes"),
        "information_set_policy_version": info_summary.get("policy_version"),
        "vertical_policy_version": vertical_summary.get("policy_version"),
        "publication_aware_model_comparison_allowed": False,
        "release_time_backtest_available_in_package": True,
        "model_code_changed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "run_summary.json", _canonical_json(summary))
    report = [
        "# Armilar v0.9.3 official first-published HICP panel",
        "",
        f"The panel contains {len(panel_rows)} official first-published observations for five economies, CP00-CP12 and {policy.start_period} to {policy.end_period}.",
        "",
        "## Capability gained",
        "",
        f"`{CAPABILITY}`",
        "",
        "The Eurostat first-published dataset preserves the values disseminated on the monthly full-data release date. The release-calendar evidence supplies the exact day of availability.",
        "",
        "## Remaining boundary",
        "",
        "This panel alone does not rerun B0-B4. The companion release-time backtest in this package evaluates missing-cell completion as of each target month's complete-data release. Pre-release forecasting and model promotion remain prohibited.",
        "",
        f"Mean absolute first-versus-final revision: {revision_summary['mean_absolute_revision_bps']} bps.",
        f"P95 absolute revision: {revision_summary['p95_absolute_revision_bps']} bps.",
        "",
        "`publication_aware_model_comparison_allowed=false`",
        "",
        "`model_promotion_allowed=false`",
        "",
        "`research_release_allowed=false`",
        "",
        "`monetary_release_allowed=false`",
    ]
    _atomic_write(output / "FIRST_PUBLISHED_PANEL_REPORT.md", ("\n".join(report) + "\n").encode("utf-8"))
    _write_manifest(output)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.3 official first-published HICP panel")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--policy", required=True)
    acquire.add_argument("--snapshot-dir", required=True)
    build = sub.add_parser("build")
    build.add_argument("--policy", required=True)
    build.add_argument("--snapshot-dir", required=True)
    build.add_argument("--information-set-dir", required=True)
    build.add_argument("--vertical-output-dir", required=True)
    build.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "acquire":
        result = acquire_snapshot(args.policy, args.snapshot_dir)
    elif args.command == "build":
        result = build_first_published_panel(
            args.policy,
            args.snapshot_dir,
            args.information_set_dir,
            args.vertical_output_dir,
            args.output_dir,
        )
    else:
        verify_manifest(args.root)
        result = {"status": "MANIFEST_VERIFIED", "root": args.root}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
