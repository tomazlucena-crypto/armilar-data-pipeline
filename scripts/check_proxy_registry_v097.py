#!/usr/bin/env python3
"""Fail-closed repository checker for ARMILAR v0.9.7 proxy registry and acquisition."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

EXPECTED_VERSION = "0.9.7"
EXPECTED_BASELINE_COMMIT = "be8b5018ab09cde9a9bcaeda07b849a37f61aa3e"
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_REGISTRY_HASH = "fbf32c5af1d5016a2de73449cbdda0efb76b7468172633663245f3a0ca677414"
EXPECTED_SOURCE_IDS = {
    "WORLD_BANK_PINK_SHEET_MONTHLY",
    "FAO_FOOD_PRICE_INDEX_MONTHLY",
    "EC_WEEKLY_OIL_BULLETIN_HISTORY",
    "EUROSTAT_OOHPI_QUARTERLY",
}
EXPECTED_DOMAINS = {"ENERGY", "FUELS", "FOOD", "TRANSPORT", "HOUSING_OOH_SENSITIVITY"}
EXPECTED_PARSER_IDS = {
    "world_bank_pink_sheet_xlsx_v1",
    "fao_ffpi_csv_v1",
    "ec_oil_bulletin_xlsx_v1",
    "eurostat_jsonstat_v1",
}
EXPECTED_PROXY_DEPENDENCY = "openpyxl>=3.1,<4"
EXPECTED_SCRIPT = "armilar_proxies.registry_v097:main"
UTF8_BOM = b"\xef\xbb\xbf"

REGISTRY = Path("config/proxy_source_registry_v097.json")
ASSET_MANIFEST = Path("config/proxy_registry_v097_files.sha256")
SOURCE = Path("src/armilar_proxies/registry_v097.py")
PYPROJECT = Path("pyproject.toml")
WORKFLOW = Path(".github/workflows/fetch-data.yml")
CONSTITUTION = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
RECORD = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
SCHEMAS = (
    Path("schemas/proxy_source_registry_v097.schema.json"),
    Path("schemas/proxy_observation_v097.schema.json"),
    Path("schemas/proxy_snapshot_receipt_v097.schema.json"),
    Path("schemas/proxy_normalization_summary_v097.schema.json"),
    Path("schemas/proxy_snapshot_ledger_entry_v097.schema.json"),
)


class CheckError(RuntimeError):
    pass


def canonical_text_bytes(payload: bytes) -> bytes:
    if payload.startswith(UTF8_BOM):
        raise CheckError("UTF-8 BOM is forbidden")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CheckError("canonical asset is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def digest(path: Path) -> str:
    if not path.is_file():
        raise CheckError(f"required file missing: {path.as_posix()}")
    return hashlib.sha256(canonical_text_bytes(path.read_bytes())).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(canonical_text_bytes(path.read_bytes()).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"invalid JSON: {path.as_posix()}") from exc


def verify_asset_manifest(root: Path) -> dict[str, str]:
    manifest = root / ASSET_MANIFEST
    if not manifest.is_file():
        raise CheckError("v0.9.7 asset manifest is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(canonical_text_bytes(manifest.read_bytes()).decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise CheckError(f"invalid asset manifest line {line_number}")
        expected, relative = parts
        if relative in entries:
            raise CheckError(f"duplicate asset path: {relative}")
        actual = digest(root / relative)
        if actual != expected:
            raise CheckError(f"asset hash mismatch: {relative}")
        entries[relative] = expected
    actual_assets = {
        "RELEASE_NOTES_V0.9.7.md",
        "config/proxy_source_registry_v097.json",
        "docs/DECISION_PROXY_REGISTRY_V097.md",
        "docs/PROXY_REGISTRY_AND_ACQUISITION_V097_CONTRACT.md",
        "docs/PROXY_SOURCE_AUDIT_V097.md",
        "schemas/proxy_source_registry_v097.schema.json",
        "schemas/proxy_observation_v097.schema.json",
        "schemas/proxy_snapshot_receipt_v097.schema.json",
        "schemas/proxy_normalization_summary_v097.schema.json",
        "schemas/proxy_snapshot_ledger_entry_v097.schema.json",
        "scripts/check_proxy_registry_v097.py",
        "src/armilar_proxies/__init__.py",
        "src/armilar_proxies/core_v097.py",
        "src/armilar_proxies/parsers_v097.py",
        "src/armilar_proxies/acquisition_v097.py",
        "src/armilar_proxies/registry_v097.py",
        "tests/test_proxy_registry_v097.py",
    }
    if set(entries) != actual_assets:
        raise CheckError(
            f"asset manifest set mismatch; missing={sorted(actual_assets - set(entries))}, "
            f"extra={sorted(set(entries) - actual_assets)}"
        )
    return entries


def load_registry_module(root: Path) -> Any:
    source_root = str(root / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        return importlib.import_module("armilar_proxies.registry_v097")
    except ImportError as exc:
        raise CheckError("cannot load v0.9.7 registry package") from exc


def check_protected_core(root: Path) -> dict[str, str]:
    hashes = {
        "constitution_sha256": digest(root / CONSTITUTION),
        "ratification_record_sha256": digest(root / RECORD),
        "basket_sha256": digest(root / BASKET),
    }
    expected = {
        "constitution_sha256": EXPECTED_CONSTITUTION_HASH,
        "ratification_record_sha256": EXPECTED_RECORD_HASH,
        "basket_sha256": EXPECTED_BASKET_HASH,
    }
    if hashes != expected:
        raise CheckError(f"protected Research Core hash mismatch: {hashes}")
    constitution = read_json(root / CONSTITUTION)
    record = read_json(root / RECORD)
    if constitution.get("constitution_status") != "RATIFIED_FOR_ENGINE_DEVELOPMENT":
        raise CheckError("Research Core constitution is not ratified for engine development")
    if any((constitution.get("release_gates") or {}).values()):
        raise CheckError("constitutional release gates must remain false")
    if any((record.get("release_gates") or {}).values()):
        raise CheckError("ratification-record release gates must remain false")
    return hashes


def check_registry(root: Path, module: Any) -> dict[str, Any]:
    path = root / REGISTRY
    if digest(path) != EXPECTED_REGISTRY_HASH:
        raise CheckError("proxy registry hash mismatch")
    registry = module.load_registry(path)
    sources = registry["sources"]
    if {source["source_id"] for source in sources} != EXPECTED_SOURCE_IDS:
        raise CheckError("unexpected v0.9.7 source set")
    if {source["parser_id"] for source in sources} != EXPECTED_PARSER_IDS:
        raise CheckError("unexpected v0.9.7 parser set")
    domains = {domain for source in sources for domain in source["proxy_domains"]}
    if domains != EXPECTED_DOMAINS:
        raise CheckError(f"unexpected proxy-domain set: {sorted(domains)}")
    for source in sources:
        if source["historical_vintage_support"] is not False:
            raise CheckError(f"historical_vintage_support opened without evidence: {source['source_id']}")
        for gate in (
            "direct_index_use_allowed",
            "arm_l_use_allowed",
            "model_training_allowed",
            "shadow_production_allowed",
            "monetary_use_allowed",
        ):
            if source[gate] is not False:
                raise CheckError(f"prohibited source gate opened: {source['source_id']}.{gate}")
    if any(registry["global_invariants"][key] for key in (
        "direct_index_use_allowed", "arm_l_use_allowed", "model_training_allowed",
        "shadow_production_allowed", "monetary_use_allowed", "live_acquisition_in_ci_allowed"
    )):
        raise CheckError("a prohibited global proxy gate is open")
    return {
        "registry_sha256": EXPECTED_REGISTRY_HASH,
        "source_count": len(sources),
        "sources": sorted(EXPECTED_SOURCE_IDS),
        "domains": sorted(domains),
        "all_information_set_ready": False,
    }


def check_isolation(root: Path) -> None:
    forbidden = (
        "import armilar_prices",
        "from armilar_prices",
        "public/latest",
        "research_release_allowed=true",
        "monetary_release_allowed=true",
    )
    for path in sorted((root / "src/armilar_proxies").glob("*.py")):
        text = canonical_text_bytes(path.read_bytes()).decode("utf-8")
        for token in forbidden:
            if token in text:
                raise CheckError(f"proxy module violates isolation contract: {path.name}: {token}")


def check_pyproject(root: Path) -> dict[str, Any]:
    project = tomllib.loads(canonical_text_bytes((root / PYPROJECT).read_bytes()).decode("utf-8"))["project"]
    if project.get("version") != EXPECTED_VERSION:
        raise CheckError(f"pyproject version must be {EXPECTED_VERSION}")
    scripts = project.get("scripts") or {}
    if scripts.get("armilar-proxies-v097") != EXPECTED_SCRIPT:
        raise CheckError("v0.9.7 CLI entry point mismatch")
    optional = project.get("optional-dependencies") or {}
    if optional.get("proxies") != [EXPECTED_PROXY_DEPENDENCY]:
        raise CheckError("v0.9.7 proxy dependency set mismatch")
    if optional.get("temporal") != ["duckdb>=1.1,<2"]:
        raise CheckError("v0.9.6 temporal dependency changed")
    return {"version": project["version"], "script": scripts["armilar-proxies-v097"], "dependency": optional["proxies"][0]}


def check_workflow(root: Path) -> None:
    text = canonical_text_bytes((root / WORKFLOW).read_bytes()).decode("utf-8")
    if 'python -m pip install -e ".[test,temporal,proxies]"' not in text:
        raise CheckError("CI does not install the proxy parser dependency")
    if "python scripts/check_proxy_registry_v097.py --root ." not in text:
        raise CheckError("CI does not run the v0.9.7 checker")
    if re.search(r"armilar-proxies-v097\s+acquire", text):
        raise CheckError("live proxy acquisition is forbidden in CI")


def check_schemas(root: Path) -> list[str]:
    loaded: list[str] = []
    for relative in SCHEMAS:
        schema = read_json(root / relative)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise CheckError(f"unexpected schema draft: {relative.as_posix()}")
        if schema.get("additionalProperties") is not False:
            raise CheckError(f"schema is not closed: {relative.as_posix()}")
        loaded.append(relative.as_posix())
    return loaded


def check_v096(root: Path) -> dict[str, Any]:
    checker = root / "scripts/check_official_engine_v096.py"
    if not checker.is_file():
        raise CheckError("v0.9.6 official-engine checker is missing")
    worktree_root = root
    worktree_created = False
    try:
        if (root / ".git").exists():
            with tempfile.TemporaryDirectory(prefix="armilar-v096-baseline-") as temp_dir:
                worktree_root = Path(temp_dir) / "baseline"
                process = subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree_root), EXPECTED_BASELINE_COMMIT],
                    cwd=root,
                    text=True,
                    capture_output=True,
                )
                if process.returncode != 0:
                    raise CheckError(
                        "cannot create baseline v0.9.6 worktree:\n"
                        f"{process.stdout}\n{process.stderr}"
                    )
                worktree_created = True
                process = subprocess.run(
                    [sys.executable, str(checker), "--root", str(worktree_root)],
                    cwd=worktree_root,
                    text=True,
                    capture_output=True,
                )
        else:
            process = subprocess.run(
                [sys.executable, str(checker), "--root", str(root)],
                cwd=root,
                text=True,
                capture_output=True,
            )
        if process.returncode != 0:
            raise CheckError(f"v0.9.6 checker failed:\n{process.stdout}\n{process.stderr}")
    finally:
        if worktree_created:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree_root)], cwd=root, text=True, capture_output=True)
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise CheckError("v0.9.6 checker returned invalid JSON") from exc


def check(root: Path) -> dict[str, Any]:
    assets = verify_asset_manifest(root)
    protected = check_protected_core(root)
    module = load_registry_module(root)
    registry = check_registry(root, module)
    check_isolation(root)
    pyproject = check_pyproject(root)
    check_workflow(root)
    schemas = check_schemas(root)
    v096 = check_v096(root)
    return {
        "status": "PROXY_REGISTRY_AND_ACQUISITION_V097_VALID",
        "version": EXPECTED_VERSION,
        "baseline_commit": EXPECTED_BASELINE_COMMIT,
        "asset_count": len(assets),
        "protected_core": protected,
        "registry": registry,
        "pyproject": pyproject,
        "schemas": schemas,
        "v096_status": v096.get("status"),
        "direct_index_use_allowed": False,
        "arm_l_use_allowed": False,
        "model_training_allowed": False,
        "shadow_production_allowed": False,
        "monetary_use_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except (CheckError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
