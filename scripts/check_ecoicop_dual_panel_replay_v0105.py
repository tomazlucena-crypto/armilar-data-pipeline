from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID"


class CheckError(RuntimeError):
    pass


def _load_module(root: Path):
    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_replay_v0105.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_replay_v0105", module_path)
    if spec is None or spec.loader is None:
        raise CheckError("cannot import v0.10.5 module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_pyproject(root: Path) -> None:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.10.5"' not in text:
        raise CheckError("pyproject.toml version is not 0.10.5")
    if 'armilar-ecoicop-dual-panel-replay-v0105 = "armilar_backtest.ecoicop_dual_panel_replay_v0105:main"' not in text:
        raise CheckError("v0.10.5 console script entry missing")


def _validate_workflow(root: Path) -> None:
    text = (root / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
    if "scripts/check_ecoicop_dual_panel_replay_v0105.py" not in text:
        raise CheckError("workflow does not run v0.10.5 checker")


def _validate_manifest(root: Path) -> None:
    module = _load_module(root)
    manifest_path = root / "config" / "ecoicop_dual_panel_replay_v0105_files.sha256"
    expected = {
        "RELEASE_NOTES_V0.10.5.md",
        "config/ecoicop_dual_panel_replay_v0105.json",
        "docs/DECISION_ECOICOP_DUAL_PANEL_REPLAY_V0105.md",
        "docs/ECOICOP_DUAL_PANEL_REPLAY_V0105_CONTRACT.md",
        "schemas/ecoicop_dual_panel_replay_policy_v0105.schema.json",
        "schemas/ecoicop_dual_panel_replay_summary_v0105.schema.json",
        "scripts/check_ecoicop_dual_panel_replay_v0105.py",
        "src/armilar_backtest/ecoicop_dual_panel_replay_v0105.py",
        "tests/test_ecoicop_dual_panel_replay_v0105.py",
    }
    if not manifest_path.is_file():
        raise CheckError("v0.10.5 manifest missing")
    actual: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise CheckError(f"invalid manifest line {line_number}")
        digest, relative = parts
        actual[relative] = digest
    if set(actual) != expected:
        raise CheckError(f"manifest mismatch: missing={sorted(expected-set(actual))}, extra={sorted(set(actual)-expected)}")
    for relative, digest in actual.items():
        if module.sha256_file(root / relative) != digest:
            raise CheckError(f"manifest hash mismatch: {relative}")


def _validate_no_public_latest_diff(root: Path) -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "public/latest"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckError(f"cannot inspect public/latest diff: {result.stderr}")
    if result.stdout.strip():
        raise CheckError("v0.10.5 changes public/latest")


def validate_repository(root: Path) -> dict[str, str]:
    root = root.resolve()
    _validate_pyproject(root)
    _validate_workflow(root)
    _validate_manifest(root)
    module = _load_module(root)
    policy_path = root / "config" / "ecoicop_dual_panel_replay_v0105.json"
    policy = module.ReplayPolicy.load(policy_path)
    if policy.payload["status"] != STATUS:
        raise CheckError("policy status mismatch")
    if any(bool(value) for value in policy.gates.values()):
        raise CheckError("a v0.10.5 gate is open")
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != PREDECESSOR_STATUS:
        raise CheckError("predecessor status mismatch")
    with tempfile.TemporaryDirectory(prefix="armilar_v0105_check_") as tmp:
        out = Path(tmp) / "contract"
        summary = module.build_replay_contract_scaffold(policy_path, out, created_at="2026-07-09T00:00:00Z")
        replay = module.verify_replay_contract_scaffold(policy_path, out)
        if summary != replay:
            raise CheckError("replay verifier contract scaffold is not reproducible")
    if summary["receipt_count"] != 0 or summary["observation_count"] != 0:
        raise CheckError("v0.10.5 contract scaffold must not contain empirical rows")
    if summary["panel_verified_gate_open"] is not False:
        raise CheckError("v0.10.5 must not open the panel verification gate")
    _validate_no_public_latest_diff(root)
    return {
        "status": STATUS,
        "policy_sha256": policy.policy_sha256,
        "required_artifact_file_count": str(len(policy.required_files)),
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ARMILAR v0.10.5 ECOICOP dual-panel replay verifier")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = validate_repository(args.root)
    except CheckError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_REPLAY_V0105_INVALID: {exc}") from exc
    print(STATUS)
    print(f"policy_sha256={result['policy_sha256']}")
    print(f"required_artifact_file_count={result['required_artifact_file_count']}")
    print("contract_receipt_count=0")
    print("contract_observation_count=0")
    print("live_2026_observation_count=0")
    print("panel_verified_gate_open=false")
    print("transition_backtest_executed=false")
    print(f"predecessor_status={result['predecessor_status']}")
    print(f"predecessor_policy_sha256={result['predecessor_policy_sha256']}")
    print("next_milestone=V0106_MATERIALIZE_AND_VERIFY_EXTERNAL_DUAL_PANEL_BEFORE_BACKTEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
