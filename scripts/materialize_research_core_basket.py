from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from pathlib import Path


getcontext().prec = 28

TARGET_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
TARGET_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
TARGET_SUM = Decimal("0.160150831582167491646292")
ONE = Decimal("1.000000000000000000000000000")
QUANT = Decimal("0.000000000000000000000000000")


@dataclass(frozen=True)
class Row:
    economy_code: str
    economy_name: str
    armilar_category: str
    raw_world_weight: Decimal
    fixed_universe_weight: Decimal
    evidence_class: str
    method_id: str
    model_version: str
    source_ids: str


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--check", action="store_true")
    return p


def load_source(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 744:
        raise ValueError(f"expected 744 rows, found {len(rows)}")
    if sum(Decimal(row["weight"]) for row in rows) != ONE.quantize(Decimal("0.000000000000000000000000")):
        raise ValueError("unexpected global sum")
    if hashlib.sha256(path.read_bytes()).hexdigest() != "743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83":
        raise ValueError("unexpected source hash")
    return rows


def select_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in rows if row["economy_code"] in TARGET_ECONOMIES and row["armilar_category"] in TARGET_CATEGORIES]
    if len(selected) != 60:
        raise ValueError(f"expected 60 rows, found {len(selected)}")
    raw_total = sum(Decimal(row["weight"]) for row in selected)
    if raw_total != TARGET_SUM:
        raise ValueError(f"unexpected selected sum {raw_total}")
    return sorted(selected, key=lambda row: (row["economy_code"], row["armilar_category"]))


def build_rows(rows: list[dict[str, str]]) -> list[Row]:
    built: list[Row] = []
    for row in rows:
        raw = Decimal(row["weight"])
        fixed = (raw / TARGET_SUM).quantize(QUANT, rounding=ROUND_HALF_EVEN)
        if row["armilar_category"] in {"CP01", "CP02", "CP03", "CP04", "CP05", "CP06"}:
            evidence = "EXACT_OFFICIAL"
        elif row["armilar_category"] == "CP07":
            evidence = "OFFICIAL_DETERMINISTIC_DERIVATION"
        else:
            evidence = "EXPERIMENTAL_RESEARCH"
        built.append(
            Row(
                economy_code=row["economy_code"],
                economy_name=row["economy_name"],
                armilar_category=row["armilar_category"],
                raw_world_weight=raw,
                fixed_universe_weight=fixed,
                evidence_class=evidence,
                method_id="FIXED_UNIVERSE_NORMALISE_ONCE",
                model_version="0.2.0-draft",
                source_ids=row["numerator_source_id"],
            )
        )
    if sum(item.fixed_universe_weight for item in built) != ONE:
        raise ValueError("unexpected normalized sum")
    return built


