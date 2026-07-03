from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SOURCE_RELATIVE_PATH = Path("public/latest/weights_observed_universe.csv")
BASKET_RELATIVE_PATH = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
MANIFEST_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1.sha256")
CONSTITUTION_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
CONSTITUTION_MD_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1.md")
CONSTITUTION_SCHEMA_RELATIVE_PATH = Path("schemas/research_core_constitution.schema.json")
BASKET_SCHEMA_RELATIVE_PATH = Path("schemas/research_core_basket.schema.json")
DECISION_RELATIVE_PATH = Path("docs/DECISION_RESEARCH_CORE_BASKET_MATERIALIZATION.md")
REPAIR_DECISION_RELATIVE_PATH = Path("docs/DECISION_RESEARCH_CORE_CONTRACT_REPAIR.md")
DECISION_V1_RELATIVE_PATH = Path("docs/DECISION_RESEARCH_CORE_V1.md")
SCOPE_RELATIVE_PATH = Path("docs/ARMILAR_RESEARCH_CORE_V1_SCOPE.md")
SCRIPT_RELATIVE_PATH = Path("scripts/materialize_research_core_basket.py")
CONFIG_RELATIVE_PATH = Path("config/eurostat_vertical_v087.json")

SOURCE_SHA256 = "743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83"
SOURCE_ROW_COUNT = 744
SOURCE_GLOBAL_SUM = Decimal("1.000000000000000000000000")
TARGET_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
TARGET_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
TARGET_GRID = {(economy, category) for economy in TARGET_ECONOMIES for category in TARGET_CATEGORIES}
TARGET_RAW_SUM = Decimal("0.160150831582167491646292")
TARGET_NORMALIZED_SUM = Decimal("1.000000000000000000000000000")
NORMALIZATION_RULE = "FIXED_UNIVERSE_NORMALISE_ONCE"
RESEARCH_CORE_ID = "ARMILAR_RESEARCH_CORE_V1"
BASKET_VERSION = "0.3.0-draft"
WEIGHT_SOURCE_VERSION = "0.9.4"
STATUS = "RESEARCH_ONLY"
DECIMAL_PRECISION = 28
NORMALIZED_QUANTUM = Decimal("0.000000000000000000000000000")

SOURCE_REQUIRED_COLUMNS = (
    "economy_code",
    "economy_name",
    "armilar_category",
    "numerator_source_id",
    "numerator_source_file",
    "numerator_source_hash",
    "ppp_source_heading",
    "ppp_scope",
    "derivation",
    "quality_flags",
    "weight",
    "rounding_residual_applied",
)

BASKET_COLUMNS = (
    "research_core_id",
    "basket_version",
    "economy_code",
    "economy_name",
    "category_code",
    "raw_world_weight",
    "fixed_universe_weight",
    "covered_world_weight",
    "normalization_rule",
    "weight_source",
    "weight_source_version",
    "numerator_source_id",
    "numerator_source_file",
    "numerator_source_hash",
    "ppp_source_heading",
    "ppp_scope",
    "derivation",
    "quality_flags",
    "rounding_residual_applied",
    "evidence_class",
    "status",
)

EXPECTED_EVIDENCE_COUNTS = {
    "EXACT_OFFICIAL": 30,
    "OFFICIAL_DETERMINISTIC_DERIVATION": 5,
    "EXPERIMENTAL_RESEARCH": 25,
}

MANIFEST_PATHS = tuple(
    sorted(
        (
            BASKET_RELATIVE_PATH,
            CONSTITUTION_RELATIVE_PATH,
            CONSTITUTION_MD_RELATIVE_PATH,
            SOURCE_RELATIVE_PATH,
            CONSTITUTION_SCHEMA_RELATIVE_PATH,
            BASKET_SCHEMA_RELATIVE_PATH,
            SCRIPT_RELATIVE_PATH,
            DECISION_RELATIVE_PATH,
            REPAIR_DECISION_RELATIVE_PATH,
            DECISION_V1_RELATIVE_PATH,
            SCOPE_RELATIVE_PATH,
            CONFIG_RELATIVE_PATH,
        ),
        key=lambda path: path.as_posix(),
    )
)


