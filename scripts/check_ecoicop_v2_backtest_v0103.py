#!/usr/bin/env python3
"""Validate the ARMILAR v0.10.3 ECOICOP v1/v2 backtest protocol."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_VERSION = "0.10.3"
EXPECTED_STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
EXPECTED_V0102_COMMIT = "215bba966f2a376d2cd4370297512d440b0dbb7d"
EXPECTED_V0102_STATUS = "ECOICOP_V2_TRANSITION_V0102_VALID"
EXPECTED_V0101_STATUS = "ARM_O_MATERIALIZATION_BRIDGE_V0101_VALID"
EXPECTED_V0100_STATUS = "POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID"
EXPECTED_PREDECESSOR_POLICY_SHA256 = (
    "8ae44a982a2ae88fa6e33c23bb95437dc4f91e0f17896190d2bbbfbaa6ff5557"
)
PREDECESSOR_POLICY_PATH = "config/ecoicop_v2_transition_v0102.json"
EXPECTED_ASSETS = (
    "RELEASE_NOTES_V0.10.3.md",
    "config/ecoicop_v2_backtest_protocol_v0103.json",
    "config/ecoicop_v1_v2_mapping_candidates_v0103.json",
    "docs/ECOICOP_V2_BACKTEST_PROTOCOL_V0103_CONTRACT.md",
    "docs/DECISION_ECOICOP_V2_BACKTEST_PROTOCOL_V0103.md",
    "schemas/ecoicop_v2_backtest_protocol_v0103.schema.json",
    "schemas/ecoicop_v1_v2_mapping_candidates_v0103.schema.json",
    "schemas/ecoicop_v2_backtest_summary_v0103.schema.json",
    "scripts/check_ecoicop_v2_backtest_v0103.py",
    "src/armilar_backtest/ecoicop_v2_backtest_v0103.py",
    "tests/test_ecoicop_v2_backtest_v0103.py",
)
MANIFEST_PATH = "config/ecoicop_v2_backtest_v0103_files.sha256"
FORBIDDEN_RUNTIME_TOKENS = (
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
    if not manifest.is_file():
        raise CheckError(f"required manifest missing: {MANIFEST_PATH}")
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64}) ([^ ].*)", line)
        if match is None:
            raise CheckError(f"invalid v0.10.3 manifest line {number}")
        digest, relative = match.groups()
        if relative in entries:
            raise CheckError(f"duplicate v0.10.3 manifest entry: {relative}")
        entries[relative] = digest
    if set(entries) != set(EXPECTED_ASSETS):
        raise CheckError(
            "v0.10.3 manifest file set mismatch: "
            f"missing={sorted(set(EXPECTED_ASSETS) - set(entries))}, "
            f"extra={sorted(set(entries) - set(EXPECTED_ASSETS))}"
        )
    for relative, digest in entries.items():
        if sha256(root / relative) != digest:
            raise CheckError(f"v0.10.3 asset hash mismatch: {relative}")


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
    if not re.search(r'^version\s*=\s*"0\.10\.3"\s*$', text, re.MULTILINE):
        raise CheckError("pyproject.toml must declare version 0.10.3")
    entry = (
        'armilar-ecoicop-v2-backtest-v0103 = '
        '"armilar_backtest.ecoicop_v2_backtest_v0103:main"'
    )
    if entry not in text:
        raise CheckError("v0.10.3 console script entry missing")


def verify_workflow(root: Path) -> None:
    text = (root / ".github/workflows/fetch-data.yml").read_text(encoding="utf-8")
    required = (
        "Validate v0.10.3 ECOICOP v1/v2 backtest protocol and predecessor gate",
        "python scripts/check_ecoicop_v2_backtest_v0103.py --root .",
        "python -m pytest -q",
    )
    for token in required:
        if token not in text:
            raise CheckError(f"workflow token missing: {token}")
    if "python scripts/check_ecoicop_v2_transition_v0102.py --root ." in text:
        raise CheckError(
            "CI must not run the historical v0.10.2 checker directly on a v0.10.3 tree"
        )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=False,
        capture_output=True,
        check=False,
    )


def _parse_key_value_output(stdout: str) -> tuple[str, dict[str, str]]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise CheckError("historical checker returned empty output")
    status = lines[0]
    payload: dict[str, str] = {}
    for line in lines[1:]:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key] = value
    return status, payload


def _git_blob(root: Path, commit: str, relative: str) -> bytes:
    process = _git_bytes(root, "show", f"{commit}:{relative}")
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise CheckError(detail or f"cannot read {relative} from {commit}")
    return process.stdout


def _git_blob_sha256(root: Path, commit: str, relative: str) -> str:
    return hashlib.sha256(_git_blob(root, commit, relative)).hexdigest()


def _read_git_json(root: Path, commit: str, relative: str) -> dict[str, object]:
    try:
        payload = json.loads(_git_blob(root, commit, relative).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckError(f"invalid historical JSON: {commit}:{relative}") from exc
    if not isinstance(payload, dict):
        raise CheckError(f"historical JSON object required: {commit}:{relative}")
    return payload


def _verify_git_manifest(
    root: Path,
    commit: str,
    manifest_path: str,
    *,
    expected_assets: tuple[str, ...] | None = None,
    required_assets: tuple[str, ...] = (),
) -> dict[str, str]:
    try:
        manifest_text = _git_blob(root, commit, manifest_path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CheckError(f"historical manifest is not UTF-8: {commit}:{manifest_path}") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest_text.splitlines(), start=1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})\s+([^ ].*)", line)
        if match is None:
            raise CheckError(f"invalid historical manifest line {number}: {manifest_path}")
        digest, relative = match.groups()
        if relative in entries:
            raise CheckError(f"duplicate historical manifest entry: {relative}")
        if _git_blob_sha256(root, commit, relative) != digest:
            raise CheckError(f"historical asset hash mismatch: {commit}:{relative}")
        entries[relative] = digest
    if expected_assets is not None and set(entries) != set(expected_assets):
        raise CheckError(
            f"historical manifest set mismatch for {manifest_path}: "
            f"missing={sorted(set(expected_assets) - set(entries))}, "
            f"extra={sorted(set(entries) - set(expected_assets))}"
        )
    missing = sorted(set(required_assets) - set(entries))
    if missing:
        raise CheckError(f"historical manifest missing required assets: {missing}")
    return entries


def _verify_historical_pyproject_version(root: Path, commit: str, expected_version: str) -> None:
    try:
        text = _git_blob(root, commit, "pyproject.toml").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CheckError(f"historical pyproject is not UTF-8: {commit}") from exc
    if not re.search(rf'^version\s*=\s*"{re.escape(expected_version)}"\s*$', text, re.MULTILINE):
        raise CheckError(f"historical pyproject version mismatch for {commit}")


def _verify_historical_policy(
    root: Path,
    commit: str,
    policy_path: str,
    expected_version: str,
) -> dict[str, object]:
    payload = _read_git_json(root, commit, policy_path)
    if payload.get("policy_version") != expected_version:
        raise CheckError(f"historical policy version mismatch: {commit}:{policy_path}")
    gates = payload.get("gates")
    if not isinstance(gates, dict) or any(gates.values()):
        raise CheckError(f"historical policy gates must remain closed: {commit}:{policy_path}")
    return payload


def _load_module_from_path(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise CheckError(f"cannot load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _verify_v0102_runtime_without_subprocess(worktree: Path) -> dict[str, object]:
    module = _load_module_from_path(
        worktree / "src/armilar_backtest/ecoicop_v2_transition_v0102.py",
        "armilar_historical_ecoicop_v2_transition_v0102",
    )
    policy_path = worktree / PREDECESSOR_POLICY_PATH
    temp = Path(tempfile.mkdtemp(prefix="armilar-v0102-runtime-"))
    try:
        first = temp / "first"
        second = temp / "second"
        summary = module.build_transition_audit(
            policy_path=policy_path,
            root=worktree,
            output_dir=first,
            created_at="2026-07-06T00:00:00Z",
        )
        verified = module.verify_transition_audit(first, policy_path=policy_path, root=worktree)
        module.build_transition_audit(
            policy_path=policy_path,
            root=worktree,
            output_dir=second,
            created_at="2026-07-06T00:00:00Z",
        )
        if summary != verified:
            raise CheckError("historical v0.10.2 audit verification changed the summary")
        if {p.name: p.read_bytes() for p in first.iterdir() if p.is_file()} != {
            p.name: p.read_bytes() for p in second.iterdir() if p.is_file()
        }:
            raise CheckError("historical v0.10.2 audit is not byte deterministic")
        if summary.get("status") != "ECOICOP_V2_TRANSITION_BLOCKED_PENDING_EXPLICIT_DECISION":
            raise CheckError("historical v0.10.2 transition status mismatch")
        if summary.get("automatic_use_allowed_count") != 0:
            raise CheckError("historical v0.10.2 allowed automatic transition use")
        return {
            "v0102_transition_status": summary["status"],
            "v0102_audit_manifest_sha256": hashlib.sha256((first / "MANIFEST.sha256").read_bytes()).hexdigest(),
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def verify_v0102_predecessor(root: Path) -> dict[str, object]:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise CheckError("v0.10.3 repository validation requires Git history")
    for commit, label in (
        (EXPECTED_V0102_COMMIT, "v0.10.2"),
        ("43c3bf02216635d41624f56fa0f2951c3d0cfdae", "v0.10.1"),
        ("de2008f6f020a0bccd2105a515525109a8e70c7e", "v0.10.0"),
    ):
        if _git(root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
            raise CheckError(f"historical {label} commit is missing")
        if _git(root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
            raise CheckError(f"historical {label} commit is not an ancestor")

    v0102_assets = (
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
    _verify_git_manifest(
        root,
        EXPECTED_V0102_COMMIT,
        "config/ecoicop_v2_transition_v0102_files.sha256",
        expected_assets=v0102_assets,
    )
    _verify_historical_pyproject_version(root, EXPECTED_V0102_COMMIT, "0.10.2")
    v0102_policy = _verify_historical_policy(
        root,
        EXPECTED_V0102_COMMIT,
        PREDECESSOR_POLICY_PATH,
        "0.10.2",
    )
    if hashlib.sha256(_git_blob(root, EXPECTED_V0102_COMMIT, PREDECESSOR_POLICY_PATH)).hexdigest() != EXPECTED_PREDECESSOR_POLICY_SHA256:
        raise CheckError("historical v0.10.2 predecessor policy hash mismatch")
    if v0102_policy.get("required_next_decision") != "EXPLICIT_CONSTITUTIONAL_TRANSITION_DECISION_AND_BACKTEST":
        raise CheckError("historical v0.10.2 next decision changed")

    _verify_git_manifest(
        root,
        "43c3bf02216635d41624f56fa0f2951c3d0cfdae",
        "config/arm_o_materialization_bridge_v0101_files.sha256",
        required_assets=(
            "config/arm_o_materialization_bridge_v0101.json",
            "scripts/check_arm_o_materialization_bridge_v0101.py",
            "src/armilar_backtest/arm_o_materialization_v0101.py",
        ),
    )
    _verify_historical_pyproject_version(
        root, "43c3bf02216635d41624f56fa0f2951c3d0cfdae", "0.10.1"
    )
    _verify_historical_policy(
        root,
        "43c3bf02216635d41624f56fa0f2951c3d0cfdae",
        "config/arm_o_materialization_bridge_v0101.json",
        "0.10.1",
    )

    _verify_git_manifest(
        root,
        "de2008f6f020a0bccd2105a515525109a8e70c7e",
        "config/point_in_time_backtest_v0100_files.sha256",
        required_assets=(
            "config/point_in_time_backtest_protocol_v0100.json",
            "scripts/check_point_in_time_backtest_v0100.py",
            "src/armilar_backtest/protocol_v0100.py",
        ),
    )
    _verify_historical_pyproject_version(
        root, "de2008f6f020a0bccd2105a515525109a8e70c7e", "0.10.0"
    )
    _verify_historical_policy(
        root,
        "de2008f6f020a0bccd2105a515525109a8e70c7e",
        "config/point_in_time_backtest_protocol_v0100.json",
        "0.10.0",
    )

    temp = Path(tempfile.mkdtemp(prefix="armilar-v0102-check-"))
    worktree = temp / "worktree"
    try:
        added = _git(root, "worktree", "add", "--detach", str(worktree), EXPECTED_V0102_COMMIT)
        if added.returncode != 0:
            raise CheckError(f"cannot create v0.10.2 worktree: {added.stderr}")
        runtime = _verify_v0102_runtime_without_subprocess(worktree)
        return {
            "v0102_status": EXPECTED_V0102_STATUS,
            "v0102_mode": "DETACHED_WORKTREE",
            "v0102_commit": EXPECTED_V0102_COMMIT,
            "v0101_status": EXPECTED_V0101_STATUS,
            "v0101_mode": "DETACHED_WORKTREE",
            "v0100_status": EXPECTED_V0100_STATUS,
            "v0100_mode": "DETACHED_WORKTREE",
            **runtime,
        }
    finally:
        _git(root, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(temp, ignore_errors=True)

def verify_no_network_code(root: Path) -> None:
    module = (
        root / "src/armilar_backtest/ecoicop_v2_backtest_v0103.py"
    ).read_text(encoding="utf-8")
    for token in FORBIDDEN_RUNTIME_TOKENS:
        if token in module:
            raise CheckError(f"network or process token forbidden in v0.10.3 runtime: {token}")


def verify_predecessor_files(root: Path) -> None:
    predecessor = root / PREDECESSOR_POLICY_PATH
    if not predecessor.is_file():
        raise CheckError(f"required predecessor policy missing: {PREDECESSOR_POLICY_PATH}")

    historical_blob = _git_bytes(
        root, "show", f"{EXPECTED_V0102_COMMIT}:{PREDECESSOR_POLICY_PATH}"
    )
    if historical_blob.returncode != 0:
        detail = historical_blob.stderr.decode("utf-8", errors="replace").strip()
        raise CheckError(detail or "cannot read predecessor policy from v0.10.2 commit")
    historical_digest = hashlib.sha256(historical_blob.stdout).hexdigest()
    if historical_digest != EXPECTED_PREDECESSOR_POLICY_SHA256:
        raise CheckError(
            "v0.10.2 predecessor policy Git-blob hash changed: "
            f"{historical_digest}"
        )

    head_blob = _git_bytes(root, "show", f"HEAD:{PREDECESSOR_POLICY_PATH}")
    if head_blob.returncode != 0:
        detail = head_blob.stderr.decode("utf-8", errors="replace").strip()
        raise CheckError(detail or "cannot read predecessor policy from HEAD")
    if head_blob.stdout != historical_blob.stdout:
        raise CheckError("HEAD changed the committed v0.10.2 predecessor policy")

    try:
        committed_policy = json.loads(historical_blob.stdout.decode("utf-8"))
        working_policy = json.loads(predecessor.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckError("invalid v0.10.2 predecessor policy JSON") from exc
    if working_policy != committed_policy:
        raise CheckError(
            "working-tree predecessor policy differs semantically from the committed policy"
        )

    protocol = read_json(root / "config/ecoicop_v2_backtest_protocol_v0103.json")
    predecessor_contract = protocol.get("predecessor")
    if not isinstance(predecessor_contract, dict):
        raise CheckError("v0.10.3 predecessor contract malformed")
    if predecessor_contract.get("policy_sha256") != EXPECTED_PREDECESSOR_POLICY_SHA256:
        raise CheckError("v0.10.3 embeds an unexpected predecessor policy hash")


def verify_documentary_scope(root: Path) -> None:
    release = (root / "RELEASE_NOTES_V0.10.3.md").read_text(encoding="utf-8")
    decision = (
        root / "docs/DECISION_ECOICOP_V2_BACKTEST_PROTOCOL_V0103.md"
    ).read_text(encoding="utf-8")
    required_release = (
        "does not acquire live 2026 data",
        "does not execute the empirical backtest",
        "does not ratify a transition strategy",
        "does not extend ARM-O",
    )
    for token in required_release:
        if token not in release:
            raise CheckError(f"release notes scope token missing: {token}")
    if "classification_transition_ratified=false" not in decision:
        raise CheckError("decision document must keep classification transition unratified")
    if "backtest_execution_claim_allowed=false" not in decision:
        raise CheckError("decision document must keep backtest execution claim closed")


def verify_runtime(root: Path) -> dict[str, object]:
    sys.path.insert(0, str(root / "src"))
    try:
        from armilar_backtest.ecoicop_v2_backtest_v0103 import (  # noqa: PLC0415
            NEXT_MILESTONE,
            STATUS,
            ProtocolBundle,
            build_protocol_audit,
            verify_protocol_audit,
        )
    except ImportError as exc:
        raise CheckError("cannot import v0.10.3 module") from exc

    policy_path = root / "config/ecoicop_v2_backtest_protocol_v0103.json"
    mapping_path = root / "config/ecoicop_v1_v2_mapping_candidates_v0103.json"
    bundle = ProtocolBundle.load(policy_path, mapping_path)
    if any(bundle.policy["gates"].values()):
        raise CheckError("a v0.10.3 release, training or monetary gate is open")

    temp = Path(tempfile.mkdtemp(prefix="armilar-v0103-check-"))
    try:
        first = temp / "first"
        second = temp / "second"
        summary = build_protocol_audit(
            policy_path=policy_path,
            mapping_path=mapping_path,
            output_dir=first,
            created_at="2026-07-07T00:00:00Z",
        )
        verified = verify_protocol_audit(
            first,
            policy_path=policy_path,
            mapping_path=mapping_path,
        )
        build_protocol_audit(
            policy_path=policy_path,
            mapping_path=mapping_path,
            output_dir=second,
            created_at="2026-07-07T00:00:00Z",
        )
        if summary != verified:
            raise CheckError("audit verification changed the summary")
        first_files = {path.name: path.read_bytes() for path in first.iterdir() if path.is_file()}
        second_files = {path.name: path.read_bytes() for path in second.iterdir() if path.is_file()}
        if first_files != second_files:
            raise CheckError("protocol audit is not byte deterministic")
        if summary.get("status") != STATUS or STATUS != EXPECTED_STATUS:
            raise CheckError("protocol status mismatch")
        if summary.get("next_milestone") != NEXT_MILESTONE:
            raise CheckError("next milestone mismatch")
        hard_false = (
            "classification_transition_ratified",
            "arm_o_2026_extension_allowed",
            "backtest_execution_claim_allowed",
            "automatic_winner_allowed",
        )
        if any(summary.get(key) is not False for key in hard_false):
            raise CheckError("protocol summary opened a forbidden decision or execution gate")
        if summary.get("empirical_observation_count") != 0:
            raise CheckError("v0.10.3 must contain zero empirical observations")
        if summary.get("live_2026_observation_count") != 0:
            raise CheckError("v0.10.3 must contain zero live 2026 observations")
        return {
            "status": summary["status"],
            "strategy_count": summary["strategy_count"],
            "mapping_row_count": summary["mapping_row_count"],
            "automatic_mapping_count": summary["automatic_mapping_count"],
            "required_metric_count": summary["required_metric_count"],
            "dataset_contract_count": summary["dataset_contract_count"],
            "transformation_dimension_count": summary["transformation_dimension_count"],
            "completion_gate_count": summary["completion_gate_count"],
            "empirical_observation_count": summary["empirical_observation_count"],
            "live_2026_observation_count": summary["live_2026_observation_count"],
            "open_gate_count": summary["open_gate_count"],
            "next_milestone": summary["next_milestone"],
            "audit_manifest_sha256": sha256(first / "MANIFEST.sha256"),
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def run(root: Path) -> dict[str, object]:
    root = root.resolve()
    verify_asset_manifest(root)
    for relative in (
        "schemas/ecoicop_v2_backtest_protocol_v0103.schema.json",
        "schemas/ecoicop_v1_v2_mapping_candidates_v0103.schema.json",
        "schemas/ecoicop_v2_backtest_summary_v0103.schema.json",
    ):
        verify_closed_schema(root / relative)
    verify_pyproject(root)
    verify_workflow(root)
    verify_predecessor_files(root)
    predecessor = verify_v0102_predecessor(root)
    verify_no_network_code(root)
    verify_documentary_scope(root)
    runtime = verify_runtime(root)
    return {
        "checker_status": EXPECTED_STATUS,
        "policy_sha256": sha256(root / "config/ecoicop_v2_backtest_protocol_v0103.json"),
        "mapping_sha256": sha256(root / "config/ecoicop_v1_v2_mapping_candidates_v0103.json"),
        "predecessor_policy_sha256": EXPECTED_PREDECESSOR_POLICY_SHA256,
        **predecessor,
        **runtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        payload = run(args.root)
    except (CheckError, OSError, RuntimeError, ValueError) as exc:
        print(f"ECOICOP_V2_BACKTEST_PROTOCOL_V0103_INVALID: {exc}", file=sys.stderr)
        return 1
    print(EXPECTED_STATUS)
    for key, value in payload.items():
        if key != "checker_status":
            rendered = str(value).lower() if isinstance(value, bool) else value
            print(f"{key}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
