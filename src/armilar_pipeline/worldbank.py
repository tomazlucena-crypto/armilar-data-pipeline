from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .acquire import AcquisitionRecord, fetch_json_pages
from .config import Step2Config
from .util import normalize_text, read_json, sha256_file


KNOWN_HEADINGS = {
    "1100000", "1101000", "1102000", "1102100", "1102200", "1102300",
    "1103000", "1104000", "1105000", "1106000", "1107000", "1108000",
    "1109000", "1110000", "1111000", "1112000", "1113000",
}


@dataclass(frozen=True)
class Variable:
    concept_id: str
    variable_id: str
    value: str


@dataclass(frozen=True)
class DimensionRoles:
    country: str
    heading: str
    measure: str
    time: str
    concept_order: tuple[str, ...]
    year_id: str


@dataclass(frozen=True)
class Observation:
    variables: dict[str, tuple[str, str]]
    value: Decimal
    source_file: Path
    source_url: str
    retrieved_at: str
    source_hash: str


def extract_concepts(payload: Any) -> list[tuple[str, str]]:
    source_objects = _source_objects(payload)
    result: list[tuple[str, str]] = []
    for source in source_objects:
        concepts = source.get("concept", [])
        if isinstance(concepts, dict):
            concepts = [concepts]
        for item in concepts:
            if isinstance(item, dict):
                concept_id = str(item.get("id", "")).strip()
                label = str(item.get("value") or item.get("name") or concept_id).strip()
                if concept_id:
                    result.append((concept_id, label))
    return result


def extract_variables(payload: Any) -> list[Variable]:
    result: list[Variable] = []
    for source in _source_objects(payload):
        concepts = source.get("concept", [])
        if isinstance(concepts, dict):
            concepts = [concepts]
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            concept_id = str(concept.get("id") or concept.get("name") or "").strip()
            variables = concept.get("variable", [])
            if isinstance(variables, dict):
                variables = [variables]
            for item in variables:
                if not isinstance(item, dict):
                    continue
                variable_id = str(item.get("id", "")).strip()
                value = str(item.get("value") or item.get("name") or "").strip()
                if variable_id:
                    result.append(Variable(concept_id, variable_id, value))
    return result


def identify_roles(
    concepts: list[tuple[str, str]], inventories: dict[str, list[Variable]], year: int
) -> DimensionRoles:
    concept_ids = [item[0] for item in concepts]
    if len(concept_ids) < 4:
        raise ValueError(f"Expected at least four concepts, found {concept_ids}")

    by_norm = {normalize_text(concept_id): concept_id for concept_id in concept_ids}
    country = by_norm.get("country")
    time = by_norm.get("time")

    heading_candidates: list[str] = []
    for concept_id, variables in inventories.items():
        ids = {item.variable_id for item in variables}
        if len(ids & KNOWN_HEADINGS) >= 5:
            heading_candidates.append(concept_id)
    if len(heading_candidates) != 1:
        raise ValueError(f"Could not identify unique heading dimension: {heading_candidates}")
    heading = heading_candidates[0]

    if not time:
        time_candidates = [
            concept_id
            for concept_id, variables in inventories.items()
            if any(item.value.strip() == str(year) for item in variables)
        ]
        if len(time_candidates) == 1:
            time = time_candidates[0]
    if not country:
        country_candidates = [
            concept_id
            for concept_id, variables in inventories.items()
            if sum(1 for item in variables if len(item.variable_id) == 3 and item.variable_id.isalpha()) > 100
        ]
        if len(country_candidates) == 1:
            country = country_candidates[0]
    if not country or not time:
        raise ValueError(f"Could not identify country/time dimensions: country={country}, time={time}")

    remaining = [item for item in concept_ids if item not in {country, time, heading}]
    if len(remaining) != 1:
        raise ValueError(f"Could not identify unique measure dimension: {remaining}")
    measure = remaining[0]

    year_matches = [item.variable_id for item in inventories[time] if item.value.strip() == str(year)]
    if len(year_matches) != 1:
        raise ValueError(f"Could not identify unique time variable for {year}: {year_matches}")
    return DimensionRoles(
        country=country,
        heading=heading,
        measure=measure,
        time=time,
        concept_order=tuple(concept_ids),
        year_id=year_matches[0],
    )


def build_heading_query(config: Step2Config, roles: DimensionRoles, heading_code: str) -> str:
    selectors = {
        roles.country: "all",
        roles.heading: heading_code,
        roles.measure: "all",
        roles.time: roles.year_id,
    }
    parts = [config.urls["advanced_data_base"].rstrip("/")]
    for concept_id in roles.concept_order:
        parts.extend([quote(concept_id.lower(), safe=""), quote(selectors[concept_id], safe="")])
    parts.append("data")
    return "/".join(parts)


