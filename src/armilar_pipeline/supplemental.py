from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .util import normalize_text, read_csv, sha256_file
from .worldbank import Variable


TARGET_CATEGORIES = {f"CP{i:02d}" for i in range(1, 13)}
REQUIRED_PROXY_CATEGORIES = {"CP04", "CP06", "CP09", "CP10", "CP12"}


@dataclass(frozen=True)
class NominalObservation:
    economy_code: str
    economy_name: str
    armilar_category: str
    value_lcu: Decimal
    currency: str
    source_id: str
    source_file: str
    source_url: str
    retrieved_at: str
    source_hash: str
    concept: str
    classification: str
    quality_flags: tuple[str, ...]
    source_priority: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "economy_code": self.economy_code,
            "economy_name": self.economy_name,
            "armilar_category": self.armilar_category,
            "value_lcu": self.value_lcu,
            "currency": self.currency,
            "source_id": self.source_id,
            "source_file": self.source_file,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "source_hash": self.source_hash,
            "concept": self.concept,
            "classification": self.classification,
            "quality_flags": "|".join(self.quality_flags),
            "source_priority": self.source_priority,
        }


@dataclass(frozen=True)
class SupplementalParseResult:
    observations: list[NominalObservation]
    exclusions: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class EconomyMapper:
    def __init__(self, country_variables: Iterable[Variable], aliases_path: Path, code_crosswalk_path: Path):
        self.by_code = {item.variable_id.upper(): item for item in country_variables}
        self.by_name: dict[str, list[Variable]] = {}
        for item in country_variables:
            self.by_name.setdefault(normalize_text(item.value), []).append(item)
        self.aliases = {
            normalize_text(row["official_page_name"]): row["world_bank_name_or_code"].strip()
            for row in read_csv(aliases_path)
        }
        self.code_crosswalk = {
            row["external_code"].strip().upper(): row["world_bank_icp_code"].strip().upper()
            for row in read_csv(code_crosswalk_path)
        }

    def map_code(self, code: str) -> tuple[str, str]:
        raw = (code or "").strip().upper()
        target = self.code_crosswalk.get(raw, raw)
        variable = self.by_code.get(target)
        return (variable.variable_id, variable.value) if variable else ("", "")

    def map_name(self, name: str) -> tuple[str, str]:
        norm = normalize_text(name)
        alias = self.aliases.get(norm)
        if alias:
            code, label = self.map_code(alias)
            if code:
                return code, label
            candidates = self.by_name.get(normalize_text(alias), [])
            if len(candidates) == 1:
                return candidates[0].variable_id, candidates[0].value
        candidates = self.by_name.get(norm, [])
        if len(candidates) == 1:
            return candidates[0].variable_id, candidates[0].value
        return "", ""


