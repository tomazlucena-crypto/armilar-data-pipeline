"""Core utilities for ARMILAR v0.10.0 point-in-time target alignment.

The module deliberately contains no model fitting, feature selection, ARM-L logic or
release-gate opening.  It only builds deterministic research artefacts from verified
ARM-O and v0.9.9 feature bundles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PRECISION = 28
ROUNDING = ROUND_HALF_EVEN
ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


class BacktestProtocolError(RuntimeError):
    """Raised when an artefact would violate the frozen v0.10.0 protocol."""


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise BacktestProtocolError(f"{field} must be an exact decimal string, integer or Decimal")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BacktestProtocolError(f"invalid decimal for {field}: {value!r}") from exc
    if not parsed.is_finite():
        raise BacktestProtocolError(f"{field} must be finite")
    return parsed


def decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fixed_decimal_text(value: Decimal, places: int = 12) -> str:
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUNDING
        quantized = value.quantize(quantum)
    return format(quantized, f".{places}f")


def parse_utc(value: str, field: str) -> datetime:
    if not UTC_RE.fullmatch(value):
        raise BacktestProtocolError(f"{field} must be an explicit UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BacktestProtocolError(f"invalid {field}: {value!r}") from exc
    if result.utcoffset() != timezone.utc.utcoffset(result):
        raise BacktestProtocolError(f"{field} must be UTC")
    return result


def canonical_utc(value: str, field: str) -> str:
    parsed = parse_utc(value, field)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_month(value: str, field: str = "period") -> str:
    if not MONTH_RE.fullmatch(value):
        raise BacktestProtocolError(f"invalid {field}: {value!r}")
    return value


def add_months(period: str, delta: int) -> str:
    validate_month(period)
    year, month = (int(part) for part in period.split("-"))
    ordinal = year * 12 + (month - 1) + delta
    if ordinal < 0:
        raise BacktestProtocolError("period arithmetic underflow")
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def month_distance(earlier: str, later: str) -> int:
    validate_month(earlier, "earlier_period")
    validate_month(later, "later_period")
    ey, em = (int(x) for x in earlier.split("-"))
    ly, lm = (int(x) for x in later.split("-"))
    return (ly - ey) * 12 + (lm - em)


def cutoff_month(cutoff: str) -> str:
    parsed = parse_utc(cutoff, "cutoff")
    return f"{parsed.year:04d}-{parsed.month:02d}"


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise BacktestProtocolError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise BacktestProtocolError(f"cannot read CSV: {path}") from exc


def csv_bytes(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return stream.getvalue().encode("utf-8")


def write_manifest(root: Path, included: Iterable[str] | None = None) -> dict[str, str]:
    names = sorted(included if included is not None else (
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    ))
    entries: dict[str, str] = {}
    for name in names:
        candidate = root / name
        if not candidate.is_file():
            raise BacktestProtocolError(f"manifest input missing: {name}")
        entries[name] = sha256_path(candidate)
    (root / "MANIFEST.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in entries.items()),
        encoding="utf-8",
        newline="\n",
    )
    return entries


def read_manifest(root: Path) -> dict[str, str]:
    path = root / "MANIFEST.sha256"
    if not path.is_file():
        raise BacktestProtocolError(f"manifest missing: {path}")
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise BacktestProtocolError(f"invalid manifest line {number}") from exc
        if not SHA256_RE.fullmatch(digest) or not name or name in entries:
            raise BacktestProtocolError(f"invalid manifest entry on line {number}")
        entries[name] = digest
    if not entries:
        raise BacktestProtocolError("manifest must not be empty")
    return entries


def verify_manifest(root: Path, *, exact: bool = True) -> dict[str, str]:
    entries = read_manifest(root)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if exact and actual_files != set(entries):
        missing = sorted(set(entries) - actual_files)
        extra = sorted(actual_files - set(entries))
        raise BacktestProtocolError(f"manifest file set mismatch; missing={missing}, extra={extra}")
    for name, expected in entries.items():
        path = root / name
        if not path.is_file() or sha256_path(path) != expected:
            raise BacktestProtocolError(f"manifest hash mismatch: {name}")
    return entries


def directory_manifest_sha256(root: Path) -> str:
    verify_manifest(root)
    return sha256_path(root / "MANIFEST.sha256")


def write_transactional(output_dir: Path, writer) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise BacktestProtocolError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        writer(staging)
        verify_manifest(staging)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
            import shutil
            shutil.rmtree(staging, ignore_errors=True)


def stable_id(*parts: str) -> str:
    return sha256_bytes("\x1f".join(parts).encode("utf-8"))
