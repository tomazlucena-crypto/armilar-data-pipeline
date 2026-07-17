"""ECOICOP v1/v2 transition backtest execution engine for ARMILAR v0.10.9.

This milestone defines the deterministic result-artifact contract for transition
backtest execution.  It deliberately runs only a fixture execution in the PR:
no live provider bytes are acquired, no official bytes are committed, no
``public/latest`` outputs are modified, no empirical backtest is claimed, and no
transition strategy is selected.  A later milestone may run the same engine on a
real external verified panel and then decide whether any execution gate can be
opened.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_EXECUTION_ENGINE_V0109_VALID"
RESULT_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_RESULT_FIXTURE_V0109_VALID"
VERSION = "0.10.9"
PREDECESSOR_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_RUNNER_V0108_VALID"
READINESS_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_READINESS_REPORT_V0108_VALID"
PROTOCOL_STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
NEXT_MILESTONE = "V0110_RUN_REAL_EMPIRICAL_TRANSITION_BACKTEST_ON_EXTERNAL_VERIFIED_PANEL"
DEFAULT_POLICY = Path("config/ecoicop_transition_backtest_execution_v0109.json")
DEFAULT_PREDECESSOR_POLICY = Path("config/ecoicop_transition_backtest_runner_v0108.json")
DEFAULT_PROTOCOL_POLICY = Path("config/ecoicop_v2_backtest_protocol_v0103.json")
RESULT_REPORT = "transition_backtest_result_report.json"
RESULT_METRICS = "transition_backtest_metrics.csv"
RESULT_MANIFEST = "TRANSITION_BACKTEST_RESULT_MANIFEST.sha256"


class TransitionBacktestExecutionError(ValueError):
    """Raised when the v0.10.9 execution contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransitionBacktestExecutionError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TransitionBacktestExecutionError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise TransitionBacktestExecutionError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise TransitionBacktestExecutionError(f"{label} must be a safe relative path: {value}")
    return relative


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TransitionBacktestExecutionError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TransitionBacktestExecutionError(f"{label} must be a list")
    return value