def parse_oecd_csv(
    path: Path,
    mapper: EconomyMapper,
    *,
    source_id: str,
    source_url: str,
    retrieved_at: str,
    priority: int,
    classification: str,
) -> SupplementalParseResult:
    observations: list[NominalObservation] = []
    exclusions: list[dict[str, Any]] = []
    source_hash = sha256_file(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[tuple[str, str], list[NominalObservation]] = {}
    for row_number, row in enumerate(rows, start=2):
        reason = ""
        if row.get("TIME_PERIOD", "") != "2021":
            reason = "REFERENCE_YEAR_NOT_2021"
        elif row.get("FREQ", "") not in {"", "A"}:
            reason = "FREQUENCY_NOT_ANNUAL"
        elif row.get("SECTOR", "") not in {"", "S14"}:
            reason = "SECTOR_NOT_HOUSEHOLDS_S14"
        elif row.get("TRANSACTION", "") not in {"", "P31DC"}:
            reason = "TRANSACTION_NOT_DOMESTIC_HFCE_P31DC"
        elif row.get("UNIT_MEASURE", "") not in {"XDC", "NCU", "NAC"}:
            reason = "UNIT_NOT_NATIONAL_CURRENCY"
        elif row.get("PRICE_BASE", "") not in {"", "V"}:
            reason = "NOT_CURRENT_PRICES"
        expenditure = (row.get("EXPENDITURE") or "").strip().upper()
        category = _coicop_to_armilar(expenditure, classification)
        if not category or category not in TARGET_CATEGORIES:
            if not reason:
                reason = "NOT_REQUIRED_PROXY_CATEGORY"
        economy_code, economy_name = mapper.map_code(row.get("REF_AREA", ""))
        if not economy_code and not reason:
            reason = "ECONOMY_NOT_MAPPED_TO_ICP_SOURCE90"
        try:
            value = Decimal((row.get("OBS_VALUE") or "").strip())
            multiplier = Decimal(10) ** int((row.get("UNIT_MULT") or "0").strip() or "0")
            value_lcu = value * multiplier
            if value_lcu < 0:
                reason = reason or "NEGATIVE_NOMINAL_EXPENDITURE"
        except (InvalidOperation, ValueError):
            value_lcu = Decimal("0")
            reason = reason or "INVALID_OBSERVATION_VALUE"
        if reason:
            exclusions.append({
                "source_id": source_id, "row_number": row_number,
                "economy_external": row.get("REF_AREA", ""), "economy_code": economy_code,
                "category_external": expenditure, "armilar_category": category,
                "reason": reason,
            })
            continue
        obs = NominalObservation(
            economy_code=economy_code,
            economy_name=economy_name,
            armilar_category=category,
            value_lcu=value_lcu,
            currency=(row.get("CURRENCY") or "").strip(),
            source_id=source_id,
            source_file=path.as_posix(),
            source_url=source_url,
            retrieved_at=retrieved_at,
            source_hash=source_hash,
            concept="HOUSEHOLDS_S14_DOMESTIC_HFCE_P31DC_CURRENT_PRICES",
            classification=classification,
            quality_flags=("OFFICIAL_OECD", "STRICT_HOUSEHOLD_NUMERATOR", "DOMESTIC_CONCEPT", f"SOURCE_COMPONENT_{expenditure}"),
            source_priority=priority,
        )
        grouped.setdefault((economy_code, category), []).append(obs)
    observations.extend(_combine_classification_components(grouped, classification, exclusions))
    return SupplementalParseResult(
        observations=observations,
        exclusions=exclusions,
        diagnostics={"source_id": source_id, "input_rows": len(rows), "accepted_rows": len(observations), "excluded_rows": len(exclusions)},
    )


def parse_eurostat_jsonstat(
    path: Path,
    mapper: EconomyMapper,
    *,
    source_id: str,
    source_url: str,
    retrieved_at: str,
    priority: int,
) -> SupplementalParseResult:
    obj = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal, parse_int=Decimal)
    ids = [str(item) for item in obj.get("id", [])]
    sizes = [int(item) for item in obj.get("size", [])]
    if len(ids) != len(sizes) or not ids:
        raise ValueError("Invalid Eurostat JSON-stat id/size vectors")
    dimensions = obj.get("dimension", {})
    orders: dict[str, list[str]] = {}
    for dim_id, size in zip(ids, sizes):
        category = dimensions.get(dim_id, {}).get("category", {})
        index = category.get("index", {})
        if isinstance(index, dict):
            order = [str(code) for code, _ in sorted(index.items(), key=lambda item: int(item[1]))]
        elif isinstance(index, list):
            order = [str(code) for code in index]
        else:
            order = [str(code) for code in category.get("label", {})]
        if len(order) != size:
            raise ValueError(f"Eurostat dimension {dim_id} size mismatch")
        orders[dim_id] = order
    source_hash = sha256_file(path)
    grouped_components: dict[tuple[str, str], list[tuple[str, Decimal, str, str]]] = {}
    exclusions: list[dict[str, Any]] = []
    values = obj.get("value", {})
    items = values.items() if isinstance(values, dict) else enumerate(values)
    accepted_cells = 0
    for raw_index, raw_value in items:
        if raw_value is None:
            continue
        flat_index = int(raw_index)
        coords = _cube_coordinates(flat_index, sizes)
        row = {dim_id: orders[dim_id][coord] for dim_id, coord in zip(ids, coords)}
        if row.get("time") != "2021" or row.get("freq", "A") != "A":
            continue
        if row.get("unit") != "CP_MNAC":
            continue
        geo = row.get("geo", "")
        economy_code, economy_name = mapper.map_code(geo)
        if not economy_code:
            continue
        code = (row.get("coicop18") or row.get("coicop") or "").upper()
        category = _coicop_to_armilar(code, "COICOP2018")
        if not category or category not in TARGET_CATEGORIES:
            continue
        try:
            value_lcu = Decimal(str(raw_value)) * Decimal("1000000")
        except InvalidOperation:
            exclusions.append({"source_id": source_id, "economy_external": geo, "category_external": code, "reason": "INVALID_OBSERVATION_VALUE"})
            continue
        if value_lcu < 0:
            exclusions.append({"source_id": source_id, "economy_external": geo, "category_external": code, "reason": "NEGATIVE_NOMINAL_EXPENDITURE"})
            continue
        grouped_components.setdefault((economy_code, category), []).append((code, value_lcu, economy_name, geo))
        accepted_cells += 1
    observations: list[NominalObservation] = []
    for (economy_code, category), components in sorted(grouped_components.items()):
        required = {"CP12", "CP13"} if category == "CP12" else {category}
        top_level = [(code, value, name, geo) for code, value, name, geo in components if code in required]
        codes = {item[0] for item in top_level}
        if codes != required:
            exclusions.append({
                "source_id": source_id, "economy_code": economy_code,
                "armilar_category": category, "reason": "INCOMPLETE_COICOP2018_BRIDGE",
                "present_components": "|".join(sorted(codes)), "required_components": "|".join(sorted(required)),
            })
            continue
        value = sum((item[1] for item in top_level), Decimal("0"))
        economy_name = top_level[0][2]
        observations.append(NominalObservation(
            economy_code=economy_code,
            economy_name=economy_name,
            armilar_category=category,
            value_lcu=value,
            currency="NATIONAL_CURRENCY",
            source_id=source_id,
            source_file=path.as_posix(),
            source_url=source_url,
            retrieved_at=retrieved_at,
            source_hash=source_hash,
            concept="HOUSEHOLDS_S14_DOMESTIC_HFCE_CURRENT_PRICES",
            classification="COICOP2018_BRIDGED_TO_ARMILAR12",
            quality_flags=("OFFICIAL_EUROSTAT", "STRICT_HOUSEHOLD_NUMERATOR", "DOMESTIC_CONCEPT", "COICOP2018_BRIDGE"),
            source_priority=priority,
        ))
    return SupplementalParseResult(
        observations=observations,
        exclusions=exclusions,
        diagnostics={"source_id": source_id, "non_null_cells_scanned": accepted_cells, "accepted_rows": len(observations), "excluded_rows": len(exclusions)},
    )


