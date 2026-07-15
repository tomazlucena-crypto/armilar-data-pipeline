"""ECOICOP v1/v2 dual-panel replay verifier for ARMILAR v0.10.5.

This milestone defines and tests the offline verifier that a future materialised
official dual panel must satisfy before any transition backtest can be executed.
It deliberately commits no provider bytes, no empirical panel and no backtest
results.  External artifacts may be verified by this module after a non-PR live
acquisition run has preserved raw bytes, hashes, coverage and lineage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID"
EXTERNAL_REPLAY_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
VERSION = "0.10.5"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID"
NEXT_MILESTONE = "V0106_MATERIALIZE_AND_VERIFY_EXTERNAL_DUAL_PANEL_BEFORE_BACKTEST"
EXPECTED_FILES = (
    "PANEL_MANIFEST.sha256",
    "dual_panel_coverage.csv",
    "dual_panel_lineage.csv",
    "normalised_observations.csv",
    "panel_summary.json",
    "raw_receipts.csv",
)
QUALITY_STATUSES = ("OBSERVED_OFFICIAL", "MISSING", "QUARANTINED")
COVERAGE_STATUSES = ("OBSERVED", "MISSING", "QUARANTINED")
FORBIDDEN_SUMMARY_VALUES = {
    "panel_verified_gate_open": True,
    "transition_backtest_executed": True,
    "selected_strategy": {"T0", "T1", "T2", "T3"},
}


class ReplayVerifierError(ValueError):
    """Raised when the v0.10.5 replay verifier contract is violated."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayVerifierError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ReplayVerifierError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ReplayVerifierError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _require_exact_keys(payload: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual_set = set(payload)
    if actual_set != expected_set:
        raise ReplayVerifierError(
            f"{label} keys mismatch: missing={sorted(expected_set-actual_set)}, "
            f"extra={sorted(actual_set-expected_set)}"
        )


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayVerifierError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReplayVerifierError(f"{label} must be a list")
    return value


def _require_unique(values: Sequence[str], label: str) -> None:
    if len(set(values)) != len(values):
        raise ReplayVerifierError(f"{label} contains duplicates")


