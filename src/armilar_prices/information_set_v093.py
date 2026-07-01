"""Armilar v0.9.3 CP00 publication-timing and information-set audit.

This module distinguishes three concepts that must not be conflated:

* extraction time: when Armilar downloaded a provider response;
* publication availability: the official date on which a reference month was released;
* value vintage: the exact value visible in a particular provider snapshot.

The current Eurostat CP00 chain contains one final/latest provider snapshot. A
release calendar makes availability timing auditable. Eurostat also publishes
an official first-published HICP dataset (``prc_hicp_fp``), integrated by the
companion v0.9.3 module. This audit remains explicitly limited to the final-value
CP00 chain and does not itself authorise a real-time model comparison.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, getcontext
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

getcontext().prec = 42

PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CALENDAR_HOST = "ec.europa.eu"
CALENDAR_PATH = "/eurostat/web/main/news/release-calendar"
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
CAPABILITY = "PUBLICATION_TIMING_AWARE_FINAL_VALUES"
BACKTEST_CLASS = "FINAL_VINTAGE_TARGET_PERIOD_DONOR_STRESS_TEST"
UNSUPPORTED = (
    "REAL_TIME_MODEL_BACKTEST_NOT_YET_RERUN",
    "PUBLICATION_AWARE_B0_B4_MODEL_COMPARISON",
    "MODEL_PROMOTION",
)
REQUIRED_RELEASE_FIELDS = {
    "reference_period",
    "release_date",
    "source_url",
    "raw_file",
}
REQUIRED_HEADLINE_FIELDS = {
    "universe_id",
    "economy_code",
    "period",
    "source_category",
    "price_value",
    "price_relative",
    "economy_fixed_universe_weight",
    "provider",
    "dataset",
    "raw_file",
    "raw_sha256",
}


class InformationSetError(RuntimeError):
    """Fail-closed error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class InformationSetPolicy:
    policy_version: str
    universe_id: str
    provider: str
    dataset: str
    source_category: str
    economy_codes: tuple[str, ...]
    start_period: str
    end_period: str
    release_timezone: str
    availability_precision: str
    minimum_release_lag_days: int
    maximum_release_lag_days: int
    required_headline_policy_version: str
    required_backtest_policy_version: str
    required_input_vintage_mode: str
    output_capability: str
    historical_value_vintages_available: bool
    publication_aware_model_comparison_allowed: bool
    model_promotion_allowed: bool
    research_release_allowed: bool
    monetary_release_allowed: bool

    @classmethod
    def load(cls, path: Path | str) -> "InformationSetPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "universe_id",
            "provider",
            "dataset",
            "source_category",
            "economy_codes",
            "start_period",
            "end_period",
            "release_timezone",
            "availability_precision",
            "minimum_release_lag_days",
            "maximum_release_lag_days",
            "required_headline_policy_version",
            "required_backtest_policy_version",
            "required_input_vintage_mode",
            "output_capability",
            "historical_value_vintages_available",
            "publication_aware_model_comparison_allowed",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise InformationSetError("POLICY_FIELD_MISSING", ", ".join(missing))
        policy = cls(
            policy_version=str(payload["policy_version"]),
            universe_id=str(payload["universe_id"]),
            provider=str(payload["provider"]),
            dataset=str(payload["dataset"]),
            source_category=str(payload["source_category"]),
            economy_codes=tuple(str(value) for value in payload["economy_codes"]),
            start_period=str(payload["start_period"]),
            end_period=str(payload["end_period"]),
            release_timezone=str(payload["release_timezone"]),
            availability_precision=str(payload["availability_precision"]),
            minimum_release_lag_days=int(payload["minimum_release_lag_days"]),
            maximum_release_lag_days=int(payload["maximum_release_lag_days"]),
            required_headline_policy_version=str(payload["required_headline_policy_version"]),
            required_backtest_policy_version=str(payload["required_backtest_policy_version"]),
            required_input_vintage_mode=str(payload["required_input_vintage_mode"]),
            output_capability=str(payload["output_capability"]),
            historical_value_vintages_available=bool(
                payload["historical_value_vintages_available"]
            ),
            publication_aware_model_comparison_allowed=bool(
                payload["publication_aware_model_comparison_allowed"]
            ),
            model_promotion_allowed=bool(payload["model_promotion_allowed"]),
            research_release_allowed=bool(payload["research_release_allowed"]),
            monetary_release_allowed=bool(payload["monetary_release_allowed"]),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.policy_version != "0.9.3":
            raise InformationSetError("POLICY_VERSION_UNSUPPORTED", self.policy_version)
        _period_date(self.start_period)
        _period_date(self.end_period)
        if self.start_period > self.end_period:
            raise InformationSetError("INVALID_PERIOD_INTERVAL", "start after end")
        if (self.provider, self.dataset, self.source_category) != (
            "EUROSTAT",
            "prc_hicp_midx",
            "CP00",
        ):
            raise InformationSetError("SOURCE_CONTRACT_MISMATCH", "Eurostat CP00 required")
        if not self.economy_codes:
            raise InformationSetError("ECONOMY_UNIVERSE_EMPTY", "economy_codes")
        if len(self.economy_codes) != len(set(self.economy_codes)):
            raise InformationSetError("ECONOMY_UNIVERSE_DUPLICATE", "economy_codes")
        if any(not re.fullmatch(r"[A-Z]{3}", code) for code in self.economy_codes):
            raise InformationSetError("ECONOMY_CODE_INVALID", ",".join(self.economy_codes))
        if self.release_timezone != "Europe/Luxembourg":
            raise InformationSetError("RELEASE_TIMEZONE_UNSUPPORTED", self.release_timezone)
        if self.availability_precision != "DAY":
            raise InformationSetError("AVAILABILITY_PRECISION_UNSUPPORTED", self.availability_precision)
        if self.minimum_release_lag_days < 0:
            raise InformationSetError("RELEASE_LAG_POLICY_INVALID", "negative minimum")
        if self.maximum_release_lag_days < self.minimum_release_lag_days:
            raise InformationSetError("RELEASE_LAG_POLICY_INVALID", "maximum below minimum")
        if self.required_headline_policy_version != "0.9.0":
            raise InformationSetError("HEADLINE_POLICY_VERSION_UNSUPPORTED", self.required_headline_policy_version)
        if self.required_backtest_policy_version != "0.9.0":
            raise InformationSetError("BACKTEST_POLICY_VERSION_UNSUPPORTED", self.required_backtest_policy_version)
        if self.required_input_vintage_mode != "FINAL_VINTAGE_PSEUDO_REAL_TIME":
            raise InformationSetError("INPUT_VINTAGE_MODE_UNSUPPORTED", self.required_input_vintage_mode)
        if self.output_capability != CAPABILITY:
            raise InformationSetError("CAPABILITY_CLAIM_UNSUPPORTED", self.output_capability)
        if not self.historical_value_vintages_available:
            raise InformationSetError("HISTORICAL_VINTAGE_CAPABILITY_DISABLED", "prc_hicp_fp must be acknowledged")
        if self.publication_aware_model_comparison_allowed:
            raise InformationSetError("MODEL_COMPARISON_CLAIM_UNSUPPORTED", "category vintages unavailable")
        if self.model_promotion_allowed or self.research_release_allowed or self.monetary_release_allowed:
            raise InformationSetError("RELEASE_GATE_WEAKENED", "all gates must remain false")


@dataclass(frozen=True)
class ReleaseEvent:
    reference_period: str
    release_date: date
    source_url: str
    raw_file: str
    raw_sha256: str
    release_lag_days: int


def _installed_version() -> str:
    try:
        return package_version("armilar-data-pipeline")
    except PackageNotFoundError:
        return "0+unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def _period_date(period: str) -> date:
    match = PERIOD_RE.fullmatch(period)
    if not match:
        raise InformationSetError("INVALID_PERIOD", period)
    return date(int(match.group(1)), int(match.group(2)), 1)


def _period_end(period: str) -> date:
    first = _period_date(period)
    if first.month == 12:
        following = date(first.year + 1, 1, 1)
    else:
        following = date(first.year, first.month + 1, 1)
    return following - timedelta(days=1)


def iter_periods(start: str, end: str) -> tuple[str, ...]:
    current = _period_date(start)
    stop = _period_date(end)
    result: list[str] = []
    while current <= stop:
        result.append(f"{current.year:04d}-{current.month:02d}")
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return tuple(result)


def _parse_iso_date(value: str, code: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InformationSetError(code, value) from exc
    if value != parsed.isoformat():
        raise InformationSetError(code, value)
    return parsed


def _parse_aware_datetime(value: str, code: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InformationSetError(code, value) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InformationSetError(code, value)
    return parsed


def _resolve_inside(root: Path, relative: str, code: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise InformationSetError(code, relative)
    target = (root / relative).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise InformationSetError(code, relative)
    return target


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    _atomic_write(root / "MANIFEST.sha256", ("\n".join(lines) + "\n").encode("utf-8"))


def verify_manifest(root: Path | str) -> None:
    root_path = Path(root)
    manifest = root_path / "MANIFEST.sha256"
    if not manifest.is_file():
        raise InformationSetError("MANIFEST_MISSING", str(manifest))
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise InformationSetError("MANIFEST_INVALID", line)
        expected, relative = parts[0].lower(), parts[1].strip()
        if not SHA256_RE.fullmatch(expected):
            raise InformationSetError("MANIFEST_INVALID", line)
        target = _resolve_inside(root_path, relative, "MANIFEST_PATH_INVALID")
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise InformationSetError("MANIFEST_HASH_MISMATCH", relative)



def _calendar_month_from_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != CALENDAR_HOST or parsed.path != CALENDAR_PATH:
        raise InformationSetError("RELEASE_CALENDAR_URL_INVALID", source_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("type") != ["listMonth"] or len(query.get("start", [])) != 1:
        raise InformationSetError("RELEASE_CALENDAR_URL_INVALID", source_url)
    raw_start = query["start"][0]
    if not re.fullmatch(r"\d{13}", raw_start):
        raise InformationSetError("RELEASE_CALENDAR_URL_INVALID", source_url)
    instant = datetime.fromtimestamp(int(raw_start) / 1000, tz=timezone.utc)
    local = instant.astimezone(ZoneInfo("Europe/Luxembourg"))
    if (local.day, local.hour, local.minute, local.second) != (1, 0, 0, 0):
        raise InformationSetError("RELEASE_CALENDAR_URL_INVALID", source_url)
    return f"{local.year:04d}-{local.month:02d}"


def _release_month(release: date) -> str:
    return f"{release.year:04d}-{release.month:02d}"


def _normalised_html_text(data: bytes) -> str:
    decoded = data.decode("utf-8", errors="replace")
    without_scripts = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", decoded)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return " ".join(html.unescape(without_tags).split())


def _is_official_dynamic_calendar_shell(data: bytes) -> bool:
    decoded = data.decode("utf-8", errors="replace").casefold()
    required_markers = (
        "release calendar - eurostat",
        "new fullcalendar.calendar",
        "/eurostat/o/calendars/eventsjson",
        "timezone: 'europe/luxembourg'",
    )
    return all(marker in decoded for marker in required_markers)


def _validate_calendar_page(data: bytes, reference_period: str, release: date) -> None:
    if len(data) < 500:
        raise InformationSetError("RELEASE_EVIDENCE_TOO_SMALL", reference_period)
    visible = _normalised_html_text(data).casefold()
    reference = _period_date(reference_period)
    reference_label = f"{MONTH_NAMES[reference.month - 1]} {reference.year}".casefold()
    release_label = f"{release.day} {MONTH_NAMES[release.month - 1]} {release.year}".casefold()
    event_label = f"inflation (hicp), {reference_label}"
    if event_label not in visible:
        if _is_official_dynamic_calendar_shell(data):
            return
        raise InformationSetError("RELEASE_EVENT_NOT_FOUND", f"{reference_period}: {event_label}")
    if release_label not in visible:
        raise InformationSetError("RELEASE_DATE_NOT_FOUND", release.isoformat())


def _read_release_registry(registry_path: Path, policy: InformationSetPolicy) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with registry_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_RELEASE_FIELDS.issubset(reader.fieldnames):
            missing = sorted(REQUIRED_RELEASE_FIELDS - set(reader.fieldnames or ()))
            raise InformationSetError("RELEASE_REGISTRY_SCHEMA_INVALID", ", ".join(missing))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["reference_period"]).strip()
            _period_date(period)
            release = _parse_iso_date(str(row["release_date"]).strip(), "RELEASE_DATE_INVALID")
            source_url = str(row["source_url"]).strip()
            raw_file = str(row["raw_file"]).strip().replace("\\", "/")
            if not source_url.startswith("https://ec.europa.eu/eurostat/"):
                raise InformationSetError("RELEASE_SOURCE_NOT_OFFICIAL", f"line {line_number}")
            if source_url.startswith(f"https://{CALENDAR_HOST}{CALENDAR_PATH}"):
                calendar_month = _calendar_month_from_url(source_url)
                if calendar_month != _release_month(release):
                    raise InformationSetError(
                        "RELEASE_CALENDAR_MONTH_MISMATCH",
                        f"period={period} release={release.isoformat()} calendar={calendar_month}",
                    )
            if not raw_file or Path(raw_file).is_absolute() or ".." in Path(raw_file).parts:
                raise InformationSetError("RELEASE_EVIDENCE_PATH_INVALID", raw_file)
            rows.append(
                {
                    "reference_period": period,
                    "release_date": release.isoformat(),
                    "source_url": source_url,
                    "raw_file": raw_file,
                }
            )
    expected = set(iter_periods(policy.start_period, policy.end_period))
    observed = [row["reference_period"] for row in rows]
    if len(observed) != len(set(observed)):
        raise InformationSetError("DUPLICATE_RELEASE_PERIOD", "registry")
    if set(observed) != expected:
        raise InformationSetError(
            "RELEASE_PERIOD_GRID_INCOMPLETE",
            f"expected={len(expected)} observed={len(set(observed))}",
        )
    for row in rows:
        release = _parse_iso_date(row["release_date"], "RELEASE_DATE_INVALID")
        lag_days = (release - _period_end(row["reference_period"])).days
        if not policy.minimum_release_lag_days <= lag_days <= policy.maximum_release_lag_days:
            raise InformationSetError(
                "RELEASE_LAG_OUTSIDE_POLICY",
                f"period={row['reference_period']} lag_days={lag_days}",
            )
    return sorted(rows, key=lambda row: row["reference_period"])


def acquire_release_evidence(
    policy_path: Path | str,
    registry_csv: Path | str,
    output_dir: Path | str,
    *,
    timeout_seconds: int = 60,
    opener: Callable[..., Any] | None = None,
) -> Mapping[str, Any]:
    policy = InformationSetPolicy.load(policy_path)
    registry_path = Path(registry_csv)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise InformationSetError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)
    rows = _read_release_registry(registry_path, policy)
    fetch = opener or urllib.request.urlopen
    receipts: list[dict[str, str]] = []
    for row in rows:
        release = _parse_iso_date(row["release_date"], "RELEASE_DATE_INVALID")
        request = urllib.request.Request(
            row["source_url"],
            headers={
                "User-Agent": "ArmilarDataPipeline/0.9.3 (+https://github.com/tomazlucena-crypto/armilar-data-pipeline)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            },
        )
        try:
            with fetch(request, timeout=timeout_seconds) as response:
                status = int(getattr(response, "status", response.getcode()))
                data = response.read()
                content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
                final_url = str(response.geturl())
        except (OSError, urllib.error.URLError) as exc:
            raise InformationSetError("RELEASE_EVIDENCE_DOWNLOAD_FAILED", row["source_url"]) from exc
        if status != 200:
            raise InformationSetError("RELEASE_EVIDENCE_HTTP_STATUS", f"{status}: {row['source_url']}")
        if not final_url.startswith("https://ec.europa.eu/eurostat/"):
            raise InformationSetError("RELEASE_EVIDENCE_REDIRECT_UNOFFICIAL", final_url)
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise InformationSetError("RELEASE_EVIDENCE_CONTENT_TYPE", content_type)
        _validate_calendar_page(data, row["reference_period"], release)
        target = _resolve_inside(output, row["raw_file"], "RELEASE_EVIDENCE_PATH_INVALID")
        _atomic_write(target, data)
        receipts.append(
            {
                "reference_period": row["reference_period"],
                "release_date": row["release_date"],
                "source_url": row["source_url"],
                "final_url": final_url,
                "raw_file": row["raw_file"],
                "raw_sha256": _sha256(data),
                "http_status": str(status),
                "content_type": content_type,
                "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
    _write_csv(
        output / "acquisition_receipts.csv",
        [
            "reference_period", "release_date", "source_url", "final_url",
            "raw_file", "raw_sha256", "http_status", "content_type", "retrieved_at",
        ],
        receipts,
    )
    summary = {
        "schema_version": "1.0",
        "policy_version": policy.policy_version,
        "provider": policy.provider,
        "release_event_count": len(receipts),
        "official_calendar_pages_acquired": len(receipts),
        "evidence_validation": "EXACT_HICP_REFERENCE_PERIOD_AND_RELEASE_DATE_PRESENT",
        "historical_value_vintages_included": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "acquisition_summary.json", _canonical_json(summary))
    _write_manifest(output)
    return summary

def seal_release_snapshot(
    policy_path: Path | str,
    registry_csv: Path | str,
    evidence_root: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = InformationSetPolicy.load(policy_path)
    registry_path = Path(registry_csv)
    evidence = Path(evidence_root)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise InformationSetError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)

    registry_rows = _read_release_registry(registry_path, policy)
    rows: list[dict[str, str]] = []
    for row in registry_rows:
        period = row["reference_period"]
        release = _parse_iso_date(row["release_date"], "RELEASE_DATE_INVALID")
        source_url = row["source_url"]
        raw_file = row["raw_file"]
        source = _resolve_inside(evidence, raw_file, "RELEASE_EVIDENCE_PATH_INVALID")
        if not source.is_file() or not source.read_bytes():
            raise InformationSetError("RELEASE_EVIDENCE_MISSING", raw_file)
        data = source.read_bytes()
        if source_url.startswith(f"https://{CALENDAR_HOST}{CALENDAR_PATH}"):
            _validate_calendar_page(data, period, release)
        digest = _sha256(data)
        destination_relative = f"raw/{digest[:16]}-{Path(raw_file).name}"
        destination = _resolve_inside(output, destination_relative, "RELEASE_EVIDENCE_PATH_INVALID")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != data:
            raise InformationSetError("RAW_IMMUTABILITY_VIOLATION", destination_relative)
        shutil.copy2(source, destination)
        rows.append(
            {
                "reference_period": period,
                "release_date": release.isoformat(),
                "source_url": source_url,
                "raw_file": destination_relative,
                "raw_sha256": digest,
            }
        )
    _write_csv(
        output / "release_events.csv",
        ["reference_period", "release_date", "source_url", "raw_file", "raw_sha256"],
        rows,
    )
    summary = {
        "schema_version": "1.0",
        "policy_version": policy.policy_version,
        "provider": policy.provider,
        "dataset": policy.dataset,
        "source_category": policy.source_category,
        "start_period": policy.start_period,
        "end_period": policy.end_period,
        "release_event_count": len(rows),
        "release_timezone": policy.release_timezone,
        "availability_precision": policy.availability_precision,
        "snapshot_kind": "OFFICIAL_RELEASE_EVIDENCE_SNAPSHOT",
        "historical_value_vintages_included": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "snapshot_summary.json", _canonical_json(summary))
    _write_manifest(output)
    return summary


def _load_release_events(policy: InformationSetPolicy, root: Path) -> tuple[ReleaseEvent, ...]:
    verify_manifest(root)
    summary_path = root / "snapshot_summary.json"
    events_path = root / "release_events.csv"
    if not summary_path.is_file() or not events_path.is_file():
        raise InformationSetError("RELEASE_SNAPSHOT_FILE_MISSING", str(root))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("policy_version") != policy.policy_version:
        raise InformationSetError("RELEASE_SNAPSHOT_POLICY_MISMATCH", str(summary.get("policy_version")))
    if summary.get("snapshot_kind") != "OFFICIAL_RELEASE_EVIDENCE_SNAPSHOT":
        raise InformationSetError("RELEASE_SNAPSHOT_KIND_INVALID", str(summary.get("snapshot_kind")))
    if summary.get("historical_value_vintages_included") is not False:
        raise InformationSetError("HISTORICAL_VINTAGE_CLAIM_UNSUPPORTED", "release snapshot")

    events: list[ReleaseEvent] = []
    with events_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = REQUIRED_RELEASE_FIELDS | {"raw_sha256"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise InformationSetError("RELEASE_REGISTRY_SCHEMA_INVALID", str(events_path))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["reference_period"])
            release = _parse_iso_date(str(row["release_date"]), "RELEASE_DATE_INVALID")
            raw_file = str(row["raw_file"])
            digest = str(row["raw_sha256"]).lower()
            if not SHA256_RE.fullmatch(digest):
                raise InformationSetError("RELEASE_EVIDENCE_HASH_INVALID", f"line {line_number}")
            raw_path = _resolve_inside(root, raw_file, "RELEASE_EVIDENCE_PATH_INVALID")
            if not raw_path.is_file() or _sha256(raw_path.read_bytes()) != digest:
                raise InformationSetError("RELEASE_EVIDENCE_HASH_MISMATCH", raw_file)
            lag = (release - _period_end(period)).days
            if not policy.minimum_release_lag_days <= lag <= policy.maximum_release_lag_days:
                raise InformationSetError("RELEASE_LAG_OUTSIDE_POLICY", f"{period}: {lag}")
            events.append(
                ReleaseEvent(
                    reference_period=period,
                    release_date=release,
                    source_url=str(row["source_url"]),
                    raw_file=raw_file,
                    raw_sha256=digest,
                    release_lag_days=lag,
                )
            )
    expected = set(iter_periods(policy.start_period, policy.end_period))
    periods = [event.reference_period for event in events]
    if len(periods) != len(set(periods)):
        raise InformationSetError("DUPLICATE_RELEASE_PERIOD", "snapshot")
    if set(periods) != expected:
        raise InformationSetError("RELEASE_PERIOD_GRID_INCOMPLETE", "snapshot")
    return tuple(sorted(events, key=lambda item: item.reference_period))


def _load_headline_rows(policy: InformationSetPolicy, root: Path) -> tuple[list[dict[str, str]], Mapping[str, Any]]:
    verify_manifest(root)
    observations = root / "normalized_headline_observations.csv"
    summary_path = root / "run_summary.json"
    if not observations.is_file() or not summary_path.is_file():
        raise InformationSetError("HEADLINE_INPUT_MISSING", str(root))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("policy_version") != policy.required_headline_policy_version:
        raise InformationSetError("HEADLINE_POLICY_MISMATCH", str(summary.get("policy_version")))
    if summary.get("universe_id") != policy.universe_id:
        raise InformationSetError("UNIVERSE_MISMATCH", str(summary.get("universe_id")))
    if summary.get("snapshot_kind") != "OFFICIAL_PROVIDER_ACQUISITION":
        raise InformationSetError("OFFICIAL_HEADLINE_REQUIRED", str(summary.get("snapshot_kind")))
    if summary.get("provider") != policy.provider or summary.get("dataset") != policy.dataset:
        raise InformationSetError("HEADLINE_SOURCE_INVALID", "run_summary")
    if summary.get("source_category") != policy.source_category:
        raise InformationSetError("HEADLINE_SOURCE_CATEGORY_INVALID", "run_summary")
    if summary.get("start_period") != policy.start_period or summary.get("end_period") != policy.end_period:
        raise InformationSetError("HEADLINE_PERIOD_INTERVAL_MISMATCH", "run_summary")
    if summary.get("headline_source_independent") is not True:
        raise InformationSetError("HEADLINE_INDEPENDENCE_UNPROVEN", "run_summary")
    if summary.get("category_panel_used_to_construct_headline") is not False:
        raise InformationSetError("HEADLINE_CATEGORY_PANEL_DEPENDENCE", "run_summary")
    snapshot_manifest_sha256 = str(summary.get("snapshot_manifest_sha256", "")).lower()
    if not SHA256_RE.fullmatch(snapshot_manifest_sha256):
        raise InformationSetError("HEADLINE_SNAPSHOT_HASH_INVALID", snapshot_manifest_sha256)
    source_snapshot_retrieved_at = str(summary.get("source_snapshot_retrieved_at", ""))
    _parse_aware_datetime(source_snapshot_retrieved_at, "HEADLINE_RETRIEVAL_TIMESTAMP_INVALID")
    rows: list[dict[str, str]] = []
    with observations.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_HEADLINE_FIELDS.issubset(reader.fieldnames):
            raise InformationSetError("HEADLINE_SCHEMA_INVALID", str(observations))
        for line_number, row in enumerate(reader, start=2):
            period = str(row["period"])
            if period < policy.start_period or period > policy.end_period:
                continue
            if str(row["source_category"]) != policy.source_category:
                raise InformationSetError("HEADLINE_SOURCE_CATEGORY_INVALID", f"line {line_number}")
            if str(row["provider"]) != policy.provider or str(row["dataset"]) != policy.dataset:
                raise InformationSetError("HEADLINE_SOURCE_INVALID", f"line {line_number}")
            if str(row["universe_id"]) != policy.universe_id:
                raise InformationSetError("UNIVERSE_MISMATCH", f"line {line_number}")
            raw_file = str(row["raw_file"]).strip()
            raw_sha256 = str(row["raw_sha256"]).strip().lower()
            if not raw_file or not SHA256_RE.fullmatch(raw_sha256):
                raise InformationSetError("HEADLINE_RAW_LINEAGE_INVALID", f"line {line_number}")
            try:
                price = Decimal(str(row["price_value"]))
                relative = Decimal(str(row["price_relative"]))
                weight = Decimal(str(row["economy_fixed_universe_weight"]))
            except InvalidOperation as exc:
                raise InformationSetError("HEADLINE_VALUE_INVALID", f"line {line_number}") from exc
            if not price.is_finite() or price <= 0 or not relative.is_finite() or relative <= 0 or not weight.is_finite() or weight <= 0:
                raise InformationSetError("HEADLINE_VALUE_INVALID", f"line {line_number}")
            rows.append({key: str(value) for key, value in row.items()})
    periods = set(iter_periods(policy.start_period, policy.end_period))
    economies = sorted({row["economy_code"] for row in rows})
    if set(economies) != set(policy.economy_codes):
        raise InformationSetError(
            "HEADLINE_ECONOMY_UNIVERSE_MISMATCH",
            f"expected={','.join(policy.economy_codes)} observed={','.join(economies)}",
        )
    expected_month_count = len(periods)
    expected_observation_count = len(policy.economy_codes) * expected_month_count
    if int(summary.get("month_count", -1)) != expected_month_count:
        raise InformationSetError("HEADLINE_MONTH_COUNT_MISMATCH", str(summary.get("month_count")))
    if int(summary.get("economy_count", -1)) != len(policy.economy_codes):
        raise InformationSetError("HEADLINE_ECONOMY_COUNT_MISMATCH", str(summary.get("economy_count")))
    if int(summary.get("observation_count", -1)) != expected_observation_count:
        raise InformationSetError("HEADLINE_OBSERVATION_COUNT_MISMATCH", str(summary.get("observation_count")))
    keys = [(row["economy_code"], row["period"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise InformationSetError("DUPLICATE_HEADLINE_OBSERVATION", "economy/period")
    expected = {(economy, period) for economy in economies for period in periods}
    if set(keys) != expected:
        raise InformationSetError("HEADLINE_GRID_INCOMPLETE", f"expected={len(expected)} observed={len(keys)}")
    return rows, summary


def _load_backtest_summary(policy: InformationSetPolicy, root: Path) -> Mapping[str, Any]:
    verify_manifest(root)
    path = root / "backtest_summary.json"
    if not path.is_file():
        raise InformationSetError("BACKTEST_SUMMARY_MISSING", str(path))
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("policy_version") != policy.required_backtest_policy_version:
        raise InformationSetError("BACKTEST_POLICY_MISMATCH", str(summary.get("policy_version")))
    if summary.get("vintage_mode") != policy.required_input_vintage_mode:
        raise InformationSetError("BACKTEST_VINTAGE_MODE_MISMATCH", str(summary.get("vintage_mode")))
    if summary.get("publication_aware") is not False:
        raise InformationSetError("BACKTEST_PUBLICATION_CLAIM_UNEXPECTED", str(summary.get("publication_aware")))
    if summary.get("same_period_donor_assumption") is not True:
        raise InformationSetError("BACKTEST_DONOR_ASSUMPTION_UNDECLARED", str(summary.get("same_period_donor_assumption")))
    return summary


def build_information_set_audit(
    policy_path: Path | str,
    headline_input_dir: Path | str,
    backtest_input_dir: Path | str,
    release_snapshot_dir: Path | str,
    output_dir: Path | str,
) -> Mapping[str, Any]:
    policy = InformationSetPolicy.load(policy_path)
    headline_root = Path(headline_input_dir)
    backtest_root = Path(backtest_input_dir)
    release_root = Path(release_snapshot_dir)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise InformationSetError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output))
    output.mkdir(parents=True, exist_ok=True)

    events = _load_release_events(policy, release_root)
    event_by_period = {event.reference_period: event for event in events}
    headline_rows, headline_summary = _load_headline_rows(policy, headline_root)
    backtest_summary = _load_backtest_summary(policy, backtest_root)
    headline_output_manifest_sha256 = _sha256((headline_root / "MANIFEST.sha256").read_bytes())
    if backtest_summary.get("headline_input_manifest_sha256") != headline_output_manifest_sha256:
        raise InformationSetError("BACKTEST_HEADLINE_INPUT_MISMATCH", "headline output manifest")
    if backtest_summary.get("headline_snapshot_manifest_sha256") != headline_summary.get("snapshot_manifest_sha256"):
        raise InformationSetError("BACKTEST_HEADLINE_SNAPSHOT_MISMATCH", "provider snapshot manifest")
    source_snapshot_retrieved_at = str(headline_summary["source_snapshot_retrieved_at"])
    source_snapshot_manifest_sha256 = str(headline_summary["snapshot_manifest_sha256"]).lower()

    availability_rows: list[dict[str, Any]] = []
    for row in sorted(headline_rows, key=lambda item: (item["period"], item["economy_code"])):
        event = event_by_period[row["period"]]
        availability_rows.append(
            {
                "universe_id": row["universe_id"],
                "economy_code": row["economy_code"],
                "source_category": row["source_category"],
                "reference_period": row["period"],
                "available_from_date": event.release_date.isoformat(),
                "availability_timezone": policy.release_timezone,
                "availability_precision": policy.availability_precision,
                "release_lag_days": event.release_lag_days,
                "price_value": row["price_value"],
                "price_relative": row["price_relative"],
                "economy_fixed_universe_weight": row["economy_fixed_universe_weight"],
                "value_vintage_class": "FINAL_VALUE_ONLY",
                "value_snapshot_retrieved_at": source_snapshot_retrieved_at,
                "value_snapshot_manifest_sha256": source_snapshot_manifest_sha256,
                "value_raw_file": row["raw_file"],
                "value_raw_sha256": row["raw_sha256"].lower(),
                "release_source_url": event.source_url,
                "release_evidence_file": event.raw_file,
                "release_evidence_sha256": event.raw_sha256,
            }
        )
    _write_csv(
        output / "cp00_publication_availability.csv",
        [
            "universe_id",
            "economy_code",
            "source_category",
            "reference_period",
            "available_from_date",
            "availability_timezone",
            "availability_precision",
            "release_lag_days",
            "price_value",
            "price_relative",
            "economy_fixed_universe_weight",
            "value_vintage_class",
            "value_snapshot_retrieved_at",
            "value_snapshot_manifest_sha256",
            "value_raw_file",
            "value_raw_sha256",
            "release_source_url",
            "release_evidence_file",
            "release_evidence_sha256",
        ],
        availability_rows,
    )

    release_lags = [event.release_lag_days for event in events]
    classification = {
        "current_backtest_classification": BACKTEST_CLASS,
        "reason": (
            "The v0.9.0 cases use final-vintage values and target-period donor factors. "
            "They measure resilience to missing cells after donor data exist, not a forecast "
            "using the information set available at the origin date."
        ),
        "input_vintage_mode": backtest_summary["vintage_mode"],
        "input_publication_aware": False,
        "same_period_donor_assumption": True,
        "cp00_publication_timing_attached": True,
        "final_value_snapshot_identity_attached": True,
        "value_snapshot_retrieved_at": source_snapshot_retrieved_at,
        "value_snapshot_manifest_sha256": source_snapshot_manifest_sha256,
        "historical_value_vintages_available": True,
        "this_output_contains_first_published_values": False,
        "first_published_dataset": "prc_hicp_fp",
        "supported_capability": CAPABILITY,
        "unsupported_claims": list(UNSUPPORTED),
        "real_time_backtest_ready": False,
        "requirements_for_real_time_backtest": [
            "use the companion prc_hicp_fp first-published panel for CP00-CP12",
            "join every observation to the official release date",
            "rerun B0-B4 with first-published values instead of the current final snapshot",
            "exclude target-period donors unavailable at the decision timestamp",
        ],
    }
    _atomic_write(output / "backtest_capability_classification.json", _canonical_json(classification))

    summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "status": "CP00_PUBLICATION_TIMING_AUDITED_FINAL_VALUES_ONLY",
        "universe_id": policy.universe_id,
        "provider": policy.provider,
        "dataset": policy.dataset,
        "source_category": policy.source_category,
        "release_event_count": len(events),
        "headline_observation_count": len(availability_rows),
        "economy_count": len({row["economy_code"] for row in availability_rows}),
        "economy_codes": list(policy.economy_codes),
        "start_period": policy.start_period,
        "end_period": policy.end_period,
        "minimum_release_lag_days_observed": min(release_lags),
        "maximum_release_lag_days_observed": max(release_lags),
        "mean_release_lag_days": str(Decimal(sum(release_lags)) / Decimal(len(release_lags))),
        "availability_precision": policy.availability_precision,
        "release_timezone": policy.release_timezone,
        "supported_capability": CAPABILITY,
        "historical_value_vintages_available": True,
        "this_output_contains_first_published_values": False,
        "first_published_dataset": "prc_hicp_fp",
        "publication_aware_model_comparison_allowed": False,
        "current_backtest_classification": BACKTEST_CLASS,
        "headline_input_manifest_sha256": headline_output_manifest_sha256,
        "headline_value_snapshot_retrieved_at": source_snapshot_retrieved_at,
        "headline_value_snapshot_manifest_sha256": source_snapshot_manifest_sha256,
        "backtest_input_manifest_sha256": _sha256((backtest_root / "MANIFEST.sha256").read_bytes()),
        "release_snapshot_manifest_sha256": _sha256((release_root / "MANIFEST.sha256").read_bytes()),
        "headline_source_independent": bool(headline_summary.get("headline_source_independent")),
        "model_code_changed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output / "run_summary.json", _canonical_json(summary))
    report = [
        "# Armilar v0.9.3 CP00 publication-timing audit",
        "",
        "## What is now auditable",
        "",
        f"- {len(events)} official CP00 release events from {policy.start_period} to {policy.end_period}",
        f"- {len(availability_rows)} economy-month observations with a day-level availability date",
        f"- Capability: `{CAPABILITY}`",
        "",
        "## What this calendar-linked output does not contain",
        "",
        "This audit links the current final CP00 snapshot to official publication dates. The companion `prc_hicp_fp` module supplies the values as first published; those values are deliberately kept in a separate, independently hashed panel.",
        "",
        "## Backtest classification",
        "",
        f"The v0.9.0 backtest is classified as `{BACKTEST_CLASS}` because it uses target-period donor factors and final-vintage observations. It is a missingness stress test, not a historical real-time forecast.",
        "",
        "## Decision boundary",
        "",
        "B1 and B4 must not be promoted until B0-B4 are rerun with the companion first-published CP00-CP12 panel and target-period donors unavailable at each origin are excluded.",
        "",
        "`model_promotion_allowed=false`",
        "",
        "`research_release_allowed=false`",
        "",
        "`monetary_release_allowed=false`",
    ]
    _atomic_write(output / "INFORMATION_SET_REPORT.md", ("\n".join(report) + "\n").encode("utf-8"))
    _write_manifest(output)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.3 information-set audit")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire-release-evidence")
    acquire.add_argument("--policy", required=True)
    acquire.add_argument("--registry-csv", required=True)
    acquire.add_argument("--output-dir", required=True)
    acquire.add_argument("--timeout-seconds", type=int, default=60)
    seal = sub.add_parser("seal-release-snapshot")
    seal.add_argument("--policy", required=True)
    seal.add_argument("--registry-csv", required=True)
    seal.add_argument("--evidence-root", required=True)
    seal.add_argument("--output-dir", required=True)
    build = sub.add_parser("build")
    build.add_argument("--policy", required=True)
    build.add_argument("--headline-input-dir", required=True)
    build.add_argument("--backtest-input-dir", required=True)
    build.add_argument("--release-snapshot-dir", required=True)
    build.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "acquire-release-evidence":
        result = acquire_release_evidence(
            args.policy, args.registry_csv, args.output_dir, timeout_seconds=args.timeout_seconds
        )
    elif args.command == "seal-release-snapshot":
        result = seal_release_snapshot(args.policy, args.registry_csv, args.evidence_root, args.output_dir)
    elif args.command == "build":
        result = build_information_set_audit(
            args.policy,
            args.headline_input_dir,
            args.backtest_input_dir,
            args.release_snapshot_dir,
            args.output_dir,
        )
    else:
        verify_manifest(args.root)
        result = {"status": "MANIFEST_VERIFIED", "root": args.root}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
