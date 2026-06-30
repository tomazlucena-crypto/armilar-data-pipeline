from __future__ import annotations

import csv
import hashlib
import json
import math
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from .models import validate_month

FX_CONVENTION = "CURRENCY_UNITS_PER_EUR"
PRICE_BASIS = "LOCAL_CURRENCY_RELATIVE"
ECB_PROVIDER = "ECB"
ECB_DATASET = "EXR"
PRIMARY_INDEX_ID = "ARM-PPP-WEIGHTED-LOCAL-PRICE-RELATIVES-V0.8.3"
COMMON_CURRENCY_INDEX_ID = "ARM-COMMON-CURRENCY-BASKET-COST-EUR-V0.8.3"


class FXMethodologyError(ValueError):
    """Raised when FX data or methodology would violate the ratified contract."""


@dataclass(frozen=True, slots=True)
class PriceCell:
    period: str
    economy_code: str
    category_code: str
    fixed_weight: float
    price_relative: float
    price_basis: str = PRICE_BASIS

    def validate(self) -> None:
        validate_month(self.period)
        if len(self.economy_code) != 3 or self.economy_code != self.economy_code.upper():
            raise FXMethodologyError(f"invalid economy_code: {self.economy_code!r}")
        if not self.category_code.strip():
            raise FXMethodologyError("category_code is required")
        if not math.isfinite(self.fixed_weight) or self.fixed_weight <= 0:
            raise FXMethodologyError("fixed_weight must be finite and positive")
        if not math.isfinite(self.price_relative) or self.price_relative <= 0:
            raise FXMethodologyError("price_relative must be finite and positive")
        if self.price_basis != PRICE_BASIS:
            raise FXMethodologyError(
                "price input must be LOCAL_CURRENCY_RELATIVE; common-currency inputs "
                "would cause double conversion"
            )


@dataclass(frozen=True, slots=True)
class CurrencyAssignment:
    economy_code: str
    currency_code: str
    effective_from: str
    effective_to: str = ""

    def validate(self) -> None:
        if len(self.economy_code) != 3 or self.economy_code != self.economy_code.upper():
            raise FXMethodologyError(f"invalid economy_code: {self.economy_code!r}")
        if len(self.currency_code) != 3 or self.currency_code != self.currency_code.upper():
            raise FXMethodologyError(f"invalid currency_code: {self.currency_code!r}")
        validate_month(self.effective_from)
        if self.effective_to:
            validate_month(self.effective_to)
            if self.effective_to < self.effective_from:
                raise FXMethodologyError("currency assignment effective_to precedes effective_from")

    def applies(self, period: str) -> bool:
        return self.effective_from <= period and (not self.effective_to or period <= self.effective_to)


@dataclass(frozen=True, slots=True)
class FXObservation:
    period: str
    currency_code: str
    currency_units_per_eur: float
    redenomination_factor_to_canonical: float = 1.0
    convention: str = FX_CONVENTION
    provider: str = ECB_PROVIDER
    dataset: str = ECB_DATASET
    series_key: str = ""
    retrieved_at: str = ""
    raw_sha256: str = ""

    def validate(self) -> None:
        validate_month(self.period)
        if len(self.currency_code) != 3 or self.currency_code != self.currency_code.upper():
            raise FXMethodologyError(f"invalid currency_code: {self.currency_code!r}")
        if not math.isfinite(self.currency_units_per_eur) or self.currency_units_per_eur <= 0:
            raise FXMethodologyError("currency_units_per_eur must be finite and positive")
        if (
            not math.isfinite(self.redenomination_factor_to_canonical)
            or self.redenomination_factor_to_canonical <= 0
        ):
            raise FXMethodologyError(
                "redenomination_factor_to_canonical must be finite and positive"
            )
        if self.convention != FX_CONVENTION:
            raise FXMethodologyError(
                f"unsupported FX convention {self.convention!r}; expected {FX_CONVENTION}"
            )
        if self.currency_code != "EUR" and self.provider != ECB_PROVIDER:
            raise FXMethodologyError("the v0.8.3 pilot accepts ECB FX observations only")
        if self.currency_code != "EUR" and self.dataset != ECB_DATASET:
            raise FXMethodologyError("the v0.8.3 pilot accepts ECB EXR observations only")
        if self.raw_sha256 and len(self.raw_sha256) != 64:
            raise FXMethodologyError("raw_sha256 must contain 64 hexadecimal characters")

    @property
    def canonical_units_per_eur(self) -> float:
        return self.currency_units_per_eur * self.redenomination_factor_to_canonical


