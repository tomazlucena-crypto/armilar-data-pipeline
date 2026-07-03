#!/usr/bin/env python3
"""Fail-closed repository checker for the ARMILAR v0.9.6 official engine."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import sys
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

BASELINE_COMMIT = "c8616710a71bba74e747b44adf828b78411d0b40"
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_VERSION = "0.9.6"
EXPECTED_PROXY_CELL_COUNT = 25
EXPECTED_PROXY_WEIGHT_TOTAL = Decimal("0.589731681350816432896035605")
EXPECTED_SCRIPT = "armilar_prices.official_engine_v096:main"
EXPECTED_TEMPORAL_DEPENDENCY = "duckdb>=1.1,<2"
EXPECTED_STATUS = "RATIFIED_FOR_ENGINE_DEVELOPMENT"
CATEGORIES = tuple(f"CP{index:02d}" for index in range(1, 13))
ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
UTF8_BOM = b"\xef\xbb\xbf"

CONSTITUTION = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
RECORD = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
BUILD_WORKFLOW = Path(".github/workflows/fetch-data.yml")
POLICY = Path("config/official_engine_v096.json")
ASSET_MANIFEST = Path("config/official_engine_v096_files.sha256")
SOURCE = Path("src/armilar_prices/official_engine_v096.py")
TEST = Path("tests/test_official_engine_v096.py")
SCHEMAS = (
    Path("schemas/official_engine_policy_v096.schema.json"),
    Path("schemas/official_engine_observation_v096.schema.json"),
    Path("schemas/official_engine_run_summary_v096.schema.json"),
    Path("schemas/official_engine_reconciliation_summary_v096.schema.json"),
    Path("schemas/official_engine_ooh_summary_v096.schema.json"),
    Path("schemas/official_engine_parquet_summary_v096.schema.json"),
    Path("schemas/temporal_ledger_v096.schema.json"),
)
REQUIRED_ASSETS = {
    POLICY,
    Path("config/ooh_scenarios_v096.json"),
    SOURCE,
    TEST,
    *SCHEMAS,
    Path("docs/OFFICIAL_ENGINE_V096_CONTRACT.md"),
    Path("docs/DECISION_OFFICIAL_ENGINE_AND_TEMPORAL_LEDGER_V096.md"),
    Path("RELEASE_NOTES_V0.9.6.md"),
    Path("scripts/check_official_engine_v096.py"),
}
PROTECTED_PREFIXES = (
    "public/latest/",
    "constitution/",
    "basket/",
)


class CheckError(RuntimeError):
    pass


def canonical_text_bytes(payload: bytes) -> bytes:
    if payload.startswith(UTF8_BOM):
        raise CheckError("UTF-8 BOM is forbidden")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CheckError("asset is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_text_bytes(path.read_bytes())).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(canonical_text_bytes(path.read_bytes()).decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckError(f"invalid JSON: {path.as_posix()}") from exc
    if not isinstance(payload, dict):
        raise CheckError(f"JSON root must be an object: {path.as_posix()}")
    return payload


def safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved = root.resolve()
    if candidate != resolved and resolved not in candidate.parents:
        raise CheckError(f"manifest path escapes repository: {relative}")
    return candidate


def check_asset_manifest(root: Path) -> dict[str, str]:
    path = root / ASSET_MANIFEST
    if not path.is_file():
        raise CheckError(f"missing v0.9.6 asset manifest: {ASSET_MANIFEST.as_posix()}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise CheckError(f"invalid asset manifest line {line_number}")
        expected_hash, relative = parts
        if relative in entries:
            raise CheckError(f"duplicate asset manifest path: {relative}")
        candidate = safe_path(root, relative)
        if not candidate.is_file():
            raise CheckError(f"manifested asset is missing: {relative}")
        actual = digest(candidate)
        if actual != expected_hash:
            raise CheckError(f"v0.9.6 asset hash mismatch: {relative}")
        entries[relative] = actual
    expected = {path.as_posix() for path in REQUIRED_ASSETS}
    if set(entries) != expected:
        raise CheckError(
            "v0.9.6 asset manifest set mismatch; "
            f"missing={sorted(expected - set(entries))}, extra={sorted(set(entries) - expected)}"
        )
    if any(path.startswith(PROTECTED_PREFIXES) for path in entries):
        raise CheckError("v0.9.6 asset manifest may not include protected paths")
    return entries


def check_ratification(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    constitution_path = root / CONSTITUTION
    record_path = root / RECORD
    basket_path = root / BASKET
    for path in (constitution_path, record_path, basket_path):
        if not path.is_file():
            raise CheckError(f"missing ratified baseline file: {path.relative_to(root).as_posix()}")
    if digest(constitution_path) != EXPECTED_CONSTITUTION_HASH:
        raise CheckError("ratified constitution hash changed")
    if digest(record_path) != EXPECTED_RECORD_HASH:
        raise CheckError("ratification record hash changed")
    if digest(basket_path) != EXPECTED_BASKET_HASH:
        raise CheckError("canonical Research Core basket hash changed")
    constitution = load_object(constitution_path)
    record = load_object(record_path)
    if constitution.get("constitution_status") != EXPECTED_STATUS:
        raise CheckError("constitution is not ratified for engine development")
    if constitution.get("constitution_version") != "1.0.0-research":
        raise CheckError("unexpected constitution version")
    if constitution.get("pending_decisions") != []:
        raise CheckError("ratified constitution has pending decisions")
    decisions = constitution.get("ratified_decisions")
    if not isinstance(decisions, list) or len(decisions) != 7:
        raise CheckError("ratified constitution must contain seven decisions")
    gates = constitution.get("release_gates")
    if not isinstance(gates, dict) or any(gates.values()):
        raise CheckError("all constitutional gates must remain false")
    if record.get("approved_constitution_sha256") != EXPECTED_CONSTITUTION_HASH:
        raise CheckError("ratification record points to a different constitution")
    if record.get("approved_basket_sha256") != EXPECTED_BASKET_HASH:
        raise CheckError("ratification record points to a different basket")
    if any((record.get("release_gates") or {}).values()):
        raise CheckError("all ratification-record gates must remain false")
    return constitution, record


def check_basket(root: Path) -> dict[str, Any]:
    with (root / BASKET).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 60:
        raise CheckError("canonical basket must contain exactly 60 cells")
    cells = {(row.get("economy_code"), row.get("category_code")) for row in rows}
    expected_cells = {(economy, category) for economy in ECONOMIES for category in CATEGORIES}
    if cells != expected_cells:
        raise CheckError("canonical basket economy-category grid changed")
    try:
        total = sum((Decimal(row["fixed_universe_weight"]) for row in rows), Decimal("0"))
    except Exception as exc:
        raise CheckError("invalid fixed_universe_weight in canonical basket") from exc
    if total != Decimal("1.000000000000000000000000000"):
        raise CheckError(f"canonical basket weights do not sum exactly to one: {total}")
    experimental = [row for row in rows if row.get("evidence_class") == "EXPERIMENTAL_RESEARCH"]
    experimental_total = sum(
        (Decimal(row["fixed_universe_weight"]) for row in experimental), Decimal("0")
    )
    if len(experimental) != EXPECTED_PROXY_CELL_COUNT:
        raise CheckError("canonical basket experimental proxy cell count changed")
    if experimental_total != EXPECTED_PROXY_WEIGHT_TOTAL:
        raise CheckError("canonical basket experimental proxy weight changed")
    return {
        "cell_count": len(rows),
        "weight_sum": format(total, "f"),
        "experimental_proxy_cell_count": len(experimental),
        "experimental_proxy_weight_total": format(experimental_total, "f"),
    }


def check_policy_and_source(root: Path) -> dict[str, Any]:
    source_path = root / SOURCE
    try:
        ast.parse(source_path.read_text(encoding="utf-8"), filename=SOURCE.as_posix())
    except (OSError, SyntaxError) as exc:
        raise CheckError("official engine source does not parse") from exc
    sys.path.insert(0, str((root / "src").resolve()))
    try:
        from armilar_prices.official_engine_v096 import EnginePolicy  # type: ignore

        policy = EnginePolicy.load(root / POLICY)
    except Exception as exc:
        raise CheckError(f"official engine policy or import failed: {exc}") from exc
    finally:
        try:
            sys.path.remove(str((root / "src").resolve()))
        except ValueError:
            pass
    if policy.constitution_sha256 != EXPECTED_CONSTITUTION_HASH:
        raise CheckError("engine policy constitution hash mismatch")
    if policy.ratification_record_sha256 != EXPECTED_RECORD_HASH:
        raise CheckError("engine policy ratification record hash mismatch")
    if policy.policy_version != EXPECTED_VERSION:
        raise CheckError("engine policy version mismatch")
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "start_period": policy.start_period,
        "end_period": policy.end_period,
    }


def check_schemas(root: Path) -> None:
    for relative in SCHEMAS:
        payload = load_object(root / relative)
        if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise CheckError(f"schema draft mismatch: {relative.as_posix()}")
        if payload.get("additionalProperties") is not False:
            raise CheckError(f"schema must be closed: {relative.as_posix()}")
        if payload.get("type") != "object":
            raise CheckError(f"schema root must be object: {relative.as_posix()}")


def check_pyproject(root: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CheckError("invalid pyproject.toml") from exc
    project = payload.get("project") or {}
    if project.get("version") != EXPECTED_VERSION:
        raise CheckError(f"pyproject version must be {EXPECTED_VERSION}")
    scripts = project.get("scripts") or {}
    if scripts.get("armilar-official-engine-v096") != EXPECTED_SCRIPT:
        raise CheckError("official engine CLI entry point is missing or incorrect")
    optional = project.get("optional-dependencies") or {}
    temporal = optional.get("temporal")
    if temporal != [EXPECTED_TEMPORAL_DEPENDENCY]:
        raise CheckError("temporal optional dependency contract mismatch")
    return {"version": project["version"], "entry_point": scripts["armilar-official-engine-v096"]}



def check_ci_temporal_dependency(root: Path) -> dict[str, Any]:
    path = root / BUILD_WORKFLOW
    if not path.is_file():
        raise CheckError("build workflow is missing")
    text = path.read_text(encoding="utf-8")
    expected = 'python -m pip install -e ".[test,temporal]"'
    if text.count(expected) != 1:
        raise CheckError("build workflow must install the test and temporal extras exactly once")
    if 'python -m pip install -e ".[test]"' in text:
        raise CheckError("build workflow still contains the pre-v0.9.6 test-only install")
    checker_command = "python scripts/check_official_engine_v096.py --root ."
    if text.count(checker_command) != 1:
        raise CheckError("build workflow must run the v0.9.6 contract checker exactly once")
    return {
        "workflow": BUILD_WORKFLOW.as_posix(),
        "temporal_extra_installed": True,
        "official_engine_checker_enabled": True,
    }

def check_no_generated_release(root: Path) -> None:
    forbidden = [
        root / "public/latest/official_engine_v096",
        root / "public/latest/arm_o",
        root / "public/latest/arm_r",
        root / "public/latest/arm_h",
    ]
    if any(path.exists() for path in forbidden):
        raise CheckError("v0.9.6 must not publish generated runs to public/latest")


def check(root: Path) -> dict[str, Any]:
    root = root.resolve()
    ratification, record = check_ratification(root)
    basket = check_basket(root)
    assets = check_asset_manifest(root)
    policy = check_policy_and_source(root)
    check_schemas(root)
    package = check_pyproject(root)
    ci = check_ci_temporal_dependency(root)
    check_no_generated_release(root)
    return {
        "status": "OFFICIAL_ENGINE_V096_CONTRACT_VALID",
        "baseline_commit": BASELINE_COMMIT,
        "constitution_status": ratification["constitution_status"],
        "ratification_record_id": record["ratification_record_id"],
        "asset_count": len(assets),
        "basket": basket,
        "policy": policy,
        "package": package,
        "ci": ci,
        "all_release_gates_closed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = check(args.root)
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