def acquire_heading_data(
    config: Step2Config,
    roles: DimensionRoles,
    heading_codes: Iterable[str],
    raw_root: Path,
    cache_root: Path,
) -> list[AcquisitionRecord]:
    records: list[AcquisitionRecord] = []
    for code in heading_codes:
        url = build_heading_query(config, roles, code)
        records.extend(
            fetch_json_pages(
                config,
                source_id=f"icp2021_heading_{code}",
                base_url=url,
                destination_dir=raw_root / "data" / code,
                cache_dir=cache_root / "world_bank_source_90",
            )
        )
    return records


def parse_observation_pages(paths: Iterable[Path], run_root: Path) -> list[Observation]:
    result: list[Observation] = []
    for path in sorted(paths):
        payload = read_json(path, decimal=True)
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta = read_json(meta_path) if meta_path.exists() else {}
        source_url = str(meta.get("final_url") or meta.get("url") or "")
        retrieved_at = str(meta.get("retrieved_at") or "")
        source_hash = sha256_file(path)
        for source in _source_objects(payload):
            data = source.get("data", [])
            if isinstance(data, dict):
                data = [data]
            for row in data:
                if not isinstance(row, dict) or row.get("value") is None:
                    continue
                raw_value = row["value"]
                value = raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value))
                variables: dict[str, tuple[str, str]] = {}
                items = row.get("variable", [])
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    concept = str(item.get("concept", "")).strip()
                    variable_id = str(item.get("id", "")).strip()
                    label = str(item.get("value") or "").strip()
                    if concept:
                        variables[concept] = (variable_id, label)
                result.append(
                    Observation(
                        variables=variables,
                        value=value,
                        source_file=path.relative_to(run_root),
                        source_url=source_url,
                        retrieved_at=retrieved_at,
                        source_hash=source_hash,
                    )
                )
    return result


def _source_objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if len(payload) >= 2 and isinstance(payload[1], list):
            return [item for item in payload[1] if isinstance(item, dict)]
        return [item for item in payload if isinstance(item, dict) and "source" in item for item in _as_list(item["source"])]
    if isinstance(payload, dict):
        return [item for item in _as_list(payload.get("source", [])) if isinstance(item, dict)]
    return []


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def validate_source_metadata(payload: Any, expected_source_id: str = "90") -> dict[str, str]:
    """Validate that the acquired source descriptor is the official ICP 2021 database."""
    sources = _source_objects(payload)
    matches = [item for item in sources if str(item.get("id", "")).strip() == expected_source_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one source metadata record for {expected_source_id}, found {len(matches)}")
    source = matches[0]
    name = str(source.get("name") or "").strip()
    description = str(source.get("description") or "").strip()
    normalized = normalize_text(f"{name} {description}")
    if "icp 2021" not in normalized and "international comparison program 2021" not in normalized:
        raise ValueError(f"Source {expected_source_id} is not identified as ICP 2021: {name!r}")
    source_code = str(source.get("code") or source.get("sourcecode") or source.get("source_code") or "").strip()
    return {
        "id": expected_source_id,
        "name": name,
        "source_code": source_code,
        "lastupdated": str(source.get("lastupdated") or source.get("last_updated") or "").strip(),
        "dataavailability": str(source.get("dataavailability") or "").strip(),
        "metadataavailability": str(source.get("metadataavailability") or "").strip(),
    }


def validate_classification_workbook(path: Path, required_heading_codes: Iterable[str]) -> dict[str, Any]:
    """Fail closed unless the official XLSX contains every required HFCE heading code."""
    import zipfile

    if not zipfile.is_zipfile(path):
        raise ValueError(f"Classification workbook is not a valid XLSX/ZIP file: {path}")
    xml_text: list[str] = []
    with zipfile.ZipFile(path) as archive:
        xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if not xml_names:
            raise ValueError("Classification workbook contains no XML parts")
        for name in xml_names:
            xml_text.append(archive.read(name).decode("utf-8", errors="ignore"))
    corpus = "\n".join(xml_text)
    required = sorted(set(str(code) for code in required_heading_codes))
    missing = [code for code in required if code not in corpus]
    if missing:
        raise ValueError("Classification workbook is missing required heading codes: " + ",".join(missing))
    return {
        "valid_xlsx": True,
        "xml_parts_scanned": len(xml_text),
        "required_heading_codes": len(required),
        "missing_heading_codes": missing,
    }