@dataclass(frozen=True, slots=True)
class FXReceipt:
    provider: str
    dataset: str
    final_url: str
    retrieved_at: str
    mode: str
    http_status: int
    content_type: str
    byte_count: int
    sha256: str
    query_spec: dict[str, object]
    discovered_columns: tuple[str, ...]
    observation_count: int

    def validate(self) -> None:
        if self.provider != ECB_PROVIDER or self.dataset != ECB_DATASET:
            raise FXMethodologyError("FX receipt must identify ECB/EXR")
        if self.mode not in {"live", "replay"}:
            raise FXMethodologyError("FX receipt mode must be live or replay")
        if self.http_status != 200:
            raise FXMethodologyError("only successful ECB responses are admissible")
        if self.byte_count <= 0 or self.observation_count <= 0:
            raise FXMethodologyError("FX receipt cannot describe an empty response")
        if len(self.sha256) != 64:
            raise FXMethodologyError("FX receipt sha256 must contain 64 characters")
        if not self.discovered_columns:
            raise FXMethodologyError("FX receipt must preserve discovered columns")


def build_ecb_exr_url(currencies: Iterable[str], start_period: str, end_period: str) -> str:
    validate_month(start_period)
    validate_month(end_period)
    if end_period < start_period:
        raise FXMethodologyError("end_period precedes start_period")
    codes = sorted({str(code).strip().upper() for code in currencies if str(code).strip()})
    if "EUR" in codes:
        codes.remove("EUR")
    if not codes:
        raise FXMethodologyError("at least one non-EUR currency is required")
    for code in codes:
        if len(code) != 3 or not code.isalpha():
            raise FXMethodologyError(f"invalid ECB currency code: {code!r}")
    key = f"M.{'+'.join(codes)}.EUR.SP00.A"
    return (
        "https://data-api.ecb.europa.eu/service/data/EXR/"
        f"{quote(key, safe='.+')}?startPeriod={start_period}&endPeriod={end_period}"
        "&format=csvdata&detail=dataonly"
    )


