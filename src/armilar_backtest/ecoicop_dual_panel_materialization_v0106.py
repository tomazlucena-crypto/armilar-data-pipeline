"""Offline ECOICOP v1/v2 dual-panel materialization runner for ARMILAR v0.10.6.

This milestone turns the v0.10.5 replay contract into a deterministic offline
materializer.  It accepts a staging directory of already acquired official bytes
and parsed rows, materializes the external replay artifact, and immediately
verifies that artifact with the v0.10.5 verifier.  It deliberately performs no
network acquisition, commits no official bytes, opens no panel verification gate,
and executes no transition backtest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZATION_RUNNER_V0106_VALID"
MATERIALIZED_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZED_ARTIFACT_REPLAY_VALID"
VERSION = "0.10.6"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID"
PREDECESSOR_REPLAY_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
NEXT_MILESTONE = "V0107_RUN_EXTERNAL_DUAL_PANEL_ACQUISITION_AND_ATTACH_VERIFIED_ARTIFACT"
STAGING_FILES = (
    "STAGING_MANIFEST.sha256",
    "staged_coverage.csv",
    "staged_observations.csv",
    "staged_receipts.csv",
)
QUALITY_STATUSES = ("OBSERVED_OFFICIAL", "MISSING", "QUARANTINED")
COVERAGE_STATUSES = ("OBSERVED", "MISSING", "QUARANTINED")
REPLAY_POLICY = Path("config/ecoicop_dual_panel_replay_v0105.json")


class MaterializationError(ValueError):
    """Raised when the v0.10.6 materialization contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MaterializationError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise MaterializationError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _safe_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise MaterializationError(f"{label} must be a safe relative path: {value}")
    return relative


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaterializationError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MaterializationError(f"{label} must be a list")
    return value


def _read_csv(path: Path, required_fields: Sequence[str]) -> tuple[dict[str, str], ...]:
    if not path.is_file():
        raise MaterializationError(f"required CSV missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [field for field in required_fields if field not in fieldnames]
        if missing:
            raise MaterializationError(f"{path.name} missing fields: {missing}")
        return tuple({key: (value or "") for key, value in row.items()} for row in reader)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _index_by(rows: Sequence[Mapping[str, str]], key: str, label: str) -> dict[str, Mapping[str, str]]:
    indexed: dict[str, Mapping[str, str]] = {}
    for row in rows:
        value = row.get(key, "")
        if not value:
            raise MaterializationError(f"{label} row missing {key}")
        if value in indexed:
            raise MaterializationError(f"duplicate {label} key: {value}")
        indexed[value] = row
    return indexed


def _manifest_entries(path: Path, manifest_name: str) -> dict[str, str]:
    manifest = path / manifest_name
    if not manifest.is_file():
        raise MaterializationError(f"manifest missing: {manifest_name}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise MaterializationError(f"invalid manifest line {line_number} in {manifest_name}")
        digest, relative = parts
        _safe_relative(relative, label="manifest path")
        if relative in entries:
            raise MaterializationError(f"duplicate manifest entry: {relative}")
        entries[relative] = digest
    return entries


def verify_manifest(path: Path, manifest_name: str) -> dict[str, str]:
    entries = _manifest_entries(path, manifest_name)
    for relative, expected in entries.items():
        candidate = path / relative
        if not candidate.is_file():
            raise MaterializationError(f"manifest entry missing: {relative}")
        actual = sha256_file(candidate)
        if actual != expected:
            raise MaterializationError(f"manifest hash mismatch: {relative}")
    return entries


def _write_manifest(path: Path, manifest_name: str) -> None:
    entries: list[str] = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix()
        if relative == manifest_name:
            continue
        entries.append(f"{sha256_file(candidate)}  {relative}")
    (path / manifest_name).write_text("\n".join(entries) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class MaterializationPolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "MaterializationPolicy":
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
    def staging_contract(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["staging_contract"], "staging contract")

    @property
    def receipt_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.staging_contract["staged_receipts_required_fields"])

    @property
    def observation_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.staging_contract["staged_observations_required_fields"])

    @property
    def coverage_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.staging_contract["staged_coverage_required_fields"])


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    required = {
        "policy_id", "policy_version", "status", "predecessor_status", "predecessor_policy",
        "scope", "staging_contract", "materialized_artifact_contract", "gates", "next_milestone",
    }
    missing = required - set(policy)
    if missing:
        raise MaterializationError(f"materialization policy missing fields: {sorted(missing)}")
    if policy["policy_version"] != VERSION:
        raise MaterializationError("policy version mismatch")
    if policy["status"] != STATUS:
        raise MaterializationError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise MaterializationError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise MaterializationError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    for key in ("define_offline_materialization_runner", "materialize_from_staged_official_bytes", "verify_materialized_artifact_with_v0105_replay"):
        if scope.get(key) is not True:
            raise MaterializationError(f"required v0.10.6 scope not enabled: {key}")
    forbidden = [
        key for key, value in scope.items()
        if key not in {"define_offline_materialization_runner", "materialize_from_staged_official_bytes", "verify_materialized_artifact_with_v0105_replay"}
        and bool(value)
    ]
    if forbidden:
        raise MaterializationError(f"forbidden v0.10.6 scope enabled: {forbidden}")

    staging = _require_dict(policy["staging_contract"], "staging contract")
    files = tuple(sorted(str(item) for item in _require_list(staging["required_files"], "required staging files")))
    if files != STAGING_FILES:
        raise MaterializationError("required staging files mismatch")
    if tuple(str(item) for item in staging["allowed_quality_statuses"]) != QUALITY_STATUSES:
        raise MaterializationError("quality statuses mismatch")
    if tuple(str(item) for item in staging["allowed_coverage_statuses"]) != COVERAGE_STATUSES:
        raise MaterializationError("coverage statuses mismatch")

    artifact = _require_dict(policy["materialized_artifact_contract"], "artifact contract")
    if artifact.get("must_pass_replay_verifier_status") != PREDECESSOR_REPLAY_STATUS:
        raise MaterializationError("materialized artifact must be verified by v0.10.5 replay status")
    if artifact.get("selected_strategy_must_equal") != "NONE":
        raise MaterializationError("v0.10.6 must not select a strategy")
    open_gates = [key for key, value in _require_dict(policy["gates"], "gates").items() if bool(value)]
    if open_gates:
        raise MaterializationError(f"v0.10.6 gates must remain closed: {open_gates}")


