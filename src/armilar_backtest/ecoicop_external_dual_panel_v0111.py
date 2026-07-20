"""External ECOICOP v1/v2 dual-panel intake runner for ARMILAR v0.11.1.

This milestone is the first boundary that can consume a real external dual-panel
artifact.  The artifact and provider bytes remain outside the repository.  The
runner verifies a v0.10.7 attachment descriptor and the materialized artifact it
points to, then writes a deterministic intake report that a later empirical run
can consume.  It does not run or claim the empirical transition backtest, does
not select a transition strategy, and opens no research or monetary gate.
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

STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EXTERNAL_PANEL_INTAKE_V0111_VALID"
INTAKE_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EXTERNAL_PANEL_INTAKE_REPORT_V0111_VALID"
VERSION = "0.11.1"
PREDECESSOR_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_GATE_V0110_VALID"
ATTACHMENT_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_ATTACHMENT_V0107_VALID"
ARTIFACT_REPLAY_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
NEXT_MILESTONE = "V0112_RUN_SEPARATE_EMPIRICAL_BACKTEST_WITH_ATTACHED_EXTERNAL_PANEL"
DEFAULT_POLICY = Path("config/ecoicop_external_dual_panel_v0111.json")
DEFAULT_PREDECESSOR_POLICY = Path("config/ecoicop_transition_backtest_empirical_v0110.json")
INTAKE_REPORT = "external_dual_panel_intake_report.json"
INTAKE_MANIFEST = "EXTERNAL_DUAL_PANEL_INTAKE_MANIFEST.sha256"


class ExternalDualPanelIntakeError(ValueError):
    """Raised when the v0.11.1 external-panel intake contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalDualPanelIntakeError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ExternalDualPanelIntakeError(f"JSON object required: {path}")
    return payload


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ExternalDualPanelIntakeError(f"required file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExternalDualPanelIntakeError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExternalDualPanelIntakeError(f"{label} must be a list")
    return value


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise ExternalDualPanelIntakeError(f"{label} must be a safe relative path: {value}")
    return relative


def _write_manifest(path: Path, manifest_name: str) -> None:
    rows: list[str] = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix()
        if relative == manifest_name:
            continue
        rows.append(f"{sha256_file(candidate)}  {relative}")
    (path / manifest_name).write_text("\n".join(rows) + "\n", encoding="utf-8")


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise ExternalDualPanelIntakeError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise ExternalDualPanelIntakeError(f"invalid manifest line {line_number}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise ExternalDualPanelIntakeError(f"duplicate manifest entry: {relative}")
        candidate = path / relative
        if not candidate.is_file():
            raise ExternalDualPanelIntakeError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != digest:
            raise ExternalDualPanelIntakeError(f"manifest hash mismatch: {relative}")
        entries[relative] = digest
    return entries


def _load_module(root: Path, relative: str, name: str):
    module_path = root / relative
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise ExternalDualPanelIntakeError(f"cannot import module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class ExternalDualPanelIntakePolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "ExternalDualPanelIntakePolicy":
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
    def intake_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["external_panel_intake_contract"], "external panel intake contract")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {"policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy", "scope", "external_panel_intake_contract", "gates", "next_milestone"}
    missing = required - set(policy)
    if missing:
        raise ExternalDualPanelIntakeError(f"policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise ExternalDualPanelIntakeError("policy version mismatch")
    if policy["status"] != STATUS:
        raise ExternalDualPanelIntakeError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise ExternalDualPanelIntakeError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise ExternalDualPanelIntakeError("next milestone mismatch")
    scope = _require_dict(policy["scope"], "scope")
    required_true = {"define_external_panel_intake_runner", "require_v0110_empirical_gatekeeper", "require_external_attachment_descriptor", "require_materialized_panel_artifact", "verify_attachment_with_v0107", "verify_artifact_with_v0107_and_v0105", "generate_non_committed_intake_report"}
    for key in required_true:
        if scope.get(key) is not True:
            raise ExternalDualPanelIntakeError(f"required v0.11.1 scope not enabled: {key}")
    forbidden = [key for key, value in scope.items() if key not in required_true and bool(value)]
    if forbidden:
        raise ExternalDualPanelIntakeError(f"forbidden v0.11.1 scope enabled: {forbidden}")
    contract = _require_dict(policy["external_panel_intake_contract"], "external panel intake contract")
    if contract.get("intake_report_file") != INTAKE_REPORT:
        raise ExternalDualPanelIntakeError("intake report name mismatch")
    if contract.get("intake_manifest_file") != INTAKE_MANIFEST:
        raise ExternalDualPanelIntakeError("intake manifest name mismatch")
    if contract.get("required_intake_status") != INTAKE_STATUS:
        raise ExternalDualPanelIntakeError("intake status mismatch")
    if contract.get("required_predecessor_status") != PREDECESSOR_STATUS:
        raise ExternalDualPanelIntakeError("required predecessor status mismatch")
    if contract.get("required_attachment_status") != ATTACHMENT_STATUS:
        raise ExternalDualPanelIntakeError("required attachment status mismatch")
    if contract.get("required_artifact_replay_status") != ARTIFACT_REPLAY_STATUS:
        raise ExternalDualPanelIntakeError("required artifact replay status mismatch")
    if contract.get("external_verified_panel_available_must_equal") is not True:
        raise ExternalDualPanelIntakeError("v0.11.1 intake must require an external verified panel")
    if contract.get("empirical_transition_backtest_executed_must_equal") is not False:
        raise ExternalDualPanelIntakeError("v0.11.1 must not execute empirical backtest")
    if contract.get("backtest_execution_claim_allowed_must_equal") is not False:
        raise ExternalDualPanelIntakeError("v0.11.1 must not claim backtest execution")
    if contract.get("selected_strategy_must_equal") != "NONE":
        raise ExternalDualPanelIntakeError("v0.11.1 must not select a strategy")
    fields = tuple(str(item) for item in _require_list(contract["required_report_fields"], "required report fields"))
    if len(fields) != len(set(fields)):
        raise ExternalDualPanelIntakeError("duplicate required report field")
    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise ExternalDualPanelIntakeError(f"v0.11.1 gates must remain closed: {open_gates}")


def validate_predecessor(root: Path) -> dict[str, Any]:
    module = _load_module(root, "src/armilar_backtest/ecoicop_transition_backtest_empirical_v0110.py", "ecoicop_transition_backtest_empirical_v0110_for_v0111")
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise ExternalDualPanelIntakeError("v0.11.0 predecessor status mismatch")
    policy = module.EmpiricalBacktestGatePolicy.load(root / DEFAULT_PREDECESSOR_POLICY)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="armilar-v0111-predecessor-") as temp:
        report = module.create_empirical_preflight_report(root / DEFAULT_PREDECESSOR_POLICY, Path(temp) / "preflight", repo_root=root, repository_commit="fixture-v0111-predecessor", created_at="2026-07-10T00:00:00Z")
    if report["preflight_status"] != "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_PREFLIGHT_REPORT_V0110_VALID":
        raise ExternalDualPanelIntakeError("v0.11.0 predecessor preflight status mismatch")
    if report["empirical_transition_backtest_executed"] is not False:
        raise ExternalDualPanelIntakeError("v0.11.0 predecessor claimed empirical execution")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": policy.policy_sha256, "fixture_status": report["preflight_status"], "strategy_ids": report["strategy_ids"], "metric_count": report["metric_count"], "metric_row_count": report["metric_row_count"]}


def _load_attachment_module(root: Path):
    return _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_for_v0111")


def validate_external_panel_inputs(policy_path: Path, attachment_dir: Path, artifact_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    policy = ExternalDualPanelIntakePolicy.load(policy_path)
    attachment_module = _load_attachment_module(repo_root)
    try:
        attachment = attachment_module.validate_attachment_directory(repo_root / "config" / "ecoicop_dual_panel_attachment_v0107.json", attachment_dir)
        artifact = attachment_module.validate_materialized_artifact(repo_root / "config" / "ecoicop_dual_panel_attachment_v0107.json", artifact_dir, repo_root=repo_root)
    except Exception as exc:  # normalize predecessor-module errors into the v0.11.1 contract
        raise ExternalDualPanelIntakeError(str(exc)) from exc
    contract = policy.intake_contract
    if attachment["attachment_status"] != contract["required_attachment_status"]:
        raise ExternalDualPanelIntakeError("attachment status mismatch")
    if artifact["artifact_replay_status"] != contract["required_artifact_replay_status"]:
        raise ExternalDualPanelIntakeError("artifact replay status mismatch")
    if bool(attachment["official_bytes_committed_to_repository"]):
        raise ExternalDualPanelIntakeError("attachment claims official bytes were committed")
    if bool(attachment["public_latest_modified"]):
        raise ExternalDualPanelIntakeError("attachment claims public/latest was modified")
    if bool(attachment["transition_backtest_executed"]):
        raise ExternalDualPanelIntakeError("attachment claims transition backtest execution")
    if attachment["selected_strategy"] != "NONE":
        raise ExternalDualPanelIntakeError("attachment selected a strategy")
    return {**attachment, **artifact}


def create_external_panel_intake_report(policy_path: Path, attachment_dir: Path, artifact_dir: Path, output_dir: Path, *, repo_root: Path, repository_commit: str, created_at: str) -> dict[str, Any]:
    policy = ExternalDualPanelIntakePolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ExternalDualPanelIntakeError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    predecessor = validate_predecessor(repo_root)
    external = validate_external_panel_inputs(policy_path, attachment_dir, artifact_dir, repo_root=repo_root)
    report = {
        "intake_status": INTAKE_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "repository_commit": repository_commit,
        "policy_sha256": policy.policy_sha256,
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
        "attachment_status": external["attachment_status"],
        "attachment_manifest_sha256": external["attachment_manifest_sha256"],
        "artifact_replay_status": external["artifact_replay_status"],
        "artifact_manifest_sha256": external["artifact_manifest_sha256"],
        "artifact_summary_sha256": external["artifact_summary_sha256"],
        "receipt_count": int(external.get("receipt_count", 0)),
        "observation_count": int(external.get("observation_count", 0)),
        "coverage_row_count": int(external.get("coverage_row_count", 0)),
        "lineage_row_count": int(external.get("lineage_row_count", 0)),
        "strategy_ids": predecessor["strategy_ids"],
        "metric_count": predecessor["metric_count"],
        "metric_row_count": predecessor["metric_row_count"],
        "external_verified_panel_available": True,
        "external_result_artifact_available": False,
        "empirical_transition_backtest_executed": False,
        "backtest_execution_claim_allowed": False,
        "selected_strategy": "NONE",
        "result_interpretation_allowed": False,
        "panel_verified_gate_open": False,
        "public_latest_modified": False,
        "official_bytes_committed_to_repository": False,
        "blocking_reason": "EXTERNAL_PANEL_ATTACHED_READY_FOR_SEPARATE_EMPIRICAL_RUN",
        "next_milestone": NEXT_MILESTONE,
    }
    for field in policy.intake_contract["required_report_fields"]:
        if field not in report:
            raise ExternalDualPanelIntakeError(f"intake report missing field: {field}")
    (output_dir / INTAKE_REPORT).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, INTAKE_MANIFEST)
    validate_external_panel_intake_report(policy_path, output_dir)
    return report


def validate_external_panel_intake_report(policy_path: Path, intake_dir: Path) -> dict[str, Any]:
    policy = ExternalDualPanelIntakePolicy.load(policy_path)
    verify_manifest(intake_dir, INTAKE_MANIFEST)
    report = _read_json(intake_dir / INTAKE_REPORT)
    contract = policy.intake_contract
    for field in contract["required_report_fields"]:
        if field not in report:
            raise ExternalDualPanelIntakeError(f"intake report missing field: {field}")
    if report["intake_status"] != INTAKE_STATUS:
        raise ExternalDualPanelIntakeError("intake status mismatch")
    checks = {
        "external_verified_panel_available": True,
        "empirical_transition_backtest_executed": False,
        "backtest_execution_claim_allowed": False,
        "result_interpretation_allowed": False,
        "panel_verified_gate_open": False,
        "public_latest_modified": False,
        "official_bytes_committed_to_repository": False,
    }
    for key, expected in checks.items():
        if report.get(key) is not expected:
            raise ExternalDualPanelIntakeError(f"{key} must be {expected}")
    if report["selected_strategy"] != "NONE":
        raise ExternalDualPanelIntakeError("intake report selected a strategy")
    if report["blocking_reason"] != contract["blocking_reason_must_equal"]:
        raise ExternalDualPanelIntakeError("blocking reason mismatch")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.11.1 ECOICOP external dual-panel intake runner")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--attachment-dir", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-intake", type=Path)
    parser.add_argument("--repository-commit", default="UNCOMMITTED_EXTERNAL_PANEL_INTAKE")
    parser.add_argument("--created-at", default="2026-07-10T00:00:00Z")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    try:
        if args.verify_intake:
            summary = validate_external_panel_intake_report(policy_path, args.verify_intake)
        elif args.attachment_dir or args.artifact_dir:
            if not (args.attachment_dir and args.artifact_dir and args.output_dir):
                raise ExternalDualPanelIntakeError("--attachment-dir, --artifact-dir and --output-dir are required together")
            summary = create_external_panel_intake_report(policy_path, args.attachment_dir, args.artifact_dir, args.output_dir, repo_root=root, repository_commit=args.repository_commit, created_at=args.created_at)
        else:
            policy = ExternalDualPanelIntakePolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            summary = {"intake_status": STATUS, "policy_version": VERSION, "policy_sha256": policy.policy_sha256, "predecessor_status": predecessor["status"], "predecessor_policy_sha256": predecessor["policy_sha256"], "gate_count_open": sum(bool(value) for value in policy.gates.values()), "next_milestone": NEXT_MILESTONE}
    except ExternalDualPanelIntakeError as exc:
        raise SystemExit(f"ECOICOP_EXTERNAL_DUAL_PANEL_V0111_INVALID: {exc}") from exc
    print(summary["intake_status"])
    for key in sorted(key for key in summary if key != "intake_status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