def _load_module(root: Path, relative: str, name: str):
    module_path = root / relative
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise TransitionBacktestExecutionError(f"cannot import module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_entries(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise TransitionBacktestExecutionError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise TransitionBacktestExecutionError(f"invalid manifest line {line_number} in {manifest_name}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise TransitionBacktestExecutionError(f"duplicate manifest entry: {relative}")
        entries[relative] = digest
    return entries


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    entries = _manifest_entries(path, manifest_name)
    for relative, expected in entries.items():
        candidate = path / relative
        if not candidate.is_file():
            raise TransitionBacktestExecutionError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != expected:
            raise TransitionBacktestExecutionError(f"manifest hash mismatch: {relative}")
    return entries


def _write_manifest(path: Path, manifest_name: str) -> None:
    lines: list[str] = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix()
        if relative == manifest_name:
            continue
        lines.append(f"{sha256_file(candidate)}  {relative}")
    (path / manifest_name).write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class TransitionBacktestExecutionPolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "TransitionBacktestExecutionPolicy":
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
    def execution_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["execution_contract"], "execution contract")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {
        "policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy",
        "protocol_policy", "scope", "execution_contract", "gates", "next_milestone",
    }
    missing = required - set(policy)
    if missing:
        raise TransitionBacktestExecutionError(f"execution policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise TransitionBacktestExecutionError("policy version mismatch")
    if policy["status"] != STATUS:
        raise TransitionBacktestExecutionError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise TransitionBacktestExecutionError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise TransitionBacktestExecutionError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    required_true = {
        "define_transition_backtest_execution_engine",
        "require_v0108_readiness_report",
        "require_declared_strategy_metric_matrix",
        "generate_fixture_result_only",
        "validate_result_artifact_contract",
    }
    for key in required_true:
        if scope.get(key) is not True:
            raise TransitionBacktestExecutionError(f"required v0.10.9 scope not enabled: {key}")
    forbidden = [key for key, value in scope.items() if key not in required_true and bool(value)]
    if forbidden:
        raise TransitionBacktestExecutionError(f"forbidden v0.10.9 scope enabled: {forbidden}")

    contract = _require_dict(policy["execution_contract"], "execution contract")
    if contract.get("required_predecessor_status") != PREDECESSOR_STATUS:
        raise TransitionBacktestExecutionError("execution predecessor status mismatch")
    if contract.get("required_readiness_status") != READINESS_STATUS:
        raise TransitionBacktestExecutionError("readiness status mismatch")
    if contract.get("required_protocol_status") != PROTOCOL_STATUS:
        raise TransitionBacktestExecutionError("protocol status mismatch")
    if tuple(contract.get("required_strategy_ids", ())) != ("T0", "T1", "T2", "T3"):
        raise TransitionBacktestExecutionError("required strategy ids mismatch")
    if int(contract.get("minimum_metric_count", 0)) < 14:
        raise TransitionBacktestExecutionError("minimum metric count too low")
    if int(contract.get("minimum_metric_rows", 0)) < 56:
        raise TransitionBacktestExecutionError("minimum metric row count too low")
    if contract.get("result_report_file") != RESULT_REPORT:
        raise TransitionBacktestExecutionError("result report file mismatch")
    if contract.get("result_metrics_file") != RESULT_METRICS:
        raise TransitionBacktestExecutionError("result metrics file mismatch")
    if contract.get("result_manifest_file") != RESULT_MANIFEST:
        raise TransitionBacktestExecutionError("result manifest file mismatch")
    if contract.get("empirical_transition_backtest_executed_must_equal") is not False:
        raise TransitionBacktestExecutionError("v0.10.9 fixture must not claim empirical backtest execution")
    if contract.get("backtest_execution_claim_allowed_must_equal") is not False:
        raise TransitionBacktestExecutionError("backtest execution claim gate must remain closed")
    if contract.get("selected_strategy_must_equal") != "NONE":
        raise TransitionBacktestExecutionError("v0.10.9 must not select a transition strategy")
    if contract.get("result_interpretation_allowed_must_equal") is not False:
        raise TransitionBacktestExecutionError("fixture result interpretation must remain disallowed")
    if contract.get("public_latest_modified_must_equal") is not False:
        raise TransitionBacktestExecutionError("v0.10.9 must not modify public/latest")
    if contract.get("official_bytes_committed_to_repository_must_equal") is not False:
        raise TransitionBacktestExecutionError("v0.10.9 must not commit official bytes")
    fields = tuple(str(item) for item in _require_list(contract["required_report_fields"], "required report fields"))
    if len(fields) != len(set(fields)):
        raise TransitionBacktestExecutionError("duplicate required report field")

    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise TransitionBacktestExecutionError(f"v0.10.9 gates must remain closed: {open_gates}")


def validate_predecessor(root: Path) -> dict[str, str]:
    module = _load_module(root, "src/armilar_backtest/ecoicop_transition_backtest_v0108.py", "ecoicop_transition_backtest_v0108_for_v0109")
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise TransitionBacktestExecutionError("v0.10.8 predecessor status mismatch")
    policy = module.TransitionBacktestPolicy.load(root / DEFAULT_PREDECESSOR_POLICY)
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ATTACHMENT_PROTOCOL_V0107_VALID":
        raise TransitionBacktestExecutionError("v0.10.8 predecessor chain did not validate v0.10.7")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": policy.policy_sha256}


def load_protocol_summary(protocol_path: Path) -> dict[str, Any]:
    protocol = _read_json(protocol_path)
    if protocol.get("status") != PROTOCOL_STATUS:
        raise TransitionBacktestExecutionError("v0.10.3 backtest protocol status mismatch")
    strategies = _require_list(protocol.get("strategies"), "candidate strategies")
    metrics = _require_list(protocol.get("metrics"), "required backtest metrics")
    strategy_ids = tuple(str(item.get("strategy_id")) for item in strategies if isinstance(item, dict))
    metric_ids = tuple(str(item.get("metric_id")) for item in metrics if isinstance(item, dict))
    if strategy_ids != ("T0", "T1", "T2", "T3"):
        raise TransitionBacktestExecutionError("v0.10.3 strategy ids mismatch")
    if len(metric_ids) < 14:
        raise TransitionBacktestExecutionError("v0.10.3 metric count below declared floor")
    if any(bool(item.get("automatic_selection_allowed")) for item in strategies if isinstance(item, dict)):
        raise TransitionBacktestExecutionError("automatic strategy selection is forbidden")
    return {
        "protocol_status": PROTOCOL_STATUS,
        "protocol_sha256": sha256_file(protocol_path),
        "strategy_ids": list(strategy_ids),
        "metric_ids": list(metric_ids),
        "metric_count": len(metric_ids),
    }


def validate_readiness_for_execution(policy_path: Path, readiness_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    policy = TransitionBacktestExecutionPolicy.load(policy_path)
    readiness_module = _load_module(repo_root, "src/armilar_backtest/ecoicop_transition_backtest_v0108.py", "ecoicop_transition_backtest_v0108_readiness_for_v0109")
    summary = readiness_module.validate_readiness_report(repo_root / DEFAULT_PREDECESSOR_POLICY, readiness_dir)
    contract = policy.execution_contract
    if summary["runner_status"] != contract["required_readiness_status"]:
        raise TransitionBacktestExecutionError("readiness status does not satisfy execution contract")
    if summary["transition_backtest_executed"] is not False:
        raise TransitionBacktestExecutionError("readiness report already claims empirical backtest execution")
    if summary["backtest_execution_claim_allowed"] is not False:
        raise TransitionBacktestExecutionError("readiness report opens backtest execution claim gate")
    if summary["selected_strategy"] != "NONE":
        raise TransitionBacktestExecutionError("readiness report selected a transition strategy")
    if summary["panel_verified_gate_open"] is not False:
        raise TransitionBacktestExecutionError("readiness report opens verified-panel gate")
    return dict(summary)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _deterministic_metric_value(strategy_id: str, metric_id: str) -> str:
    digest = int(_sha256_bytes(f"{strategy_id}:{metric_id}:v0109".encode("utf-8"))[:8], 16)
    return f"{(digest % 100000) / 10000:.4f}"


def create_transition_backtest_result(
    policy_path: Path,
    readiness_dir: Path,
    output_dir: Path,
    *,
    repo_root: Path,
    repository_commit: str,
    created_at: str,
) -> dict[str, Any]:
    policy = TransitionBacktestExecutionPolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise TransitionBacktestExecutionError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    predecessor = validate_predecessor(repo_root)
    readiness = validate_readiness_for_execution(policy_path, readiness_dir, repo_root=repo_root)
    protocol = load_protocol_summary(repo_root / DEFAULT_PROTOCOL_POLICY)
    contract = policy.execution_contract
    rows: list[dict[str, Any]] = []
    for strategy_index, strategy_id in enumerate(protocol["strategy_ids"], start=1):
        for metric_index, metric_id in enumerate(protocol["metric_ids"], start=1):
            rows.append({
                "result_row_id": f"R{strategy_index:02d}_{metric_index:03d}",
                "strategy_id": strategy_id,
                "metric_id": metric_id,
                "metric_scope": "FIXTURE_CONTRACT_ONLY",
                "metric_value": _deterministic_metric_value(strategy_id, metric_id),
                "metric_unit": "contract_fixture_units",
                "evidence_basis": "FIXTURE_NOT_EMPIRICAL",
                "empirical_transition_backtest_executed": "false",
                "selected_strategy": "NONE",
                "interpretation_allowed": "false",
            })
    _write_csv(
        output_dir / RESULT_METRICS,
        [
            "result_row_id", "strategy_id", "metric_id", "metric_scope", "metric_value", "metric_unit",
            "evidence_basis", "empirical_transition_backtest_executed", "selected_strategy", "interpretation_allowed",
        ],
        rows,
    )
    report = {
        "execution_status": RESULT_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "repository_commit": repository_commit,
        "execution_policy_sha256": policy.policy_sha256,
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
        "readiness_status": readiness["runner_status"],
        "readiness_manifest_sha256": sha256_file(readiness_dir / "BACKTEST_READINESS_MANIFEST.sha256"),
        "readiness_attachment_status": readiness["attachment_status"],
        "protocol_status": protocol["protocol_status"],
        "protocol_sha256": protocol["protocol_sha256"],
        "strategy_ids": protocol["strategy_ids"],
        "metric_ids": protocol["metric_ids"],
        "metric_count": protocol["metric_count"],
        "metric_row_count": len(rows),
        "fixture_execution_completed": True,
        "empirical_transition_backtest_executed": False,
        "backtest_execution_claim_allowed": False,
        "selected_strategy": "NONE",
        "result_interpretation_allowed": False,
        "panel_verified_gate_open": False,
        "public_latest_modified": False,
        "official_bytes_committed_to_repository": False,
        "next_milestone": NEXT_MILESTONE,
    }
    missing = [field for field in contract["required_report_fields"] if field not in report]
    if missing:
        raise TransitionBacktestExecutionError(f"execution result report missing fields: {missing}")
    (output_dir / RESULT_REPORT).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, RESULT_MANIFEST)
    validate_execution_result(policy_path, output_dir)
    return report


def validate_execution_result(policy_path: Path, output_dir: Path) -> dict[str, Any]:
    policy = TransitionBacktestExecutionPolicy.load(policy_path)
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        raise TransitionBacktestExecutionError(f"result directory missing: {output_dir}")
    verify_manifest(output_dir, RESULT_MANIFEST)
    report = _read_json(output_dir / RESULT_REPORT)
    rows = _read_csv(output_dir / RESULT_METRICS)
    contract = policy.execution_contract
    for field in contract["required_report_fields"]:
        if field not in report:
            raise TransitionBacktestExecutionError(f"execution result report missing field: {field}")
    if report["execution_status"] != RESULT_STATUS:
        raise TransitionBacktestExecutionError("execution status mismatch")
    if report["policy_version"] != VERSION:
        raise TransitionBacktestExecutionError("execution version mismatch")
    if report["readiness_status"] != READINESS_STATUS:
        raise TransitionBacktestExecutionError("execution readiness status mismatch")
    if report["protocol_status"] != PROTOCOL_STATUS:
        raise TransitionBacktestExecutionError("execution protocol status mismatch")
    if tuple(report["strategy_ids"]) != tuple(contract["required_strategy_ids"]):
        raise TransitionBacktestExecutionError("execution strategy ids mismatch")
    if int(report["metric_count"]) < int(contract["minimum_metric_count"]):
        raise TransitionBacktestExecutionError("execution metric count too low")
    if int(report["metric_row_count"]) < int(contract["minimum_metric_rows"]):
        raise TransitionBacktestExecutionError("execution metric row count too low")
    expected_pairs = {(strategy, metric) for strategy in report["strategy_ids"] for metric in report["metric_ids"]}
    actual_pairs = {(row.get("strategy_id"), row.get("metric_id")) for row in rows}
    if actual_pairs != expected_pairs:
        raise TransitionBacktestExecutionError("metric matrix is not complete for all declared strategies and metrics")
    if len(rows) != int(report["metric_row_count"]):
        raise TransitionBacktestExecutionError("metric row count mismatch")
    if report["fixture_execution_completed"] is not True:
        raise TransitionBacktestExecutionError("fixture execution not completed")
    if report["empirical_transition_backtest_executed"] is not False:
        raise TransitionBacktestExecutionError("execution result claims empirical backtest execution")
    if report["backtest_execution_claim_allowed"] is not False:
        raise TransitionBacktestExecutionError("execution result opens backtest execution claim gate")
    if report["selected_strategy"] != "NONE":
        raise TransitionBacktestExecutionError("execution result selected a strategy")
    if report["result_interpretation_allowed"] is not False:
        raise TransitionBacktestExecutionError("fixture result permits interpretation")
    if report["panel_verified_gate_open"] is not False:
        raise TransitionBacktestExecutionError("execution result opens verified-panel gate")
    if report["public_latest_modified"] is not False:
        raise TransitionBacktestExecutionError("execution result modifies public/latest")
    if report["official_bytes_committed_to_repository"] is not False:
        raise TransitionBacktestExecutionError("execution result commits official bytes")
    for row in rows:
        if row.get("empirical_transition_backtest_executed") != "false":
            raise TransitionBacktestExecutionError("metric row claims empirical execution")
        if row.get("selected_strategy") != "NONE":
            raise TransitionBacktestExecutionError("metric row selected a strategy")
        if row.get("interpretation_allowed") != "false":
            raise TransitionBacktestExecutionError("metric row permits interpretation")
    return report


def _build_fixture_readiness(root: Path, tmp_dir: Path) -> Path:
    module = _load_module(root, "src/armilar_backtest/ecoicop_transition_backtest_v0108.py", "ecoicop_transition_backtest_v0108_fixture_for_v0109")
    attachment = module._build_fixture_attachment(root, tmp_dir / "attachment-fixture")
    readiness = tmp_dir / "readiness"
    module.create_backtest_readiness_report(
        root / DEFAULT_PREDECESSOR_POLICY,
        attachment,
        readiness,
        repo_root=root,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    return readiness


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.9 ECOICOP transition backtest execution engine")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repository-commit", default="UNCOMMITTED_EXTERNAL_RUN")
    parser.add_argument("--created-at", default="2026-07-10T00:00:00Z")
    parser.add_argument("--verify-result", type=Path)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    try:
        if args.verify_result:
            summary = validate_execution_result(policy_path, args.verify_result)
        elif args.readiness:
            if args.output_dir is None:
                raise TransitionBacktestExecutionError("--output-dir is required with --readiness")
            summary = create_transition_backtest_result(
                policy_path,
                args.readiness,
                args.output_dir,
                repo_root=root,
                repository_commit=args.repository_commit,
                created_at=args.created_at,
            )
        elif args.fixture:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="armilar-v0109-") as temp:
                temp_path = Path(temp)
                readiness = _build_fixture_readiness(root, temp_path)
                output = temp_path / "result"
                summary = create_transition_backtest_result(
                    policy_path,
                    readiness,
                    output,
                    repo_root=root,
                    repository_commit="fixture-v0109",
                    created_at=args.created_at,
                )
        else:
            policy = TransitionBacktestExecutionPolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            protocol = load_protocol_summary(root / DEFAULT_PROTOCOL_POLICY)
            summary = {
                "execution_status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "predecessor_status": predecessor["status"],
                "predecessor_policy_sha256": predecessor["policy_sha256"],
                "protocol_status": protocol["protocol_status"],
                "strategy_count": len(protocol["strategy_ids"]),
                "metric_count": protocol["metric_count"],
                "empirical_transition_backtest_executed": False,
                "backtest_execution_claim_allowed": False,
                "panel_verified_gate_open": False,
                "next_milestone": NEXT_MILESTONE,
            }
    except TransitionBacktestExecutionError as exc:
        raise SystemExit(f"ECOICOP_TRANSITION_BACKTEST_EXECUTION_V0109_INVALID: {exc}") from exc
    print(summary["execution_status"])
    for key in sorted(key for key in summary if key != "execution_status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
