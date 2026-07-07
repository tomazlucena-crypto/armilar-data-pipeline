#!/usr/bin/env python3
"""Validate the frozen ARMILAR v0.10.2 ECOICOP v2 transition contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_VERSION = "0.10.2"
EXPECTED_STATUS = "ECOICOP_V2_TRANSITION_BLOCKED_PENDING_EXPLICIT_DECISION"
EXPECTED_NEXT_DECISION = "EXPLICIT_CONSTITUTIONAL_TRANSITION_DECISION_AND_BACKTEST"
EXPECTED_V0101_COMMIT = "43c3bf02216635d41624f56fa0f2951c3d0cfdae"
EXPECTED_V0101_STATUS = "ARM_O_MATERIALIZATION_BRIDGE_V0101_VALID"
EXPECTED_V0100_STATUS = "POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID"
EXPECTED_ASSETS = (
    "RELEASE_NOTES_V0.10.2.md",
    "config/ecoicop_v2_transition_v0102.json",
    "docs/ECOICOP_V2_TRANSITION_V0102_CONTRACT.md",
    "docs/DECISION_ECOICOP_V2_TRANSITION_V0102.md",
    "schemas/ecoicop_v2_transition_policy_v0102.schema.json",
    "schemas/ecoicop_v2_transition_summary_v0102.schema.json",
    "scripts/check_ecoicop_v2_transition_v0102.py",
    "src/armilar_backtest/ecoicop_v2_transition_v0102.py",
    "tests/test_ecoicop_v2_transition_v0102.py",
)
MANIFEST_PATH = "config/ecoicop_v2_transition_v0102_files.sha256"
FORBIDDEN_NETWORK_TOKENS = (
    "urllib.request",
    "requests.",
    "httpx.",
    "socket.",
    "urlopen(",
    "subprocess.",
    "os.system(",
)


class CheckError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    if not path.is_file():
        raise CheckError(f"required file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CheckError(f"JSON object required: {path}")
    return payload


def verify_asset_manifest(root: Path) -> None:
    manifest = root / MANIFEST_PATH
    lines = manifest.read_text(encoding="utf-8").splitlines()
    entries: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^ ].*)", line)
        if match is None:
            raise CheckError(f"invalid v0.10.2 manifest line {number}")
        digest, relative = match.groups()
        if relative in entries:
            raise CheckError(f"duplicate v0.10.2 manifest entry: {relative}")
        entries[relative] = digest
    if set(entries) != set(EXPECTED_ASSETS):
        raise CheckError(
            "v0.10.2 manifest file set mismatch: "
            f"missing={sorted(set(EXPECTED_ASSETS)-set(entries))}, "
            f"extra={sorted(set(entries)-set(EXPECTED_ASSETS))}"
        )
    for relative, digest in entries.items():
        if sha256(root / relative) != digest:
            raise CheckError(f"v0.10.2 asset hash mismatch: {relative}")


def verify_closed_schema(path: Path) -> None:
    schema = read_json(path)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise CheckError(f"unexpected schema dialect: {path}")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise CheckError(f"top-level schema must be a closed object: {path}")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        raise CheckError(f"schema required/properties malformed: {path}")
    if set(required) != set(properties):
        raise CheckError(f"schema required set differs from properties: {path}")


def verify_pyproject(root: Path) -> None:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if not re.search(r'^version\s*=\s*"0\.10\.2"\s*$', text, re.MULTILINE):
        raise CheckError("pyproject.toml must declare version 0.10.2")
    entry = (
        'armilar-ecoicop-v2-transition-v0102 = '
        '"armilar_backtest.ecoicop_v2_transition_v0102:main"'
    )
    if entry not in text:
        raise CheckError("v0.10.2 console script entry missing")


def verify_workflow(root: Path) -> None:
    text = (root / ".github/workflows/fetch-data.yml").read_text(encoding="utf-8")
    required = (
        "Validate v0.10.2 ECOICOP v2 transition and predecessor gate",
        "python scripts/check_ecoicop_v2_transition_v0102.py --root .",
        "python -m pytest -q",
    )
    for token in required:
        if token not in text:
            raise CheckError(f"workflow token missing: {token}")
    direct_predecessor = (
        "python scripts/check_arm_o_materialization_bridge_v0101.py --root ."
    )
    if direct_predecessor in text:
        raise CheckError(
            "CI must not run the historical v0.10.1 checker directly on a v0.10.2 tree"
        )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def verify_v0101_predecessor(root: Path) -> dict[str, object]:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise CheckError("v0.10.2 repository validation requires Git history")
    if (
        _git(root, "cat-file", "-e", f"{EXPECTED_V0101_COMMIT}^{{commit}}").returncode
        != 0
    ):
        raise CheckError("historical v0.10.1 commit is missing")
    if (
        _git(root, "merge-base", "--is-ancestor", EXPECTED_V0101_COMMIT, "HEAD").returncode
        != 0
    ):
        raise CheckError("historical v0.10.1 commit is not an ancestor")

    temp = Path(tempfile.mkdtemp(prefix="armilar-v0101-check-"))
    worktree = temp / "worktree"
    try:
        added = _git(root, "worktree", "add", "--detach", str(worktree), EXPECTED_V0101_COMMIT)
        if added.returncode != 0:
            raise CheckError(f"cannot create v0.10.1 worktree: {added.stderr}")
        process = subprocess.run(
            [
                sys.executable,
                str(worktree / "scripts/check_arm_o_materialization_bridge_v0101.py"),
                "--root",
                str(worktree),
            ],
            cwd=worktree,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise CheckError(
                "historical v0.10.1 checker failed:\n"
                f"{process.stdout}\n{process.stderr}"
            )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise CheckError("historical v0.10.1 checker returned invalid JSON") from exc
        if payload.get("status") != EXPECTED_V0101_STATUS:
            raise CheckError("unexpected v0.10.1 checker status")
        if payload.get("version") != "0.10.1":
            raise CheckError("unexpected v0.10.1 checker version")
        if payload.get("v0100_status") != EXPECTED_V0100_STATUS:
            raise CheckError("unexpected v0.10.0 predecessor status inside v0.10.1")
        if payload.get("v0100_mode") != "DETACHED_WORKTREE":
            raise CheckError("v0.10.1 did not validate v0.10.0 in a detached worktree")
        return {
            "v0101_status": payload["status"],
            "v0101_mode": "DETACHED_WORKTREE",
            "v0101_commit": EXPECTED_V0101_COMMIT,
            "v0100_status": payload["v0100_status"],
            "v0100_mode": payload["v0100_mode"],
        }
    finally:
        _git(root, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(temp, ignore_errors=True)


def verify_no_network_code(root: Path) -> None:
    module = (root / "src/armilar_backtest/ecoicop_v2_transition_v0102.py").read_text(
        encoding="utf-8"
    )
    for token in FORBIDDEN_NETWORK_TOKENS:
        if token in module:
            raise CheckError(f"network or process token forbidden in v0.10.2: {token}")


def verify_runtime(root: Path) -> dict[str, object]:
    sys.path.insert(0, str(root / "src"))
    try:
        from armilar_backtest.ecoicop_v2_transition_v0102 import (  # noqa: PLC0415
            STATUS,
            TransitionPolicy,
            build_transition_audit,
            verify_transition_audit,
        )
    except ImportError as exc:
        raise CheckError("cannot import v0.10.2 module") from exc
    policy_path = root / "config/ecoicop_v2_transition_v0102.json"
    policy = TransitionPolicy.load(policy_path)
    if policy.policy_version != EXPECTED_VERSION:
        raise CheckError("loaded policy version mismatch")
    if any(policy.gates.values()):
        raise CheckError("a v0.10.2 gate is open")
    temp = Path(tempfile.mkdtemp(prefix="armilar-v0102-check-"))
    try:
        first = temp / "first"
        second = temp / "second"
        summary = build_transition_audit(
            policy_path=policy_path,
            root=root,
            output_dir=first,
            created_at="2026-07-06T00:00:00Z",
        )
        verified = verify_transition_audit(first, policy_path=policy_path, root=root)
        build_transition_audit(
            policy_path=policy_path,
            root=root,
            output_dir=second,
            created_at="2026-07-06T00:00:00Z",
        )
        if summary != verified:
            raise CheckError("audit verification changed the summary")
        if summary.get("status") != STATUS or STATUS != EXPECTED_STATUS:
            raise CheckError("transition status mismatch")
        if summary.get("required_next_decision") != EXPECTED_NEXT_DECISION:
            raise CheckError("required next decision mismatch")
        first_files = {p.name: p.read_bytes() for p in first.iterdir() if p.is_file()}
        second_files = {p.name: p.read_bytes() for p in second.iterdir() if p.is_file()}
        if first_files != second_files:
            raise CheckError("transition audit is not byte deterministic")
        return {
            "status": summary["status"],
            "legacy_category_count": summary["legacy_category_count"],
            "replacement_division_count": summary["replacement_division_count"],
            "material_reclassification_count": summary["material_reclassification_count"],
            "automatic_use_allowed_count": summary["automatic_use_allowed_count"],
            "replacement_back_series_available": summary[
                "replacement_back_series_available"
            ],
            "required_next_decision": summary["required_next_decision"],
            "audit_manifest_sha256": sha256(first / "MANIFEST.sha256"),
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def run(root: Path) -> dict[str, object]:
    root = root.resolve()
    verify_asset_manifest(root)
    verify_closed_schema(root / "schemas/ecoicop_v2_transition_policy_v0102.schema.json")
    verify_closed_schema(root / "schemas/ecoicop_v2_transition_summary_v0102.schema.json")
    verify_pyproject(root)
    verify_workflow(root)
    predecessor = verify_v0101_predecessor(root)
    verify_no_network_code(root)
    policy = read_json(root / "config/ecoicop_v2_transition_v0102.json")
    if policy.get("legacy_source_policy_path") != "config/eurostat_vertical_v087.json":
        raise CheckError("legacy source policy path changed")
    if policy.get("constitution_path") != "constitution/ARMILAR_RESEARCH_CORE_V1.json":
        raise CheckError("constitution path changed")
    result = verify_runtime(root)
    return {
        "checker_status": "ECOICOP_V2_TRANSITION_V0102_VALID",
        "policy_sha256": sha256(root / "config/ecoicop_v2_transition_v0102.json"),
        "constitution_sha256": sha256(root / "constitution/ARMILAR_RESEARCH_CORE_V1.json"),
        "legacy_source_policy_sha256": sha256(root / "config/eurostat_vertical_v087.json"),
        **predecessor,
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        payload = run(args.root)
    except (CheckError, RuntimeError, OSError, ValueError) as exc:
        print(f"ECOICOP_V2_TRANSITION_V0102_INVALID: {exc}", file=sys.stderr)
        return 1
    print("ECOICOP_V2_TRANSITION_V0102_VALID")
    for key, value in payload.items():
        if key != "checker_status":
            print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
