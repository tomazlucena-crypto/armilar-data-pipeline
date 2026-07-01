"""Replayable Eurostat HICP vertical slice for Armilar v0.8.7.

The module intentionally keeps live retrieval separate from deterministic replay.
Exact provider bytes are preserved before any parsing.  The primary index is a
PPP-weighted aggregation of local price relatives over a fixed economy-category
universe.  Current FX never enters this index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

try:
    from armilar_pipeline.version import build_user_agent, installed_version
except ModuleNotFoundError:  # Overlay-only validation before application to the repository.
    def installed_version() -> str:
        return "0+unknown"

    def build_user_agent(version: str | None = None) -> str:
        resolved = installed_version() if version is None else version
        return (
            f"ArmilarDataPipeline/{resolved} "
            "(+https://github.com/tomazlucena-crypto/armilar-data-pipeline)"
        )

getcontext().prec = 42

DATASET = "prc_hicp_midx"
PROVIDER = "EUROSTAT"
PARSER_ID = "armilar-eurostat-vertical"
OFFICIAL_SNAPSHOT_KIND = "OFFICIAL_PROVIDER_ACQUISITION"
TEST_SNAPSHOT_KIND = "SYNTHETIC_TEST_FIXTURE"
DEFAULT_API_BASE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    + DATASET
)
SOURCE_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
DEFAULT_CATEGORY_MAP = {
    "CP01": "ARM01",
    "CP02": "ARM02",
    "CP03": "ARM03",
    "CP04": "ARM04",
    "CP05": "ARM04",
    "CP06": "ARM05",
    "CP07": "ARM06",
    "CP08": "ARM06",
    "CP09": "ARM07",
    "CP10": "ARM07",
    "CP11": "ARM08",
    "CP12": "ARM09",
}


class EurostatVerticalError(RuntimeError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class Economy:
    eurostat_code: str
    armilar_code: str
    name: str


@dataclass(frozen=True)
class VerticalPolicy:
    policy_version: str
    universe_id: str
    dataset: str
    unit: str
    frequency: str
    classification_version: str
    reference_year: int
    start_period: str
    end_period: str
    economies: tuple[Economy, ...]
    source_categories: tuple[str, ...]
    category_map: Mapping[str, str]
    api_base: str
    price_concept: str
    weight_concept: str
    concept_alignment_status: str
    research_release_allowed: bool
    monetary_release_allowed: bool
    request_timeout_seconds: int
    max_response_bytes: int

    @classmethod
    def load(cls, path: Path | str) -> "VerticalPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "universe_id",
            "dataset",
            "unit",
            "frequency",
            "classification_version",
            "reference_year",
            "start_period",
            "end_period",
            "economies",
            "source_categories",
            "category_map",
            "price_concept",
            "weight_concept",
            "concept_alignment_status",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise EurostatVerticalError(
                "POLICY_FIELD_MISSING", f"missing policy fields: {', '.join(missing)}"
            )
        economies = tuple(
            Economy(
                eurostat_code=str(item["eurostat_code"]),
                armilar_code=str(item["armilar_code"]),
                name=str(item["name"]),
            )
            for item in payload["economies"]
        )
        policy = cls(
            policy_version=str(payload["policy_version"]),
            universe_id=str(payload["universe_id"]),
            dataset=str(payload["dataset"]),
            unit=str(payload["unit"]),
            frequency=str(payload["frequency"]),
            classification_version=str(payload["classification_version"]),
            reference_year=int(payload["reference_year"]),
            start_period=str(payload["start_period"]),
            end_period=str(payload["end_period"]),
            economies=economies,
            source_categories=tuple(str(x) for x in payload["source_categories"]),
            category_map={str(k): str(v) for k, v in payload["category_map"].items()},
            api_base=str(payload.get("api_base", DEFAULT_API_BASE)),
            price_concept=str(payload["price_concept"]),
            weight_concept=str(payload["weight_concept"]),
            concept_alignment_status=str(payload["concept_alignment_status"]),
            research_release_allowed=bool(payload["research_release_allowed"]),
            monetary_release_allowed=bool(payload["monetary_release_allowed"]),
            request_timeout_seconds=int(payload.get("request_timeout_seconds", 30)),
            max_response_bytes=int(payload.get("max_response_bytes", 25_000_000)),
        )
        policy.validate()
        return policy

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return {
            "policy_version": self.policy_version,
            "universe_id": self.universe_id,
            "dataset": self.dataset,
            "unit": self.unit,
            "frequency": self.frequency,
            "classification_version": self.classification_version,
            "reference_year": self.reference_year,
            "start_period": self.start_period,
            "end_period": self.end_period,
            "economies": [
                {
                    "eurostat_code": economy.eurostat_code,
                    "armilar_code": economy.armilar_code,
                    "name": economy.name,
                }
                for economy in self.economies
            ],
            "source_categories": list(self.source_categories),
            "category_map": dict(sorted(self.category_map.items())),
            "api_base": self.api_base,
            "price_concept": self.price_concept,
            "weight_concept": self.weight_concept,
            "concept_alignment_status": self.concept_alignment_status,
            "research_release_allowed": self.research_release_allowed,
            "monetary_release_allowed": self.monetary_release_allowed,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_response_bytes": self.max_response_bytes,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha256(_canonical_json_bytes(self.fingerprint_payload()))

    def validate(self) -> None:
        if self.dataset != DATASET:
            raise EurostatVerticalError(
                "SOURCE_CONCEPT_MISMATCH", f"expected dataset {DATASET}, got {self.dataset}"
            )
        if self.frequency != "M":
            raise EurostatVerticalError("SOURCE_CONCEPT_MISMATCH", "frequency must be M")
        if self.unit != "I15":
            raise EurostatVerticalError(
                "SOURCE_CONCEPT_MISMATCH", "v0.8.7 requires HICP unit I15"
            )
        if self.classification_version != "ECOICOP_V1_PRE_2026":
            raise EurostatVerticalError(
                "SOURCE_CONCEPT_MISMATCH",
                "v0.8.7 is bounded to the pre-2026 ECOICOP classification",
            )
        if self.end_period > "2025-12":
            raise EurostatVerticalError(
                "CLASSIFICATION_BREAK_UNRESOLVED",
                "data from 2026 onward require an explicit ECOICOP v2 mapping",
            )
        if self.research_release_allowed or self.monetary_release_allowed:
            raise EurostatVerticalError(
                "RELEASE_GATE_WEAKENED", "v0.8.7 release flags must remain false"
            )
        if not self.economies:
            raise EurostatVerticalError("EMPTY_UNIVERSE", "at least one economy is required")
        euro_codes = [e.eurostat_code for e in self.economies]
        armilar_codes = [e.armilar_code for e in self.economies]
        if len(set(euro_codes)) != len(euro_codes) or len(set(armilar_codes)) != len(armilar_codes):
            raise EurostatVerticalError("DUPLICATE_ECONOMY", "economy codes must be unique")
        if tuple(self.source_categories) != SOURCE_CATEGORIES:
            raise EurostatVerticalError(
                "SOURCE_CONCEPT_MISMATCH", "source categories must be CP01 through CP12"
            )
        if set(self.category_map) != set(SOURCE_CATEGORIES):
            raise EurostatVerticalError(
                "CLASSIFICATION_MAPPING_INCOMPLETE", "all source categories need a mapping"
            )
        for period in (self.start_period, self.end_period):
            _parse_period(period)
        if self.reference_year < 1900:
            raise EurostatVerticalError(
                "INVALID_REFERENCE_YEAR", f"invalid reference year: {self.reference_year}"
            )
        reference_start = f"{self.reference_year:04d}-01"
        reference_end = f"{self.reference_year:04d}-12"
        if not (self.start_period <= reference_start and reference_end <= self.end_period):
            raise EurostatVerticalError(
                "REFERENCE_PERIOD_OUTSIDE_INTERVAL",
                "all twelve months of the reference year must be inside the interval",
            )

    @property
    def eurostat_to_armilar(self) -> Mapping[str, str]:
        return {e.eurostat_code: e.armilar_code for e in self.economies}

    @property
    def armilar_to_name(self) -> Mapping[str, str]:
        return {e.armilar_code: e.name for e in self.economies}


@dataclass(frozen=True)
class Observation:
    economy_code: str
    eurostat_geo: str
    source_category: str
    armilar_category: str
    period: str
    value: Decimal
    status: str
    raw_file: str
    raw_sha256: str
    request_id: str


@dataclass(frozen=True)
class WeightCell:
    economy_code: str
    economy_name: str
    source_category: str
    raw_world_weight: Decimal
    fixed_universe_weight: Decimal
    quality_flags: str
    numerator_source_id: str
    numerator_source_file: str
    numerator_source_hash: str
    ppp_source_heading: str
    ppp_scope: str
    derivation: str


def _parse_period(period: str) -> tuple[int, int]:
    if len(period) != 7 or period[4] != "-":
        raise EurostatVerticalError("INVALID_PERIOD", f"invalid monthly period: {period}")
    try:
        year = int(period[:4])
        month = int(period[5:])
    except ValueError as exc:
        raise EurostatVerticalError("INVALID_PERIOD", f"invalid monthly period: {period}") from exc
    if year < 1900 or month < 1 or month > 12:
        raise EurostatVerticalError("INVALID_PERIOD", f"invalid monthly period: {period}")
    return year, month


def iter_periods(start: str, end: str) -> Iterator[str]:
    year, month = _parse_period(start)
    end_year, end_month = _parse_period(end)
    if (year, month) > (end_year, end_month):
        raise EurostatVerticalError("INVALID_INTERVAL", "start period is after end period")
    while (year, month) <= (end_year, end_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temp = Path(handle.name)
    os.replace(temp, path)


def build_request_url(policy: VerticalPolicy, source_category: str) -> str:
    if source_category not in policy.source_categories:
        raise EurostatVerticalError(
            "UNDECLARED_FALLBACK", f"category {source_category} is outside the declared universe"
        )
    params = [
        ("format", "JSON"),
        ("lang", "EN"),
        ("freq", policy.frequency),
        ("unit", policy.unit),
        ("coicop", source_category),
        *(("geo", economy.eurostat_code) for economy in policy.economies),
        ("sinceTimePeriod", policy.start_period),
        ("untilTimePeriod", policy.end_period),
    ]
    return policy.api_base + "?" + urllib.parse.urlencode(params)


def acquire_official_snapshot(
    policy_path: Path | str,
    snapshot_dir: Path | str,
    *,
    retrieved_at: str | None = None,
    opener: Any = urllib.request.urlopen,
) -> Mapping[str, Any]:
    """Acquire one official JSON-stat response per source category.

    This function is intentionally not called by PR tests.  It performs no broad
    retry loop.  Existing raw files are never overwritten with different bytes.
    """

    policy = VerticalPolicy.load(policy_path)
    snapshot_root = Path(snapshot_dir)
    raw_root = snapshot_root / "raw" / "eurostat" / policy.dataset
    raw_root.mkdir(parents=True, exist_ok=True)
    retrieved = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    requests: list[dict[str, Any]] = []

    for category in policy.source_categories:
        request_id = f"{policy.dataset}-{policy.unit}-{category}"
        url = build_request_url(policy, category)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": build_user_agent(),
                "Accept-Encoding": "identity",
            },
            method="GET",
        )
        try:
            with opener(request, timeout=policy.request_timeout_seconds) as response:
                status_value = getattr(response, "status", None)
                status = int(status_value if status_value is not None else response.getcode())
                content_type = str(response.headers.get("Content-Type", ""))
                data = response.read(policy.max_response_bytes + 1)
                final_url = str(getattr(response, "url", url))
                etag = response.headers.get("ETag")
                last_modified = response.headers.get("Last-Modified")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EurostatVerticalError("NETWORK_BLOCKED", f"{request_id}: {exc}") from exc
        if status != 200:
            raise EurostatVerticalError("PROVIDER_HTTP_ERROR", f"{request_id}: HTTP {status}")
        if len(data) > policy.max_response_bytes:
            raise EurostatVerticalError(
                "PROVIDER_RESPONSE_TOO_LARGE",
                f"{request_id}: response exceeds {policy.max_response_bytes} bytes",
            )
        if not data:
            raise EurostatVerticalError("EMPTY_PROVIDER_RESPONSE", request_id)
        if "json" not in content_type.lower() and not data.lstrip().startswith(b"{"):
            raise EurostatVerticalError(
                "PROVIDER_CONTENT_TYPE_MISMATCH", f"{request_id}: {content_type}"
            )
        digest = _sha256(data)
        relative = Path("raw") / "eurostat" / policy.dataset / f"{request_id}.{digest[:16]}.json"
        target = snapshot_root / relative
        if target.exists() and target.read_bytes() != data:
            raise EurostatVerticalError(
                "RAW_IMMUTABILITY_VIOLATION", f"existing raw path differs: {relative}"
            )
        _atomic_write(target, data)
        requests.append(
            {
                "request_id": request_id,
                "provider": PROVIDER,
                "dataset": policy.dataset,
                "source_category": category,
                "request_url": url,
                "final_url": final_url,
                "retrieved_at": retrieved,
                "http_status": status,
                "content_type": content_type,
                "etag": etag,
                "last_modified": last_modified,
                "raw_file": relative.as_posix(),
                "raw_sha256": digest,
                "raw_bytes": len(data),
            }
        )

    manifest = {
        "snapshot_schema_version": "1.0",
        "parser_id": PARSER_ID,
        "provider": PROVIDER,
        "dataset": policy.dataset,
        "policy_version": policy.policy_version,
        "policy_sha256": policy.policy_sha256,
        "universe_id": policy.universe_id,
        "retrieved_at": retrieved,
        "snapshot_kind": OFFICIAL_SNAPSHOT_KIND,
        "requests": sorted(requests, key=lambda item: item["request_id"]),
    }
    _atomic_write(snapshot_root / "snapshot_manifest.json", _canonical_json_bytes(manifest))
    _write_sha_manifest(snapshot_root, include=("snapshot_manifest.json", "raw"))
    return manifest


def _dimension_codes(dimension: Mapping[str, Any], dim_id: str, expected_size: int) -> list[str]:
    try:
        category = dimension[dim_id]["category"]
        index = category["index"]
    except (KeyError, TypeError) as exc:
        raise EurostatVerticalError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"missing category index for dimension {dim_id}"
        ) from exc
    if isinstance(index, list):
        codes = [str(x) for x in index]
    elif isinstance(index, Mapping):
        codes = [""] * expected_size
        for code, position in index.items():
            pos = int(position)
            if pos < 0 or pos >= expected_size or codes[pos]:
                raise EurostatVerticalError(
                    "PROVIDER_SCHEMA_UNRESOLVED", f"invalid position in dimension {dim_id}"
                )
            codes[pos] = str(code)
        if any(not code for code in codes):
            raise EurostatVerticalError(
                "PROVIDER_SCHEMA_UNRESOLVED", f"incomplete index for dimension {dim_id}"
            )
    else:
        raise EurostatVerticalError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"unsupported index for dimension {dim_id}"
        )
    if len(codes) != expected_size:
        raise EurostatVerticalError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"dimension {dim_id} size mismatch"
        )
    return codes


def parse_jsonstat_response(
    data: bytes,
    *,
    request: Mapping[str, Any],
    policy: VerticalPolicy,
) -> list[Observation]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise EurostatVerticalError("PROVIDER_SCHEMA_UNRESOLVED", "invalid JSON") from exc
    ids = payload.get("id")
    sizes = payload.get("size")
    dimension = payload.get("dimension")
    values = payload.get("value")
    statuses = payload.get("status", {})
    if not isinstance(ids, list) or not isinstance(sizes, list) or len(ids) != len(sizes):
        raise EurostatVerticalError("PROVIDER_SCHEMA_UNRESOLVED", "invalid id/size arrays")
    if not isinstance(dimension, Mapping):
        raise EurostatVerticalError("PROVIDER_SCHEMA_UNRESOLVED", "missing dimension object")
    required_dims = {"freq", "unit", "coicop", "geo", "time"}
    if not required_dims.issubset(set(ids)):
        raise EurostatVerticalError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"missing dimensions: {sorted(required_dims - set(ids))}"
        )
    sizes_int = [int(x) for x in sizes]
    dim_codes = {
        dim_id: _dimension_codes(dimension, dim_id, sizes_int[pos])
        for pos, dim_id in enumerate(ids)
    }
    total_size = math.prod(sizes_int)
    if isinstance(values, list):
        value_at = lambda idx: values[idx] if idx < len(values) else None
    elif isinstance(values, Mapping):
        value_at = lambda idx: values.get(str(idx), values.get(idx))
    else:
        raise EurostatVerticalError("PROVIDER_SCHEMA_UNRESOLVED", "invalid value container")
    if isinstance(statuses, list):
        status_at = lambda idx: statuses[idx] if idx < len(statuses) else ""
    elif isinstance(statuses, Mapping):
        status_at = lambda idx: statuses.get(str(idx), statuses.get(idx, ""))
    else:
        status_at = lambda idx: ""

    expected_category = str(request["source_category"])
    allowed_geos = policy.eurostat_to_armilar
    result: list[Observation] = []
    for linear in range(total_size):
        raw_value = value_at(linear)
        if raw_value is None:
            continue
        remainder = linear
        positions = [0] * len(sizes_int)
        for pos in range(len(sizes_int) - 1, -1, -1):
            positions[pos] = remainder % sizes_int[pos]
            remainder //= sizes_int[pos]
        coords = {dim_id: dim_codes[dim_id][positions[pos]] for pos, dim_id in enumerate(ids)}
        if coords["freq"] != policy.frequency or coords["unit"] != policy.unit:
            continue
        if coords["coicop"] != expected_category:
            continue
        if coords["geo"] not in allowed_geos:
            continue
        period = coords["time"]
        if period < policy.start_period or period > policy.end_period:
            continue
        try:
            value = Decimal(str(raw_value))
        except InvalidOperation as exc:
            raise EurostatVerticalError(
                "INVALID_PRICE_VALUE", f"{expected_category}/{coords['geo']}/{period}: {raw_value}"
            ) from exc
        if not value.is_finite() or value <= 0:
            raise EurostatVerticalError(
                "INVALID_PRICE_VALUE", f"{expected_category}/{coords['geo']}/{period}: {value}"
            )
        result.append(
            Observation(
                economy_code=allowed_geos[coords["geo"]],
                eurostat_geo=coords["geo"],
                source_category=expected_category,
                armilar_category=policy.category_map[expected_category],
                period=period,
                value=value,
                status=str(status_at(linear) or ""),
                raw_file=str(request["raw_file"]),
                raw_sha256=str(request["raw_sha256"]),
                request_id=str(request["request_id"]),
            )
        )
    return result


def _resolve_inside(root: Path, relative: str, error_code: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise EurostatVerticalError(error_code, f"absolute path is forbidden: {relative}")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise EurostatVerticalError(error_code, f"path escapes root: {relative}")
    return resolved


def load_snapshot(policy: VerticalPolicy, snapshot_dir: Path | str) -> tuple[list[Observation], Mapping[str, Any]]:
    root = Path(snapshot_dir)
    manifest_path = root / "snapshot_manifest.json"
    if not manifest_path.exists():
        raise EurostatVerticalError("SNAPSHOT_MANIFEST_MISSING", str(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("provider") != PROVIDER or manifest.get("dataset") != policy.dataset:
        raise EurostatVerticalError("SOURCE_CONCEPT_MISMATCH", "snapshot provider/dataset mismatch")
    snapshot_kind = manifest.get("snapshot_kind")
    if snapshot_kind not in {OFFICIAL_SNAPSHOT_KIND, TEST_SNAPSHOT_KIND}:
        raise EurostatVerticalError(
            "SNAPSHOT_KIND_UNDECLARED",
            "snapshot must declare whether it is an official acquisition or a test fixture",
        )
    if manifest.get("policy_sha256") != policy.policy_sha256:
        raise EurostatVerticalError(
            "SNAPSHOT_POLICY_MISMATCH",
            "snapshot was acquired under a different policy fingerprint",
        )
    requests = manifest.get("requests")
    if not isinstance(requests, list):
        raise EurostatVerticalError("SNAPSHOT_MANIFEST_INVALID", "requests must be a list")
    by_category: dict[str, Mapping[str, Any]] = {}
    observations: list[Observation] = []
    for request in requests:
        category = str(request.get("source_category", ""))
        if category in by_category:
            raise EurostatVerticalError("DUPLICATE_REQUEST", category)
        by_category[category] = request
        raw_path = _resolve_inside(root, str(request["raw_file"]), "RAW_PATH_INVALID")
        if not raw_path.is_file():
            raise EurostatVerticalError("RAW_FILE_MISSING", str(raw_path))
        data = raw_path.read_bytes()
        actual_hash = _sha256(data)
        if actual_hash != request.get("raw_sha256"):
            raise EurostatVerticalError(
                "REPLAY_HASH_MISMATCH", f"{raw_path}: {actual_hash} != {request.get('raw_sha256')}"
            )
        observations.extend(parse_jsonstat_response(data, request=request, policy=policy))
    missing_requests = sorted(set(policy.source_categories) - set(by_category))
    extra_requests = sorted(set(by_category) - set(policy.source_categories))
    if missing_requests or extra_requests:
        raise EurostatVerticalError(
            "UNDECLARED_FALLBACK",
            f"request set mismatch; missing={missing_requests}, extra={extra_requests}",
        )
    _validate_observation_grid(policy, observations)
    return observations, manifest


def _validate_observation_grid(policy: VerticalPolicy, observations: Sequence[Observation]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for obs in observations:
        key = (obs.economy_code, obs.source_category, obs.period)
        if key in seen:
            raise EurostatVerticalError("DUPLICATE_OBSERVATION", "/".join(key))
        seen.add(key)
    expected = {
        (economy.armilar_code, category, period)
        for economy in policy.economies
        for category in policy.source_categories
        for period in iter_periods(policy.start_period, policy.end_period)
    }
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    if missing or extra:
        sample = missing[:5]
        raise EurostatVerticalError(
            "INCOMPLETE_COMMON_INTERVAL",
            f"missing={len(missing)} sample={sample}; extra={len(extra)}",
        )


def load_fixed_weights(policy: VerticalPolicy, weights_path: Path | str) -> tuple[list[WeightCell], Decimal]:
    path = Path(weights_path)
    rows: dict[tuple[str, str], dict[str, str]] = {}
    total_world = Decimal("0")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"economy_code", "armilar_category", "weight"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise EurostatVerticalError(
                "WEIGHT_SCHEMA_INVALID", f"required columns: {sorted(required)}"
            )
        for row in reader:
            try:
                raw_weight = Decimal(str(row["weight"]))
            except InvalidOperation as exc:
                raise EurostatVerticalError("INVALID_WEIGHT", str(row)) from exc
            if not raw_weight.is_finite() or raw_weight < 0:
                raise EurostatVerticalError("INVALID_WEIGHT", str(row))
            total_world += raw_weight
            key = (str(row["economy_code"]), str(row["armilar_category"]))
            if key in rows:
                raise EurostatVerticalError("DUPLICATE_WEIGHT", "/".join(key))
            rows[key] = row
    if abs(total_world - Decimal("1")) > Decimal("1e-18"):
        raise EurostatVerticalError(
            "WORLD_WEIGHT_SUM_INVALID", f"weights sum to {total_world}, expected 1"
        )
    selected_keys = [
        (economy.armilar_code, category)
        for economy in policy.economies
        for category in policy.source_categories
    ]
    missing = [key for key in selected_keys if key not in rows]
    if missing:
        raise EurostatVerticalError("WEIGHT_GRID_INCOMPLETE", f"missing={missing[:5]}")
    covered_weight = sum((Decimal(rows[key]["weight"]) for key in selected_keys), Decimal("0"))
    if covered_weight <= 0:
        raise EurostatVerticalError("EMPTY_WEIGHT_UNIVERSE", "selected weight is zero")
    cells: list[WeightCell] = []
    for key in selected_keys:
        row = rows[key]
        raw = Decimal(row["weight"])
        cells.append(
            WeightCell(
                economy_code=key[0],
                economy_name=str(row.get("economy_name", policy.armilar_to_name.get(key[0], key[0]))),
                source_category=key[1],
                raw_world_weight=raw,
                fixed_universe_weight=raw / covered_weight,
                quality_flags=str(row.get("quality_flags", "")),
                numerator_source_id=str(row.get("numerator_source_id", "")),
                numerator_source_file=str(row.get("numerator_source_file", "")),
                numerator_source_hash=str(row.get("numerator_source_hash", "")),
                ppp_source_heading=str(row.get("ppp_source_heading", "")),
                ppp_scope=str(row.get("ppp_scope", "")),
                derivation=str(row.get("derivation", "")),
            )
        )
    fixed_sum = sum((cell.fixed_universe_weight for cell in cells), Decimal("0"))
    if abs(fixed_sum - Decimal("1")) > Decimal("1e-36"):
        raise EurostatVerticalError("FIXED_WEIGHT_SUM_INVALID", str(fixed_sum))
    return cells, covered_weight


def _decimal_text(value: Decimal, places: int = 12) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _write_sha_manifest(root: Path, include: Sequence[str] | None = None) -> None:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "MANIFEST.sha256":
            continue
        relative = path.relative_to(root)
        if include is not None and not any(
            relative == Path(prefix) or Path(prefix) in relative.parents for prefix in include
        ):
            continue
        files.append(path)
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in sorted(files)]
    _atomic_write(root / "MANIFEST.sha256", (("\n".join(lines) + "\n") if lines else "").encode("utf-8"))


def build_vertical_series(
    policy_path: Path | str,
    snapshot_dir: Path | str,
    weights_path: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = VerticalPolicy.load(policy_path)
    observations, snapshot_manifest = load_snapshot(policy, snapshot_dir)
    weights, covered_world_weight = load_fixed_weights(policy, weights_path)
    snapshot_kind = str(snapshot_manifest["snapshot_kind"])
    is_official_snapshot = snapshot_kind == OFFICIAL_SNAPSHOT_KIND
    price_evidence_class = (
        "P1_OFFICIAL_CATEGORY" if is_official_snapshot else "TEST_FIXTURE_NOT_EVIDENCE"
    )
    row_status = (
        "RESEARCH_ONLY_SCOPE_UNCERTAINTY_UNQUANTIFIED"
        if is_official_snapshot
        else "TEST_FIXTURE_NOT_RESEARCH_RESULT"
    )
    output_root = Path(output_dir)
    if output_root.resolve() == Path(snapshot_dir).resolve():
        raise EurostatVerticalError("OUTPUT_PATH_INVALID", "output and snapshot paths must differ")
    if output_root.exists() and any(output_root.iterdir()):
        raise EurostatVerticalError(
            "OUTPUT_DIRECTORY_NOT_EMPTY",
            "use a new empty output directory so stale files cannot enter the manifest",
        )
    output_root.mkdir(parents=True, exist_ok=True)

    weight_by_key = {(w.economy_code, w.source_category): w for w in weights}
    obs_by_key = {
        (o.economy_code, o.source_category, o.period): o for o in observations
    }
    reference_months = [f"{policy.reference_year:04d}-{month:02d}" for month in range(1, 13)]
    reference_prices = {
        (economy.armilar_code, category): sum(
            (
                obs_by_key[(economy.armilar_code, category, period)].value
                for period in reference_months
            ),
            Decimal("0"),
        )
        / Decimal("12")
        for economy in policy.economies
        for category in policy.source_categories
    }

    normalized_rows: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    economy_rows: list[dict[str, Any]] = []
    source_category_rows: list[dict[str, Any]] = []
    armilar_category_rows: list[dict[str, Any]] = []
    previous_index: Decimal | None = None

    periods = list(iter_periods(policy.start_period, policy.end_period))
    for period in periods:
        total = Decimal("0")
        by_economy: dict[str, Decimal] = {e.armilar_code: Decimal("0") for e in policy.economies}
        by_source: dict[str, Decimal] = {c: Decimal("0") for c in policy.source_categories}
        by_armilar: dict[str, Decimal] = {
            arm: Decimal("0") for arm in sorted(set(policy.category_map.values()))
        }
        for economy in policy.economies:
            for category in policy.source_categories:
                key = (economy.armilar_code, category)
                obs = obs_by_key[(economy.armilar_code, category, period)]
                weight = weight_by_key[key]
                relative = obs.value / reference_prices[key]
                contribution = Decimal("100") * weight.fixed_universe_weight * relative
                total += contribution
                by_economy[economy.armilar_code] += contribution
                by_source[category] += contribution
                by_armilar[policy.category_map[category]] += contribution
                normalized_rows.append(
                    {
                        "universe_id": policy.universe_id,
                        "economy_code": economy.armilar_code,
                        "economy_name": economy.name,
                        "eurostat_geo": economy.eurostat_code,
                        "source_category": category,
                        "armilar_category": policy.category_map[category],
                        "period": period,
                        "price_value": _decimal_text(obs.value, 8),
                        "reference_period": f"{policy.reference_year:04d}_ANNUAL_AVERAGE",
                        "reference_price_value": _decimal_text(reference_prices[key], 8),
                        "price_relative": _decimal_text(relative, 14),
                        "raw_world_weight": _decimal_text(weight.raw_world_weight, 18),
                        "fixed_universe_weight": _decimal_text(weight.fixed_universe_weight, 18),
                        "index_level_contribution": _decimal_text(contribution, 14),
                        "price_evidence_class": price_evidence_class,
                        "provider": PROVIDER,
                        "dataset": policy.dataset,
                        "unit": policy.unit,
                        "status": obs.status,
                        "request_id": obs.request_id,
                        "raw_file": obs.raw_file,
                        "raw_sha256": obs.raw_sha256,
                        "weight_numerator_source_id": weight.numerator_source_id,
                        "weight_numerator_source_file": weight.numerator_source_file,
                        "weight_numerator_source_hash": weight.numerator_source_hash,
                        "weight_ppp_source_heading": weight.ppp_source_heading,
                        "weight_ppp_scope": weight.ppp_scope,
                        "weight_derivation": weight.derivation,
                        "weight_quality_flags": weight.quality_flags,
                    }
                )
        component_sum = sum(by_source.values(), Decimal("0"))
        if abs(component_sum - total) > Decimal("1e-30"):
            raise EurostatVerticalError("CONTRIBUTION_IDENTITY_FAILED", period)
        monthly_change = None if previous_index is None else (total / previous_index - 1) * 100
        index_rows.append(
            {
                "universe_id": policy.universe_id,
                "period": period,
                "index_value": _decimal_text(total, 12),
                "monthly_change_percent": "" if monthly_change is None else _decimal_text(monthly_change, 10),
                "lower_bound": "",
                "upper_bound": "",
                "direct_observation_weight_declared_universe": "1.000000000000",
                "declared_universe_world_weight": _decimal_text(covered_world_weight, 12),
                "status": row_status,
                "research_release_allowed": "false",
                "monetary_release_allowed": "false",
            }
        )
        for code, value in sorted(by_economy.items()):
            economy_rows.append(
                {
                    "period": period,
                    "economy_code": code,
                    "economy_name": policy.armilar_to_name[code],
                    "index_level_contribution": _decimal_text(value, 14),
                    "share_of_index": _decimal_text(value / total, 14),
                }
            )
        for category, value in sorted(by_source.items()):
            source_category_rows.append(
                {
                    "period": period,
                    "source_category": category,
                    "armilar_category": policy.category_map[category],
                    "index_level_contribution": _decimal_text(value, 14),
                    "share_of_index": _decimal_text(value / total, 14),
                }
            )
        for category, value in sorted(by_armilar.items()):
            armilar_category_rows.append(
                {
                    "period": period,
                    "armilar_category": category,
                    "index_level_contribution": _decimal_text(value, 14),
                    "share_of_index": _decimal_text(value / total, 14),
                }
            )
        previous_index = total

    _write_csv(
        output_root / "normalized_price_observations.csv",
        [
            "universe_id", "economy_code", "economy_name", "eurostat_geo",
            "source_category", "armilar_category", "period", "price_value",
            "reference_period", "reference_price_value", "price_relative",
            "raw_world_weight", "fixed_universe_weight", "index_level_contribution",
            "price_evidence_class", "provider", "dataset", "unit", "status",
            "request_id", "raw_file", "raw_sha256",
            "weight_numerator_source_id", "weight_numerator_source_file",
            "weight_numerator_source_hash", "weight_ppp_source_heading",
            "weight_ppp_scope", "weight_derivation", "weight_quality_flags",
        ],
        normalized_rows,
    )
    _write_csv(
        output_root / "monthly_index.csv",
        [
            "universe_id", "period", "index_value", "monthly_change_percent",
            "lower_bound", "upper_bound", "direct_observation_weight_declared_universe",
            "declared_universe_world_weight", "status", "research_release_allowed",
            "monetary_release_allowed",
        ],
        index_rows,
    )
    _write_csv(
        output_root / "contributions_by_economy.csv",
        ["period", "economy_code", "economy_name", "index_level_contribution", "share_of_index"],
        economy_rows,
    )
    _write_csv(
        output_root / "contributions_by_source_category.csv",
        ["period", "source_category", "armilar_category", "index_level_contribution", "share_of_index"],
        source_category_rows,
    )
    _write_csv(
        output_root / "contributions_by_armilar_category.csv",
        ["period", "armilar_category", "index_level_contribution", "share_of_index"],
        armilar_category_rows,
    )
    weight_rows = [
        {
            "economy_code": w.economy_code,
            "economy_name": w.economy_name,
            "source_category": w.source_category,
            "armilar_category": policy.category_map[w.source_category],
            "raw_world_weight": _decimal_text(w.raw_world_weight, 18),
            "fixed_universe_weight": _decimal_text(w.fixed_universe_weight, 18),
            "quality_flags": w.quality_flags,
            "numerator_source_id": w.numerator_source_id,
            "numerator_source_file": w.numerator_source_file,
            "numerator_source_hash": w.numerator_source_hash,
            "ppp_source_heading": w.ppp_source_heading,
            "ppp_scope": w.ppp_scope,
            "derivation": w.derivation,
        }
        for w in weights
    ]
    _write_csv(
        output_root / "fixed_universe_weights.csv",
        [
            "economy_code", "economy_name", "source_category", "armilar_category",
            "raw_world_weight", "fixed_universe_weight", "quality_flags",
            "numerator_source_id", "numerator_source_file", "numerator_source_hash",
            "ppp_source_heading", "ppp_scope", "derivation",
        ],
        weight_rows,
    )

    uncertainty = {
        "schema_version": "1.0",
        "universe_id": policy.universe_id,
        "numeric_interval_available": False,
        "lower_bound": None,
        "upper_bound": None,
        "reason": (
            "The official P1 price observations are point estimates, while the HICP HFMCE versus "
            "Armilar HFCE scope mismatch and weight uncertainty are not yet quantitatively calibrated. "
            "Publishing zero-width bounds would be misleading."
        ),
        "concept_alignment_status": policy.concept_alignment_status,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "uncertainty_summary.json", _canonical_json_bytes(uncertainty))

    snapshot_manifest_hash = _sha256((Path(snapshot_dir) / "snapshot_manifest.json").read_bytes())
    summary = {
        "schema_version": "1.0",
        "pipeline_version": installed_version(),
        "parser_id": PARSER_ID,
        "status": (
            "RESEARCH_VERTICAL_SERIES_BUILT"
            if is_official_snapshot
            else "TEST_FIXTURE_VERTICAL_SERIES_BUILT"
        ),
        "universe_id": policy.universe_id,
        "provider": PROVIDER,
        "dataset": policy.dataset,
        "classification_version": policy.classification_version,
        "policy_sha256": policy.policy_sha256,
        "weights_input_file": Path(weights_path).name,
        "weights_input_sha256": _sha256(Path(weights_path).read_bytes()),
        "reference_period": f"{policy.reference_year:04d}_ANNUAL_AVERAGE",
        "start_period": policy.start_period,
        "end_period": policy.end_period,
        "month_count": len(periods),
        "economy_count": len(policy.economies),
        "source_category_count": len(policy.source_categories),
        "armilar_category_count": len(set(policy.category_map.values())),
        "observation_count": len(observations),
        "declared_universe_world_weight": _decimal_text(covered_world_weight, 18),
        "direct_price_weight_within_declared_universe": "1.000000000000000000",
        "normalization_rule": "FIXED_UNIVERSE_NORMALISE_ONCE",
        "aggregation_mode": "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES",
        "fx_treatment": "SEPARATE_NOT_USED_IN_PRIMARY_INDEX",
        "price_concept": policy.price_concept,
        "weight_concept": policy.weight_concept,
        "concept_alignment_status": policy.concept_alignment_status,
        "uncertainty_numeric_interval_available": False,
        "snapshot_manifest_sha256": snapshot_manifest_hash,
        "source_snapshot_retrieved_at": snapshot_manifest.get("retrieved_at"),
        "snapshot_kind": snapshot_kind,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "run_summary.json", _canonical_json_bytes(summary))
    _write_economic_report(output_root, policy, summary, index_rows, armilar_category_rows)
    _write_sha_manifest(output_root)
    return summary


def _write_economic_report(
    output_root: Path,
    policy: VerticalPolicy,
    summary: Mapping[str, Any],
    index_rows: Sequence[Mapping[str, str]],
    armilar_rows: Sequence[Mapping[str, str]],
) -> None:
    first = Decimal(index_rows[0]["index_value"])
    last = Decimal(index_rows[-1]["index_value"])
    cumulative = (last / first - 1) * 100
    last_period = index_rows[-1]["period"]
    latest_components = [row for row in armilar_rows if row["period"] == last_period]
    latest_components.sort(key=lambda row: Decimal(row["index_level_contribution"]), reverse=True)
    lines = [
        "# Armilar v0.8.7 Eurostat vertical research series",
        "",
        "## Scope",
        "",
        f"- Universe: `{policy.universe_id}`",
        f"- Economies: {', '.join(e.name for e in policy.economies)}",
        f"- Interval: {policy.start_period} to {policy.end_period}",
        f"- Reference period: annual average {policy.reference_year} = 100",
        f"- Declared-universe share of observed world weights: {Decimal(str(summary['declared_universe_world_weight'])) * 100:.4f}%",
        "- Primary method: PPP-weighted local price relatives with a fixed universe",
        "- Current FX: excluded from the primary index",
        "",
        "## Result",
        "",
        f"The research index moves from {first:.6f} to {last:.6f}, a cumulative change of {cumulative:.4f}% over the declared interval.",
        "",
        f"Largest index-level components in {last_period}:",
        "",
    ]
    for row in latest_components[:5]:
        lines.append(
            f"- {row['armilar_category']}: {Decimal(row['index_level_contribution']):.6f} index points"
        )
    snapshot_kind = str(summary["snapshot_kind"])
    if snapshot_kind == OFFICIAL_SNAPSHOT_KIND:
        evidence_statement = (
            "All prices inside the declared universe are direct Eurostat category observations "
            "and every value is linked to preserved official raw bytes and a SHA-256 receipt."
        )
        readiness_statement = (
            "This series may proceed to the v0.8.8 minimum backtest after the official snapshot "
            "has been independently replayed. It is not a worldwide Armilar index and cannot "
            "inform monetary policy."
        )
    else:
        evidence_statement = (
            "This report was generated from a synthetic test fixture. It validates schemas, "
            "identities and replay behaviour, but contains no official price evidence and is not "
            "an economic result."
        )
        readiness_statement = (
            "An official network acquisition and exact replay are still required before v0.8.7 "
            "can close or the series can enter a backtest."
        )
    lines.extend(
        [
            "",
            "## Quality and release status",
            "",
            evidence_statement,
            "",
            "A numeric confidence interval is deliberately not published. The HICP household final monetary consumption concept does not fully match the Armilar HFCE weight concept, and the uncertainty introduced by that scope difference has not yet been calibrated.",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
            "",
            readiness_statement,
        ]
    )
    _atomic_write(output_root / "ECONOMIC_REPORT.md", ("\n".join(lines) + "\n").encode("utf-8"))


def verify_manifest(root: Path | str) -> None:
    root_path = Path(root)
    manifest_path = root_path / "MANIFEST.sha256"
    if not manifest_path.is_file():
        raise EurostatVerticalError("MANIFEST_MISSING", str(manifest_path))
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise EurostatVerticalError("MANIFEST_INVALID", line) from exc
        path = _resolve_inside(root_path, relative, "MANIFEST_PATH_INVALID")
        if not path.is_file() or _sha256(path.read_bytes()) != expected:
            raise EurostatVerticalError("MANIFEST_HASH_MISMATCH", relative)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.8.7 Eurostat vertical series")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire", help="acquire official Eurostat snapshot")
    acquire.add_argument("--policy", required=True)
    acquire.add_argument("--snapshot-dir", required=True)
    replay = sub.add_parser("replay", help="rebuild series from exact snapshot bytes")
    replay.add_argument("--policy", required=True)
    replay.add_argument("--snapshot-dir", required=True)
    replay.add_argument("--weights", required=True)
    replay.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify", help="verify an output manifest")
    verify.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "acquire":
            result = acquire_official_snapshot(args.policy, args.snapshot_dir)
        elif args.command == "replay":
            result = build_vertical_series(args.policy, args.snapshot_dir, args.weights, args.output_dir)
        else:
            verify_manifest(args.root)
            result = {"status": "MANIFEST_VALID"}
    except EurostatVerticalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
