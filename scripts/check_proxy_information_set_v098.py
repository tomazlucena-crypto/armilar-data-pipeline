#!/usr/bin/env python3
"""Fail-closed repository checker for ARMILAR v0.9.8 point-in-time proxy archives."""
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

EXPECTED_VERSION = "0.9.8"
EXPECTED_V097_COMMIT = "e4fab3d"
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_SCRIPT = "armilar_proxies.information_set_v098:main"
UTF8_BOM = b"\xef\xbb\xbf"

POLICY = Path("config/proxy_information_set_v098.json")
ASSET_MANIFEST = Path("config/proxy_information_set_v098_files.sha256")
PYPROJECT = Path("pyproject.toml")
WORKFLOW = Path(".github/workflows/fetch-data.yml")
CONSTITUTION = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
RECORD = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
SCHEMAS = (
    Path("schemas/proxy_snapshot_observation_v098.schema.json"),
    Path("schemas/proxy_value_version_v098.schema.json"),
    Path("schemas/proxy_revision_event_v098.schema.json"),
    Path("schemas/proxy_snapshot_delta_v098.schema.json"),
    Path("schemas/proxy_source_cutoff_status_v098.schema.json"),
    Path("schemas/proxy_archive_lineage_v098.schema.json"),
    Path("schemas/proxy_archive_summary_v098.schema.json"),
    Path("schemas/proxy_information_set_summary_v098.schema.json"),
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
        raise CheckError("v0.9.8 asset manifest is missing")
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
    expected_assets = {
        "RELEASE_NOTES_V0.9.8.md",
        "config/proxy_information_set_v098.json",
        "docs/DECISION_PROXY_POINT_IN_TIME_ARCHIVE_V098.md",
        "docs/PROXY_POINT_IN_TIME_ARCHIVE_V098_CONTRACT.md",
        "schemas/proxy_snapshot_observation_v098.schema.json",
        "schemas/proxy_value_version_v098.schema.json",
        "schemas/proxy_revision_event_v098.schema.json",
        "schemas/proxy_snapshot_delta_v098.schema.json",
        "schemas/proxy_source_cutoff_status_v098.schema.json",
        "schemas/proxy_archive_lineage_v098.schema.json",
        "schemas/proxy_archive_summary_v098.schema.json",
        "schemas/proxy_information_set_summary_v098.schema.json",
        "scripts/check_proxy_information_set_v098.py",
        "src/armilar_proxies/archive_core_v098.py",
        "src/armilar_proxies/archive_builder_v098.py",
        "src/armilar_proxies/information_set_v098.py",
        "tests/test_proxy_information_set_v098.py",
    }
    if set(entries) != expected_assets:
        raise CheckError(
            f"asset manifest set mismatch; missing={sorted(expected_assets-set(entries))}, extra={sorted(set(entries)-expected_assets)}"
        )
    return entries


def load_module(root: Path) -> Any:
    source_root = str(root / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        return importlib.import_module("armilar_proxies.information_set_v098")
    except ImportError as exc:
        raise CheckError("cannot load v0.9.8 information-set package") from exc


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


def check_policy(root: Path, module: Any) -> dict[str, Any]:
    policy_module = importlib.import_module("armilar_proxies.archive_core_v098")
    policy = policy_module.load_policy(root / POLICY)
    if policy["contract_version"] != EXPECTED_VERSION:
        raise CheckError("v0.9.8 policy version mismatch")
    if any(policy["output_gates"].values()):
        raise CheckError("a v0.9.8 output gate is open")
    if policy["availability_policy"]["clock"] != "FIRST_VERIFIED_RETRIEVAL":
        raise CheckError("availability clock changed")
    for key in (
        "preserve_snapshot_deltas",
        "successor_archive_lineage_required_when_extending",
        "predecessor_content_must_be_preserved",
    ):
        if policy["archive_policy"].get(key) is not True:
            raise CheckError(f"archive policy invariant changed: {key}")
    return {
        "policy_sha256": policy_module.policy_hash(root / POLICY),
        "availability_clock": policy["availability_policy"]["clock"],
        "historical_first_published_claim_allowed": False,
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
        "import armilar_prices",
        "from armilar_prices",
        "public/latest",
        "research_release_allowed=true",
        "arm_l_use_allowed=true",
        "monetary_release_allowed=true",
    )
    for name in ("archive_core_v098.py", "archive_builder_v098.py", "information_set_v098.py"):
        text = canonical_text_bytes((root / "src/armilar_proxies" / name).read_bytes()).decode("utf-8")
        for token in forbidden:
            if token in text:
                raise CheckError(f"v0.9.8 module violates isolation contract: {name}: {token}")


def check_pyproject(root: Path) -> dict[str, Any]:
    project = tomllib.loads(canonical_text_bytes((root / PYPROJECT).read_bytes()).decode("utf-8"))["project"]
    if project.get("version") != EXPECTED_VERSION:
        raise CheckError(f"pyproject version must be {EXPECTED_VERSION}")
    scripts = project.get("scripts") or {}
    if scripts.get("armilar-proxy-information-v098") != EXPECTED_SCRIPT:
        raise CheckError("v0.9.8 CLI entry point mismatch")
    if scripts.get("armilar-proxies-v097") != "armilar_proxies.registry_v097:main":
        raise CheckError("v0.9.7 CLI entry point changed")
    optional = project.get("optional-dependencies") or {}
    if optional.get("proxies") != ["openpyxl>=3.1,<4"]:
        raise CheckError("proxy dependency set changed")
    return {"version": project["version"], "script": scripts["armilar-proxy-information-v098"]}


def check_workflow(root: Path) -> None:
    text = canonical_text_bytes((root / WORKFLOW).read_bytes()).decode("utf-8")
    expected_install = 'python -m pip install -e "' + '.[test,temporal,proxies]' + '"'
    if expected_install not in text:
        raise CheckError("CI does not install the v0.9.8 test dependencies")
    if "python scripts/check_proxy_information_set_v098.py --root ." not in text:
        raise CheckError("CI does not run the v0.9.8 checker")
    if "python scripts/check_proxy_registry_v097.py --root ." in text:
        raise CheckError("CI must not run the historical v0.9.7 checker on a v0.9.8 tree")
    if "python scripts/check_research_core_constitution.py --root ." not in text:
        raise CheckError("CI does not run the canonical constitution checker")
    if re.search(r"armilar-(?:proxies-v097|proxy-information-v098)\s+acquire", text):
        raise CheckError("live proxy acquisition is forbidden in CI")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)


def check_v097(root: Path) -> dict[str, Any]:
    git_dir = _git(root, "rev-parse", "--git-dir")
    if git_dir.returncode == 0:
        exists = _git(root, "cat-file", "-e", f"{EXPECTED_V097_COMMIT}^{{commit}}")
        ancestor = _git(root, "merge-base", "--is-ancestor", EXPECTED_V097_COMMIT, "HEAD")
        if exists.returncode != 0 or ancestor.returncode != 0:
            raise CheckError("historical v0.9.7 commit is missing or is not an ancestor")
        temp = Path(tempfile.mkdtemp(prefix="armilar-v097-check-"))
        worktree = temp / "worktree"
        try:
            add = _git(root, "worktree", "add", "--detach", str(worktree), EXPECTED_V097_COMMIT)
            if add.returncode != 0:
                raise CheckError(f"cannot create historical v0.9.7 worktree: {add.stderr}")
            checker = worktree / "scripts/check_proxy_registry_v097.py"
            process = subprocess.run(
                [sys.executable, str(checker), "--root", str(worktree)],
                cwd=worktree,
                text=True,
                capture_output=True,
            )
            if process.returncode != 0:
                raise CheckError(f"historical v0.9.7 checker failed:\n{process.stdout}\n{process.stderr}")
            try:
                result = json.loads(process.stdout)
            except json.JSONDecodeError as exc:
                raise CheckError("historical v0.9.7 checker returned invalid JSON") from exc
            return {"mode": "DETACHED_WORKTREE", "status": result.get("status"), "commit": EXPECTED_V097_COMMIT}
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))
            shutil.rmtree(temp, ignore_errors=True)
    manifest = root / "config/proxy_registry_v097_files.sha256"
    if not manifest.is_file():
        raise CheckError("v0.9.7 asset manifest is missing in non-git validation")
    for line in canonical_text_bytes(manifest.read_bytes()).decode("utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        if digest(root / relative) != expected:
            raise CheckError(f"v0.9.7 asset hash mismatch in non-git validation: {relative}")
    registry = read_json(root / "config/proxy_source_registry_v097.json")
    if registry.get("registry_version") != "0.9.7" or len(registry.get("sources") or []) != 4:
        raise CheckError("v0.9.7 registry baseline is invalid")
    return {"mode": "ASSET_MANIFEST", "status": "PROXY_REGISTRY_AND_ACQUISITION_V097_ASSETS_VALID", "commit": None}


def check(root: Path) -> dict[str, Any]:
    assets = verify_asset_manifest(root)
    protected = check_protected_core(root)
    module = load_module(root)
    policy = check_policy(root, module)
    schemas = check_schemas(root)
    check_isolation(root)
    pyproject = check_pyproject(root)
    check_workflow(root)
    v097 = check_v097(root)
    return {
        "status": "PROXY_POINT_IN_TIME_ARCHIVE_V098_VALID",
        "version": EXPECTED_VERSION,
        "asset_count": len(assets),
        "protected_core": protected,
        "policy": policy,
        "schemas": schemas,
        "pyproject": pyproject,
        "v097_status": v097["status"],
        "v097_validation_mode": v097["mode"],
        "historical_first_published_claim_allowed": False,
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
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
