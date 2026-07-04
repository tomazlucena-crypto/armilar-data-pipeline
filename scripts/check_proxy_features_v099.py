#!/usr/bin/env python3
"""Fail-closed repository checker for ARMILAR v0.9.9 mapped point-in-time proxy features."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

EXPECTED_VERSION = "0.9.9"
EXPECTED_V098_COMMIT = "71da526"
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_SCRIPT = "armilar_proxies.feature_panel_v099:main"
UTF8_BOM = b"\xef\xbb\xbf"

POLICY = Path("config/proxy_feature_mapping_v099.json")
ASSET_MANIFEST = Path("config/proxy_feature_panel_v099_files.sha256")
PYPROJECT = Path("pyproject.toml")
WORKFLOW = Path(".github/workflows/fetch-data.yml")
CONSTITUTION = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
RECORD = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
SCHEMAS = (
    Path("schemas/proxy_feature_mapping_v099.schema.json"),
    Path("schemas/proxy_feature_value_v099.schema.json"),
    Path("schemas/proxy_feature_cell_coverage_v099.schema.json"),
    Path("schemas/proxy_feature_mapping_audit_v099.schema.json"),
    Path("schemas/proxy_feature_unmapped_v099.schema.json"),
    Path("schemas/proxy_feature_summary_v099.schema.json"),
    Path("schemas/proxy_feature_stream_history_v099.schema.json"),
    Path("schemas/proxy_feature_cell_period_coverage_v099.schema.json"),
    Path("schemas/proxy_feature_concordance_v099.schema.json"),
    Path("schemas/proxy_feature_cell_research_diagnostics_v099.schema.json"),
    Path("schemas/proxy_feature_delta_v099.schema.json"),
    Path("schemas/proxy_feature_coverage_delta_v099.schema.json"),
    Path("schemas/proxy_feature_comparison_summary_v099.schema.json"),
    Path("schemas/proxy_feature_availability_profile_v099.schema.json"),
    Path("schemas/proxy_feature_provenance_concentration_v099.schema.json"),
    Path("schemas/proxy_feature_cell_risk_flags_v099.schema.json"),
    Path("schemas/proxy_feature_stream_revision_stability_v099.schema.json"),
    Path("schemas/proxy_feature_cell_revision_stability_v099.schema.json"),
)
SOURCE_FILES = (
    Path("src/armilar_proxies/feature_core_v099.py"),
    Path("src/armilar_proxies/feature_builder_v099.py"),
    Path("src/armilar_proxies/feature_compare_v099.py"),
    Path("src/armilar_proxies/feature_diagnostics_v099.py"),
    Path("src/armilar_proxies/feature_stability_v099.py"),
    Path("src/armilar_proxies/feature_panel_v099.py"),
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


def expected_assets() -> set[str]:
    return {
        "RELEASE_NOTES_V0.9.9.md",
        POLICY.as_posix(),
        "docs/DECISION_PROXY_FEATURE_MAPPING_V099.md",
        "docs/PROXY_FEATURE_PANEL_V099_CONTRACT.md",
        *(path.as_posix() for path in SCHEMAS),
        "scripts/check_proxy_features_v099.py",
        *(path.as_posix() for path in SOURCE_FILES),
        "tests/test_proxy_feature_panel_v099.py",
    }


def verify_asset_manifest(root: Path) -> dict[str, str]:
    manifest = root / ASSET_MANIFEST
    if not manifest.is_file():
        raise CheckError("v0.9.9 asset manifest is missing")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(canonical_text_bytes(manifest.read_bytes()).decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise CheckError(f"invalid asset manifest line {line_number}")
        expected, relative = parts
        if relative in entries:
            raise CheckError(f"duplicate asset path: {relative}")
        if digest(root / relative) != expected:
            raise CheckError(f"asset hash mismatch: {relative}")
        entries[relative] = expected
    expected = expected_assets()
    if set(entries) != expected:
        raise CheckError(f"asset manifest set mismatch; missing={sorted(expected-set(entries))}, extra={sorted(set(entries)-expected)}")
    return entries


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
    if any((constitution.get("release_gates") or {}).values()) or any((record.get("release_gates") or {}).values()):
        raise CheckError("constitutional release gates must remain false")
    return hashes


def load_modules(root: Path) -> tuple[Any, Any]:
    source_root = str(root / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        core = importlib.import_module("armilar_proxies.feature_core_v099")
        cli = importlib.import_module("armilar_proxies.feature_panel_v099")
    except ImportError as exc:
        raise CheckError("cannot load v0.9.9 feature package") from exc
    return core, cli


def check_policy(root: Path, core: Any) -> dict[str, Any]:
    policy = core.load_policy(root / POLICY)
    if policy["contract_version"] != EXPECTED_VERSION:
        raise CheckError("v0.9.9 policy version mismatch")
    if any(policy["output_gates"].values()):
        raise CheckError("a v0.9.9 output gate is open")
    if len(policy["category_mappings"]) != 15:
        raise CheckError("unexpected v0.9.9 mapping rule count")
    if policy["transformation_policy"]["target_frequency"] != "MONTHLY":
        raise CheckError("feature target frequency changed")
    diagnostic = policy.get("diagnostic_policy") or {}
    if diagnostic.get("no_automatic_eligibility_promotion") is not True:
        raise CheckError("diagnostic policy permits automatic eligibility promotion")
    if diagnostic.get("no_quality_weighting") is not True or diagnostic.get("no_feature_selection") is not True:
        raise CheckError("diagnostic policy exceeds descriptive scope")
    if diagnostic.get("no_aggregate_risk_score") is not True or diagnostic.get("no_eligibility_from_risk_flags") is not True:
        raise CheckError("diagnostic risk flags exceed descriptive scope")
    if diagnostic.get("availability_lag_diagnostic_days") != 90:
        raise CheckError("unexpected availability lag diagnostic window")
    if diagnostic.get("provenance_concentration_diagnostic_percent") != 75:
        raise CheckError("unexpected provenance concentration diagnostic threshold")
    ooh = [item for item in policy["category_mappings"] if item["source_id"] == "EUROSTAT_OOHPI_QUARTERLY"]
    if len(ooh) != 1 or ooh[0]["feature_role"] != "SENSITIVITY_ONLY":
        raise CheckError("OOH mapping must remain sensitivity-only")
    return {
        "policy_sha256": core.policy_hash(root / POLICY),
        "mapping_rule_count": 15,
        "schema_count": len(SCHEMAS),
        "long_history_min_complete_periods": diagnostic["long_history_min_complete_periods"],
        "concordance_min_overlap_periods": diagnostic["concordance_min_overlap_periods"],
        "availability_lag_diagnostic_days": diagnostic["availability_lag_diagnostic_days"],
        "provenance_concentration_diagnostic_percent": diagnostic["provenance_concentration_diagnostic_percent"],
    }


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


def check_isolation(root: Path) -> None:
    forbidden = (
        "import armilar_prices", "from armilar_prices", "public/latest",
        "direct_index_use_allowed=true", "arm_l_use_allowed=true",
        "model_training_allowed=true", "monetary_use_allowed=true",
    )
    for relative in SOURCE_FILES:
        text = canonical_text_bytes((root / relative).read_bytes()).decode("utf-8")
        for token in forbidden:
            if token in text:
                raise CheckError(f"v0.9.9 module violates isolation contract: {relative.name}: {token}")


def check_pyproject(root: Path) -> dict[str, Any]:
    project = tomllib.loads(canonical_text_bytes((root / PYPROJECT).read_bytes()).decode("utf-8"))["project"]
    if project.get("version") != EXPECTED_VERSION:
        raise CheckError(f"pyproject version must be {EXPECTED_VERSION}")
    scripts = project.get("scripts") or {}
    if scripts.get("armilar-proxy-features-v099") != EXPECTED_SCRIPT:
        raise CheckError("v0.9.9 CLI entry point mismatch")
    if scripts.get("armilar-proxy-information-v098") != "armilar_proxies.information_set_v098:main":
        raise CheckError("v0.9.8 CLI entry point changed")
    optional = project.get("optional-dependencies") or {}
    if optional.get("proxies") != ["openpyxl>=3.1,<4"]:
        raise CheckError("proxy dependency set changed")
    return {"version": project["version"], "script": scripts["armilar-proxy-features-v099"]}


def check_workflow(root: Path) -> None:
    text = canonical_text_bytes((root / WORKFLOW).read_bytes()).decode("utf-8")
    if 'python -m pip install -e ".[test,temporal,proxies]"' not in text:
        raise CheckError("CI does not install v0.9.9 test dependencies")
    if "python scripts/check_proxy_features_v099.py --root ." not in text:
        raise CheckError("CI does not run the v0.9.9 checker")
    if "python scripts/check_proxy_information_set_v098.py --root ." in text:
        raise CheckError("CI must not run the historical v0.9.8 checker on a v0.9.9 tree")
    if "python scripts/check_research_core_constitution.py --root ." not in text:
        raise CheckError("CI does not run the canonical constitution checker")
    if re.search(r"armilar-(?:proxies-v097|proxy-information-v098|proxy-features-v099)\s+acquire", text):
        raise CheckError("live proxy acquisition is forbidden in CI")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)


def check_v098(root: Path) -> dict[str, Any]:
    if _git(root, "rev-parse", "--git-dir").returncode == 0:
        exists = _git(root, "cat-file", "-e", f"{EXPECTED_V098_COMMIT}^{{commit}}")
        ancestor = _git(root, "merge-base", "--is-ancestor", EXPECTED_V098_COMMIT, "HEAD")
        if exists.returncode != 0 or ancestor.returncode != 0:
            raise CheckError("historical v0.9.8 commit is missing or is not an ancestor")
        temp = Path(tempfile.mkdtemp(prefix="armilar-v098-check-"))
        worktree = temp / "worktree"
        try:
            add = _git(root, "worktree", "add", "--detach", str(worktree), EXPECTED_V098_COMMIT)
            if add.returncode != 0:
                raise CheckError(f"cannot create historical v0.9.8 worktree: {add.stderr}")
            process = subprocess.run(
                [sys.executable, str(worktree / "scripts/check_proxy_information_set_v098.py"), "--root", str(worktree)],
                cwd=worktree, text=True, capture_output=True,
            )
            if process.returncode != 0:
                raise CheckError(f"historical v0.9.8 checker failed:\n{process.stdout}\n{process.stderr}")
            result = json.loads(process.stdout)
            return {"mode": "DETACHED_WORKTREE", "status": result.get("status"), "commit": EXPECTED_V098_COMMIT}
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))
            shutil.rmtree(temp, ignore_errors=True)
    manifest = root / "config/proxy_information_set_v098_files.sha256"
    if not manifest.is_file():
        raise CheckError("v0.9.8 asset manifest is missing in non-git validation")
    for line in canonical_text_bytes(manifest.read_bytes()).decode("utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        if digest(root / relative) != expected:
            raise CheckError(f"v0.9.8 asset hash mismatch in non-git validation: {relative}")
    return {"mode": "ASSET_MANIFEST", "status": "PROXY_POINT_IN_TIME_ARCHIVE_V098_VALID", "commit": None}


def check(root: Path) -> dict[str, Any]:
    assets = verify_asset_manifest(root)
    protected = check_protected_core(root)
    core, _ = load_modules(root)
    policy = check_policy(root, core)
    schemas = check_schemas(root)
    check_isolation(root)
    pyproject = check_pyproject(root)
    check_workflow(root)
    v098 = check_v098(root)
    return {
        "status": "POINT_IN_TIME_PROXY_FEATURE_PANEL_V099_VALID",
        "version": EXPECTED_VERSION,
        "asset_count": len(assets),
        "protected_core": protected,
        "policy": policy,
        "schemas": schemas,
        "pyproject": pyproject,
        "v098_status": v098["status"],
        "v098_validation_mode": v098["mode"],
        "direct_index_use_allowed": False,
        "arm_l_use_allowed": False,
        "model_training_allowed": False,
        "shadow_production_allowed": False,
        "monetary_use_allowed": False,
        "price_coverage_claim_allowed": False,
        "model_ready_claim_allowed": False,
        "backtest_eligibility_claim_allowed": False,
        "concordance_approval_claim_allowed": False,
        "comparison_decision_use_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except (CheckError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
