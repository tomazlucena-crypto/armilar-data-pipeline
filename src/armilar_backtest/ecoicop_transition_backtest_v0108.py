"""ECOICOP v1/v2 transition backtest runner contract for ARMILAR v0.10.8.

This milestone defines the fail-closed runner that may execute the transition
backtest only when supplied with an external dual-panel attachment validated by
v0.10.7 and a protocol ratified by v0.10.3.  The PR itself deliberately creates
only a readiness report from a fixture attachment.  It does not acquire live
provider bytes, commit official data, alter ``public/latest``, select a
transition strategy, or claim that an empirical transition backtest has been
executed.
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

STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_RUNNER_V0108_VALID"
READY_STATUS = "ECOICOP_V2_TRANSITION_BACKTEST_READINESS_REPORT_V0108_VALID"
VERSION = "0.10.8"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ATTACHMENT_PROTOCOL_V0107_VALID"
ATTACHMENT_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_ATTACHMENT_V0107_VALID"
ARTIFACT_REPLAY_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
PROTOCOL_STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
NEXT_MILESTONE = "V0109_RUN_EMPIRICAL_TRANSITION_BACKTEST_ON_EXTERNAL_VERIFIED_PANEL"
DEFAULT_POLICY = Path("config/ecoicop_transition_backtest_runner_v0108.json")
DEFAULT_ATTACHMENT_POLICY = Path("config/ecoicop_dual_panel_attachment_v0107.json")
DEFAULT_PROTOCOL_POLICY = Path("config/ecoicop_v2_backtest_protocol_v0103.json")
READINESS_REPORT = "transition_backtest_readiness_report.json"
READINESS_MANIFEST = "BACKTEST_READINESS_MANIFEST.sha256"


class TransitionBacktestError(ValueError):
    """Raised when the v0.10.8 backtest runner contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransitionBacktestError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TransitionBacktestError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise TransitionBacktestError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise TransitionBacktestError(f"{label} must be a safe relative path: {value}")
    return relative


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TransitionBacktestError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TransitionBacktestError(f"{label} must be a list")
    return value


