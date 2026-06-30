from __future__ import annotations

import csv
import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .models import PriceObservation, PriceSeriesDefinition
from .normalizer import normalize_observations
from .registry import load_registry


PARSER_VERSION = "armilar-prices-acquisition-v0.8.1-provenance-bound"


class PriceAcquisitionError(ValueError):
    """Raised when price acquisition or replay violates its contract."""


@dataclass(frozen=True, slots=True)
class ProviderStructure:
    provider: str
    dataset: str
    dimension_order: tuple[str, ...]
    allowed_values: dict[str, tuple[str, ...]]
    schema_sha256: str
    source_url: str
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    provider: str
    dataset: str
    series_id: str
    final_url: str
    query_spec: dict[str, str]
    retrieved_at: str
    http_status: int
    content_type: str
    byte_count: int
    sha256: str
    etag: str
    last_modified: str
    dsd_schema_sha256: str
    parser_version: str = PARSER_VERSION


def acquire_prices(
    registry_path: Path,
    output_dir: Path,
    *,
    mode: str,
    fixture_dir: Path | None = None,
    reference_period: str = "2021-01",
) -> dict[str, object]:
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_version = str(registry_payload.get("registry_version", "")).strip()
    if not registry_version:
        raise PriceAcquisitionError("registry_version is required")
    definitions = load_registry(registry_path)
    if mode == "replay":
        if fixture_dir is None:
            raise PriceAcquisitionError("fixture_dir is required in replay mode")
        observations, receipts, structures = replay_price_fixtures(definitions, fixture_dir)
    elif mode == "live":
        observations, receipts, structures = acquire_live_prices(definitions)
    else:
        raise PriceAcquisitionError(f"unsupported acquisition mode: {mode}")

    normalized, normalization_summary = normalize_observations(
        definitions,
        observations,
        reference_period,
    )
    write_acquisition_outputs(
        output_dir,
        definitions,
        observations,
        normalized,
        receipts,
        structures,
        {
            "registry_version": registry_version,
            "mode": mode,
            "reference_period": reference_period,
            "raw_observation_count": len(observations),
            "normalized_observation_count": len(normalized),
            "provider_count": len({row.provider for row in definitions if row.enabled}),
            "series_count": len([row for row in definitions if row.enabled]),
            "research_release_allowed": False,
            "monetary_release_allowed": False,
            "normalization": normalization_summary,
        },
    )
    return {
        "registry_version": registry_version,
        "mode": mode,
        "reference_period": reference_period,
        "raw_observation_count": len(observations),
        "normalized_observation_count": len(normalized),
        "receipt_count": len(receipts),
        "provider_structure_count": len(structures),
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }


def replay_price_fixtures(
    definitions: Iterable[PriceSeriesDefinition],
    fixture_dir: Path,
) -> tuple[list[PriceObservation], list[SourceReceipt], list[ProviderStructure]]:
    definitions_by_id = {row.series_id: row for row in definitions}
    structures = _load_provider_structures(fixture_dir / "provider_structure_manifest.json")
    structures_by_key = {(row.provider, row.dataset): row for row in structures}
    raw_dir = fixture_dir / "raw"
    observations: list[PriceObservation] = []
    receipts: list[SourceReceipt] = []
    seen: set[tuple[str, str]] = set()

    for definition in sorted(
        (row for row in definitions_by_id.values() if row.enabled),
        key=lambda row: row.series_id,
    ):
        structure = structures_by_key.get((definition.provider, definition.dataset))
        if structure is None:
            raise PriceAcquisitionError(
                f"missing provider structure for {definition.provider}/{definition.dataset}"
            )
        _validate_definition_against_structure(definition, structure)

        raw_name = f"{definition.series_id}.json"
        raw_path = raw_dir / raw_name
        if not raw_path.exists():
            raise PriceAcquisitionError(f"missing raw fixture: {raw_name}")
        content = raw_path.read_bytes()

        parsed = _parse_replay_payload(definition, structure, content)
        for observation in parsed:
            key = (observation.series_id, observation.period)
            if key in seen:
                raise PriceAcquisitionError(f"duplicate replay observation: {key}")
            seen.add(key)
            observations.append(observation)

        receipts.append(
            SourceReceipt(
                provider=definition.provider,
                dataset=definition.dataset,
                series_id=definition.series_id,
                final_url=definition.source_url,
                query_spec={
                    "provider_code": definition.provider_code,
                    "query_key": definition.query_key,
                    "frequency": definition.frequency,
                    "seasonal_adjustment": definition.seasonal_adjustment,
                    "source_category_code": definition.source_category_code,
                },
                retrieved_at=structure.retrieved_at,
                http_status=200,
                content_type="application/json",
                byte_count=len(content),
                sha256=_sha256(content),
                etag="",
                last_modified="",
                dsd_schema_sha256=structure.schema_sha256,
            )
        )

    if not observations:
        raise PriceAcquisitionError("raw replay fixtures contain no enabled observations")

    return (
        sorted(observations, key=lambda row: (row.series_id, row.period)),
        receipts,
        structures,
    )