def parse_ecb_csv(
    content: bytes,
    *,
    retrieved_at: str,
    raw_sha256: str,
    requested_currencies: Iterable[str] | None = None,
) -> tuple[list[FXObservation], tuple[str, ...]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FXMethodologyError(f"ECB response is not UTF-8 CSV: {exc}") from exc
    reader = csv.DictReader(text.splitlines())
    columns = tuple(reader.fieldnames or ())
    if not columns:
        raise FXMethodologyError("ECB CSV has no header")

    aliases = {
        "period": ("TIME_PERIOD", "TIME PERIOD", "TIME_PERIOD_START"),
        "value": ("OBS_VALUE", "OBS VALUE"),
        "currency": ("CURRENCY",),
        "denominator": ("CURRENCY_DENOM", "CURRENCY DENOM"),
        "frequency": ("FREQ", "FREQUENCY"),
        "type": ("EXR_TYPE", "EXR TYPE"),
        "suffix": ("EXR_SUFFIX", "EXR SUFFIX"),
        "series_key": ("KEY", "SERIES_KEY", "SERIES KEY"),
    }

    def discover(name: str, *, required: bool = True) -> str:
        for candidate in aliases[name]:
            if candidate in columns:
                return candidate
        if required:
            raise FXMethodologyError(
                f"ECB CSV is missing {name}; discovered columns={list(columns)}"
            )
        return ""

    period_col = discover("period")
    value_col = discover("value")
    currency_col = discover("currency")
    denominator_col = discover("denominator")
    frequency_col = discover("frequency")
    type_col = discover("type")
    suffix_col = discover("suffix")
    series_key_col = discover("series_key", required=False)

    requested = (
        {str(code).strip().upper() for code in requested_currencies}
        if requested_currencies is not None
        else None
    )
    observations: list[FXObservation] = []
    seen: set[tuple[str, str]] = set()
    for line_number, row in enumerate(reader, start=2):
        period = (row.get(period_col) or "").strip()[:7]
        currency = (row.get(currency_col) or "").strip().upper()
        if requested is not None and currency not in requested:
            continue
        if (row.get(frequency_col) or "").strip() != "M":
            raise FXMethodologyError(f"non-monthly ECB row at line {line_number}")
        if (row.get(denominator_col) or "").strip().upper() != "EUR":
            raise FXMethodologyError(f"non-EUR denominator at line {line_number}")
        if (row.get(type_col) or "").strip() != "SP00":
            raise FXMethodologyError(f"non-spot ECB row at line {line_number}")
        if (row.get(suffix_col) or "").strip() != "A":
            raise FXMethodologyError(f"non-average ECB row at line {line_number}")
        try:
            value = float((row.get(value_col) or "").strip())
        except ValueError as exc:
            raise FXMethodologyError(f"invalid ECB FX value at line {line_number}") from exc
        key = (currency, period)
        if key in seen:
            raise FXMethodologyError(f"duplicate ECB FX observation: {key}")
        seen.add(key)
        observation = FXObservation(
            period=period,
            currency_code=currency,
            currency_units_per_eur=value,
            convention=FX_CONVENTION,
            provider=ECB_PROVIDER,
            dataset=ECB_DATASET,
            series_key=(row.get(series_key_col) or "").strip() if series_key_col else "",
            retrieved_at=retrieved_at,
            raw_sha256=raw_sha256,
        )
        observation.validate()
        observations.append(observation)
    if not observations:
        raise FXMethodologyError("ECB CSV contains no admissible monthly observations")
    if requested is not None:
        missing = sorted(requested - {row.currency_code for row in observations})
        if missing:
            raise FXMethodologyError(f"ECB response omitted requested currencies: {missing}")
    return sorted(observations, key=lambda row: (row.currency_code, row.period)), columns


def acquire_ecb_fx(
    currencies: Iterable[str],
    start_period: str,
    end_period: str,
    output_dir: Path,
    *,
    mode: str,
    fixture_path: Path | None = None,
    expected_sha256: str = "",
) -> dict[str, object]:
    codes = sorted({str(code).strip().upper() for code in currencies if str(code).strip()})
    non_eur = [code for code in codes if code != "EUR"]
    url = build_ecb_exr_url(non_eur, start_period, end_period)
    if mode == "replay":
        if fixture_path is None:
            raise FXMethodologyError("fixture_path is required in replay mode")
        content = fixture_path.read_bytes()
        retrieved_at = "REPLAY"
        final_url = url
        status = 200
        content_type = "text/csv"
    elif mode == "live":
        if fixture_path is not None:
            raise FXMethodologyError("fixture_path is forbidden in live mode")
        request = urllib.request.Request(
            url,
            headers={"Accept": "text/csv", "User-Agent": "armilar-data-pipeline/0.8.3"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:  # nosec B310
            content = response.read()
            final_url = response.geturl()
            status = int(getattr(response, "status", 200))
            content_type = response.headers.get_content_type()
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    else:
        raise FXMethodologyError(f"unsupported acquisition mode: {mode}")

    raw_hash = hashlib.sha256(content).hexdigest()
    if expected_sha256 and raw_hash != expected_sha256.lower():
        raise FXMethodologyError(
            f"ECB replay hash mismatch: expected {expected_sha256}, got {raw_hash}"
        )
    observations, columns = parse_ecb_csv(
        content,
        retrieved_at=retrieved_at,
        raw_sha256=raw_hash,
        requested_currencies=non_eur,
    )
    receipt = FXReceipt(
        provider=ECB_PROVIDER,
        dataset=ECB_DATASET,
        final_url=final_url,
        retrieved_at=retrieved_at,
        mode=mode,
        http_status=status,
        content_type=content_type,
        byte_count=len(content),
        sha256=raw_hash,
        query_spec={
            "frequency": "M",
            "currencies": non_eur,
            "currency_denominator": "EUR",
            "exchange_rate_type": "SP00",
            "series_variation": "A",
            "start_period": start_period,
            "end_period": end_period,
            "convention": FX_CONVENTION,
        },
        discovered_columns=columns,
        observation_count=len(observations),
    )
    receipt.validate()

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "ecb_exr_monthly.csv"
    raw_path.write_bytes(content)
    _write_fx_observations(output_dir / "normalized_fx_observations.csv", observations)
    _write_receipts(output_dir / "fx_receipts.jsonl", [receipt])
    structure = {
        "provider": ECB_PROVIDER,
        "dataset": ECB_DATASET,
        "discovered_columns": list(columns),
        "structure_sha256": hashlib.sha256(
            json.dumps(list(columns), separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "raw_sha256": raw_hash,
    }
    (output_dir / "fx_provider_structure.json").write_text(
        json.dumps(structure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_manifest(
        output_dir,
        [
            "raw/ecb_exr_monthly.csv",
            "normalized_fx_observations.csv",
            "fx_receipts.jsonl",
            "fx_provider_structure.json",
        ],
    )
    return {
        "provider": ECB_PROVIDER,
        "dataset": ECB_DATASET,
        "mode": mode,
        "currency_count": len(non_eur),
        "observation_count": len(observations),
        "raw_sha256": raw_hash,
        "convention": FX_CONVENTION,
        "monetary_release_allowed": False,
    }


def build_fx_separation(
    price_cells: Iterable[PriceCell],
    assignments: Iterable[CurrencyAssignment],
    fx_observations: Iterable[FXObservation],
    receipts: Iterable[FXReceipt],
    reference_period: str,
    scope_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    validate_month(reference_period)
    if not scope_id.strip():
        raise FXMethodologyError("scope_id is required")
    prices = list(price_cells)
    currency_assignments = list(assignments)
    fx_rows = list(fx_observations)
    receipt_rows = list(receipts)
    if not prices:
        raise FXMethodologyError("price cells are empty")
    if not currency_assignments:
        raise FXMethodologyError("currency assignments are empty")
    for row in prices:
        row.validate()
    for row in currency_assignments:
        row.validate()
    for row in fx_rows:
        row.validate()
    for row in receipt_rows:
        row.validate()

    price_by_key = {(row.period, row.economy_code, row.category_code): row for row in prices}
    if len(price_by_key) != len(prices):
        raise FXMethodologyError("duplicate price cell")
    periods = sorted({row.period for row in prices})
    if reference_period not in periods:
        raise FXMethodologyError("reference period is absent from price cells")
    base_keys = {
        (row.economy_code, row.category_code): row.fixed_weight
        for row in prices
        if row.period == reference_period
    }
    if not base_keys:
        raise FXMethodologyError("reference-period price grid is empty")
    if not math.isclose(sum(base_keys.values()), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise FXMethodologyError("reference-period fixed weights must sum to 1")
    for period in periods:
        period_rows = [row for row in prices if row.period == period]
        period_keys = {(row.economy_code, row.category_code): row.fixed_weight for row in period_rows}
        if period_keys != base_keys:
            raise FXMethodologyError(
                f"price universe or fixed weights changed at {period}; no renormalisation allowed"
            )

    _validate_assignment_overlaps(currency_assignments)
    fx_by_key = {(row.currency_code, row.period): row for row in fx_rows}
    if len(fx_by_key) != len(fx_rows):
        raise FXMethodologyError("duplicate FX observation")

    inflation_rows: list[dict[str, object]] = []
    common_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    for period in periods:
        period_prices = sorted(
            (row for row in prices if row.period == period),
            key=lambda row: (row.economy_code, row.category_code),
        )
        inflation_value = sum(row.fixed_weight * row.price_relative for row in period_prices)
        inflation_rows.append(
            {
                "index_id": PRIMARY_INDEX_ID,
                "scope_id": scope_id,
                "period": period,
                "value": inflation_value,
                "status": "COMPLETE",
                "reference_period": reference_period,
                "aggregation_mode": "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES",
                "current_fx_included": False,
                "informs_monetary_policy": False,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            }
        )

        common_value = 0.0
        covered_weight = 0.0
        missing: dict[str, float] = {}
        by_economy_weight: dict[str, float] = {}
        for row in period_prices:
            by_economy_weight[row.economy_code] = (
                by_economy_weight.get(row.economy_code, 0.0) + row.fixed_weight
            )
            currency = _currency_for(currency_assignments, row.economy_code, period)
            ref_currency = _currency_for(currency_assignments, row.economy_code, reference_period)
            if currency != ref_currency:
                missing[f"{row.economy_code}:CURRENCY_TRANSITION_{ref_currency}_TO_{currency}"] = (
                    missing.get(
                        f"{row.economy_code}:CURRENCY_TRANSITION_{ref_currency}_TO_{currency}",
                        0.0,
                    )
                    + row.fixed_weight
                )
                continue
            current_fx = _fx_for(fx_by_key, currency, period)
            reference_fx = _fx_for(fx_by_key, currency, reference_period)
            if current_fx is None or reference_fx is None:
                missing[f"{row.economy_code}:{currency}"] = (
                    missing.get(f"{row.economy_code}:{currency}", 0.0) + row.fixed_weight
                )
                continue
            factor = reference_fx / current_fx
            common_value += row.fixed_weight * row.price_relative * factor
            covered_weight += row.fixed_weight

        status = "COMPLETE" if math.isclose(covered_weight, 1.0, abs_tol=1e-9) else "INCOMPLETE_FX"
        common_rows.append(
            {
                "index_id": COMMON_CURRENCY_INDEX_ID,
                "scope_id": scope_id,
                "period": period,
                "value": common_value if status == "COMPLETE" else "",
                "status": status,
                "reference_period": reference_period,
                "numeraire": "EUR",
                "fx_convention": FX_CONVENTION,
                "covered_fixed_weight": covered_weight,
                "missing_fixed_weight": max(0.0, 1.0 - covered_weight),
                "missing_economy_currency": "|".join(sorted(missing)),
                "informs_monetary_policy": False,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            }
        )
        for economy, weight in sorted(by_economy_weight.items()):
            currency = _currency_for(currency_assignments, economy, period)
            ref_currency = _currency_for(currency_assignments, economy, reference_period)
            transition = currency != ref_currency
            current_fx = None if transition else _fx_for(fx_by_key, currency, period)
            reference_fx = None if transition else _fx_for(fx_by_key, currency, reference_period)
            available = current_fx is not None and reference_fx is not None
            coverage_rows.append(
                {
                    "scope_id": scope_id,
                    "period": period,
                    "economy_code": economy,
                    "currency_code": currency,
                    "fixed_weight": weight,
                    "fx_available": available,
                    "reference_fx_available": reference_fx is not None,
                    "current_fx_available": current_fx is not None,
                    "fx_convention": FX_CONVENTION,
                    "reason": (
                        ""
                        if available
                        else (
                            f"UNRATIFIED_CURRENCY_TRANSITION_{ref_currency}_TO_{currency}"
                            if transition
                            else "MISSING_ECB_FX"
                        )
                    ),
                }
            )

    if not math.isclose(float(inflation_rows[0]["value"]), 100.0, abs_tol=1e-9):
        raise FXMethodologyError("primary inflation index reference period is not 100")
    if common_rows[0]["status"] == "COMPLETE" and not math.isclose(
        float(common_rows[0]["value"]), 100.0, abs_tol=1e-9
    ):
        raise FXMethodologyError("common-currency reference period is not 100")

    summary = {
        "methodology_version": "0.8.3",
        "scope_id": scope_id,
        "reference_period": reference_period,
        "primary_index_id": PRIMARY_INDEX_ID,
        "primary_method": "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES",
        "primary_current_fx_included": False,
        "common_currency_index_id": COMMON_CURRENCY_INDEX_ID,
        "common_currency_method": "COMMON_CURRENCY_BASKET_COST",
        "common_currency_numeraire": "EUR",
        "fx_provider": ECB_PROVIDER,
        "fx_dataset": ECB_DATASET,
        "fx_frequency": "M",
        "fx_series_variation": "A",
        "fx_convention": FX_CONVENTION,
        "double_conversion_prevention": PRICE_BASIS,
        "period_count": len(periods),
        "complete_common_currency_period_count": sum(
            row["status"] == "COMPLETE" for row in common_rows
        ),
        "receipt_count": len(receipt_rows),
        "primary_informs_monetary_policy": False,
        "common_currency_informs_monetary_policy": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    return inflation_rows, common_rows, coverage_rows, summary


def write_fx_separation_outputs(
    inflation_rows: list[dict[str, object]],
    common_rows: list[dict[str, object]],
    coverage_rows: list[dict[str, object]],
    summary: dict[str, object],
    receipts: Iterable[FXReceipt],
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_dict_csv(output_dir / "monthly_global_inflation_index.csv", inflation_rows)
    _write_dict_csv(output_dir / "monthly_common_currency_cost.csv", common_rows)
    _write_dict_csv(output_dir / "fx_coverage.csv", coverage_rows)
    _write_receipts(output_dir / "fx_receipts.jsonl", list(receipts))
    (output_dir / "fx_methodology_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_manifest(
        output_dir,
        [
            "monthly_global_inflation_index.csv",
            "monthly_common_currency_cost.csv",
            "fx_receipts.jsonl",
            "fx_coverage.csv",
            "fx_methodology_summary.json",
        ],
    )
    return summary


def build_fx_separation_from_files(
    price_contributions_path: Path,
    currency_registry_path: Path,
    fx_observations_path: Path,
    fx_receipts_path: Path,
    reference_period: str,
    scope_id: str,
    output_dir: Path,
    *,
    price_basis: str,
) -> dict[str, object]:
    if price_basis != PRICE_BASIS:
        raise FXMethodologyError(
            "--price-basis must explicitly be LOCAL_CURRENCY_RELATIVE"
        )
    prices = load_price_cells(price_contributions_path, price_basis=price_basis)
    assignments = load_currency_assignments(currency_registry_path)
    observations = load_fx_observations(fx_observations_path)
    receipts = load_fx_receipts(fx_receipts_path)
    result = build_fx_separation(
        prices, assignments, observations, receipts, reference_period, scope_id
    )
    return write_fx_separation_outputs(*result, receipts, output_dir)


def load_price_cells(path: Path, *, price_basis: str) -> list[PriceCell]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: list[PriceCell] = []
    for line, row in enumerate(rows, start=2):
        category = (row.get("source_category_code") or row.get("category_code") or "").strip()
        try:
            item = PriceCell(
                period=(row.get("period") or "").strip(),
                economy_code=(row.get("economy_code") or "").strip().upper(),
                category_code=category,
                fixed_weight=float(row["fixed_universe_weight"]),
                price_relative=float(row["price_relative"]),
                price_basis=price_basis,
            )
            item.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise FXMethodologyError(f"invalid price contribution at line {line}: {exc}") from exc
        result.append(item)
    if not result:
        raise FXMethodologyError("price contribution input is empty")
    return result


def load_currency_assignments(path: Path) -> list[CurrencyAssignment]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: list[CurrencyAssignment] = []
    for line, row in enumerate(rows, start=2):
        item = CurrencyAssignment(
            economy_code=(row.get("economy_code") or "").strip().upper(),
            currency_code=(row.get("currency_code") or "").strip().upper(),
            effective_from=(row.get("effective_from") or "").strip(),
            effective_to=(row.get("effective_to") or "").strip(),
        )
        try:
            item.validate()
        except ValueError as exc:
            raise FXMethodologyError(f"invalid currency assignment at line {line}: {exc}") from exc
        result.append(item)
    if not result:
        raise FXMethodologyError("currency registry is empty")
    _validate_assignment_overlaps(result)
    return result


def load_fx_observations(path: Path) -> list[FXObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: list[FXObservation] = []
    for line, row in enumerate(rows, start=2):
        try:
            item = FXObservation(
                period=(row.get("period") or "").strip(),
                currency_code=(row.get("currency_code") or "").strip().upper(),
                currency_units_per_eur=float(row["currency_units_per_eur"]),
                redenomination_factor_to_canonical=float(
                    row.get("redenomination_factor_to_canonical") or 1.0
                ),
                convention=(row.get("convention") or "").strip(),
                provider=(row.get("provider") or "").strip(),
                dataset=(row.get("dataset") or "").strip(),
                series_key=(row.get("series_key") or "").strip(),
                retrieved_at=(row.get("retrieved_at") or "").strip(),
                raw_sha256=(row.get("raw_sha256") or "").strip(),
            )
            item.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise FXMethodologyError(f"invalid FX observation at line {line}: {exc}") from exc
        result.append(item)
    return result


def load_fx_receipts(path: Path) -> list[FXReceipt]:
    receipts: list[FXReceipt] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            receipt = FXReceipt(
                provider=payload["provider"],
                dataset=payload["dataset"],
                final_url=payload["final_url"],
                retrieved_at=payload["retrieved_at"],
                mode=payload["mode"],
                http_status=int(payload["http_status"]),
                content_type=payload["content_type"],
                byte_count=int(payload["byte_count"]),
                sha256=payload["sha256"],
                query_spec=dict(payload["query_spec"]),
                discovered_columns=tuple(payload["discovered_columns"]),
                observation_count=int(payload["observation_count"]),
            )
            receipt.validate()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FXMethodologyError(f"invalid FX receipt at line {line_number}: {exc}") from exc
        receipts.append(receipt)
    return receipts


def _currency_for(assignments: list[CurrencyAssignment], economy: str, period: str) -> str:
    matches = [row.currency_code for row in assignments if row.economy_code == economy and row.applies(period)]
    if len(matches) != 1:
        raise FXMethodologyError(
            f"expected exactly one currency assignment for {economy}/{period}, got {matches}"
        )
    return matches[0]


def _fx_for(fx_by_key: dict[tuple[str, str], FXObservation], currency: str, period: str) -> float | None:
    if currency == "EUR":
        return 1.0
    row = fx_by_key.get((currency, period))
    return None if row is None else row.canonical_units_per_eur


def _validate_assignment_overlaps(assignments: list[CurrencyAssignment]) -> None:
    by_economy: dict[str, list[CurrencyAssignment]] = {}
    for row in assignments:
        by_economy.setdefault(row.economy_code, []).append(row)
    for economy, rows in by_economy.items():
        ordered = sorted(rows, key=lambda row: (row.effective_from, row.effective_to))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                left_end = left.effective_to or "9999-12"
                right_end = right.effective_to or "9999-12"
                if max(left.effective_from, right.effective_from) <= min(left_end, right_end):
                    raise FXMethodologyError(
                        f"overlapping currency assignments for {economy}: {left} / {right}"
                    )


def _write_fx_observations(path: Path, rows: list[FXObservation]) -> None:
    fieldnames = [
        "period",
        "currency_code",
        "currency_units_per_eur",
        "redenomination_factor_to_canonical",
        "convention",
        "provider",
        "dataset",
        "series_key",
        "retrieved_at",
        "raw_sha256",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_receipts(path: Path, receipts: list[FXReceipt]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for receipt in receipts:
            payload = asdict(receipt)
            payload["discovered_columns"] = list(receipt.discovered_columns)
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _write_dict_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise FXMethodologyError(f"cannot write empty output: {path.name}")
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(output_dir: Path, names: list[str]) -> None:
    entries = [
        f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()} {name}"
        for name in names
    ]
    (output_dir / "MANIFEST.sha256").write_text(
        "\n".join(entries) + "\n", encoding="utf-8"
    )