def _load_module(root: Path, relative: str, name: str):
    module_path = root / relative
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise TransitionBacktestError(f"cannot import module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_entries(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise TransitionBacktestError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise TransitionBacktestError(f"invalid manifest line {line_number} in {manifest_name}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise TransitionBacktestError(f"duplicate manifest entry: {relative}")
        entries[relative] = digest
    return entries


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    entries = _manifest_entries(path, manifest_name)
    for relative, expected in entries.items():
        candidate = path / relative
        if not candidate.is_file():
            raise TransitionBacktestError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != expected:
            raise TransitionBacktestError(f"manifest hash mismatch: {relative}")
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
class TransitionBacktestPolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "TransitionBacktestPolicy":
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
    def runner_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["runner_contract"], "runner contract")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {
        "policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy",
        "protocol_policy", "scope", "runner_contract", "gates", "next_milestone",
    }
    missing = required - set(policy)
    if missing:
        raise TransitionBacktestError(f"transition backtest policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise TransitionBacktestError("policy version mismatch")
    if policy["status"] != STATUS:
        raise TransitionBacktestError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise TransitionBacktestError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise TransitionBacktestError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    required_true = {
        "define_transition_backtest_runner",
        "require_verified_external_attachment",
        "load_declared_candidate_strategies",
        "load_declared_backtest_metrics",
        "generate_readiness_report_only",
    }
    for key in required_true:
        if scope.get(key) is not True:
            raise TransitionBacktestError(f"required v0.10.8 scope not enabled: {key}")
    forbidden = [key for key, value in scope.items() if key not in required_true and bool(value)]
    if forbidden:
        raise TransitionBacktestError(f"forbidden v0.10.8 scope enabled: {forbidden}")

    contract = _require_dict(policy["runner_contract"], "runner contract")
    if contract.get("required_attachment_status") != ATTACHMENT_STATUS:
        raise TransitionBacktestError("attachment status mismatch")
    if contract.get("required_artifact_replay_status") != ARTIFACT_REPLAY_STATUS:
        raise TransitionBacktestError("artifact replay status mismatch")
    if contract.get("required_protocol_status") != PROTOCOL_STATUS:
        raise TransitionBacktestError("protocol status mismatch")
    if tuple(contract.get("required_strategy_ids", ())) != ("T0", "T1", "T2", "T3"):
        raise TransitionBacktestError("required strategy ids mismatch")
    if int(contract.get("minimum_metric_count", 0)) < 14:
        raise TransitionBacktestError("minimum metric count too low")
    if contract.get("readiness_report_file") != READINESS_REPORT:
        raise TransitionBacktestError("readiness report file mismatch")
    if contract.get("readiness_manifest_file") != READINESS_MANIFEST:
        raise TransitionBacktestError("readiness manifest file mismatch")
    if contract.get("transition_backtest_executed_must_equal") is not False:
        raise TransitionBacktestError("v0.10.8 PR must not claim backtest execution")
    if contract.get("backtest_execution_claim_allowed_must_equal") is not False:
        raise TransitionBacktestError("backtest execution claim gate must remain closed")
    if contract.get("selected_strategy_must_equal") != "NONE":
        raise TransitionBacktestError("v0.10.8 must not select a transition strategy")
    if contract.get("public_latest_modified_must_equal") is not False:
        raise TransitionBacktestError("v0.10.8 must not modify public/latest")
    if contract.get("official_bytes_committed_to_repository_must_equal") is not False:
        raise TransitionBacktestError("v0.10.8 must not commit official bytes")
    fields = tuple(str(item) for item in _require_list(contract["required_report_fields"], "required report fields"))
    if len(fields) != len(set(fields)):
        raise TransitionBacktestError("duplicate required report field")

    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise TransitionBacktestError(f"v0.10.8 gates must remain closed: {open_gates}")


def validate_predecessor(root: Path) -> dict[str, str]:
    module = _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_for_v0108")
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise TransitionBacktestError("v0.10.7 predecessor status mismatch")
    policy = module.AttachmentPolicy.load(root / DEFAULT_ATTACHMENT_POLICY)
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZATION_RUNNER_V0106_VALID":
        raise TransitionBacktestError("v0.10.7 predecessor chain did not validate v0.10.6")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": policy.policy_sha256}


def load_protocol_summary(protocol_path: Path) -> dict[str, Any]:
    protocol = _read_json(protocol_path)
    if protocol.get("status") != PROTOCOL_STATUS:
        raise TransitionBacktestError("v0.10.3 backtest protocol status mismatch")
    strategies = _require_list(protocol.get("strategies"), "candidate strategies")
    metrics = _require_list(protocol.get("metrics"), "required backtest metrics")
    strategy_ids = tuple(str(item.get("strategy_id")) for item in strategies if isinstance(item, dict))
    metric_ids = tuple(str(item.get("metric_id")) for item in metrics if isinstance(item, dict))
    if strategy_ids != ("T0", "T1", "T2", "T3"):
        raise TransitionBacktestError("v0.10.3 strategy ids mismatch")
    if len(metric_ids) < 14:
        raise TransitionBacktestError("v0.10.3 metric count below declared floor")
    if any(bool(item.get("automatic_selection_allowed")) for item in strategies if isinstance(item, dict)):
        raise TransitionBacktestError("automatic strategy selection is forbidden")
    return {
        "protocol_status": PROTOCOL_STATUS,
        "protocol_sha256": sha256_file(protocol_path),
        "strategy_ids": list(strategy_ids),
        "metric_ids": list(metric_ids),
        "metric_count": len(metric_ids),
    }


def validate_attachment_for_backtest(policy_path: Path, attachment_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    policy = TransitionBacktestPolicy.load(policy_path)
    attachment_module = _load_module(repo_root, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_runner_for_v0108")
    summary = attachment_module.validate_attachment_directory(repo_root / DEFAULT_ATTACHMENT_POLICY, attachment_dir)
    contract = policy.runner_contract
    if summary["attachment_status"] != contract["required_attachment_status"]:
        raise TransitionBacktestError("attachment status does not satisfy runner contract")
    if summary["artifact_replay_status"] != contract["required_artifact_replay_status"]:
        raise TransitionBacktestError("artifact replay status does not satisfy runner contract")
    if summary["transition_backtest_executed"] is not False:
        raise TransitionBacktestError("attachment already claims backtest execution")
    if summary["selected_strategy"] != "NONE":
        raise TransitionBacktestError("attachment selected a transition strategy")
    if summary["panel_verified_gate_open"] is not False:
        raise TransitionBacktestError("attachment opens verified-panel gate")
    return dict(summary)


def create_backtest_readiness_report(
    policy_path: Path,
    attachment_dir: Path,
    output_dir: Path,
    *,
    repo_root: Path,
    repository_commit: str,
    created_at: str,
) -> dict[str, Any]:
    policy = TransitionBacktestPolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise TransitionBacktestError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    predecessor = validate_predecessor(repo_root)
    attachment = validate_attachment_for_backtest(policy_path, attachment_dir, repo_root=repo_root)
    protocol = load_protocol_summary(repo_root / DEFAULT_PROTOCOL_POLICY)
    contract = policy.runner_contract
    report = {
        "runner_status": READY_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "repository_commit": repository_commit,
        "runner_policy_sha256": policy.policy_sha256,
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
        "attachment_status": attachment["attachment_status"],
        "attachment_manifest_sha256": attachment["attachment_manifest_sha256"],
        "artifact_replay_status": attachment["artifact_replay_status"],
        "artifact_manifest_entry_count": attachment["artifact_manifest_entry_count"],
        "protocol_status": protocol["protocol_status"],
        "protocol_sha256": protocol["protocol_sha256"],
        "strategy_ids": protocol["strategy_ids"],
        "metric_ids": protocol["metric_ids"],
        "metric_count": protocol["metric_count"],
        "transition_backtest_executed": False,
        "backtest_execution_claim_allowed": False,
        "selected_strategy": "NONE",
        "panel_verified_gate_open": False,
        "public_latest_modified": False,
        "official_bytes_committed_to_repository": False,
        "next_milestone": NEXT_MILESTONE,
    }
    missing = [field for field in contract["required_report_fields"] if field not in report]
    if missing:
        raise TransitionBacktestError(f"readiness report missing fields: {missing}")
    (output_dir / READINESS_REPORT).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, READINESS_MANIFEST)
    validate_readiness_report(policy_path, output_dir)
    return report


def validate_readiness_report(policy_path: Path, output_dir: Path) -> dict[str, Any]:
    policy = TransitionBacktestPolicy.load(policy_path)
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        raise TransitionBacktestError(f"readiness directory missing: {output_dir}")
    verify_manifest(output_dir, READINESS_MANIFEST)
    report = _read_json(output_dir / READINESS_REPORT)
    contract = policy.runner_contract
    for field in contract["required_report_fields"]:
        if field not in report:
            raise TransitionBacktestError(f"readiness report missing field: {field}")
    if report["runner_status"] != READY_STATUS:
        raise TransitionBacktestError("readiness status mismatch")
    if report["policy_version"] != VERSION:
        raise TransitionBacktestError("readiness version mismatch")
    if report["attachment_status"] != ATTACHMENT_STATUS:
        raise TransitionBacktestError("readiness attachment status mismatch")
    if report["artifact_replay_status"] != ARTIFACT_REPLAY_STATUS:
        raise TransitionBacktestError("readiness artifact replay status mismatch")
    if report["protocol_status"] != PROTOCOL_STATUS:
        raise TransitionBacktestError("readiness protocol status mismatch")
    if tuple(report["strategy_ids"]) != tuple(contract["required_strategy_ids"]):
        raise TransitionBacktestError("readiness strategy ids mismatch")
    if int(report["metric_count"]) < int(contract["minimum_metric_count"]):
        raise TransitionBacktestError("readiness metric count too low")
    if report["transition_backtest_executed"] is not False:
        raise TransitionBacktestError("readiness report claims empirical backtest execution")
    if report["backtest_execution_claim_allowed"] is not False:
        raise TransitionBacktestError("readiness report opens backtest execution claim gate")
    if report["selected_strategy"] != "NONE":
        raise TransitionBacktestError("readiness report selected a strategy")
    if report["panel_verified_gate_open"] is not False:
        raise TransitionBacktestError("readiness report opens verified-panel gate")
    if report["public_latest_modified"] is not False:
        raise TransitionBacktestError("readiness report modifies public/latest")
    if report["official_bytes_committed_to_repository"] is not False:
        raise TransitionBacktestError("readiness report commits official bytes")
    return report


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _build_fixture_attachment(root: Path, tmp_dir: Path) -> Path:
    """Build a deterministic fixture attachment from synthetic already-staged bytes.

    This helper exists only for unit tests and the checker.  It exercises the
    v0.10.6 materializer and v0.10.7 attachment path without acquiring live data
    and without committing official provider bytes.
    """
    materialization = _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_materialization_v0106.py", "ecoicop_dual_panel_materialization_v0106_fixture_for_v0108")
    attachment = _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_fixture_for_v0108")
    staging = tmp_dir / "staging"
    staging.mkdir(parents=True)
    raw = staging / "raw" / "fixture.xml"
    raw.parent.mkdir()
    raw.write_text("<fixture>ecoicop-v0108</fixture>\n", encoding="utf-8")
    raw_sha = sha256_file(raw)
    _write_csv(
        staging / "staged_receipts.csv",
        [
            "staged_receipt_id", "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at", "http_status",
            "raw_path", "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint",
        ],
        [{
            "staged_receipt_id": "SR1",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "provider": "EUROSTAT",
            "dataset_code": "prc_hicp_midx",
            "request_url": "https://example.invalid/eurostat/fixture",
            "retrieved_at": "2026-07-09T00:00:00Z",
            "http_status": "200",
            "raw_path": "raw/fixture.xml",
            "raw_sha256": raw_sha,
            "byte_count": str(raw.stat().st_size),
            "content_type": "application/xml",
            "classification": "ECOICOP_V1_PRE_2026",
            "time_window": "2025-12/2025-12",
            "query_fingerprint": _sha256_bytes(b"v0108-fixture-query"),
        }],
    )
    _write_csv(
        staging / "staged_observations.csv",
        [
            "staged_observation_id", "staged_receipt_id", "dataset_role", "economy", "armilar_code", "classification",
            "category_or_division", "period", "unit", "value", "source_period_type", "parser_version", "quality_status",
        ],
        [{
            "staged_observation_id": "SO1",
            "staged_receipt_id": "SR1",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "economy": "PT",
            "armilar_code": "PRT",
            "classification": "ECOICOP_V1_PRE_2026",
            "category_or_division": "CP01",
            "period": "2025-12",
            "unit": "index_2015_100",
            "value": "121.34",
            "source_period_type": "monthly",
            "parser_version": "fixture-parser-v1",
            "quality_status": "OBSERVED_OFFICIAL",
        }],
    )
    _write_csv(
        staging / "staged_coverage.csv",
        [
            "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status", "staged_observation_id",
        ],
        [{
            "coverage_id": "C1",
            "economy": "PT",
            "armilar_code": "PRT",
            "classification": "ECOICOP_V1_PRE_2026",
            "category_or_division": "CP01",
            "period": "2025-12",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "coverage_status": "OBSERVED",
            "staged_observation_id": "SO1",
        }],
    )
    materialization._write_manifest(staging, "STAGING_MANIFEST.sha256")
    artifact = tmp_dir / "artifact"
    materialization.materialize_external_panel(
        root / "config/ecoicop_dual_panel_materialization_v0106.json",
        root / "config/ecoicop_dual_panel_replay_v0105.json",
        staging,
        artifact,
        created_at="2026-07-09T00:00:00Z",
        repo_root=root,
    )
    attachment_dir = tmp_dir / "attachment"
    attachment.create_attachment_descriptor(
        root / DEFAULT_ATTACHMENT_POLICY,
        artifact,
        attachment_dir,
        repo_root=root,
        repository_commit="fixture-v0108",
        artifact_uri="external://fixture/ecoicop-dual-panel-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    return attachment_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.8 ECOICOP transition backtest runner")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--attachment", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repository-commit", default="UNCOMMITTED_EXTERNAL_RUN")
    parser.add_argument("--created-at", default="2026-07-09T00:00:00Z")
    parser.add_argument("--verify-readiness", type=Path)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    try:
        if args.verify_readiness:
            summary = validate_readiness_report(policy_path, args.verify_readiness)
        elif args.attachment:
            if args.output_dir is None:
                raise TransitionBacktestError("--output-dir is required with --attachment")
            summary = create_backtest_readiness_report(
                policy_path,
                args.attachment,
                args.output_dir,
                repo_root=root,
                repository_commit=args.repository_commit,
                created_at=args.created_at,
            )
        elif args.fixture:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="armilar-v0108-") as temp:
                temp_path = Path(temp)
                attachment = _build_fixture_attachment(root, temp_path)
                output = temp_path / "readiness"
                summary = create_backtest_readiness_report(
                    policy_path,
                    attachment,
                    output,
                    repo_root=root,
                    repository_commit="fixture-v0108",
                    created_at=args.created_at,
                )
        else:
            policy = TransitionBacktestPolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            protocol = load_protocol_summary(root / DEFAULT_PROTOCOL_POLICY)
            summary = {
                "runner_status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "predecessor_status": predecessor["status"],
                "predecessor_policy_sha256": predecessor["policy_sha256"],
                "protocol_status": protocol["protocol_status"],
                "strategy_count": len(protocol["strategy_ids"]),
                "metric_count": protocol["metric_count"],
                "transition_backtest_executed": False,
                "backtest_execution_claim_allowed": False,
                "panel_verified_gate_open": False,
                "next_milestone": NEXT_MILESTONE,
            }
    except TransitionBacktestError as exc:
        raise SystemExit(f"ECOICOP_TRANSITION_BACKTEST_V0108_INVALID: {exc}") from exc
    print(summary["runner_status"])
    for key in sorted(key for key in summary if key != "runner_status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