def _read_csv(path: Path, required_fields: Sequence[str]) -> tuple[dict[str, str], ...]:
    if not path.is_file():
        raise ReplayVerifierError(f"required CSV missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [field for field in required_fields if field not in fieldnames]
        if missing:
            raise ReplayVerifierError(f"{path.name} missing fields: {missing}")
        rows = tuple({key: (value or "") for key, value in row.items()} for row in reader)
    return rows


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


@dataclass(frozen=True)
class ReplayPolicy:
    path: Path
    payload: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "ReplayPolicy":
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
    def required_files(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.payload["required_artifact_files"])

    @property
    def raw_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.payload["raw_receipts_contract"]["required_fields"])

    @property
    def observation_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.payload["normalised_observations_contract"]["required_fields"])

    @property
    def coverage_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.payload["coverage_contract"]["required_fields"])

    @property
    def lineage_fields(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.payload["lineage_contract"]["required_fields"])


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    _require_exact_keys(
        policy,
        (
            "policy_id",
            "policy_version",
            "status",
            "predecessor_status",
            "predecessor_policy",
            "scope",
            "artifact_boundary",
            "required_artifact_files",
            "raw_receipts_contract",
            "normalised_observations_contract",
            "coverage_contract",
            "lineage_contract",
            "panel_summary_contract",
            "gates",
            "next_milestone",
        ),
        "replay policy",
    )
    if policy["policy_version"] != VERSION:
        raise ReplayVerifierError("policy version mismatch")
    if policy["status"] != STATUS:
        raise ReplayVerifierError("policy status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise ReplayVerifierError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise ReplayVerifierError("next milestone mismatch")
    files = tuple(sorted(str(item) for item in _require_list(policy["required_artifact_files"], "required files")))
    if files != EXPECTED_FILES:
        raise ReplayVerifierError("required artifact files mismatch")
    _require_unique(files, "required artifact files")

    scope = _require_dict(policy["scope"], "scope")
    if scope.get("define_external_panel_replay_verifier") is not True:
        raise ReplayVerifierError("v0.10.5 must define the replay verifier")
    forbidden_scope = [key for key, value in scope.items() if key != "define_external_panel_replay_verifier" and bool(value)]
    if forbidden_scope:
        raise ReplayVerifierError(f"forbidden v0.10.5 scope enabled: {forbidden_scope}")

    boundary = _require_dict(policy["artifact_boundary"], "artifact boundary")
    if boundary.get("official_bytes_committed_in_code_pr") is not False:
        raise ReplayVerifierError("official bytes must not be committed in the code PR")
    if boundary.get("external_artifact_required_for_panel_verification") is not True:
        raise ReplayVerifierError("real panel verification must require an external artifact")
    if boundary.get("public_latest_modification_allowed") is not False:
        raise ReplayVerifierError("public/latest remains frozen in v0.10.5")

    raw_fields = tuple(str(item) for item in policy["raw_receipts_contract"]["required_fields"])
    for required in ("receipt_id", "raw_path", "raw_sha256", "retrieved_at", "query_fingerprint"):
        if required not in raw_fields:
            raise ReplayVerifierError(f"raw receipts contract missing {required}")
    observation = _require_dict(policy["normalised_observations_contract"], "observation contract")
    allowed_quality = tuple(str(item) for item in observation["allowed_quality_statuses"])
    if allowed_quality != QUALITY_STATUSES:
        raise ReplayVerifierError("quality status register mismatch")
    forbidden = set(str(item) for item in observation["forbidden_fields"])
    if not {"transition_strategy", "selected_strategy", "arm_o_2026_value", "monetary_value"}.issubset(forbidden):
        raise ReplayVerifierError("observation contract must forbid transition and monetary fields")
    coverage_statuses = tuple(str(item) for item in policy["coverage_contract"]["allowed_statuses"])
    if coverage_statuses != COVERAGE_STATUSES:
        raise ReplayVerifierError("coverage status register mismatch")
    gates = _require_dict(policy["gates"], "gates")
    open_gates = [key for key, value in gates.items() if bool(value)]
    if open_gates:
        raise ReplayVerifierError(f"v0.10.5 gates must remain closed: {open_gates}")


def build_replay_contract_scaffold(policy_path: Path, output_dir: Path, *, created_at: str) -> dict[str, Any]:
    policy = ReplayPolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReplayVerifierError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "artifact_file_contract.csv", ("file_name", "required", "committed_in_pr"), (
        {"file_name": name, "required": "true", "committed_in_pr": "false"} for name in policy.required_files
    ))
    _write_csv(output_dir / "raw_receipts_contract.csv", ("field", "required"), (
        {"field": field, "required": "true"} for field in policy.raw_fields
    ))
    _write_csv(output_dir / "normalised_observations_contract.csv", ("field", "required"), (
        {"field": field, "required": "true"} for field in policy.observation_fields
    ))
    _write_csv(output_dir / "coverage_contract.csv", ("field", "required"), (
        {"field": field, "required": "true"} for field in policy.coverage_fields
    ))
    _write_csv(output_dir / "lineage_contract.csv", ("field", "required"), (
        {"field": field, "required": "true"} for field in policy.lineage_fields
    ))
    summary = {
        "status": STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "policy_sha256": policy.policy_sha256,
        "predecessor_status": PREDECESSOR_STATUS,
        "external_artifact": False,
        "receipt_count": 0,
        "observation_count": 0,
        "coverage_row_count": 0,
        "lineage_row_count": 0,
        "live_2026_observation_count": 0,
        "panel_verified_gate_open": False,
        "transition_backtest_executed": False,
        "selected_strategy": "NONE",
        "next_milestone": NEXT_MILESTONE,
    }
    (output_dir / "replay_verifier_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_manifest(output_dir, manifest_name="CONTRACT_MANIFEST.sha256")
    return summary


def verify_replay_contract_scaffold(policy_path: Path, scaffold_dir: Path) -> dict[str, Any]:
    policy = ReplayPolicy.load(policy_path)
    summary_path = scaffold_dir / "replay_verifier_summary.json"
    summary = _read_json(summary_path)
    if summary.get("status") != STATUS:
        raise ReplayVerifierError("scaffold summary status mismatch")
    if summary.get("policy_sha256") != policy.policy_sha256:
        raise ReplayVerifierError("scaffold policy hash mismatch")
    if summary.get("external_artifact") is not False:
        raise ReplayVerifierError("contract scaffold must not pretend to be an external panel")
    if summary.get("receipt_count") != 0 or summary.get("observation_count") != 0:
        raise ReplayVerifierError("contract scaffold must not contain empirical rows")
    verify_manifest(scaffold_dir, manifest_name="CONTRACT_MANIFEST.sha256")
    return summary


def _write_manifest(directory: Path, *, manifest_name: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.name == manifest_name or not path.is_file():
            continue
        hashes[path.name] = sha256_file(path)
    with (directory / manifest_name).open("w", encoding="utf-8", newline="") as handle:
        for name, digest in sorted(hashes.items()):
            handle.write(f"{digest}  {name}\n")
    hashes[manifest_name] = sha256_file(directory / manifest_name)
    return hashes


def verify_manifest(directory: Path, *, manifest_name: str = "PANEL_MANIFEST.sha256") -> dict[str, str]:
    manifest_path = directory / manifest_name
    if not manifest_path.is_file():
        raise ReplayVerifierError(f"manifest missing: {manifest_name}")
    hashes: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise ReplayVerifierError(f"invalid manifest line {line_number}")
        digest, relative = parts
        if relative in hashes:
            raise ReplayVerifierError(f"duplicate manifest entry: {relative}")
        path = directory / relative
        if not path.is_file():
            raise ReplayVerifierError(f"manifest target missing: {relative}")
        actual = sha256_file(path)
        if actual != digest:
            raise ReplayVerifierError(f"manifest hash mismatch: {relative}")
        hashes[relative] = digest
    return hashes


def _index_by(rows: Sequence[Mapping[str, str]], key: str, label: str) -> dict[str, Mapping[str, str]]:
    indexed: dict[str, Mapping[str, str]] = {}
    for row in rows:
        value = row.get(key, "")
        if not value:
            raise ReplayVerifierError(f"{label} row missing {key}")
        if value in indexed:
            raise ReplayVerifierError(f"duplicate {label} key: {value}")
        indexed[value] = row
    return indexed


def validate_external_panel_artifact(policy_path: Path, artifact_dir: Path) -> dict[str, Any]:
    policy = ReplayPolicy.load(policy_path)
    artifact_dir = artifact_dir.resolve()
    if not artifact_dir.is_dir():
        raise ReplayVerifierError(f"external artifact directory missing: {artifact_dir}")
    actual_files = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    expected = set(policy.required_files)
    if expected - actual_files:
        raise ReplayVerifierError(f"external artifact missing files: {sorted(expected-actual_files)}")
    verify_manifest(artifact_dir)

    summary = _read_json(artifact_dir / "panel_summary.json")
    required_summary = tuple(policy.payload["panel_summary_contract"]["required_fields"])
    missing_summary = [field for field in required_summary if field not in summary]
    if missing_summary:
        raise ReplayVerifierError(f"panel summary missing fields: {missing_summary}")
    if summary.get("status") != EXTERNAL_REPLAY_STATUS:
        raise ReplayVerifierError("external artifact summary status mismatch")
    if summary.get("policy_version") != VERSION:
        raise ReplayVerifierError("external artifact policy version mismatch")
    if summary.get("policy_sha256") != policy.policy_sha256:
        raise ReplayVerifierError("external artifact policy hash mismatch")
    if summary.get("predecessor_status") != PREDECESSOR_STATUS:
        raise ReplayVerifierError("external artifact predecessor status mismatch")
    if summary.get("external_artifact") is not True:
        raise ReplayVerifierError("external panel must be marked as an external artifact")
    if summary.get("live_2026_observation_count") != 0:
        raise ReplayVerifierError("v0.10.5 external verifier does not accept live 2026 observations")
    if summary.get("panel_verified_gate_open") is not False:
        raise ReplayVerifierError("v0.10.5 must not open the panel verified gate")
    if summary.get("transition_backtest_executed") is not False:
        raise ReplayVerifierError("v0.10.5 must not execute the transition backtest")
    if summary.get("selected_strategy") != "NONE":
        raise ReplayVerifierError("v0.10.5 must not select a transition strategy")

    receipt_rows = _read_csv(artifact_dir / "raw_receipts.csv", policy.raw_fields)
    observation_rows = _read_csv(artifact_dir / "normalised_observations.csv", policy.observation_fields)
    coverage_rows = _read_csv(artifact_dir / "dual_panel_coverage.csv", policy.coverage_fields)
    lineage_rows = _read_csv(artifact_dir / "dual_panel_lineage.csv", policy.lineage_fields)

    receipts = _index_by(receipt_rows, "receipt_id", "receipt")
    observations = _index_by(observation_rows, "observation_id", "observation")
    coverage_ids = _index_by(coverage_rows, "coverage_id", "coverage")
    lineage_ids = _index_by(lineage_rows, "lineage_id", "lineage")
    del coverage_ids, lineage_ids

    for receipt_id, receipt in receipts.items():
        raw_relative = receipt["raw_path"]
        if Path(raw_relative).is_absolute() or ".." in Path(raw_relative).parts:
            raise ReplayVerifierError(f"raw_path must be safe and relative: {receipt_id}")
        raw_path = artifact_dir / raw_relative
        if not raw_path.is_file():
            raise ReplayVerifierError(f"raw bytes missing for receipt {receipt_id}: {raw_relative}")
        if sha256_file(raw_path) != receipt["raw_sha256"]:
            raise ReplayVerifierError(f"raw_sha256 mismatch for receipt {receipt_id}")
        if str(raw_path.stat().st_size) != str(receipt["byte_count"]):
            raise ReplayVerifierError(f"byte_count mismatch for receipt {receipt_id}")

    for observation_id, observation in observations.items():
        if observation["receipt_id"] not in receipts:
            raise ReplayVerifierError(f"observation references unknown receipt: {observation_id}")
        if observation["quality_status"] not in QUALITY_STATUSES:
            raise ReplayVerifierError(f"invalid quality_status for observation: {observation_id}")
        for forbidden in policy.payload["normalised_observations_contract"]["forbidden_fields"]:
            if forbidden in observation and observation.get(forbidden):
                raise ReplayVerifierError(f"forbidden observation field populated: {forbidden}")
        if observation["period"] >= "2026-01":
            raise ReplayVerifierError("v0.10.5 verifier refuses live 2026 observations")

    for coverage in coverage_rows:
        if coverage["coverage_status"] not in COVERAGE_STATUSES:
            raise ReplayVerifierError(f"invalid coverage status: {coverage['coverage_id']}")
        observation_id = coverage["observation_id"]
        if coverage["coverage_status"] == "OBSERVED" and observation_id not in observations:
            raise ReplayVerifierError(f"observed coverage lacks observation: {coverage['coverage_id']}")
        if coverage["coverage_status"] != "OBSERVED" and observation_id:
            raise ReplayVerifierError(f"non-observed coverage must not point to an observation: {coverage['coverage_id']}")

    for lineage in lineage_rows:
        if lineage["observation_id"] not in observations:
            raise ReplayVerifierError(f"lineage references unknown observation: {lineage['lineage_id']}")
        if lineage["receipt_id"] not in receipts:
            raise ReplayVerifierError(f"lineage references unknown receipt: {lineage['lineage_id']}")
        if lineage["may_rewrite_history"] != "false":
            raise ReplayVerifierError(f"lineage may_rewrite_history must be false: {lineage['lineage_id']}")

    counts = {
        "receipt_count": len(receipt_rows),
        "observation_count": len(observation_rows),
        "coverage_row_count": len(coverage_rows),
        "lineage_row_count": len(lineage_rows),
    }
    for field, expected_count in counts.items():
        if summary.get(field) != expected_count:
            raise ReplayVerifierError(f"panel summary {field} mismatch")

    result = dict(summary)
    result["status"] = EXTERNAL_REPLAY_STATUS
    result["manifest_entry_count"] = len(verify_manifest(artifact_dir))
    return result


def _load_predecessor_module(root: Path):
    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_v0104.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_v0104_for_v0105", module_path)
    if spec is None or spec.loader is None:
        raise ReplayVerifierError("cannot import v0.10.4 predecessor module")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_predecessor(root: Path) -> dict[str, str]:
    module = _load_predecessor_module(root)
    if getattr(module, "STATUS", None) != PREDECESSOR_STATUS:
        raise ReplayVerifierError("v0.10.4 predecessor status mismatch")
    result = module.DualPanelPolicy.load(root / "config" / "ecoicop_dual_panel_v0104.json")
    with tempfile.TemporaryDirectory(prefix="armilar_v0104_predecessor_") as tmp:
        out = Path(tmp) / "scaffold"
        summary = module.build_dual_panel_scaffold(
            root / "config" / "ecoicop_dual_panel_v0104.json",
            out,
            created_at="2026-07-09T00:00:00Z",
        )
        replay = module.verify_dual_panel_scaffold(root / "config" / "ecoicop_dual_panel_v0104.json", out)
    if summary != replay:
        raise ReplayVerifierError("v0.10.4 predecessor scaffold is not reproducible")
    return {"status": PREDECESSOR_STATUS, "policy_sha256": result.policy_sha256}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.5 ECOICOP dual-panel replay verifier")
    parser.add_argument("--policy", type=Path, default=Path("config/ecoicop_dual_panel_replay_v0105.json"))
    parser.add_argument("--build-contract", type=Path)
    parser.add_argument("--verify-contract", type=Path)
    parser.add_argument("--verify-external-panel", type=Path)
    parser.add_argument("--created-at", default="2026-07-09T00:00:00Z")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.build_contract:
            summary = build_replay_contract_scaffold(args.policy, args.build_contract, created_at=args.created_at)
        elif args.verify_contract:
            summary = verify_replay_contract_scaffold(args.policy, args.verify_contract)
        elif args.verify_external_panel:
            summary = validate_external_panel_artifact(args.policy, args.verify_external_panel)
        else:
            policy = ReplayPolicy.load(args.policy)
            summary = {
                "status": STATUS,
                "policy_version": VERSION,
                "policy_sha256": policy.policy_sha256,
                "required_artifact_file_count": len(policy.required_files),
                "gate_count_open": sum(bool(value) for value in policy.gates.values()),
                "next_milestone": NEXT_MILESTONE,
            }
    except ReplayVerifierError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_REPLAY_V0105_INVALID: {exc}") from exc
    print(summary["status"])
    for key in sorted(key for key in summary if key != "status"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