def parse_undata_zip(
    path: Path,
    mapper: EconomyMapper,
    *,
    source_id: str,
    source_url: str,
    retrieved_at: str,
    priority: int,
) -> SupplementalParseResult:
    source_hash = sha256_file(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(candidates) != 1:
                raise ValueError(f"Expected one CSV in UNData ZIP, found {candidates}")
            member_name = candidates[0]
            data = archive.read(member_name)
    else:
        member_name = path.name
        data = path.read_bytes()
        if b"Country or Area" not in data[:4096]:
            raise ValueError("UNData response is neither a ZIP nor a recognizable CSV export")
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    accepted: dict[tuple[str, str], list[tuple[int, NominalObservation]]] = {}
    exclusions: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        country_name = _first(row, "Country or Area", "Country", "Country or area")
        subgroup = normalize_text(_first(row, "Sub Group", "SubGroup"))
        item_code = _first(row, "SNA93 Item Code", "Item Code", "SNA Item Code").strip().upper()
        year = _first(row, "Year", "Fiscal Year").strip()
        if subgroup != "individual consumption expenditure of households":
            continue
        if year != "2021":
            continue
        category = f"CP{item_code.zfill(2)}" if item_code.isdigit() and 1 <= int(item_code) <= 12 else ""
        if category not in TARGET_CATEGORIES:
            continue
        economy_code, economy_name = mapper.map_name(country_name)
        if not economy_code:
            exclusions.append({"source_id": source_id, "row_number": row_number, "economy_external": country_name, "armilar_category": category, "reason": "ECONOMY_NOT_MAPPED_TO_ICP_SOURCE90"})
            continue
        raw_value = _first(row, "Value").replace(",", "").strip()
        try:
            value_lcu = Decimal(raw_value)
        except InvalidOperation:
            exclusions.append({"source_id": source_id, "row_number": row_number, "economy_external": country_name, "armilar_category": category, "reason": "INVALID_OBSERVATION_VALUE"})
            continue
        if value_lcu < 0:
            exclusions.append({"source_id": source_id, "row_number": row_number, "economy_external": country_name, "armilar_category": category, "reason": "NEGATIVE_NOMINAL_EXPENDITURE"})
            continue
        sna_system = _first(row, "SNA System")
        fiscal_type = _first(row, "Fiscal Year Type")
        rank = (2 if "2008" in sna_system else 1 if "1993" in sna_system else 0) + (1 if normalize_text(fiscal_type) == "western calendar year" else 0)
        flags = ["OFFICIAL_UNSD_COUNTRY_DATA", "STRICT_HOUSEHOLD_NUMERATOR", "DOMESTIC_MARKET_TABLE"]
        if normalize_text(fiscal_type) != "western calendar year":
            flags.append("NON_WESTERN_FISCAL_YEAR")
        obs = NominalObservation(
            economy_code=economy_code,
            economy_name=economy_name,
            armilar_category=category,
            value_lcu=value_lcu,
            currency=_first(row, "Currency"),
            source_id=source_id,
            source_file=f"{path.as_posix()}::{member_name}",
            source_url=source_url,
            retrieved_at=retrieved_at,
            source_hash=source_hash,
            concept="HOUSEHOLD_INDIVIDUAL_CONSUMPTION_DOMESTIC_MARKET_CURRENT_PRICES",
            classification="COICOP1999_12_DIVISIONS",
            quality_flags=tuple(flags),
            source_priority=priority,
        )
        accepted.setdefault((economy_code, category), []).append((rank, obs))
    observations: list[NominalObservation] = []
    for key, candidates_ranked in sorted(accepted.items()):
        candidates_ranked.sort(key=lambda item: item[0], reverse=True)
        best_rank = candidates_ranked[0][0]
        best = [item[1] for item in candidates_ranked if item[0] == best_rank]
        distinct = {item.value_lcu for item in best}
        if len(distinct) != 1:
            exclusions.append({
                "source_id": source_id, "economy_code": key[0], "armilar_category": key[1],
                "reason": "CONFLICTING_DUPLICATE_UNDATA_VALUES", "values": "|".join(sorted(format(v, "f") for v in distinct)),
            })
            continue
        observations.append(best[0])
    return SupplementalParseResult(
        observations=observations,
        exclusions=exclusions,
        diagnostics={"source_id": source_id, "input_rows": len(rows), "accepted_rows": len(observations), "excluded_rows": len(exclusions)},
    )


def select_nominal_sources(
    observations: Iterable[NominalObservation],
    *,
    priority_order: tuple[str, ...],
    relative_tolerance: Decimal,
) -> tuple[dict[tuple[str, str], NominalObservation], list[dict[str, Any]]]:
    """Select one internally complete official nominal source per economy.

    Category-level mixing across providers is prohibited. A provider is eligible only
    when it supplies all five proxy categories required by ratified Option B.
    """
    priority = {source: index for index, source in enumerate(priority_order)}
    by_economy_source: dict[tuple[str, str], dict[str, NominalObservation]] = {}
    for obs in observations:
        key = (obs.economy_code, obs.source_id)
        category_map = by_economy_source.setdefault(key, {})
        existing = category_map.get(obs.armilar_category)
        if existing is not None and existing.value_lcu != obs.value_lcu:
            raise ValueError(
                f"Conflicting duplicate supplemental observation for {key} {obs.armilar_category}"
            )
        category_map[obs.armilar_category] = obs

    sources_by_economy: dict[str, list[str]] = {}
    for economy_code, source_id in by_economy_source:
        sources_by_economy.setdefault(economy_code, []).append(source_id)

    selected: dict[tuple[str, str], NominalObservation] = {}
    audit: list[dict[str, Any]] = []
    for economy_code, source_ids in sorted(sources_by_economy.items()):
        ordered_sources = sorted(set(source_ids), key=lambda source: (priority.get(source, 999), source))
        complete_sources = [
            source for source in ordered_sources
            if REQUIRED_PROXY_CATEGORIES <= set(by_economy_source[(economy_code, source)])
        ]
        chosen_source = complete_sources[0] if complete_sources else ""
        if chosen_source:
            for category, obs in by_economy_source[(economy_code, chosen_source)].items():
                selected[(economy_code, category)] = obs

        for source_id in ordered_sources:
            category_map = by_economy_source[(economy_code, source_id)]
            missing_proxy = sorted(REQUIRED_PROXY_CATEGORIES - set(category_map))
            complete = not missing_proxy
            for category in sorted(REQUIRED_PROXY_CATEGORIES):
                candidate = category_map.get(category)
                chosen = by_economy_source.get((economy_code, chosen_source), {}).get(category) if chosen_source else None
                if candidate is None:
                    relative_difference: Decimal | str = ""
                    status = "CANDIDATE_MISSING_CATEGORY"
                    candidate_value: Decimal | str = ""
                elif chosen is None:
                    relative_difference = ""
                    status = "NO_COMPLETE_SOURCE_FOR_ECONOMY"
                    candidate_value = candidate.value_lcu
                else:
                    denominator = max(abs(chosen.value_lcu), abs(candidate.value_lcu), Decimal("1"))
                    relative_difference = abs(chosen.value_lcu - candidate.value_lcu) / denominator
                    candidate_value = candidate.value_lcu
                    if source_id == chosen_source:
                        status = "SELECTED_SINGLE_SOURCE_ECONOMY"
                    else:
                        status = (
                            "ALTERNATIVE_CONSISTENT"
                            if relative_difference <= relative_tolerance
                            else "ALTERNATIVE_DIVERGENT"
                        )
                audit.append({
                    "economy_code": economy_code,
                    "armilar_category": category,
                    "chosen_source_id": chosen_source,
                    "candidate_source_id": source_id,
                    "chosen_value_lcu": chosen.value_lcu if chosen is not None else "",
                    "candidate_value_lcu": candidate_value,
                    "relative_difference": relative_difference,
                    "candidate_complete_proxy_set": complete,
                    "candidate_missing_proxy_categories": "|".join(missing_proxy),
                    "selection_basis": "ONE_COMPLETE_SOURCE_PER_ECONOMY_NO_PROVIDER_MIXING",
                    "status": status,
                })
    return selected, audit


def _coicop_to_armilar(code: str, classification: str) -> str:
    code = code.strip().upper()
    if classification == "COICOP2018":
        if code in {f"CP{i:02d}" for i in range(1, 12)}:
            return code
        if code in {"CP12", "CP13"}:
            return "CP12"
        return ""
    return code if code in {f"CP{i:02d}" for i in range(1, 13)} else ""


def _combine_classification_components(
    grouped: dict[tuple[str, str], list[NominalObservation]],
    classification: str,
    exclusions: list[dict[str, Any]],
) -> list[NominalObservation]:
    result: list[NominalObservation] = []
    for key, candidates in sorted(grouped.items()):
        if classification == "COICOP2018" and key[1] == "CP12":
            by_component: dict[str, NominalObservation] = {}
            for item in candidates:
                component = next((flag.removeprefix("SOURCE_COMPONENT_") for flag in item.quality_flags if flag.startswith("SOURCE_COMPONENT_")), "")
                if component in by_component and by_component[component].value_lcu != item.value_lcu:
                    exclusions.append({
                        "source_id": item.source_id, "economy_code": key[0], "armilar_category": key[1],
                        "reason": "CONFLICTING_DUPLICATE_SOURCE_COMPONENT", "component": component,
                    })
                    by_component = {}
                    break
                by_component[component] = item
            if set(by_component) != {"CP12", "CP13"}:
                exclusions.append({
                    "source_id": candidates[0].source_id, "economy_code": key[0], "armilar_category": key[1],
                    "reason": "INCOMPLETE_COICOP2018_CP12_CP13_BRIDGE",
                    "present_components": "|".join(sorted(by_component)),
                })
                continue
            first = by_component["CP12"]
            result.append(NominalObservation(
                economy_code=first.economy_code, economy_name=first.economy_name, armilar_category="CP12",
                value_lcu=by_component["CP12"].value_lcu + by_component["CP13"].value_lcu,
                currency=first.currency, source_id=first.source_id, source_file=first.source_file,
                source_url=first.source_url, retrieved_at=first.retrieved_at, source_hash=first.source_hash,
                concept=first.concept, classification="COICOP2018_CP12_PLUS_CP13",
                quality_flags=tuple(flag for flag in first.quality_flags if not flag.startswith("SOURCE_COMPONENT_")) + ("COICOP2018_CP12_PLUS_CP13",),
                source_priority=first.source_priority,
            ))
            continue
        distinct = {item.value_lcu for item in candidates}
        if len(distinct) != 1:
            exclusions.append({
                "source_id": candidates[0].source_id, "economy_code": key[0], "armilar_category": key[1],
                "reason": "CONFLICTING_DUPLICATE_SOURCE_VALUES", "values": "|".join(sorted(format(v, "f") for v in distinct)),
            })
            continue
        result.append(candidates[0])
    return result


def _cube_coordinates(flat_index: int, sizes: list[int]) -> list[int]:
    coords: list[int] = []
    remainder = flat_index
    for size in reversed(sizes):
        coords.append(remainder % size)
        remainder //= size
    return list(reversed(coords))


def _first(row: dict[str, Any], *names: str) -> str:
    normalized = {normalize_text(str(key)): value for key, value in row.items()}
    for name in names:
        value = normalized.get(normalize_text(name))
        if value not in (None, ""):
            return str(value)
    return ""
