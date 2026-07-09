from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID"
V0103_STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"


class CheckError(RuntimeError):
    pass


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _require_success(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = _run(command, cwd)
    if result.returncode != 0:
        raise CheckError(
            "required check failed: "
            + " ".join(command)
            + f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _load_module(root: Path):
    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_v0104.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_v0104", module_path)
    if spec is None or spec.loader is None:
        raise CheckError("cannot import v0.10.4 module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_manifest(root: Path) -> None:
    manifest_path = root / "config" / "ecoicop_dual_panel_v0104_files.sha256"
    if not manifest_path.is_file():
        raise CheckError("v0.10.4 manifest missing")
    expected = {
        "RELEASE_NOTES_V0.10.4.md",
        "config/ecoicop_dual_panel_v0104.json",
        "docs/DECISION_ECOICOP_DUAL_PANEL_V0104.md",
        "docs/ECOICOP_DUAL_PANEL_V0104_CONTRACT.md",
        "schemas/ecoicop_dual_panel_policy_v0104.schema.json",
        "schemas/ecoicop_dual_panel_summary_v0104.schema.json",
        "scripts/check_ecoicop_dual_panel_v0104.py",
        "src/armilar_backtest/ecoicop_dual_panel_v0104.py",
        "tests/test_ecoicop_dual_panel_v0104.py",
    }
    actual: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise CheckError(f"invalid manifest line {line_number}")
        digest, relative = parts
        if relative in actual:
            raise CheckError(f"duplicate manifest entry: {relative}")
        actual[relative] = digest
    if set(actual) != expected:
        raise CheckError(
            f"manifest file set mismatch: missing={sorted(expected-set(actual))}, extra={sorted(set(actual)-expected)}"
        )
    module = _load_module(root)
    for relative, digest in actual.items():
        path = root / relative
        if module.sha256_file(path) != digest:
            raise CheckError(f"manifest hash mismatch: {relative}")


def _validate_predecessor(root: Path) -> str:
    module_path = root / "src" / "armilar_backtest" / "ecoicop_v2_backtest_v0103.py"
    spec = importlib.util.spec_from_file_location("ecoicop_v2_backtest_v0103_for_v0104", module_path)
    if spec is None or spec.loader is None:
        raise CheckError("cannot import v0.10.3 predecessor module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if module.STATUS != V0103_STATUS:
        raise CheckError("v0.10.3 predecessor status mismatch")
    policy = root / "config" / "ecoicop_v2_backtest_protocol_v0103.json"
    mapping = root / "config" / "ecoicop_v1_v2_mapping_candidates_v0103.json"
    bundle = module.ProtocolBundle.load(policy, mapping)
    with tempfile.TemporaryDirectory(prefix="armilar_v0103_predecessor_") as tmp:
        out = Path(tmp) / "audit"
        summary = module.build_protocol_audit(
            policy_path=policy,
            mapping_path=mapping,
            output_dir=out,
            created_at="2026-07-09T00:00:00Z",
        )
        replay = module.verify_protocol_audit(
            policy_path=policy,
            mapping_path=mapping,
            audit_dir=out,
        )
    if summary["status"] != V0103_STATUS:
        raise CheckError("v0.10.3 predecessor summary status mismatch")
    if replay["status"] != V0103_STATUS:
        raise CheckError("v0.10.3 predecessor replay status mismatch")
    if summary.get("empirical_observation_count") != 0:
        raise CheckError("v0.10.3 predecessor must not contain empirical observations")
    return f"{V0103_STATUS} policy_sha256={bundle.policy_sha256} mapping_sha256={bundle.mapping_sha256}"


def _validate_pyproject(root: Path) -> None:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.10.4"' not in text:
        raise CheckError("pyproject.toml version is not 0.10.4")
    if 'armilar-ecoicop-dual-panel-v0104 = "armilar_backtest.ecoicop_dual_panel_v0104:main"' not in text:
        raise CheckError("v0.10.4 console script entry missing")


def validate_repository(root: Path) -> dict[str, str]:
    root = root.resolve()
    _validate_pyproject(root)
    _validate_manifest(root)
    predecessor_output = _validate_predecessor(root)
    module = _load_module(root)
    policy_path = root / "config" / "ecoicop_dual_panel_v0104.json"
    policy = module.DualPanelPolicy.load(policy_path)
    if policy.payload["status"] != STATUS:
        raise CheckError("policy status mismatch")
    if any(bool(value) for value in policy.gates.values()):
        raise CheckError("a v0.10.4 release, training or monetary gate is open")
    with tempfile.TemporaryDirectory(prefix="armilar_v0104_check_") as tmp:
        out = Path(tmp) / "scaffold"
        summary = module.build_dual_panel_scaffold(
            policy_path,
            out,
            created_at="2026-07-09T00:00:00Z",
        )
        replay = module.verify_dual_panel_scaffold(policy_path, out)
        if summary != replay:
            raise CheckError("dual-panel scaffold is not reproducible")
        if summary["committed_observation_count"] != 0:
            raise CheckError("v0.10.4 committed empirical observations")
        if summary["live_2026_observation_count"] != 0:
            raise CheckError("v0.10.4 committed live 2026 observations")
        if summary["request_count"] <= 0:
            raise CheckError("v0.10.4 request register is empty")
    for forbidden in ("transition_strategy_ratified", "arm_o_2026_extension_allowed=true", "monetary_use_allowed=true"):
        if forbidden in json.dumps(policy.payload, sort_keys=True):
            raise CheckError(f"forbidden token found in v0.10.4 policy: {forbidden}")
    return {
        "status": STATUS,
        "policy_sha256": policy.policy_sha256,
        "dataset_contract_count": str(len(policy.dataset_contracts)),
        "economy_count": str(len(policy.universe["economies"])),
        "legacy_category_count": str(len(policy.universe["legacy_categories"])),
        "replacement_division_count": str(len(policy.universe["replacement_divisions"])),
        "predecessor_status": V0103_STATUS,
        "predecessor_output": predecessor_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ARMILAR v0.10.4 ECOICOP dual-panel contract")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = validate_repository(args.root)
    except CheckError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_V0104_INVALID: {exc}") from exc
    print(STATUS)
    print(f"policy_sha256={result['policy_sha256']}")
    print(f"dataset_contract_count={result['dataset_contract_count']}")
    print(f"economy_count={result['economy_count']}")
    print(f"legacy_category_count={result['legacy_category_count']}")
    print(f"replacement_division_count={result['replacement_division_count']}")
    print("committed_observation_count=0")
    print("live_2026_observation_count=0")
    print("gate_count_open=0")
    print(f"predecessor_status={result['predecessor_status']}")
    print("predecessor_mode=VALIDATED_BY_V0103_CONTRACT_REPLAY")
    print("next_milestone=V0105_EXECUTE_TRANSITION_BACKTEST_AFTER_PANEL_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
