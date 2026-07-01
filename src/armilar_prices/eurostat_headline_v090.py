"""Independent Eurostat CP00 headline chain for Armilar v0.9.0.

The module preserves exact provider bytes, replays them deterministically and
builds two genuine headline baselines for the fixed five-economy universe:

* B0: equal-country aggregation of official national CP00 price relatives.
* B1: aggregation of official national CP00 price relatives using each
  economy's total Armilar fixed-universe weight.

CP01-CP12 observations are never used to construct either headline baseline.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
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
except ModuleNotFoundError:
    def installed_version() -> str:
        return "0+unknown"

    def build_user_agent(version: str | None = None) -> str:
        resolved = installed_version() if version is None else version
        return (
            f"ArmilarDataPipeline/{resolved} "
            "(+https://github.com/tomazlucena-crypto/armilar-data-pipeline)"
        )

try:
    from .eurostat_vertical import verify_manifest as verify_vertical_manifest
except (ImportError, ModuleNotFoundError):
    verify_vertical_manifest = None

getcontext().prec = 42

DATASET = "prc_hicp_midx"
PROVIDER = "EUROSTAT"
SOURCE_CATEGORY = "CP00"
PARSER_ID = "armilar-eurostat-headline-v090"
OFFICIAL_SNAPSHOT_KIND = "OFFICIAL_PROVIDER_ACQUISITION"
TEST_SNAPSHOT_KIND = "SYNTHETIC_TEST_FIXTURE"
DEFAULT_API_BASE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    + DATASET
)


class EurostatHeadlineError(RuntimeError):
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
class HeadlinePolicy:
    policy_version: str
    universe_id: str
    dataset: str
    unit: str
    frequency: str
    classification_version: str
    source_category: str
    reference_year: int
    start_period: str
    end_period: str
    economies: tuple[Economy, ...]
    api_base: str
    research_release_allowed: bool
    monetary_release_allowed: bool
    request_timeout_seconds: int
    max_response_bytes: int

    @classmethod
    def load(cls, path: Path | str) -> "HeadlinePolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "universe_id",
            "dataset",
            "unit",
            "frequency",
            "classification_version",
            "source_category",
            "reference_year",
            "start_period",
            "end_period",
            "economies",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise EurostatHeadlineError("POLICY_FIELD_MISSING", ", ".join(missing))
        policy = cls(
            policy_version=str(payload["policy_version"]),
            universe_id=str(payload["universe_id"]),
            dataset=str(payload["dataset"]),
            unit=str(payload["unit"]),
            frequency=str(payload["frequency"]),
            classification_version=str(payload["classification_version"]),
            source_category=str(payload["source_category"]),
            reference_year=int(payload["reference_year"]),
            start_period=str(payload["start_period"]),
            end_period=str(payload["end_period"]),
            economies=tuple(
                Economy(
                    eurostat_code=str(item["eurostat_code"]),
                    armilar_code=str(item["armilar_code"]),
                    name=str(item["name"]),
                )
                for item in payload["economies"]
            ),
            api_base=str(payload.get("api_base", DEFAULT_API_BASE)),
            research_release_allowed=bool(payload["research_release_allowed"]),
            monetary_release_allowed=bool(payload["monetary_release_allowed"]),
            request_timeout_seconds=int(payload.get("request_timeout_seconds", 30)),
            max_response_bytes=int(payload.get("max_response_bytes", 5_000_000)),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.dataset != DATASET:
            raise EurostatHeadlineError("SOURCE_CONCEPT_MISMATCH", self.dataset)
        if self.unit != "I15" or self.frequency != "M":
            raise EurostatHeadlineError(
                "SOURCE_CONCEPT_MISMATCH", "headline chain requires M/I15"
            )
        if self.source_category != SOURCE_CATEGORY:
            raise EurostatHeadlineError(
                "SOURCE_CONCEPT_MISMATCH", "headline source must be CP00"
            )
        if self.classification_version != "ECOICOP_V1_PRE_2026":
            raise EurostatHeadlineError(
                "SOURCE_CONCEPT_MISMATCH", "pre-2026 ECOICOP contract required"
            )
        if self.end_period > "2025-12":
            raise EurostatHeadlineError(
                "CLASSIFICATION_BREAK_UNRESOLVED",
                "data from 2026 onward require an explicit successor-dataset mapping",
            )
        if self.research_release_allowed or self.monetary_release_allowed:
            raise EurostatHeadlineError(
                "RELEASE_GATE_WEAKENED", "release flags must remain false"
            )
        if not self.economies:
            raise EurostatHeadlineError("EMPTY_UNIVERSE", "no economies")
        euro = [item.eurostat_code for item in self.economies]
        armilar = [item.armilar_code for item in self.economies]
        if len(euro) != len(set(euro)) or len(armilar) != len(set(armilar)):
            raise EurostatHeadlineError("DUPLICATE_ECONOMY", "economy codes must be unique")
        _parse_period(self.start_period)
        _parse_period(self.end_period)
        if self.start_period > self.end_period:
            raise EurostatHeadlineError("INVALID_INTERVAL", "start exceeds end")
        reference_start = f"{self.reference_year:04d}-01"
        reference_end = f"{self.reference_year:04d}-12"
        if not (self.start_period <= reference_start and reference_end <= self.end_period):
            raise EurostatHeadlineError(
                "REFERENCE_PERIOD_OUTSIDE_INTERVAL", "full reference year required"
            )

    @property
    def eurostat_to_armilar(self) -> Mapping[str, str]:
        return {item.eurostat_code: item.armilar_code for item in self.economies}

    @property
    def armilar_to_name(self) -> Mapping[str, str]:
        return {item.armilar_code: item.name for item in self.economies}

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return {
            "policy_version": self.policy_version,
            "universe_id": self.universe_id,
            "dataset": self.dataset,
            "unit": self.unit,
            "frequency": self.frequency,
            "classification_version": self.classification_version,
            "source_category": self.source_category,
            "reference_year": self.reference_year,
            "start_period": self.start_period,
            "end_period": self.end_period,
            "economies": [
                {
                    "eurostat_code": item.eurostat_code,
                    "armilar_code": item.armilar_code,
                    "name": item.name,
                }
                for item in self.economies
            ],
            "api_base": self.api_base,
            "research_release_allowed": self.research_release_allowed,
            "monetary_release_allowed": self.monetary_release_allowed,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_response_bytes": self.max_response_bytes,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha256(_canonical_json_bytes(self.fingerprint_payload()))


@dataclass(frozen=True)
class Observation:
    economy_code: str
    eurostat_geo: str
    period: str
    value: Decimal
    status: str
    request_id: str
    raw_file: str
    raw_sha256: str


def _parse_period(period: str) -> tuple[int, int]:
    if len(period) != 7 or period[4] != "-":
        raise EurostatHeadlineError("INVALID_PERIOD", period)
    try:
        year = int(period[:4])
        month = int(period[5:])
    except ValueError as exc:
        raise EurostatHeadlineError("INVALID_PERIOD", period) from exc
    if year < 1900 or not 1 <= month <= 12:
        raise EurostatHeadlineError("INVALID_PERIOD", period)
    return year, month


def iter_periods(start: str, end: str) -> Iterator[str]:
    year, month = _parse_period(start)
    end_year, end_month = _parse_period(end)
    while (year, month) <= (end_year, end_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _decimal_text(value: Decimal, places: int = 12) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _write_csv(
    path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_manifest(root: Path, include: Sequence[str] | None = None) -> None:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "MANIFEST.sha256":
            continue
        relative = path.relative_to(root)
        if include is not None and not any(
            relative == Path(prefix) or Path(prefix) in relative.parents
            for prefix in include
        ):
            continue
        files.append(path)
    lines = [
        f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}"
        for path in sorted(files)
    ]
    _atomic_write(
        root / "MANIFEST.sha256",
        (("\n".join(lines) + "\n") if lines else "").encode("utf-8"),
    )


def _resolve_inside(root: Path, relative: str, code: str) -> Path:
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise EurostatHeadlineError(code, relative)
    return candidate


def verify_manifest(root: Path | str) -> None:
    root_path = Path(root)
    manifest = root_path / "MANIFEST.sha256"
    if not manifest.is_file():
        raise EurostatHeadlineError("MANIFEST_MISSING", str(manifest))
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise EurostatHeadlineError("MANIFEST_INVALID", line) from exc
        target = _resolve_inside(root_path, relative, "MANIFEST_PATH_INVALID")
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise EurostatHeadlineError("MANIFEST_HASH_MISMATCH", relative)


def build_request_url(policy: HeadlinePolicy) -> str:
    params = [
        ("format", "JSON"),
        ("lang", "EN"),
        ("freq", policy.frequency),
        ("unit", policy.unit),
        ("coicop", policy.source_category),
        *(("geo", item.eurostat_code) for item in policy.economies),
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
    policy = HeadlinePolicy.load(policy_path)
    root = Path(snapshot_dir)
    raw_root = root / "raw" / "eurostat" / policy.dataset
    raw_root.mkdir(parents=True, exist_ok=True)
    request_id = f"{policy.dataset}-{policy.unit}-{SOURCE_CATEGORY}"
    url = build_request_url(policy)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": build_user_agent(),
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
        raise EurostatHeadlineError("NETWORK_BLOCKED", str(exc)) from exc
    if status != 200:
        raise EurostatHeadlineError("PROVIDER_HTTP_ERROR", f"HTTP {status}")
    if not data:
        raise EurostatHeadlineError("EMPTY_PROVIDER_RESPONSE", request_id)
    if len(data) > policy.max_response_bytes:
        raise EurostatHeadlineError("PROVIDER_RESPONSE_TOO_LARGE", request_id)
    if "json" not in content_type.lower() and not data.lstrip().startswith(b"{"):
        raise EurostatHeadlineError(
            "PROVIDER_CONTENT_TYPE_MISMATCH", content_type
        )
    digest = _sha256(data)
    relative = (
        Path("raw")
        / "eurostat"
        / policy.dataset
        / f"{request_id}.{digest[:16]}.json"
    )
    target = root / relative
    if target.exists() and target.read_bytes() != data:
        raise EurostatHeadlineError("RAW_IMMUTABILITY_VIOLATION", str(relative))
    _atomic_write(target, data)
    retrieved = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
        "requests": [
            {
                "request_id": request_id,
                "provider": PROVIDER,
                "dataset": policy.dataset,
                "source_category": SOURCE_CATEGORY,
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
        ],
    }
    _atomic_write(root / "snapshot_manifest.json", _canonical_json_bytes(manifest))
    _write_manifest(root, include=("snapshot_manifest.json", "raw"))
    return manifest


def _dimension_codes(
    dimension: Mapping[str, Any], dim_id: str, expected_size: int
) -> list[str]:
    try:
        index = dimension[dim_id]["category"]["index"]
    except (KeyError, TypeError) as exc:
        raise EurostatHeadlineError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"missing {dim_id} index"
        ) from exc
    if isinstance(index, list):
        result = [str(value) for value in index]
    elif isinstance(index, Mapping):
        result = [""] * expected_size
        for code, position in index.items():
            pos = int(position)
            if pos < 0 or pos >= expected_size or result[pos]:
                raise EurostatHeadlineError(
                    "PROVIDER_SCHEMA_UNRESOLVED", f"invalid {dim_id} position"
                )
            result[pos] = str(code)
    else:
        raise EurostatHeadlineError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"unsupported {dim_id} index"
        )
    if len(result) != expected_size or any(not code for code in result):
        raise EurostatHeadlineError(
            "PROVIDER_SCHEMA_UNRESOLVED", f"{dim_id} size mismatch"
        )
    return result


def parse_jsonstat_response(
    data: bytes, *, request: Mapping[str, Any], policy: HeadlinePolicy
) -> list[Observation]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise EurostatHeadlineError("PROVIDER_SCHEMA_UNRESOLVED", "invalid JSON") from exc
    ids = payload.get("id")
    sizes = payload.get("size")
    dimension = payload.get("dimension")
    values = payload.get("value")
    statuses = payload.get("status", {})
    if not isinstance(ids, list) or not isinstance(sizes, list) or len(ids) != len(sizes):
        raise EurostatHeadlineError("PROVIDER_SCHEMA_UNRESOLVED", "invalid id/size")
    if not isinstance(dimension, Mapping):
        raise EurostatHeadlineError("PROVIDER_SCHEMA_UNRESOLVED", "missing dimension")
    required_dims = {"freq", "unit", "coicop", "geo", "time"}
    if not required_dims.issubset(set(ids)):
        raise EurostatHeadlineError(
            "PROVIDER_SCHEMA_UNRESOLVED",
            f"missing dimensions: {sorted(required_dims - set(ids))}",
        )
    sizes_int = [int(value) for value in sizes]
    codes = {
        dim_id: _dimension_codes(dimension, dim_id, sizes_int[position])
        for position, dim_id in enumerate(ids)
    }
    if isinstance(values, list):
        value_at = lambda index: values[index] if index < len(values) else None
    elif isinstance(values, Mapping):
        value_at = lambda index: values.get(str(index), values.get(index))
    else:
        raise EurostatHeadlineError("PROVIDER_SCHEMA_UNRESOLVED", "invalid values")
    if isinstance(statuses, list):
        status_at = lambda index: statuses[index] if index < len(statuses) else ""
    elif isinstance(statuses, Mapping):
        status_at = lambda index: statuses.get(str(index), statuses.get(index, ""))
    else:
        status_at = lambda index: ""

    result: list[Observation] = []
    total_size = math.prod(sizes_int)
    allowed_geos = policy.eurostat_to_armilar
    for linear in range(total_size):
        raw_value = value_at(linear)
        if raw_value is None:
            continue
        remainder = linear
        positions = [0] * len(sizes_int)
        for position in range(len(sizes_int) - 1, -1, -1):
            positions[position] = remainder % sizes_int[position]
            remainder //= sizes_int[position]
        coordinates = {
            dim_id: codes[dim_id][positions[position]]
            for position, dim_id in enumerate(ids)
        }
        if coordinates["freq"] != policy.frequency or coordinates["unit"] != policy.unit:
            continue
        if coordinates["coicop"] != SOURCE_CATEGORY:
            continue
        geo = coordinates["geo"]
        if geo not in allowed_geos:
            continue
        period = coordinates["time"]
        if period < policy.start_period or period > policy.end_period:
            continue
        try:
            value = Decimal(str(raw_value))
        except InvalidOperation as exc:
            raise EurostatHeadlineError(
                "INVALID_PRICE_VALUE", f"{geo}/{period}: {raw_value}"
            ) from exc
        if not value.is_finite() or value <= 0:
            raise EurostatHeadlineError("INVALID_PRICE_VALUE", f"{geo}/{period}")
        result.append(
            Observation(
                economy_code=allowed_geos[geo],
                eurostat_geo=geo,
                period=period,
                value=value,
                status=str(status_at(linear) or ""),
                request_id=str(request["request_id"]),
                raw_file=str(request["raw_file"]),
                raw_sha256=str(request["raw_sha256"]),
            )
        )
    return result


def load_snapshot(
    policy: HeadlinePolicy, snapshot_dir: Path | str
) -> tuple[list[Observation], Mapping[str, Any]]:
    root = Path(snapshot_dir)
    verify_manifest(root)
    manifest_path = root / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("snapshot_kind") not in {
        OFFICIAL_SNAPSHOT_KIND,
        TEST_SNAPSHOT_KIND,
    }:
        raise EurostatHeadlineError("SNAPSHOT_KIND_UNDECLARED", "invalid kind")
    if manifest.get("policy_sha256") != policy.policy_sha256:
        raise EurostatHeadlineError("SNAPSHOT_POLICY_MISMATCH", "policy hash differs")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or len(requests) != 1:
        raise EurostatHeadlineError("SNAPSHOT_MANIFEST_INVALID", "one request required")
    request = requests[0]
    if request.get("source_category") != SOURCE_CATEGORY:
        raise EurostatHeadlineError("SOURCE_CONCEPT_MISMATCH", "request is not CP00")
    raw_path = _resolve_inside(root, str(request["raw_file"]), "RAW_PATH_INVALID")
    if not raw_path.is_file():
        raise EurostatHeadlineError("RAW_FILE_MISSING", str(raw_path))
    data = raw_path.read_bytes()
    if _sha256(data) != request.get("raw_sha256"):
        raise EurostatHeadlineError("REPLAY_HASH_MISMATCH", str(raw_path))
    observations = parse_jsonstat_response(data, request=request, policy=policy)
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        key = (observation.economy_code, observation.period)
        if key in seen:
            raise EurostatHeadlineError("DUPLICATE_OBSERVATION", "/".join(key))
        seen.add(key)
    expected = {
        (economy.armilar_code, period)
        for economy in policy.economies
        for period in iter_periods(policy.start_period, policy.end_period)
    }
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    if missing or extra:
        raise EurostatHeadlineError(
            "INCOMPLETE_COMMON_INTERVAL",
            f"missing={len(missing)} sample={missing[:5]} extra={len(extra)}",
        )
    return observations, manifest


def _load_economy_weights(
    policy: HeadlinePolicy, vertical_output_dir: Path | str
) -> tuple[Mapping[str, Decimal], str]:
    root = Path(vertical_output_dir)
    if verify_vertical_manifest is not None:
        try:
            verify_vertical_manifest(root)
        except Exception as exc:
            raise EurostatHeadlineError("VERTICAL_MANIFEST_INVALID", str(exc)) from exc
    summary_path = root / "run_summary.json"
    weights_path = root / "fixed_universe_weights.csv"
    if not summary_path.is_file() or not weights_path.is_file():
        raise EurostatHeadlineError("VERTICAL_INPUT_MISSING", str(root))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("universe_id") != policy.universe_id:
        raise EurostatHeadlineError("UNIVERSE_MISMATCH", str(summary.get("universe_id")))
    totals = {economy.armilar_code: Decimal("0") for economy in policy.economies}
    with weights_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"economy_code", "source_category", "fixed_universe_weight"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise EurostatHeadlineError("WEIGHT_SCHEMA_INVALID", str(weights_path))
        seen: set[tuple[str, str]] = set()
        for line_number, row in enumerate(reader, start=2):
            economy = str(row["economy_code"])
            category = str(row["source_category"])
            if economy not in totals:
                continue
            key = (economy, category)
            if key in seen:
                raise EurostatHeadlineError("DUPLICATE_WEIGHT", f"line {line_number}")
            seen.add(key)
            try:
                weight = Decimal(str(row["fixed_universe_weight"]))
            except InvalidOperation as exc:
                raise EurostatHeadlineError("INVALID_WEIGHT", f"line {line_number}") from exc
            if not weight.is_finite() or weight <= 0:
                raise EurostatHeadlineError("INVALID_WEIGHT", f"line {line_number}")
            totals[economy] += weight
    expected_cells = len(policy.economies) * 12
    if len(seen) != expected_cells:
        raise EurostatHeadlineError(
            "WEIGHT_GRID_INCOMPLETE", f"expected={expected_cells} observed={len(seen)}"
        )
    total = sum(totals.values(), Decimal("0"))
    if abs(total - Decimal("1")) > Decimal("1e-18"):
        raise EurostatHeadlineError("WEIGHTS_DO_NOT_SUM_TO_ONE", str(total))
    if any(weight <= 0 for weight in totals.values()):
        raise EurostatHeadlineError("EMPTY_ECONOMY_WEIGHT", str(totals))
    return totals, _sha256(weights_path.read_bytes())


def build_headline_series(
    policy_path: Path | str,
    snapshot_dir: Path | str,
    vertical_output_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = HeadlinePolicy.load(policy_path)
    observations, snapshot_manifest = load_snapshot(policy, snapshot_dir)
    economy_weights, weights_hash = _load_economy_weights(policy, vertical_output_dir)
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise EurostatHeadlineError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)

    by_key = {(item.economy_code, item.period): item for item in observations}
    reference_periods = [
        f"{policy.reference_year:04d}-{month:02d}" for month in range(1, 13)
    ]
    reference_values = {
        economy.armilar_code: sum(
            (by_key[(economy.armilar_code, period)].value for period in reference_periods),
            Decimal("0"),
        )
        / Decimal("12")
        for economy in policy.economies
    }
    normalized_rows: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    snapshot_kind = str(snapshot_manifest["snapshot_kind"])
    evidence = (
        "P1_OFFICIAL_HEADLINE"
        if snapshot_kind == OFFICIAL_SNAPSHOT_KIND
        else "TEST_FIXTURE_NOT_EVIDENCE"
    )
    periods = list(iter_periods(policy.start_period, policy.end_period))
    for period in periods:
        relatives: dict[str, Decimal] = {}
        for economy in policy.economies:
            observation = by_key[(economy.armilar_code, period)]
            relative = observation.value / reference_values[economy.armilar_code]
            relatives[economy.armilar_code] = relative
            normalized_rows.append(
                {
                    "universe_id": policy.universe_id,
                    "economy_code": economy.armilar_code,
                    "economy_name": economy.name,
                    "eurostat_geo": economy.eurostat_code,
                    "source_category": SOURCE_CATEGORY,
                    "period": period,
                    "price_value": _decimal_text(observation.value, 8),
                    "reference_period": f"{policy.reference_year:04d}_ANNUAL_AVERAGE",
                    "reference_price_value": _decimal_text(
                        reference_values[economy.armilar_code], 8
                    ),
                    "price_relative": _decimal_text(relative, 14),
                    "economy_fixed_universe_weight": _decimal_text(
                        economy_weights[economy.armilar_code], 18
                    ),
                    "price_evidence_class": evidence,
                    "provider": PROVIDER,
                    "dataset": policy.dataset,
                    "unit": policy.unit,
                    "status": observation.status,
                    "request_id": observation.request_id,
                    "raw_file": observation.raw_file,
                    "raw_sha256": observation.raw_sha256,
                }
            )
        b0 = Decimal("100") * sum(relatives.values(), Decimal("0")) / Decimal(
            len(relatives)
        )
        b1 = Decimal("100") * sum(
            (
                relatives[economy.armilar_code]
                * economy_weights[economy.armilar_code]
                for economy in policy.economies
            ),
            Decimal("0"),
        )
        index_rows.append(
            {
                "universe_id": policy.universe_id,
                "period": period,
                "b0_equal_country_official_headline": _decimal_text(b0, 12),
                "b1_armilar_economy_weighted_official_headline": _decimal_text(b1, 12),
                "source_category": SOURCE_CATEGORY,
                "headline_source_independent": "true",
                "snapshot_kind": snapshot_kind,
                "research_release_allowed": "false",
                "monetary_release_allowed": "false",
            }
        )

    _write_csv(
        output_root / "normalized_headline_observations.csv",
        [
            "universe_id",
            "economy_code",
            "economy_name",
            "eurostat_geo",
            "source_category",
            "period",
            "price_value",
            "reference_period",
            "reference_price_value",
            "price_relative",
            "economy_fixed_universe_weight",
            "price_evidence_class",
            "provider",
            "dataset",
            "unit",
            "status",
            "request_id",
            "raw_file",
            "raw_sha256",
        ],
        normalized_rows,
    )
    _write_csv(
        output_root / "monthly_headline_indices.csv",
        [
            "universe_id",
            "period",
            "b0_equal_country_official_headline",
            "b1_armilar_economy_weighted_official_headline",
            "source_category",
            "headline_source_independent",
            "snapshot_kind",
            "research_release_allowed",
            "monetary_release_allowed",
        ],
        index_rows,
    )
    _write_csv(
        output_root / "headline_economy_weights.csv",
        ["economy_code", "economy_name", "economy_fixed_universe_weight"],
        [
            {
                "economy_code": economy.armilar_code,
                "economy_name": economy.name,
                "economy_fixed_universe_weight": _decimal_text(
                    economy_weights[economy.armilar_code], 18
                ),
            }
            for economy in policy.economies
        ],
    )
    snapshot_manifest_hash = _sha256(
        (Path(snapshot_dir) / "snapshot_manifest.json").read_bytes()
    )
    summary = {
        "schema_version": "1.0",
        "pipeline_version": installed_version(),
        "policy_version": policy.policy_version,
        "parser_id": PARSER_ID,
        "status": (
            "INDEPENDENT_OFFICIAL_HEADLINE_SERIES_BUILT"
            if snapshot_kind == OFFICIAL_SNAPSHOT_KIND
            else "TEST_FIXTURE_HEADLINE_SERIES_BUILT"
        ),
        "universe_id": policy.universe_id,
        "provider": PROVIDER,
        "dataset": policy.dataset,
        "unit": policy.unit,
        "source_category": SOURCE_CATEGORY,
        "reference_period": f"{policy.reference_year:04d}_ANNUAL_AVERAGE",
        "start_period": policy.start_period,
        "end_period": policy.end_period,
        "month_count": len(periods),
        "economy_count": len(policy.economies),
        "observation_count": len(observations),
        "headline_source_independent": True,
        "category_panel_used_to_construct_headline": False,
        "b0_definition": "EQUAL_COUNTRY_OFFICIAL_CP00",
        "b1_definition": "ARMILAR_ECONOMY_WEIGHTED_OFFICIAL_CP00",
        "vertical_weights_sha256": weights_hash,
        "snapshot_manifest_sha256": snapshot_manifest_hash,
        "source_snapshot_retrieved_at": snapshot_manifest.get("retrieved_at"),
        "snapshot_kind": snapshot_kind,
        "rejected_v089_experiment_reused": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "run_summary.json", _canonical_json_bytes(summary))
    report = [
        "# Armilar v0.9.0 independent Eurostat headline series",
        "",
        "## Contract",
        "",
        f"- Universe: `{policy.universe_id}`",
        f"- Economies: {', '.join(item.name for item in policy.economies)}",
        f"- Interval: {policy.start_period} to {policy.end_period}",
        f"- Reference: annual average {policy.reference_year} = 100",
        "- Source: Eurostat HICP CP00, acquired and replayed separately from CP01-CP12",
        "- B0: equal-country aggregation of official national CP00 relatives",
        "- B1: Armilar economy-weighted aggregation of official national CP00 relatives",
        "",
        "The category panel is used only to obtain fixed economy weights for B1. Its prices are not used to construct either headline series.",
        "",
        "`research_release_allowed=false`",
        "",
        "`monetary_release_allowed=false`",
    ]
    _atomic_write(
        output_root / "ECONOMIC_REPORT.md", ("\n".join(report) + "\n").encode("utf-8")
    )
    _write_manifest(output_root)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Armilar v0.9.0 independent Eurostat CP00 chain"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--policy", required=True)
    acquire.add_argument("--snapshot-dir", required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("--policy", required=True)
    replay.add_argument("--snapshot-dir", required=True)
    replay.add_argument("--vertical-output-dir", required=True)
    replay.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "acquire":
        result = acquire_official_snapshot(args.policy, args.snapshot_dir)
    elif args.command == "replay":
        result = build_headline_series(
            args.policy,
            args.snapshot_dir,
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