def render_csv(rows: list[Row]) -> bytes:
    lines = ["economy_code,economy_name,armilar_category,raw_world_weight,fixed_universe_weight,evidence_class,method_id,model_version,source_ids"]
    for row in rows:
        lines.append(
            ",".join(
                [
                    row.economy_code,
                    row.economy_name,
                    row.armilar_category,
                    format(row.raw_world_weight, "f"),
                    format(row.fixed_universe_weight, "f"),
                    row.evidence_class,
                    row.method_id,
                    row.model_version,
                    row.source_ids,
                ]
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_sha(basket_bytes: bytes) -> bytes:
    return f"{hashlib.sha256(basket_bytes).hexdigest()}  basket/ARMILAR_RESEARCH_CORE_V1.csv\n".encode("utf-8")


def render_json() -> bytes:
    payload = {
        "basket": "BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS",
        "constitution_status": "DRAFT",
        "constitution_version": "0.2.0-draft",
        "eligibility": "RESEARCH_ONLY",
        "evidence_classes": {
            "EXACT_OFFICIAL": 30,
            "OFFICIAL_DETERMINISTIC_DERIVATION": 5,
            "EXPERIMENTAL_RESEARCH": 25,
        },
        "gates": {
            "monetary_release_allowed": False,
            "research_release_allowed": False,
            "shadow_production_allowed": False,
            "world_claim_allowed": False,
        },
        "pending_decisions": [
            {"id": "normalization_base", "status": "PENDING_RATIFICATION"},
            {"id": "official_formula", "status": "PENDING_RATIFICATION"},
            {"id": "vintage_and_revision_policy", "status": "PENDING_RATIFICATION"},
            {"id": "precision_and_rounding", "status": "PENDING_RATIFICATION"},
            {"id": "exact_series_semantics", "status": "PENDING_RATIFICATION"},
            {"id": "hfce_hicp_conceptual_treatment", "status": "PENDING_RATIFICATION"},
            {"id": "constitutional_amendment_process", "status": "PENDING_RATIFICATION"},
        ],
        "research_core_id": "ARMILAR_RESEARCH_CORE_V1",
        "schema_version": "1.1",
        "status": "DRAFT",
        "version": "0.2.0-draft",
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_md() -> bytes:
    return (
        "# ARMILAR_RESEARCH_CORE_V1 Constitution\n\n"
        "Status: `DRAFT`\n"
        "Version: `0.2.0-draft`\n"
        "Schema: `1.1`\n"
        "Basket: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`\n"
        "Eligibility: `RESEARCH_ONLY`\n"
    ).encode("utf-8")


def render_decision() -> bytes:
    return (
        "# Decision: Research Core basket materialization\n\n"
        "Materialize `basket/ARMILAR_RESEARCH_CORE_V1.csv` exclusively from `public/latest/weights_observed_universe.csv`.\n"
    ).encode("utf-8")


def render_schema_constitution(root: Path) -> bytes:
    return (
        '{\n'
        '  "$schema": "https://json-schema.org/draft/2020-12/schema",\n'
        '  "$id": "https://armilar.org/schemas/research_core_constitution.schema.json",\n'
        '  "title": "Armilar Research Core constitution",\n'
        '  "type": "object",\n'
        '  "additionalProperties": false,\n'
        '  "required": ["schema_version", "constitution_id", "constitution_version", "constitution_status", "research_core_id", "scope", "economies", "basket_categories", "benchmark_categories", "series", "currency_policy", "release_gates", "pending_decisions", "basket_materialization", "prohibitions", "source_documents"],\n'
        '  "properties": {\n'
        '    "schema_version": {"const": "1.1"},\n'
        '    "constitution_id": {"const": "ARMILAR_RESEARCH_CORE_V1"},\n'
        '    "constitution_version": {"const": "0.2.0-draft"},\n'
        '    "constitution_status": {"const": "DRAFT"},\n'
        '    "research_core_id": {"const": "ARMILAR_RESEARCH_CORE_V1"},\n'
        '    "scope": {"type": "object"},\n'
        '    "economies": {"const": ["DEU", "ESP", "FRA", "ITA", "PRT"]},\n'
        '    "basket_categories": {"const": ["CP01", "CP02", "CP03", "CP04", "CP05", "CP06", "CP07", "CP08", "CP09", "CP10", "CP11", "CP12"]},\n'
        '    "benchmark_categories": {"const": ["CP00"]},\n'
        '    "series": {"type": "object"},\n'
        '    "currency_policy": {"type": "object"},\n'
        '    "release_gates": {"type": "object"},\n'
        '    "pending_decisions": {"type": "array"},\n'
        '    "basket_materialization": {"type": "object"},\n'
        '    "prohibitions": {"type": "array"},\n'
        '    "source_documents": {"type": "array"}\n'
        '  }\n'
        '}\n'
    ).encode("utf-8")


def render_schema_basket(root: Path) -> bytes:
    return (
        '{\n'
        '  "$schema": "https://json-schema.org/draft/2020-12/schema",\n'
        '  "$id": "https://armilar.org/schemas/research_core_basket.schema.json",\n'
        '  "title": "Armilar Research Core basket row",\n'
        '  "type": "object",\n'
        '  "additionalProperties": false,\n'
        '  "required": ["economy_code", "economy_name", "armilar_category", "raw_world_weight", "fixed_universe_weight", "evidence_class", "method_id", "model_version", "source_ids"],\n'
        '  "properties": {"economy_code": {"enum": ["DEU", "ESP", "FRA", "ITA", "PRT"]}}\n'
        '}\n'
    ).encode("utf-8")


def write_or_check(root: Path, payloads: dict[Path, bytes], check: bool) -> None:
    if check:
        for path, expected in payloads.items():
            if path.read_bytes() != expected:
                raise ValueError(f"byte mismatch: {path}")
        return
    for path, data in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    rows = build_rows(select_rows(load_source(root / "public" / "latest" / "weights_observed_universe.csv")))
    basket_bytes = render_csv(rows)
    payloads = {
        root / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv": basket_bytes,
        root / "constitution" / "ARMILAR_RESEARCH_CORE_V1.sha256": render_sha(basket_bytes),
        root / "constitution" / "ARMILAR_RESEARCH_CORE_V1.json": render_json(),
        root / "constitution" / "ARMILAR_RESEARCH_CORE_V1.md": render_md(),
        root / "docs" / "DECISION_RESEARCH_CORE_V1.md": render_decision(),
        root / "schemas" / "research_core_constitution.schema.json": render_schema_constitution(root),
        root / "schemas" / "research_core_basket.schema.json": render_schema_basket(root),
    }
    write_or_check(root, payloads, args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