def _load_replay_module(root: Path):
    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_replay_v0105.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_replay_v0105_for_v0106", module_path)
    if spec is None or spec.loader is None:
        raise MaterializationError("cannot import v0.10.5 replay module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_predecessor(root: Path) -> dict[str, str]:
    module = _load_replay_module(root)
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise MaterializationError("v0.10.5 predecessor status mismatch")
    policy = module.ReplayPolicy.load(root / REPLAY_POLICY)
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID":
        raise MaterializationError("v0.10.5 predecessor chain did not validate v0.10.4")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": policy.policy_sha256}


def validate_staging_directory(policy_path: Path, staging_dir: Path) -> dict[str, Any]:
    policy = MaterializationPolicy.load(policy_path)
    staging_dir = staging_dir.resolve()
    if not staging_dir.is_dir():
        raise MaterializationError(f"staging directory missing: {staging_dir}")
    files = {item.name for item in staging_dir.iterdir() if item.is_file()}
    required = set(policy.staging_contract["required_files"])
    missing = required - files
    if missing:
        raise MaterializationError(f"staging directory missing files: {sorted(missing)}")
    verify_manifest(staging_dir, "STAGING_MANIFEST.sha256")

    receipts = _read_csv(staging_dir / "staged_receipts.csv", policy.receipt_fields)
    observations = _read_csv(staging_dir / "staged_observations.csv", policy.observation_fields)
    coverage = _read_csv(staging_dir / "staged_coverage.csv", policy.coverage_fields)
    receipt_index = _index_by(receipts, "staged_receipt_id", "staged receipt")
    observation_index = _index_by(observations, "staged_observation_id", "staged observation")

    for staged_id, receipt in receipt_index.items():
        raw_relative = _safe_relative(receipt["raw_path"], label="raw_path")
        raw_path = staging_dir / raw_relative
        if not raw_path.is_file():
            raise MaterializationError(f"raw bytes missing for staged receipt {staged_id}")
        if sha256_file(raw_path) != receipt["raw_sha256"]:
            raise MaterializationError(f"raw_sha256 mismatch for staged receipt {staged_id}")
        if str(raw_path.stat().st_size) != str(receipt["byte_count"]):
            raise MaterializationError(f"byte_count mismatch for staged receipt {staged_id}")

    live_2026_count = 0
    for observation_id, observation in observation_index.items():
        if observation["staged_receipt_id"] not in receipt_index:
            raise MaterializationError(f"observation references unknown staged receipt: {observation_id}")
        if observation["quality_status"] not in QUALITY_STATUSES:
            raise MaterializationError(f"invalid staged quality_status: {observation_id}")
        if observation["period"] >= "2026-01":
            live_2026_count += 1
    if live_2026_count:
        raise MaterializationError("v0.10.6 materializer refuses live 2026 observations before constitutional transition")

    for row in coverage:
        if row["coverage_status"] not in COVERAGE_STATUSES:
            raise MaterializationError(f"invalid coverage_status: {row['coverage_id']}")
        staged_observation_id = row["staged_observation_id"]
        if row["coverage_status"] == "OBSERVED" and staged_observation_id not in observation_index:
            raise MaterializationError(f"observed coverage lacks staged observation: {row['coverage_id']}")
        if row["coverage_status"] != "OBSERVED" and staged_observation_id:
            raise MaterializationError(f"non-observed coverage must not point to observation: {row['coverage_id']}")

    return {
        "status": STATUS,
        "staging_receipt_count": len(receipts),
        "staging_observation_count": len(observations),
        "staging_coverage_row_count": len(coverage),
        "live_2026_observation_count": live_2026_count,
    }


def _observation_output_sha(row: Mapping[str, str]) -> str:
    payload = json.dumps(dict(sorted(row.items())), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def materialize_external_panel(
    policy_path: Path,
    replay_policy_path: Path,
    staging_dir: Path,
    output_dir: Path,
    *,
    created_at: str,
    repo_root: Path,
) -> dict[str, Any]:
    policy = MaterializationPolicy.load(policy_path)
    validate_staging_directory(policy_path, staging_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MaterializationError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_out = output_dir / "raw"
    raw_out.mkdir()

    receipts = _read_csv(staging_dir / "staged_receipts.csv", policy.receipt_fields)
    observations = _read_csv(staging_dir / "staged_observations.csv", policy.observation_fields)
    coverage = _read_csv(staging_dir / "staged_coverage.csv", policy.coverage_fields)

    receipt_id_map: dict[str, str] = {}
    materialized_receipts: list[dict[str, Any]] = []
    for index, receipt in enumerate(receipts, start=1):
        receipt_id = f"R{index:06d}"
        receipt_id_map[receipt["staged_receipt_id"]] = receipt_id
        extension = Path(receipt["raw_path"]).suffix or ".bin"
        raw_name = f"{receipt_id}_{receipt['raw_sha256'][:12]}{extension}"
        raw_relative = Path("raw") / raw_name
        shutil.copyfile(staging_dir / _safe_relative(receipt["raw_path"], label="raw_path"), output_dir / raw_relative)
        materialized = {key: receipt[key] for key in (
            "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at", "http_status",
            "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint"
        )}
        materialized["receipt_id"] = receipt_id
        materialized["raw_path"] = raw_relative.as_posix()
        materialized_receipts.append(materialized)

    materialized_observations: list[dict[str, Any]] = []
    observation_id_map: dict[str, str] = {}
    for index, observation in enumerate(observations, start=1):
        observation_id = f"O{index:06d}"
        observation_id_map[observation["staged_observation_id"]] = observation_id
        materialized = {key: observation[key] for key in (
            "dataset_role", "economy", "armilar_code", "classification", "category_or_division", "period",
            "unit", "value", "source_period_type", "parser_version", "quality_status"
        )}
        materialized["observation_id"] = observation_id
        materialized["receipt_id"] = receipt_id_map[observation["staged_receipt_id"]]
        materialized_observations.append(materialized)

    materialized_coverage: list[dict[str, Any]] = []
    for row in coverage:
        materialized = {key: row[key] for key in (
            "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status"
        )}
        staged_observation_id = row["staged_observation_id"]
        materialized["observation_id"] = observation_id_map.get(staged_observation_id, "") if staged_observation_id else ""
        materialized_coverage.append(materialized)

    materialized_lineage: list[dict[str, Any]] = []
    receipt_by_id = {row["receipt_id"]: row for row in materialized_receipts}
    for index, observation in enumerate(materialized_observations, start=1):
        receipt = receipt_by_id[observation["receipt_id"]]
        materialized_lineage.append({
            "lineage_id": f"L{index:06d}",
            "observation_id": observation["observation_id"],
            "receipt_id": observation["receipt_id"],
            "transformation_step": "materialize_staged_official_observation",
            "input_sha256": receipt["raw_sha256"],
            "output_sha256": _observation_output_sha(observation),
            "may_rewrite_history": "false",
        })

    _write_csv(output_dir / "raw_receipts.csv", (
        "receipt_id", "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at", "http_status",
        "raw_path", "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint"
    ), materialized_receipts)
    _write_csv(output_dir / "normalised_observations.csv", (
        "observation_id", "receipt_id", "dataset_role", "economy", "armilar_code", "classification", "category_or_division",
        "period", "unit", "value", "source_period_type", "parser_version", "quality_status"
    ), materialized_observations)
    _write_csv(output_dir / "dual_panel_coverage.csv", (
        "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status", "observation_id"
    ), materialized_coverage)
    _write_csv(output_dir / "dual_panel_lineage.csv", (
        "lineage_id", "observation_id", "receipt_id", "transformation_step", "input_sha256", "output_sha256", "may_rewrite_history"
    ), materialized_lineage)

    replay_module = _load_replay_module(repo_root)
    replay_policy = replay_module.ReplayPolicy.load(replay_policy_path)
    summary = {
        "status": PREDECESSOR_REPLAY_STATUS,
        "policy_version": "0.10.5",
        "created_at": created_at,
        "policy_sha256": replay_policy.policy_sha256,
        "predecessor_status": "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID",
        "external_artifact": True,
        "receipt_count": len(materialized_receipts),
        "observation_count": len(materialized_observations),
        "coverage_row_count": len(materialized_coverage),
        "lineage_row_count": len(materialized_lineage),
        "live_2026_observation_count": 0,
        "panel_verified_gate_open": False,
        "transition_backtest_executed": False,
        "selected_strategy": "NONE",
    }
    (output_dir / "panel_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output_dir, "PANEL_MANIFEST.sha256")
    replay_summary = replay_module.validate_external_panel_artifact(replay_policy_path, output_dir)
    if replay_summary["status"] != PREDECESSOR_REPLAY_STATUS:
        raise MaterializationError("materialized artifact did not pass v0.10.5 replay verification")
    return {
        "status": MATERIALIZED_STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "materialization_policy_sha256": sha256_file(policy_path),
        "replay_policy_sha256": replay_policy.policy_sha256,
        "staging_receipt_count": len(receipts),
        "materialized_receipt_count": len(materialized_receipts),
        "materialized_observation_count": len(materialized_observations),
        "materialized_coverage_row_count": len(materialized_coverage),
        "materialized_lineage_row_count": len(materialized_lineage),
        "materialized_artifact_status": replay_summary["status"],
        "manifest_entry_count": replay_summary["manifest_entry_count"],
        "panel_verified_gate_open": False,
        "transition_backtest_executed": False,
        "selected_strategy": "NONE",
        "next_milestone": NEXT_MILESTONE,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.6 ECOICOP dual-panel materialization runner")
    parser.add_argument("--policy", type=Path, default=Path("config/ecoicop_dual_panel_materialization_v0106.json"))
    parser.add_argument("--replay-policy", type=Path, default=REPLAY_POLICY)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--verify-staging", type=Path)
    parser.add_argument("--materialize-staging", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--created-at", default="2026-07-09T00:00:00Z")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    replay_policy = args.replay_policy if args.replay_policy.is_absolute() else root / args.replay_policy
    try:
        if args.verify_staging:
            summary = validate_staging_directory(policy_path, args.verify_staging)
        elif args.materialize_staging:
            if args.output_dir is None:
                raise MaterializationError("--output-dir is required with --materialize-staging")
            summary = materialize_external_panel(
                policy_path,
                replay_policy,
                args.materialize_staging,
                args.output_dir,
                created_at=args.created_at,
                repo_root=root,
            )
        else:
            policy = MaterializationPolicy.load(policy_path)
            predecessor = validate_predecessor(root)
            summary = {
                "status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "gate_count_open": sum(bool(value) for value in policy.gates.values()),
                "predecessor_status": predecessor["status"],
                "predecessor_policy_sha256": predecessor["policy_sha256"],
                "next_milestone": NEXT_MILESTONE,
            }
    except MaterializationError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_MATERIALIZATION_V0106_INVALID: {exc}") from exc
    print(summary["status"])
    for key in sorted(key for key in summary if key != "status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
