"""ECOICOP v1/v2 empirical transition backtest gatekeeper for ARMILAR v0.11.0.

This milestone defines the fail-closed boundary between the contractual execution
engine of v0.10.9 and any future real empirical transition backtest.  It does not
run a real empirical backtest inside the repository, does not attach official
provider bytes, does not select a transition strategy, and does not open any
research or monetary gate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_GATE_V0110_VALID"
PREFLIGHT_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_PREFLIGHT_REPORT_V0110_VALID"
VERSION = "0.11.0"
PREDECESSOR_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EXECUTION_ENGINE_V0109_VALID"
PREDECESSOR_RESULT_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_RESULT_FIXTURE_V0109_VALID"
NEXT_MILESTONE = "V0111_ACQUIRE_OR_ATTACH_REAL_EXTERNAL_DUAL_PANEL_FOR_EMPIRICAL_RUN"
DEFAULT_POLICY = Path("config/ecoicop_transition_backtest_empirical_v0110.json")
DEFAULT_PREDECESSOR_POLICY = Path("config/ecoicop_transition_backtest_execution_v0109.json")
PREFLIGHT_REPORT = "empirical_transition_backtest_preflight_report.json"
PREFLIGHT_MANIFEST = "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256"


class EmpiricalBacktestGateError(ValueError):
    """Raised when the v0.11.0 empirical-gate contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmpiricalBacktestGateError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EmpiricalBacktestGateError(f"JSON object required: {path}")
    return payload


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise EmpiricalBacktestGateError(f"required file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EmpiricalBacktestGateError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EmpiricalBacktestGateError(f"{label} must be a list")
    return value


def _load_module(root: Path, relative: str, name: str):
    module_path = root / relative
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise EmpiricalBacktestGateError(f"cannot import module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise EmpiricalBacktestGateError(f"{label} must be a safe relative path: {value}")
    return relative


def _write_manifest(path: Path, manifest_name: str) -> None:
    lines: list[str] = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix()
        if relative == manifest_name:
            continue
        lines.append(f"{sha256_file(candidate)}  {relative}")
    (path / manifest_name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise EmpiricalBacktestGateError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise EmpiricalBacktestGateError(f"invalid manifest line {line_number}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise EmpiricalBacktestGateError(f"duplicate manifest entry: {relative}")
        candidate = path / relative
        if not candidate.is_file():
            raise EmpiricalBacktestGateError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != digest:
            raise EmpiricalBacktestGateError(f"manifest hash mismatch: {relative}")
        entries[relative] = digest
    return entries


@dataclass(frozen=True)
class EmpiricalBacktestGatePolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "EmpiricalBacktestGatePolicy":
        policy_path = Path(path).resolve()
        payload = _read_json(policy_path)
        validate_policy_document(payload)
        return cls(path=policy_path, payload=payload)

    @property
    def policy_sha256(self) -> str:
        return sha256_file(self.path)

    @property
    def gates(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["gates"], "gates")

    @property
    def empirical_gate_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["empirical_gate_contract"], "empirical gate contract")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {"policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy", "scope", "empirical_gate_contract", "gates", "next_milestone"}
    missing = required - set(policy)
    if missing:
        raise EmpiricalBacktestGateError(f"empirical gate policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise EmpiricalBacktestGateError("policy version mismatch")
    if policy["status"] != STATUS:
        raise EmpiricalBacktestGateError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise EmpiricalBacktestGateError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise EmpiricalBacktestGateError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    required_true = {
        "define_empirical_backtest_gatekeeper",
        "require_v0109_execution_engine",
        "require_external_verified_panel_before_real_run",
        "require_external_result_artifact_before_claim",
        "generate_fixture_preflight_only",
    }
    for key in required_true:
        if scope.get(key) is not True:
            raise EmpiricalBacktestGateError(f"required v0.11.0 scope not enabled: {key}")
    forbidden = [key for key, value in scope.items() if key not in required_true and bool(value)]
    if forbidden:
        raise EmpiricalBacktestGateError(f"forbidden v0.11.0 scope enabled: {forbidden}")

    contract = _require_dict(policy["empirical_gate_contract"], "empirical gate contract")
    if contract.get("required_predecessor_status") != PREDECESSOR_STATUS:
        raise EmpiricalBacktestGateError("required predecessor status mismatch")
    if contract.get("required_predecessor_fixture_result_status") != PREDECESSOR_RESULT_STATUS:
        raise EmpiricalBacktestGateError("required predecessor fixture status mismatch")
    if tuple(contract.get("required_strategy_ids", ())) != ("T0", "T1", "T2", "T3"):
        raise EmpiricalBacktestGateError("required strategy ids mismatch")
    if int(contract.get("minimum_metric_count", 0)) < 14:
        raise EmpiricalBacktestGateError("minimum metric count too low")
    if int(contract.get("minimum_metric_rows", 0)) < 56:
        raise EmpiricalBacktestGateError("minimum metric rows too low")
    if contract.get("preflight_report_file") != PREFLIGHT_REPORT:
        raise EmpiricalBacktestGateError("preflight report file mismatch")
    if contract.get("preflight_manifest_file") != PREFLIGHT_MANIFEST:
        raise EmpiricalBacktestGateError("preflight manifest file mismatch")
    required_inputs = tuple(contract.get("required_external_inputs", ()))
    if len(required_inputs) < 4 or len(set(required_inputs)) != len(required_inputs):
        raise EmpiricalBacktestGateError("required external inputs must be complete and unique")
    for key in (
        "external_verified_panel_available_must_equal",
        "external_result_artifact_available_must_equal",
        "empirical_transition_backtest_executed_must_equal",
        "backtest_execution_claim_allowed_must_equal",
        "result_interpretation_allowed_must_equal",
        "panel_verified_gate_open_must_equal",
        "public_latest_modified_must_equal",
        "official_bytes_committed_to_repository_must_equal",
    ):
        if contract.get(key) is not False:
            raise EmpiricalBacktestGateError(f"{key} must remain false")
    if contract.get("selected_strategy_must_equal") != "NONE":
        raise EmpiricalBacktestGateError("selected strategy must remain NONE")
    if contract.get("blocking_reason_must_equal") != "EXTERNAL_VERIFIED_PANEL_AND_EMPIRICAL_RESULT_NOT_ATTACHED":
        raise EmpiricalBacktestGateError("blocking reason mismatch")
    fields = tuple(str(item) for item in _require_list(contract["required_report_fields"], "required report fields"))
    if len(fields) != len(set(fields)):
        raise EmpiricalBacktestGateError("duplicate required report fields")
    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise EmpiricalBacktestGateError(f"v0.11.0 gates must remain closed: {open_gates}")


def validate_predecessor(root: Path) -> dict[str, Any]:
    module = _load_module(root, "src/armilar_backtest/ecoicop_transition_backtest_execution_v0109.py", "ecoicop_transition_backtest_execution_v0109_for_v0110")
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise EmpiricalBacktestGateError("v0.10.9 predecessor status mismatch")
    policy = module.TransitionBacktestExecutionPolicy.load(root / DEFAULT_PREDECESSOR_POLICY)
    protocol = module.load_protocol_summary(root / module.DEFAULT_PROTOCOL_POLICY)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="armilar-v0110-predecessor-") as temp:
        temp_path = Path(temp)
        readiness = module._build_fixture_readiness(root, temp_path)
        result = module.create_transition_backtest_result(
            root / DEFAULT_PREDECESSOR_POLICY,
            readiness,
            temp_path / "result",
            repo_root=root,
            repository_commit="fixture-v0110-predecessor",
            created_at="2026-07-10T00:00:00Z",
        )
    if result["execution_status"] != PREDECESSOR_RESULT_STATUS:
        raise EmpiricalBacktestGateError("v0.10.9 fixture result status mismatch")
    if result["empirical_transition_backtest_executed"] is not False:
        raise EmpiricalBacktestGateError("v0.10.9 predecessor claimed empirical execution")
    if result["selected_strategy"] != "NONE":
        raise EmpiricalBacktestGateError("v0.10.9 predecessor selected a strategy")
    return {
        "status": PREDECESSOR_STATUS,
        "policy_sha256": policy.policy_sha256,
        "fixture_status": result["execution_status"],
        "strategy_ids": protocol["strategy_ids"],
        "metric_count": protocol["metric_count"],
        "metric_row_count": result["metric_row_count"],
    }


def create_empirical_preflight_report(
    policy_path: Path,
    output_dir: Path,
    *,
    repo_root: Path,
    repository_commit: str,
    created_at: str,
) -> dict[str, Any]:
    policy = EmpiricalBacktestGatePolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmpiricalBacktestGateError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    predecessor = validate_predecessor(repo_root)
    contract = policy.empirical_gate_contract
    report = {
        "preflight_status": PREFLIGHT_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "repository_commit": repository_commit,
        "policy_sha256": policy.policy_sha256,
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
        "predecessor_fixture_status": predecessor["fixture_status"],
        "strategy_ids": predecessor["strategy_ids"],
        "metric_count": predecessor["metric_count"],
        "metric_row_count": predecessor["metric_row_count"],
        "required_external_inputs": contract["required_external_inputs"],
        "external_verified_panel_available": False,
        "external_result_artifact_available": False,
        "empirical_transition_backtest_executed": False,
        "backtest_execution_claim_allowed": False,
        "selected_strategy": "NONE",
        "result_interpretation_allowed": False,
        "panel_verified_gate_open": False,
        "public_latest_modified": False,
        "official_bytes_committed_to_repository": False,
        "blocking_reason": "EXTERNAL_VERIFIED_PANEL_AND_EMPIRICAL_RESULT_NOT_ATTACHED",
        "next_milestone": NEXT_MILESTONE,
    }
    missing = [field for field in contract["required_report_fields"] if field not in report]
    if missing:
        raise EmpiricalBacktestGateError(f"preflight report missing fields: {missing}")
    (output_dir / PREFLIGHT_REPORT).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, PREFLIGHT_MANIFEST)
    validate_empirical_preflight_report(policy_path, output_dir)
    return report


def validate_empirical_preflight_report(policy_path: Path, output_dir: Path) -> dict[str, Any]:
    policy = EmpiricalBacktestGatePolicy.load(policy_path)
    verify_manifest(output_dir, PREFLIGHT_MANIFEST)
    report = _read_json(output_dir / PREFLIGHT_REPORT)
    contract = policy.empirical_gate_contract
    for field in contract["required_report_fields"]:
        if field not in report:
            raise EmpiricalBacktestGateError(f"preflight report missing field: {field}")
    if report["preflight_status"] != PREFLIGHT_STATUS:
        raise EmpiricalBacktestGateError("preflight status mismatch")
    if report["policy_version"] != VERSION:
        raise EmpiricalBacktestGateError("preflight version mismatch")
    if report["predecessor_status"] != PREDECESSOR_STATUS:
        raise EmpiricalBacktestGateError("preflight predecessor status mismatch")
    if report["predecessor_fixture_status"] != PREDECESSOR_RESULT_STATUS:
        raise EmpiricalBacktestGateError("preflight predecessor fixture status mismatch")
    if tuple(report["strategy_ids"]) != tuple(contract["required_strategy_ids"]):
        raise EmpiricalBacktestGateError("preflight strategy ids mismatch")
    if int(report["metric_count"]) < int(contract["minimum_metric_count"]):
        raise EmpiricalBacktestGateError("preflight metric count too low")
    if int(report["metric_row_count"]) < int(contract["minimum_metric_rows"]):
        raise EmpiricalBacktestGateError("preflight metric row count too low")
    for field, expected in (
        ("external_verified_panel_available", False),
        ("external_result_artifact_available", False),
        ("empirical_transition_backtest_executed", False),
        ("backtest_execution_claim_allowed", False),
        ("result_interpretation_allowed", False),
        ("panel_verified_gate_open", False),
        ("public_latest_modified", False),
        ("official_bytes_committed_to_repository", False),
    ):
        if report[field] is not expected:
            raise EmpiricalBacktestGateError(f"preflight field must remain false: {field}")
    if report["selected_strategy"] != "NONE":
        raise EmpiricalBacktestGateError("preflight selected a strategy")
    if report["blocking_reason"] != contract["blocking_reason_must_equal"]:
        raise EmpiricalBacktestGateError("preflight blocking reason mismatch")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.11.0 ECOICOP empirical transition backtest gatekeeper")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-preflight", type=Path)
    parser.add_argument("--repository-commit", default="UNCOMMITTED_PREFLIGHT")
    parser.add_argument("--created-at", default="2026-07-10T00:00:00Z")
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    try:
        if args.verify_preflight:
            summary = validate_empirical_preflight_report(policy_path, args.verify_preflight)
        elif args.output_dir:
            summary = create_empirical_preflight_report(
                policy_path,
                args.output_dir,
                repo_root=root,
                repository_commit=args.repository_commit,
                created_at=args.created_at,
            )
        elif args.fixture:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="armilar-v0110-") as temp:
                summary = create_empirical_preflight_report(
                    policy_path,
                    Path(temp) / "preflight",
                    repo_root=root,
                    repository_commit="fixture-v0110",
                    created_at=args.created_at,
                )
        else:
            policy = EmpiricalBacktestGatePolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            summary = {
                "preflight_status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "predecessor_status": predecessor["status"],
                "predecessor_fixture_status": predecessor["fixture_status"],
                "metric_count": predecessor["metric_count"],
                "metric_row_count": predecessor["metric_row_count"],
                "empirical_transition_backtest_executed": False,
                "backtest_execution_claim_allowed": False,
                "selected_strategy": "NONE",
                "panel_verified_gate_open": False,
                "next_milestone": NEXT_MILESTONE,
            }
    except EmpiricalBacktestGateError as exc:
        raise SystemExit(f"ECOICOP_TRANSITION_BACKTEST_EMPIRICAL_V0110_INVALID: {exc}") from exc
    print(summary["preflight_status"])
    for key in sorted(key for key in summary if key != "preflight_status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