def acquire_live_prices(
    definitions: Iterable[PriceSeriesDefinition],
) -> tuple[list[PriceObservation], list[SourceReceipt], list[ProviderStructure]]:
    enabled = sorted(
        (row.series_id for row in definitions if row.enabled),
    )
    raise PriceAcquisitionError(
        "live acquisition is disabled in v0.8.1 until official provider DSD snapshots "
        "and provider-specific Eurostat/OECD parsers are implemented; "
        f"enabled_series={enabled}"
    )

def write_acquisition_outputs(
    output_dir: Path,
    definitions: Iterable[PriceSeriesDefinition],
    observations: Iterable[PriceObservation],
    normalized: Iterable[object],
    receipts: Iterable[SourceReceipt],
    structures: Iterable[ProviderStructure],
    summary: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    observation_rows = list(observations)
    normalized_rows = list(normalized)
    receipt_rows = list(receipts)
    structure_rows = list(structures)
    definition_rows = [row for row in definitions if row.enabled]

    _write_observations(output_dir / "raw_price_observations.csv", observation_rows)
    _write_normalized(output_dir / "normalized_price_observations.csv", normalized_rows)
    _write_jsonl(output_dir / "price_source_receipts.jsonl", [asdict(row) for row in receipt_rows])
    _write_health(output_dir / "price_source_health.csv", receipt_rows, observation_rows)
    _write_json(
        output_dir / "provider_structure_manifest.json",
        {
            "parser_version": PARSER_VERSION,
            "structures": [
                {
                    "provider": row.provider,
                    "dataset": row.dataset,
                    "dimension_order": list(row.dimension_order),
                    "allowed_values": {key: list(value) for key, value in sorted(row.allowed_values.items())},
                    "schema_sha256": row.schema_sha256,
                    "source_url": row.source_url,
                    "retrieved_at": row.retrieved_at,
                }
                for row in structure_rows
            ],
        },
    )
    _write_json(
        output_dir / "resolved_price_series_registry.json",
        {
            "registry_version": str(summary["registry_version"]),
            "research_release_allowed": False,
            "monetary_release_allowed": False,
            "series": [
                {
                    "series_id": row.series_id,
                    "provider": row.provider,
                    "dataset": row.dataset,
                    "economy_code": row.economy_code,
                    "source_category_code": row.source_category_code,
                    "target_categories": list(row.target_categories),
                    "evidence_class": row.evidence_class.value,
                    "source_priority": row.source_priority,
                    "query_key": row.query_key,
                }
                for row in sorted(definition_rows, key=lambda item: item.series_id)
            ],
        },
    )
    _write_json(output_dir / "price_acquisition_summary.json", summary)
    _write_manifest(output_dir)


def _load_provider_structures(path: Path) -> list[ProviderStructure]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("structures")
    if not isinstance(rows, list) or not rows:
        raise PriceAcquisitionError("provider structure manifest must contain structures")
    structures: list[ProviderStructure] = []
    for row in rows:
        allowed = row.get("allowed_values", {})
        structures.append(
            ProviderStructure(
                provider=str(row["provider"]),
                dataset=str(row["dataset"]),
                dimension_order=tuple(str(value) for value in row["dimension_order"]),
                allowed_values={str(key): tuple(str(item) for item in value) for key, value in allowed.items()},
                schema_sha256=str(row["schema_sha256"]),
                source_url=str(row["source_url"]),
                retrieved_at=str(row["retrieved_at"]),
            )
        )
    return structures


def _parse_replay_payload(
    definition: PriceSeriesDefinition,
    structure: ProviderStructure,
    content: bytes,
) -> list[PriceObservation]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PriceAcquisitionError(
            f"invalid raw JSON fixture for {definition.series_id}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise PriceAcquisitionError(
            f"raw fixture must be a JSON object: {definition.series_id}"
        )
    if payload.get("provider") != definition.provider:
        raise PriceAcquisitionError(
            f"raw fixture provider mismatch for {definition.series_id}"
        )
    if payload.get("dataset") != definition.dataset:
        raise PriceAcquisitionError(
            f"raw fixture dataset mismatch for {definition.series_id}"
        )

    raw_dimensions = payload.get("dimension_order")
    if not isinstance(raw_dimensions, list):
        raise PriceAcquisitionError(
            f"raw fixture dimension_order missing for {definition.series_id}"
        )
    dimension_order = tuple(str(value) for value in raw_dimensions)
    if dimension_order != structure.dimension_order:
        raise PriceAcquisitionError(
            f"raw fixture dimension_order mismatch for {definition.series_id}"
        )

    raw_key = payload.get("key")
    if not isinstance(raw_key, dict):
        raise PriceAcquisitionError(
            f"raw fixture key missing for {definition.series_id}"
        )

    dimensions = set(structure.dimension_order)
    area_dimension = "geo" if "geo" in dimensions else "ref_area"
    expected_key = {
        "freq": definition.frequency,
        area_dimension: definition.economy_code,
        "coicop": definition.source_category_code,
    }
    if "unit" in dimensions:
        expected_key["unit"] = definition.unit
    if "seasonal_adjustment" in dimensions:
        expected_key["seasonal_adjustment"] = definition.seasonal_adjustment

    for dimension, expected in expected_key.items():
        actual = str(raw_key.get(dimension, ""))
        if actual != expected:
            raise PriceAcquisitionError(
                f"raw fixture key mismatch for {definition.series_id}: "
                f"{dimension}={actual!r}, expected {expected!r}"
            )

    rows = payload.get("observations")
    if not isinstance(rows, list) or not rows:
        raise PriceAcquisitionError(
            f"raw fixture observations missing for {definition.series_id}"
        )

    raw_hash = _sha256(content)
    observations: list[PriceObservation] = []
    seen_periods: set[str] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PriceAcquisitionError(
                f"raw fixture observation {index} is not an object: "
                f"{definition.series_id}"
            )
        period = str(row.get("period", "")).strip()
        if period in seen_periods:
            raise PriceAcquisitionError(
                f"duplicate raw fixture period for {definition.series_id}: {period}"
            )
        seen_periods.add(period)

        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceAcquisitionError(
                f"invalid raw fixture value for {definition.series_id}/{period}"
            ) from exc

        observation = PriceObservation(
            series_id=definition.series_id,
            period=period,
            value=value,
            published_at=str(row.get("published_at", "")).strip(),
            retrieved_at=str(
                row.get("retrieved_at", structure.retrieved_at)
            ).strip(),
            revision_id=str(
                row.get("revision_id", f"sha256:{raw_hash}")
            ).strip(),
            status=str(row.get("status", "REPLAY")).strip(),
        )
        observation.validate()
        observations.append(observation)

    return observations

def _validate_definition_against_structure(
    definition: PriceSeriesDefinition,
    structure: ProviderStructure,
) -> None:
    dimensions = set(structure.dimension_order)
    if not {"freq", "coicop"}.issubset(dimensions) or not ({"geo", "ref_area"} & dimensions):
        raise PriceAcquisitionError(
            f"{definition.provider}/{definition.dataset} DSD lacks required dimensions"
        )
    area_dimension = "geo" if "geo" in dimensions else "ref_area"
    checks = {
        "freq": definition.frequency,
        area_dimension: definition.economy_code,
        "coicop": definition.source_category_code,
    }
    if "seasonal_adjustment" in structure.allowed_values:
        checks["seasonal_adjustment"] = definition.seasonal_adjustment
    for dimension, value in checks.items():
        allowed = structure.allowed_values.get(dimension)
        if allowed is not None and value not in allowed:
            raise PriceAcquisitionError(
                f"{definition.series_id} uses {dimension}={value}, not present in DSD snapshot"
            )


def _write_observations(path: Path, rows: list[PriceObservation]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["series_id", "period", "value", "published_at", "retrieved_at", "revision_id", "status"],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "series_id": row.series_id,
                    "period": row.period,
                    "value": format(row.value, ".17g"),
                    "published_at": row.published_at,
                    "retrieved_at": row.retrieved_at,
                    "revision_id": row.revision_id,
                    "status": row.status,
                }
            )


