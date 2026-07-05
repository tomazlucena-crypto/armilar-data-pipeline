#!/usr/bin/env python3
"""Fail-closed repository checker for ARMILAR v0.10.1 ARM-O materialization bridge."""
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

EXPECTED_VERSION = "0.10.1"
EXPECTED_V0100_COMMIT = "de2008f"
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_SCRIPT = "armilar_backtest.arm_o_materialization_v0101:main"
UTF8_BOM = b"\xef\xbb\xbf"

POLICY = Path("config/arm_o_materialization_bridge_v0101.json")
ASSET_MANIFEST = Path("config/arm_o_materialization_bridge_v0101_files.sha256")
PYPROJECT = Path("pyproject.toml")
WORKFLOW = Path(".github/workflows/fetch-data.yml")
CONSTITUTION = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
RECORD = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
V0100_MANIFEST = Path("config/point_in_time_backtest_v0100_files.sha256")
SOURCE = Path("src/armilar_backtest/arm_o_materialization_v0101.py")
TEST = Path("tests/test_arm_o_materialization_bridge_v0101.py")
SCHEMAS = tuple(sorted(Path("schemas") / name for name in (
    "arm_o_materialization_bridge_policy_v0101.schema.json",
    "arm_o_materialization_summary_v0101.schema.json",
    "arm_o_observation_bridge_summary_v0101.schema.json",
    "arm_o_observation_row_v0101.schema.json",
)))


class CheckError(RuntimeError):
    pass


def canonical_bytes(payload: bytes) -> bytes:
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
    return hashlib.sha256(canonical_bytes(path.read_bytes())).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(canonical_bytes(path.read_bytes()).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"invalid JSON: {path.as_posix()}") from exc


def expected_assets() -> set[str]:
    return {
        "RELEASE_NOTES_V0.10.1.md",
        POLICY.as_posix(),
        "docs/ARM_O_MATERIALIZATION_BRIDGE_V0101_CONTRACT.md",
        "docs/DECISION_ARM_O_MATERIALIZATION_BRIDGE_V0101.md",
        *(path.as_posix() for path in SCHEMAS),
        "scripts/check_arm_o_materialization_bridge_v0101.py",
        SOURCE.as_posix(),
        TEST.as_posix(),
    }


