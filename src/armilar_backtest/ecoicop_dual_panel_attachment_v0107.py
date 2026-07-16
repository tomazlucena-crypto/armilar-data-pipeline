"""External ECOICOP v1/v2 dual-panel artifact attachment protocol for ARMILAR v0.10.7.

This milestone attaches an already materialized and replay-verified external
ECOICOP v1/v2 dual-panel artifact to a deterministic descriptor.  It deliberately
keeps official provider bytes outside the repository, does not alter
``public/latest``, does not open the verified-panel gate, and does not execute the
transition backtest.  The descriptor is a reproducible audit handle that future
backtest execution can consume only after an explicit external artifact is
provided.
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

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ATTACHMENT_PROTOCOL_V0107_VALID"
ATTACHMENT_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_ATTACHMENT_V0107_VALID"
VERSION = "0.10.7"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZATION_RUNNER_V0106_VALID"
MATERIALIZED_REPLAY_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
NEXT_MILESTONE = "V0108_EXECUTE_ECOICOP_TRANSITION_BACKTEST_WITH_VERIFIED_DUAL_PANEL"
DEFAULT_MATERIALIZATION_POLICY = Path("config/ecoicop_dual_panel_materialization_v0106.json")
DEFAULT_REPLAY_POLICY = Path("config/ecoicop_dual_panel_replay_v0105.json")
ATTACHMENT_MANIFEST = "ATTACHMENT_MANIFEST.sha256"
DESCRIPTOR_FILE = "panel_attachment_descriptor.json"


class AttachmentError(ValueError):
    """Raised when the v0.10.7 external attachment contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttachmentError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AttachmentError(f"JSON object required: {path}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise AttachmentError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise AttachmentError(f"{label} must be a safe relative path: {value}")
    return relative


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AttachmentError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AttachmentError(f"{label} must be a list")
    return value


def _manifest_entries(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise AttachmentError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise AttachmentError(f"invalid manifest line {line_number} in {manifest_name}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise AttachmentError(f"duplicate manifest entry: {relative}")
        entries[relative] = digest
    return entries


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    entries = _manifest_entries(path, manifest_name)
    for relative, expected in entries.items():
        candidate = path / relative
        if not candidate.is_file():
            raise AttachmentError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != expected:
            raise AttachmentError(f"manifest hash mismatch: {relative}")
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
class AttachmentPolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "AttachmentPolicy":
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
    def attachment_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["attachment_contract"], "attachment contract")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {
        "policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy",
        "scope", "attachment_contract", "gates", "next_milestone",
    }
    missing = required - set(policy)
    if missing:
        raise AttachmentError(f"attachment policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise AttachmentError("policy version mismatch")
    if policy["status"] != STATUS:
        raise AttachmentError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise AttachmentError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise AttachmentError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    required_true = {
        "define_external_attachment_protocol",
        "verify_materialized_artifact_with_v0105_replay",
        "generate_non_committed_attachment_descriptor",
        "record_artifact_manifest_hash",
    }
    for key in required_true:
        if scope.get(key) is not True:
            raise AttachmentError(f"required v0.10.7 scope not enabled: {key}")
    forbidden = [key for key, value in scope.items() if key not in required_true and bool(value)]
    if forbidden:
        raise AttachmentError(f"forbidden v0.10.7 scope enabled: {forbidden}")

    contract = _require_dict(policy["attachment_contract"], "attachment contract")
    if contract.get("required_manifest") != ATTACHMENT_MANIFEST:
        raise AttachmentError("attachment manifest name mismatch")
    if contract.get("descriptor_file") != DESCRIPTOR_FILE:
        raise AttachmentError("attachment descriptor name mismatch")
    if contract.get("artifact_manifest_name") != "PANEL_MANIFEST.sha256":
        raise AttachmentError("artifact manifest name mismatch")
    if contract.get("artifact_summary_name") != "panel_summary.json":
        raise AttachmentError("artifact summary name mismatch")
    if contract.get("required_artifact_replay_status") != MATERIALIZED_REPLAY_STATUS:
        raise AttachmentError("artifact replay status mismatch")
    if contract.get("required_attachment_status") != ATTACHMENT_STATUS:
        raise AttachmentError("attachment status mismatch")
    if contract.get("selected_strategy_must_equal") != "NONE":
        raise AttachmentError("v0.10.7 must not select a transition strategy")
    if contract.get("official_bytes_committed_to_repository_must_equal") is not False:
        raise AttachmentError("v0.10.7 must not commit official bytes")
    if contract.get("public_latest_modified_must_equal") is not False:
        raise AttachmentError("v0.10.7 must not modify public/latest")
    fields = tuple(str(item) for item in _require_list(contract["required_descriptor_fields"], "required descriptor fields"))
    if len(fields) != len(set(fields)):
        raise AttachmentError("duplicate required descriptor field")
    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise AttachmentError(f"v0.10.7 gates must remain closed: {open_gates}")


def _load_module(root: Path, relative: str, name: str):
    module_path = root / relative
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise AttachmentError(f"cannot import module: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_predecessor(root: Path) -> dict[str, str]:
    module = _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_materialization_v0106.py", "ecoicop_dual_panel_materialization_v0106_for_v0107")
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise AttachmentError("v0.10.6 predecessor status mismatch")
    policy = module.MaterializationPolicy.load(root / DEFAULT_MATERIALIZATION_POLICY)
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != "ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID":
        raise AttachmentError("v0.10.6 predecessor chain did not validate v0.10.5")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": policy.policy_sha256}


def _load_replay_module(root: Path):
    return _load_module(root, "src/armilar_backtest/ecoicop_dual_panel_replay_v0105.py", "ecoicop_dual_panel_replay_v0105_for_v0107")


def validate_materialized_artifact(policy_path: Path, artifact_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    policy = AttachmentPolicy.load(policy_path)
    artifact_dir = artifact_dir.resolve()
    if not artifact_dir.is_dir():
        raise AttachmentError(f"artifact directory missing: {artifact_dir}")
    manifest_entries = verify_manifest(artifact_dir, "PANEL_MANIFEST.sha256")
    summary_path = artifact_dir / "panel_summary.json"
    summary = _read_json(summary_path)
    replay_module = _load_replay_module(repo_root)
    replay_summary = replay_module.validate_external_panel_artifact(repo_root / DEFAULT_REPLAY_POLICY, artifact_dir)
    if replay_summary["status"] != MATERIALIZED_REPLAY_STATUS:
        raise AttachmentError("artifact did not pass v0.10.5 replay verification")
    contract = policy.attachment_contract
    if summary.get("status") != MATERIALIZED_REPLAY_STATUS:
        raise AttachmentError("panel summary status mismatch")
    if summary.get("selected_strategy") != contract["selected_strategy_must_equal"]:
        raise AttachmentError("artifact selected a transition strategy")
    if summary.get("transition_backtest_executed") is not False:
        raise AttachmentError("artifact claims transition backtest execution")
    if summary.get("panel_verified_gate_open") is not False:
        raise AttachmentError("artifact opens verified-panel gate")
    return {
        "artifact_replay_status": replay_summary["status"],
        "artifact_manifest_sha256": sha256_file(artifact_dir / "PANEL_MANIFEST.sha256"),
        "artifact_manifest_entry_count": len(manifest_entries),
        "artifact_summary_sha256": sha256_file(summary_path),
        "receipt_count": int(replay_summary.get("receipt_count", 0)),
        "observation_count": int(replay_summary.get("observation_count", 0)),
        "coverage_row_count": int(replay_summary.get("coverage_row_count", 0)),
        "lineage_row_count": int(replay_summary.get("lineage_row_count", 0)),
        "replay_policy_sha256": str(replay_summary.get("policy_sha256", "")),
    }


def create_attachment_descriptor(
    policy_path: Path,
    artifact_dir: Path,
    output_dir: Path,
    *,
    repo_root: Path,
    repository_commit: str,
    artifact_uri: str,
    created_at: str,
) -> dict[str, Any]:
    policy = AttachmentPolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise AttachmentError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = validate_materialized_artifact(policy_path, artifact_dir, repo_root=repo_root)
    predecessor = validate_predecessor(repo_root)
    descriptor = {
        "attachment_status": ATTACHMENT_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "repository_commit": repository_commit,
        "artifact_uri": artifact_uri,
        "attachment_policy_sha256": policy.policy_sha256,
        "materialization_policy_sha256": predecessor["policy_sha256"],
        "replay_policy_sha256": artifact["replay_policy_sha256"],
        "artifact_manifest_sha256": artifact["artifact_manifest_sha256"],
        "artifact_manifest_entry_count": artifact["artifact_manifest_entry_count"],
        "artifact_summary_sha256": artifact["artifact_summary_sha256"],
        "artifact_replay_status": artifact["artifact_replay_status"],
        "receipt_count": artifact["receipt_count"],
        "observation_count": artifact["observation_count"],
        "coverage_row_count": artifact["coverage_row_count"],
        "lineage_row_count": artifact["lineage_row_count"],
        "official_bytes_committed_to_repository": False,
        "public_latest_modified": False,
        "transition_backtest_executed": False,
        "selected_strategy": "NONE",
        "panel_verified_gate_open": False,
        "next_milestone": NEXT_MILESTONE,
    }
    required_fields = tuple(str(item) for item in policy.attachment_contract["required_descriptor_fields"])
    missing = [field for field in required_fields if field not in descriptor]
    if missing:
        raise AttachmentError(f"descriptor missing required fields: {missing}")
    (output_dir / DESCRIPTOR_FILE).write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, ATTACHMENT_MANIFEST)
    validate_attachment_directory(policy_path, output_dir)
    return descriptor


def validate_attachment_directory(policy_path: Path, attachment_dir: Path) -> dict[str, Any]:
    policy = AttachmentPolicy.load(policy_path)
    attachment_dir = attachment_dir.resolve()
    if not attachment_dir.is_dir():
        raise AttachmentError(f"attachment directory missing: {attachment_dir}")
    verify_manifest(attachment_dir, ATTACHMENT_MANIFEST)
    descriptor = _read_json(attachment_dir / DESCRIPTOR_FILE)
    contract = policy.attachment_contract
    for field in contract["required_descriptor_fields"]:
        if field not in descriptor:
            raise AttachmentError(f"attachment descriptor missing field: {field}")
    if descriptor["attachment_status"] != ATTACHMENT_STATUS:
        raise AttachmentError("attachment descriptor status mismatch")
    if descriptor["policy_version"] != VERSION:
        raise AttachmentError("attachment descriptor version mismatch")
    if descriptor["artifact_replay_status"] != MATERIALIZED_REPLAY_STATUS:
        raise AttachmentError("attachment artifact replay status mismatch")
    if descriptor["official_bytes_committed_to_repository"] is not False:
        raise AttachmentError("attachment descriptor claims official bytes were committed")
    if descriptor["public_latest_modified"] is not False:
        raise AttachmentError("attachment descriptor claims public/latest was modified")
    if descriptor["transition_backtest_executed"] is not False:
        raise AttachmentError("attachment descriptor claims backtest execution")
    if descriptor["selected_strategy"] != "NONE":
        raise AttachmentError("attachment descriptor selected a transition strategy")
    if descriptor["panel_verified_gate_open"] is not False:
        raise AttachmentError("attachment descriptor opens verified-panel gate")
    return {
        "attachment_status": ATTACHMENT_STATUS,
        "policy_version": VERSION,
        "attachment_manifest_sha256": sha256_file(attachment_dir / ATTACHMENT_MANIFEST),
        "artifact_replay_status": descriptor["artifact_replay_status"],
        "artifact_manifest_entry_count": descriptor["artifact_manifest_entry_count"],
        "official_bytes_committed_to_repository": descriptor["official_bytes_committed_to_repository"],
        "public_latest_modified": descriptor["public_latest_modified"],
        "transition_backtest_executed": descriptor["transition_backtest_executed"],
        "selected_strategy": descriptor["selected_strategy"],
        "panel_verified_gate_open": descriptor["panel_verified_gate_open"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.7 ECOICOP external artifact attachment protocol")
    parser.add_argument("--policy", type=Path, default=Path("config/ecoicop_dual_panel_attachment_v0107.json"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--verify-artifact", type=Path)
    parser.add_argument("--attach-artifact", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repository-commit", default="UNCOMMITTED_EXTERNAL_RUN")
    parser.add_argument("--artifact-uri", default="external://uncommitted-dual-panel-artifact")
    parser.add_argument("--created-at", default="2026-07-09T00:00:00Z")
    parser.add_argument("--verify-attachment", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    try:
        if args.verify_artifact:
            summary = validate_materialized_artifact(policy_path, args.verify_artifact, repo_root=root)
            summary = {"attachment_status": STATUS, "policy_version": VERSION, **summary}
        elif args.attach_artifact:
            if args.output_dir is None:
                raise AttachmentError("--output-dir is required with --attach-artifact")
            descriptor = create_attachment_descriptor(
                policy_path,
                args.attach_artifact,
                args.output_dir,
                repo_root=root,
                repository_commit=args.repository_commit,
                artifact_uri=args.artifact_uri,
                created_at=args.created_at,
            )
            summary = descriptor
        elif args.verify_attachment:
            summary = validate_attachment_directory(policy_path, args.verify_attachment)
        else:
            policy = AttachmentPolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            summary = {
                "attachment_status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "gate_count_open": sum(bool(value) for value in policy.gates.values()),
                "predecessor_status": predecessor["status"],
                "predecessor_policy_sha256": predecessor["policy_sha256"],
                "next_milestone": NEXT_MILESTONE,
            }
    except AttachmentError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_ATTACHMENT_V0107_INVALID: {exc}") from exc
    print(summary["attachment_status"])
    for key in sorted(key for key in summary if key != "attachment_status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