def _write_normalized(path: Path, rows: list[object]) -> None:
    fieldnames = [
        "series_id",
        "economy_code",
        "category_code",
        "period",
        "price_relative",
        "evidence_class",
        "source_priority",
        "provider",
        "dataset",
        "source_category_code",
        "reference_period",
        "published_at",
        "retrieved_at",
        "revision_id",
        "quality_flags",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "series_id": row.series_id,
                    "economy_code": row.economy_code,
                    "category_code": row.category_code,
                    "period": row.period,
                    "price_relative": format(row.price_relative, ".17g"),
                    "evidence_class": row.evidence_class.value,
                    "source_priority": row.source_priority,
                    "provider": row.provider,
                    "dataset": row.dataset,
                    "source_category_code": row.source_category_code,
                    "reference_period": row.reference_period,
                    "published_at": row.published_at,
                    "retrieved_at": row.retrieved_at,
                    "revision_id": row.revision_id,
                    "quality_flags": "|".join(row.quality_flags),
                }
            )


def _write_health(path: Path, receipts: list[SourceReceipt], observations: list[PriceObservation]) -> None:
    observation_counts: dict[str, int] = {}
    for row in observations:
        observation_counts[row.series_id] = observation_counts.get(row.series_id, 0) + 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "provider",
                "dataset",
                "series_id",
                "http_status",
                "observation_count",
                "sha256",
                "dsd_schema_sha256",
                "status",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in receipts:
            writer.writerow(
                {
                    "provider": row.provider,
                    "dataset": row.dataset,
                    "series_id": row.series_id,
                    "http_status": row.http_status,
                    "observation_count": observation_counts.get(row.series_id, 0),
                    "sha256": row.sha256,
                    "dsd_schema_sha256": row.dsd_schema_sha256,
                    "status": "OK" if row.http_status == 200 and observation_counts.get(row.series_id, 0) else "FAILED",
                }
            )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_manifest(output_dir: Path) -> None:
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.name == "MANIFEST.sha256" or not path.is_file():
            continue
        rows.append(f"{_sha256(path.read_bytes())}  {path.name}")
    (output_dir / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