class ContractError(ValueError):
    """Raised when a Research Core invariant is violated."""


@dataclass(frozen=True)
class BasketRow:
    research_core_id: str
    basket_version: str
    economy_code: str
    economy_name: str
    category_code: str
    raw_world_weight: str
    fixed_universe_weight: str
    covered_world_weight: str
    normalization_rule: str
    weight_source: str
    weight_source_version: str
    numerator_source_id: str
    numerator_source_file: str
    numerator_source_hash: str
    ppp_source_heading: str
    ppp_scope: str
    derivation: str
    quality_flags: str
    rounding_residual_applied: str
    evidence_class: str
    status: str


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


UTF8_BOM = b"\xef\xbb\xbf"


def canonicalize_utf8_text(payload: bytes) -> bytes:
    """Return a cross-platform canonical representation for manifest hashing."""
    if payload.startswith(UTF8_BOM):
        raise ContractError("UTF-8 BOM is not permitted in canonical manifest inputs")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("manifest text input is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def manifest_input_bytes(path: Path, relative_path: Path) -> bytes:
    payload = path.read_bytes()
    if relative_path == SOURCE_RELATIVE_PATH:
        return payload
    return canonicalize_utf8_text(payload)


def manifest_digest(path: Path, relative_path: Path) -> str:
    return sha256_bytes(manifest_input_bytes(path, relative_path))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize and verify the Armilar Research Core basket.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--check", action="store_true", help="Verify committed outputs without writing")
    return parser.parse_args(argv)


def read_source(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ContractError(f"missing source file: {path}")
    actual_hash = sha256_file(path)
    if actual_hash != SOURCE_SHA256:
        raise ContractError(f"unexpected source SHA-256: {actual_hash}")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("source CSV has no header")
        missing = [column for column in SOURCE_REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ContractError(f"source CSV missing columns: {missing}")
        rows = list(reader)

    if len(rows) != SOURCE_ROW_COUNT:
        raise ContractError(f"expected {SOURCE_ROW_COUNT} source rows, found {len(rows)}")
    global_sum = sum((Decimal(row["weight"]) for row in rows), Decimal("0"))
    if global_sum != SOURCE_GLOBAL_SUM:
        raise ContractError(f"unexpected source global sum: {global_sum}")
    return rows


def select_source_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    selected = [
        dict(row)
        for row in rows
        if row["economy_code"] in TARGET_ECONOMIES and row["armilar_category"] in TARGET_CATEGORIES
    ]
    keys = [(row["economy_code"], row["armilar_category"]) for row in selected]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ContractError(f"duplicate Research Core cells: {duplicates}")
    actual_grid = set(keys)
    missing = sorted(TARGET_GRID - actual_grid)
    extras = sorted(actual_grid - TARGET_GRID)
    if missing or extras:
        raise ContractError(f"invalid Research Core grid; missing={missing}, extras={extras}")
    if len(selected) != len(TARGET_GRID):
        raise ContractError(f"expected 60 selected rows, found {len(selected)}")

    raw_sum = sum((Decimal(row["weight"]) for row in selected), Decimal("0"))
    if raw_sum != TARGET_RAW_SUM:
        raise ContractError(f"unexpected selected raw-world sum: {raw_sum}")

    order = {economy: index for index, economy in enumerate(TARGET_ECONOMIES)}
    return sorted(selected, key=lambda row: (order[row["economy_code"]], row["armilar_category"]))


def classify_evidence(row: Mapping[str, str]) -> str:
    ppp_scope = row["ppp_scope"]
    derivation = row["derivation"]
    if ppp_scope == "ACTUAL_CONSUMPTION_PROXY_RATIFIED_OPTION_B":
        if derivation != "STRICT_S14_P31DC_NUMERATOR_DIVIDED_BY_ACTUAL_CONSUMPTION_PPP":
            raise ContractError("Option B row has an unexpected derivation")
        return "EXPERIMENTAL_RESEARCH"
    if ppp_scope == "STRICT_HFCE" and derivation == "DIRECT_SOURCE90_HFCE":
        return "EXACT_OFFICIAL"
    if ppp_scope == "STRICT_HFCE_COMPOSITE" and derivation == "ALCOHOL_PLUS_TOBACCO_EXCLUDING_NARCOTICS":
        return "OFFICIAL_DETERMINISTIC_DERIVATION"
    raise ContractError(
        "unsupported evidence mapping: "
        f"ppp_scope={ppp_scope!r}, derivation={derivation!r}, "
        f"cell={row['economy_code']}/{row['armilar_category']}"
    )


def build_basket_rows(rows: Iterable[Mapping[str, str]]) -> list[BasketRow]:
    built: list[BasketRow] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for row in rows:
            raw_weight = Decimal(row["weight"])
            fixed_weight = (raw_weight / TARGET_RAW_SUM).quantize(
                NORMALIZED_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
            for required in (
                "economy_name",
                "numerator_source_id",
                "numerator_source_file",
                "numerator_source_hash",
                "ppp_source_heading",
                "ppp_scope",
                "derivation",
                "quality_flags",
                "rounding_residual_applied",
            ):
                if row[required] == "":
                    raise ContractError(
                        f"missing provenance {required} for {row['economy_code']}/{row['armilar_category']}"
                    )
            built.append(
                BasketRow(
                    research_core_id=RESEARCH_CORE_ID,
                    basket_version=BASKET_VERSION,
                    economy_code=row["economy_code"],
                    economy_name=row["economy_name"],
                    category_code=row["armilar_category"],
                    raw_world_weight=format(raw_weight, "f"),
                    fixed_universe_weight=format(fixed_weight, "f"),
                    covered_world_weight=format(TARGET_RAW_SUM, "f"),
                    normalization_rule=NORMALIZATION_RULE,
                    weight_source=SOURCE_RELATIVE_PATH.as_posix(),
                    weight_source_version=WEIGHT_SOURCE_VERSION,
                    numerator_source_id=row["numerator_source_id"],
                    numerator_source_file=row["numerator_source_file"],
                    numerator_source_hash=row["numerator_source_hash"],
                    ppp_source_heading=row["ppp_source_heading"],
                    ppp_scope=row["ppp_scope"],
                    derivation=row["derivation"],
                    quality_flags=row["quality_flags"],
                    rounding_residual_applied=row["rounding_residual_applied"],
                    evidence_class=classify_evidence(row),
                    status=STATUS,
                )
            )

    normalized_sum = sum((Decimal(row.fixed_universe_weight) for row in built), Decimal("0"))
    if normalized_sum != TARGET_NORMALIZED_SUM:
        raise ContractError(f"unexpected normalized sum: {normalized_sum}")
    evidence_counts = Counter(row.evidence_class for row in built)
    if dict(evidence_counts) != EXPECTED_EVIDENCE_COUNTS:
        raise ContractError(f"unexpected evidence counts: {dict(evidence_counts)}")
    return built


def render_basket_csv(rows: Iterable[BasketRow]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=BASKET_COLUMNS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))
    return output.getvalue().encode("utf-8")


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON contract {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON contract must be an object: {path}")
    return payload


def validate_static_contracts(root: Path) -> None:
    constitution = load_json(root / CONSTITUTION_RELATIVE_PATH)
    constitution_schema = load_json(root / CONSTITUTION_SCHEMA_RELATIVE_PATH)
    basket_schema = load_json(root / BASKET_SCHEMA_RELATIVE_PATH)
    config = load_json(root / CONFIG_RELATIVE_PATH)

    if config.get("normalization_rule") != NORMALIZATION_RULE:
        raise ContractError("normalization policy no longer matches the ratified pilot rule")
    if constitution.get("constitution_status") != "DRAFT":
        raise ContractError("constitution must remain DRAFT in v0.9.5-04")
    if constitution.get("constitution_version") != BASKET_VERSION:
        raise ContractError("constitution and basket draft versions must match")
    if constitution.get("schema_version") != "1.2":
        raise ContractError("unexpected constitution schema version")
    if constitution.get("economies") != list(TARGET_ECONOMIES):
        raise ContractError("constitution economy universe mismatch")
    if constitution.get("basket_categories") != list(TARGET_CATEGORIES):
        raise ContractError("constitution basket categories mismatch")
    if constitution.get("benchmark_categories") != ["CP00"]:
        raise ContractError("CP00 must remain a separate benchmark")
    release_gates = constitution.get("release_gates")
    if not isinstance(release_gates, dict) or not release_gates or any(release_gates.values()):
        raise ContractError("all release gates must remain false")
    pending = constitution.get("pending_decisions")
    if not isinstance(pending, list) or len(pending) != 7:
        raise ContractError("exactly seven decisions must remain pending")
    if any(item.get("status") != "PENDING_RATIFICATION" for item in pending if isinstance(item, dict)):
        raise ContractError("all decisions must remain pending ratification")

    materialization = constitution.get("basket_materialization")
    if not isinstance(materialization, dict):
        raise ContractError("basket_materialization must be an object")
    expected_materialization = {
        "status": "BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS",
        "expected_cell_count": 60,
        "source_input": SOURCE_RELATIVE_PATH.as_posix(),
        "source_input_sha256": SOURCE_SHA256,
        "source_pipeline_version": WEIGHT_SOURCE_VERSION,
        "source_weight_sum": format(SOURCE_GLOBAL_SUM, "f"),
        "covered_world_weight": format(TARGET_RAW_SUM, "f"),
        "fixed_universe_weight_sum": format(TARGET_NORMALIZED_SUM, "f"),
        "normalization_rule": NORMALIZATION_RULE,
        "normalization_policy": CONFIG_RELATIVE_PATH.as_posix(),
        "normalization_decimal_precision": DECIMAL_PRECISION,
        "normalization_rounding": "ROUND_HALF_EVEN",
        "materialized_basket": BASKET_RELATIVE_PATH.as_posix(),
        "eligibility": STATUS,
        "synthetic_test_weights_allowed": False,
        "silent_renormalization_allowed": False,
        "evidence_class_counts": EXPECTED_EVIDENCE_COUNTS,
    }
    for key, value in expected_materialization.items():
        if materialization.get(key) != value:
            raise ContractError(f"basket_materialization mismatch for {key}: {materialization.get(key)!r}")

    if constitution_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("constitution schema must use draft 2020-12")
    if basket_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("basket schema must use draft 2020-12")
    for schema, label in ((constitution_schema, "constitution"), (basket_schema, "basket")):
        if schema.get("additionalProperties") is not False:
            raise ContractError(f"{label} schema must reject unknown properties")


def render_manifest(root: Path, basket_bytes: bytes) -> bytes:
    lines: list[str] = []
    for relative_path in MANIFEST_PATHS:
        if relative_path == BASKET_RELATIVE_PATH:
            digest = sha256_bytes(basket_bytes)
        else:
            absolute_path = root / relative_path
            if not absolute_path.is_file():
                raise ContractError(f"manifest input missing: {relative_path.as_posix()}")
            digest = manifest_digest(absolute_path, relative_path)
        lines.append(f"{digest}  {relative_path.as_posix()}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def verify_bytes(path: Path, expected: bytes) -> None:
    if not path.is_file():
        raise ContractError(f"missing committed output: {path}")
    actual = path.read_bytes()
    if actual == expected:
        return
    if path == BASKET_RELATIVE_PATH or path.suffix in {".json", ".md", ".sha256"}:
        if canonicalize_utf8_text(actual) == canonicalize_utf8_text(expected):
            return
    raise ContractError(
        f"byte mismatch for {path}; committed_sha256={sha256_bytes(actual)}, expected_sha256={sha256_bytes(expected)}"
    )


def materialize(root: Path, *, check: bool) -> None:
    root = root.resolve()
    validate_static_contracts(root)
    source_rows = read_source(root / SOURCE_RELATIVE_PATH)
    selected_rows = select_source_rows(source_rows)
    basket_rows = build_basket_rows(selected_rows)
    basket_bytes = render_basket_csv(basket_rows)
    manifest_bytes = render_manifest(root, basket_bytes)

    if check:
        verify_bytes(root / BASKET_RELATIVE_PATH, basket_bytes)
        verify_bytes(root / MANIFEST_RELATIVE_PATH, manifest_bytes)
        return

    atomic_write(root / BASKET_RELATIVE_PATH, basket_bytes)
    atomic_write(root / MANIFEST_RELATIVE_PATH, manifest_bytes)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    materialize(args.root, check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
