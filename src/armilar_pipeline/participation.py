from __future__ import annotations

import csv
import html
import re
from pathlib import Path
from typing import Iterable

from .util import normalize_text, read_csv
from .worldbank import Variable


REGION_PATTERN = re.compile(
    r"(?:Africa:\s*52 economies|Asia and the Pacific:\s*21 economies|"
    r"Commonwealth of Independent States:\s*9 economies|"
    r"Latin America and the Caribbean:\s*32 economies|Western Asia:\s*16 economies|"
    r"Europe and Organisation for Economic Co-operation and Development \(OECD\):\s*51 economies)",
    re.IGNORECASE,
)


def html_to_text(raw_html: str) -> str:
    raw_html = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw_html, flags=re.I | re.S)
    raw_html = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw_html, flags=re.I | re.S)
    raw_html = re.sub(r"<[^>]+>", "\n", raw_html)
    return re.sub(r"[ \t]+", " ", html.unescape(raw_html)).replace("\xa0", " ")


def extract_participating_names(raw_html: str) -> list[str]:
    text = html_to_text(raw_html)
    marker = "Participating economies in the ICP 2021 cycle, by region"
    start = text.lower().find(marker.lower())
    if start < 0:
        raise ValueError("Participation marker not found in official governance page")
    section = text[start:]
    related = section.lower().find("related")
    if related > 0:
        section = section[:related]

    names: list[str] = []
    matches = list(REGION_PATTERN.finditer(section))
    if len(matches) != 6:
        raise ValueError(f"Expected six participation regions, found {len(matches)}")
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        block = section[match.end():end]
        block = re.sub(r"Regional implementing agenc(?:y|ies):[^\n]+", " ", block, flags=re.I)
        block = re.sub(r"Implementing agencies:[^\n]+", " ", block, flags=re.I)
        block = re.sub(r"\^\{a\}|\ba\b(?=\s*[;,.])", "", block)
        block = re.sub(r"\s+", " ", block).strip(" .;\n")
        # The LAC source contains a full stop between mainland and Caribbean lists.
        block = block.replace("Uruguay. Anguilla", "Uruguay; Anguilla")
        block = block.replace("Somalia, South Africa", "Somalia; South Africa")
        block = re.sub(r"\band\s+([^;]+)$", r"\1", block, flags=re.I)
        for token in block.split(";"):
            name = token.strip(" .\n")
            if name:
                names.append(name)
    unique = list(dict.fromkeys(normalize_page_name(name) for name in names))
    if len(unique) != 176:
        raise ValueError(f"Expected 176 unique participating economies, found {len(unique)}")
    return unique


def normalize_page_name(name: str) -> str:
    name = re.sub(r"\^\{a\}", "", name)
    name = re.sub(r"\s+a\s*$", "", name)
    name = re.sub(r"^a\s+(?=[A-Z])", "", name)
    cleaned = " ".join(name.replace(" ", " ").split()).strip(" .;")
    canonical = {
        "Arab Republic of Egypt": "Egypt, Arab Rep.",
        "Egypt, Arab Rep": "Egypt, Arab Rep.",
    }
    return canonical.get(cleaned, cleaned)


def map_participants_to_codes(
    names: Iterable[str], country_variables: list[Variable], aliases_path: Path
) -> tuple[dict[str, str], list[dict[str, str]]]:
    aliases = {
        normalize_text(row["official_page_name"]): row["world_bank_name_or_code"].strip()
        for row in read_csv(aliases_path)
    }
    by_code = {item.variable_id.upper(): item for item in country_variables}
    by_name: dict[str, list[Variable]] = {}
    for item in country_variables:
        by_name.setdefault(normalize_text(item.value), []).append(item)

    mapped: dict[str, str] = {}
    audit: list[dict[str, str]] = []
    for name in names:
        normalized = normalize_text(name)
        alias = aliases.get(normalized)
        candidates: list[Variable] = []
        method = "NORMALIZED_EXACT"
        if alias:
            if alias.upper() in by_code:
                candidates = [by_code[alias.upper()]]
                method = "EXPLICIT_CODE_ALIAS"
            else:
                candidates = by_name.get(normalize_text(alias), [])
                method = "EXPLICIT_NAME_ALIAS"
        else:
            candidates = by_name.get(normalized, [])
        if len(candidates) != 1:
            audit.append(
                {
                    "official_page_name": name,
                    "normalized_name": normalized,
                    "economy_code": "",
                    "world_bank_name": "",
                    "mapping_method": method,
                    "status": "UNRESOLVED" if not candidates else "AMBIGUOUS",
                }
            )
            continue
        item = candidates[0]
        mapped[item.variable_id] = name
        audit.append(
            {
                "official_page_name": name,
                "normalized_name": normalized,
                "economy_code": item.variable_id,
                "world_bank_name": item.value,
                "mapping_method": method,
                "status": "MAPPED",
            }
        )
    return mapped, audit