def verify_asset_manifest(root: Path) -> dict[str, str]:
    path = root / ASSET_MANIFEST
    if not path.is_file():
        raise CheckError("v0.10.1 asset manifest is missing")
    entries: dict[str, str] = {}
    for number, line in enumerate(canonical_bytes(path.read_bytes()).decode("utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise CheckError(f"invalid asset manifest line {number}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or relative in entries:
            raise CheckError(f"invalid asset manifest entry on line {number}")
        if digest(root / relative) != expected:
            raise CheckError(f"asset hash mismatch: {relative}")
        entries[relative] = expected
    expected = expected_assets()
    if set(entries) != expected:
        raise CheckError(
            f"asset manifest set mismatch; missing={sorted(expected-set(entries))}, extra={sorted(set(entries)-expected)}"
        )
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
        raise CheckError("constitutional gates must remain closed")
    return hashes


def load_policy(root: Path) -> Any:
    source_root = str(root / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        module = importlib.import_module("armilar_backtest.arm_o_materialization_v0101")
    except ImportError as exc:
        raise CheckError("cannot import v0.10.1 bridge") from exc
    return module.BridgePolicy.load(root / POLICY)


def check_policy(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    if policy.policy_version != EXPECTED_VERSION or any(policy.gates.values()):
        raise CheckError("v0.10.1 policy version or gates mismatch")
    if policy.availability_semantics != "FIRST_VERIFIED_ARMILAR_RETRIEVAL_NOT_OFFICIAL_PUBLICATION_TIME":
        raise CheckError("availability semantics changed")
    return {
        "policy_sha256": digest(root / POLICY),
        "availability_semantics": policy.availability_semantics,
        "gates": dict(policy.gates),
    }


def check_schemas(root: Path) -> list[str]:
    loaded: list[str] = []
    for relative in SCHEMAS:
        schema = read_json(root / relative)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise CheckError(f"unexpected schema draft: {relative}")
        if schema.get("additionalProperties") is not False:
            raise CheckError(f"schema is not closed: {relative}")
        loaded.append(relative.as_posix())
    return loaded


def check_isolation(root: Path) -> None:
    text = canonical_bytes((root / SOURCE).read_bytes()).decode("utf-8")
    required = (
        "FIRST_VERIFIED_ARMILAR_RETRIEVAL_NOT_OFFICIAL_PUBLICATION_TIME",
        "OFFICIAL_CATEGORY_FIRST_SEEN_AT_VERIFIED_RETRIEVAL",
        "V096_SINGLE_SPACE_TO_V0100_DOUBLE_SPACE_VIEW_PAYLOAD_BYTES_IDENTICAL",
        "NO_FUTURE_TARGETS_AFTER_2025_UNTIL_OFFICIAL_ENGINE_PERIOD_IS_EXTENDED",
    )
    for token in required:
        if token not in text:
            raise CheckError(f"required v0.10.1 invariant missing: {token}")
    forbidden = (
        "fit(", "partial_fit(", "GridSearch", "RandomizedSearch",
        "model_training_allowed=true", "arm_l_use_allowed=true",
        "monetary_use_allowed=true", "public/latest",
    )
    for token in forbidden:
        if token in text:
            raise CheckError(f"v0.10.1 module exceeds frozen scope: {token}")


def check_pyproject(root: Path) -> dict[str, Any]:
    project = tomllib.loads(canonical_bytes((root / PYPROJECT).read_bytes()).decode("utf-8"))["project"]
    if project.get("version") != EXPECTED_VERSION:
        raise CheckError(f"pyproject version must be {EXPECTED_VERSION}")
    scripts = project.get("scripts") or {}
    if scripts.get("armilar-arm-o-bridge-v0101") != EXPECTED_SCRIPT:
        raise CheckError("v0.10.1 CLI entry point mismatch")
    if scripts.get("armilar-backtest-v0100") != "armilar_backtest.cli_v0100:main":
        raise CheckError("v0.10.0 CLI entry point changed")
    return {"version": project["version"], "script": scripts["armilar-arm-o-bridge-v0101"]}


def check_workflow(root: Path) -> None:
    text = canonical_bytes((root / WORKFLOW).read_bytes()).decode("utf-8")
    if 'python -m pip install -e ".[test,temporal,proxies]"' not in text:
        raise CheckError("CI dependency installation changed")
    if "python scripts/check_arm_o_materialization_bridge_v0101.py --root ." not in text:
        raise CheckError("CI does not run the v0.10.1 checker")
    if "python scripts/check_point_in_time_backtest_v0100.py --root ." in text:
        raise CheckError("CI must not run the historical v0.10.0 checker directly on a v0.10.1 tree")
    if "python scripts/check_research_core_constitution.py --root ." not in text:
        raise CheckError("CI does not run the canonical constitution checker")
    if re.search(r"armilar-.*\s+acquire", text):
        raise CheckError("live acquisition remains forbidden in CI")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)


def check_v0100(root: Path) -> dict[str, Any]:
    if _git(root, "rev-parse", "--git-dir").returncode == 0:
        if _git(root, "cat-file", "-e", f"{EXPECTED_V0100_COMMIT}^{{commit}}").returncode != 0:
            raise CheckError("historical v0.10.0 commit is missing")
        if _git(root, "merge-base", "--is-ancestor", EXPECTED_V0100_COMMIT, "HEAD").returncode != 0:
            raise CheckError("historical v0.10.0 commit is not an ancestor")
        temp = Path(tempfile.mkdtemp(prefix="armilar-v0100-check-"))
        worktree = temp / "worktree"
        try:
            added = _git(root, "worktree", "add", "--detach", str(worktree), EXPECTED_V0100_COMMIT)
            if added.returncode != 0:
                raise CheckError(f"cannot create v0.10.0 worktree: {added.stderr}")
            process = subprocess.run(
                [sys.executable, str(worktree / "scripts/check_point_in_time_backtest_v0100.py"), "--root", str(worktree)],
                cwd=worktree, text=True, capture_output=True,
            )
            if process.returncode != 0:
                raise CheckError(f"historical v0.10.0 checker failed:\n{process.stdout}\n{process.stderr}")
            payload = json.loads(process.stdout)
            if payload.get("status") != "POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID":
                raise CheckError("unexpected v0.10.0 checker status")
            return {"mode": "DETACHED_WORKTREE", "status": payload["status"], "commit": EXPECTED_V0100_COMMIT}
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))
            shutil.rmtree(temp, ignore_errors=True)
    if not (root / V0100_MANIFEST).is_file():
        raise CheckError("v0.10.0 manifest missing in non-git validation")
    return {"mode": "ASSET_MANIFEST", "status": "POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID", "commit": None}


def check(root: Path) -> dict[str, Any]:
    assets = verify_asset_manifest(root)
    protected = check_protected_core(root)
    policy = check_policy(root)
    schemas = check_schemas(root)
    check_isolation(root)
    pyproject = check_pyproject(root)
    check_workflow(root)
    historical = check_v0100(root)
    return {
        "status": "ARM_O_MATERIALIZATION_BRIDGE_V0101_VALID",
        "version": EXPECTED_VERSION,
        "asset_count": len(assets),
        "schema_count": len(schemas),
        "protected": protected,
        "policy": policy,
        "pyproject": pyproject,
        "v0100_status": historical["status"],
        "v0100_mode": historical["mode"],
        "v0100_commit": historical["commit"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = check(args.root.resolve())
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
