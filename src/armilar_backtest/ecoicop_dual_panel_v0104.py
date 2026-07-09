"""ECOICOP v1/v2 official dual-panel acquisition contract for ARMILAR v0.10.4.

This milestone prepares the replayable acquisition and verification surface for the
future empirical transition backtest.  It deliberately commits no official provider
bytes, no empirical observations and no 2026 ARM-O extension.  Live retrieval and
publication of acquired bytes must happen outside pull requests and must be replayed
against the contracts defined here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID"
VERSION = "0.10.4"
PREDECESSOR_STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
NEXT_MILESTONE = "V0105_EXECUTE_TRANSITION_BACKTEST_AFTER_PANEL_VERIFICATION"
EXPECTED_ECONOMIES = ("DE", "ES", "FR", "IT", "PT")
EXPECTED_LEGACY_CATEGORIES = tuple(f"CP{number:02d}" for number in range(1, 13))
EXPECTED_REPLACEMENT_DIVISIONS = tuple(f"CP{number:02d}" for number in range(1, 14))
EXPECTED_DATASET_ROLES = (
    "LEGACY_MONTHLY_INDEX",
    "LEGACY_ITEM_WEIGHTS",
    "REPLACEMENT_MONTHLY_INDEX_AND_RATES",
    "REPLACEMENT_ITEM_WEIGHTS",
    "CLASSIFICATION_AND_CORRESPONDENCE",
    "COUNTRY_COMPILATION_METADATA",
)
EXPECTED_DATASET_CODES = {
    "LEGACY_MONTHLY_INDEX": "prc_hicp_midx",
    "LEGACY_ITEM_WEIGHTS": "prc_hicp_inw",
    "REPLACEMENT_MONTHLY_INDEX_AND_RATES": "prc_hicp_minr",
    "REPLACEMENT_ITEM_WEIGHTS": "prc_hicp_iw",
    "CLASSIFICATION_AND_CORRESPONDENCE": "ECOICOP_V1_V2_CORRESPONDENCE",
    "COUNTRY_COMPILATION_METADATA": "prc_hicp_esms",
}
EXPECTED_OUTPUT_FILES = (
    "MANIFEST.sha256",
    "acquisition_request_register.csv",
    "dataset_receipt_contract.csv",
    "dual_panel_coverage_contract.csv",
    "dual_panel_lineage_contract.csv",
    "dual_panel_summary.json",
    "normalised_observation_contract.csv",
)
REQUEST_FIELDNAMES = (
    "request_id",
    "dataset_role",
    "provider",
    "dataset_code",
    "panel_kind",
    "classification",
    "economy",
    "armilar_code",
    "category_or_division",
    "unit",
    "time_window",
    "live_fetch_allowed_in_pr",
    "use_in_v0104",
)


class DualPanelError(ValueError):
    """Raised when the v0.10.4 dual-panel contract is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DualPanelError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise DualPanelError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise DualPanelError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _require_exact_keys(payload: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual_set = set(payload)
    if actual_set != expected_set:
        raise DualPanelError(
            f"{label} keys mismatch: missing={sorted(expected_set - actual_set)}, "
            f"extra={sorted(actual_set - expected_set)}"
        )


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DualPanelError(f"{label} must be a list")
    return value


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DualPanelError(f"{label} must be an object")
    return value


def _require_unique(values: Sequence[str], label: str) -> None:
    if len(set(values)) != len(values):
        raise DualPanelError(f"{label} contains duplicates")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in fieldnames})


@dataclass(frozen=True)
class DatasetContract:
    role: str
    provider: str
    dataset_code: str
    classification: str
    required_units: tuple[str, ...]
    time_window: str
    panel_kind: str
    required_for_v0104_replay: bool

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DatasetContract":
        _require_exact_keys(
            payload,
            (
                "role",
                "provider",
                "dataset_code",
                "classification",
                "required_units",
                "time_window",
                "panel_kind",
                "required_for_v0104_replay",
            ),
            "dataset contract",
        )
        contract = cls(
            role=str(payload["role"]),
            provider=str(payload["provider"]),
            dataset_code=str(payload["dataset_code"]),
            classification=str(payload["classification"]),
            required_units=tuple(str(item) for item in _require_list(payload["required_units"], "required_units")),
            time_window=str(payload["time_window"]),
            panel_kind=str(payload["panel_kind"]),
            required_for_v0104_replay=payload["required_for_v0104_replay"],
        )
        if contract.role not in EXPECTED_DATASET_ROLES:
            raise DualPanelError(f"unexpected dataset role: {contract.role}")
        if contract.dataset_code != EXPECTED_DATASET_CODES[contract.role]:
            raise DualPanelError(f"dataset code mismatch for {contract.role}")
        if not contract.required_units:
            raise DualPanelError(f"required units missing for {contract.role}")
        _require_unique(contract.required_units, f"units for {contract.role}")
        if not isinstance(contract.required_for_v0104_replay, bool):
            raise DualPanelError(f"required_for_v0104_replay must be boolean for {contract.role}")
        if not contract.required_for_v0104_replay:
            raise DualPanelError(f"all dataset contracts are replay-required in v0.10.4: {contract.role}")
        return contract


@dataclass(frozen=True)
class DualPanelPolicy:
    path: Path
    payload: dict[str, Any]
    dataset_contracts: tuple[DatasetContract, ...]

    @classmethod
    def load(cls, path: Path | str) -> "DualPanelPolicy":
        policy_path = Path(path).resolve()
        payload = _read_json(policy_path)
        validate_policy_document(payload)
        contracts = tuple(
            DatasetContract.from_payload(item)
            for item in _require_list(payload["dataset_contracts"], "dataset_contracts")
        )
        if tuple(contract.role for contract in contracts) != EXPECTED_DATASET_ROLES:
            raise DualPanelError("dataset roles must be ordered and complete")
        return cls(path=policy_path, payload=payload, dataset_contracts=contracts)

    @property
    def policy_sha256(self) -> str:
        return sha256_file(self.path)

    @property
    def gates(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["gates"], "gates")

    @property
    def universe(self) -> Mapping[str, Any]:
        return _require_dict(self.payload["universe"], "universe")


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    _require_exact_keys(
        policy,
        (
            "policy_id",
            "policy_version",
            "status",
            "predecessor_status",
            "predecessor_policy",
            "predecessor_mapping",
            "scope",
            "universe",
            "period_policy",
            "dataset_contracts",
            "raw_receipt_contract",
            "normalized_observation_contract",
            "coverage_contract",
            "output_files",
            "gates",
            "next_milestone",
        ),
        "dual panel policy",
    )
    if policy["policy_version"] != VERSION:
        raise DualPanelError("policy version mismatch")
    if policy["status"] != STATUS:
        raise DualPanelError("status mismatch")
    if policy["predecessor_status"] != PREDECESSOR_STATUS:
        raise DualPanelError("predecessor status mismatch")
    if policy["next_milestone"] != NEXT_MILESTONE:
        raise DualPanelError("next milestone mismatch")

    scope = _require_dict(policy["scope"], "scope")
    if scope.get("define_acquisition_and_replay_contract") is not True:
        raise DualPanelError("v0.10.4 must define the acquisition and replay contract")
    forbidden_scope = [key for key, value in scope.items() if key != "define_acquisition_and_replay_contract" and bool(value)]
    if forbidden_scope:
        raise DualPanelError(f"forbidden v0.10.4 scope enabled: {forbidden_scope}")

    universe = _require_dict(policy["universe"], "universe")
    economies = _require_list(universe.get("economies"), "economies")
    if tuple(item.get("eurostat_code") for item in economies) != EXPECTED_ECONOMIES:
        raise DualPanelError("economy universe differs from the v0.8.7 ARM-O universe")
    if tuple(universe.get("legacy_categories", [])) != EXPECTED_LEGACY_CATEGORIES:
        raise DualPanelError("legacy category register mismatch")
    if tuple(universe.get("replacement_divisions", [])) != EXPECTED_REPLACEMENT_DIVISIONS:
        raise DualPanelError("replacement division register mismatch")

    period_policy = _require_dict(policy["period_policy"], "period_policy")
    if period_policy.get("committed_live_2026_observations_allowed") is not False:
        raise DualPanelError("committed live 2026 observations remain forbidden in v0.10.4")
    if period_policy.get("legacy_period_end") != "2025-12":
        raise DualPanelError("legacy period must stop at the 2025 classification boundary")

    contracts = [DatasetContract.from_payload(item) for item in _require_list(policy["dataset_contracts"], "dataset_contracts")]
    if tuple(contract.role for contract in contracts) != EXPECTED_DATASET_ROLES:
        raise DualPanelError("dataset roles mismatch")

    output_files = tuple(str(item) for item in _require_list(policy["output_files"], "output_files"))
    if tuple(sorted(output_files)) != EXPECTED_OUTPUT_FILES:
        raise DualPanelError("output file register mismatch")

    gates = _require_dict(policy["gates"], "gates")
    open_gates = [key for key, value in gates.items() if bool(value)]
    if open_gates:
        raise DualPanelError(f"v0.10.4 gates must remain closed: {open_gates}")

    raw_fields = tuple(_require_list(policy["raw_receipt_contract"].get("required_fields"), "raw receipt fields"))
    for required in ("receipt_id", "raw_path", "raw_sha256", "retrieved_at", "query_fingerprint"):
        if required not in raw_fields:
            raise DualPanelError(f"raw receipt contract missing {required}")
    observation_contract = _require_dict(policy["normalized_observation_contract"], "observation contract")
    forbidden_fields = set(_require_list(observation_contract.get("forbidden_fields"), "forbidden fields"))
    if not {"transition_strategy", "arm_o_2026_value", "monetary_value"}.issubset(forbidden_fields):
        raise DualPanelError("observation contract must forbid transition and monetary fields")


def acquisition_requests(policy: DualPanelPolicy) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    economies = policy.universe["economies"]
    for contract in policy.dataset_contracts:
        if contract.role in {"CLASSIFICATION_AND_CORRESPONDENCE", "COUNTRY_COMPILATION_METADATA"}:
            category_values = ("NOT_APPLICABLE",)
            economy_values = economies if contract.role == "COUNTRY_COMPILATION_METADATA" else [
                {"eurostat_code": "EUROSTAT", "armilar_code": "EUROSTAT", "name": "Eurostat"}
            ]
        elif contract.role.startswith("LEGACY"):
            category_values = EXPECTED_LEGACY_CATEGORIES
            economy_values = economies
        else:
            category_values = EXPECTED_REPLACEMENT_DIVISIONS
            economy_values = economies
        for economy in economy_values:
            for category in category_values:
                for unit in contract.required_units:
                    request_id = f"{contract.role}:{economy['eurostat_code']}:{category}:{unit}"
                    rows.append(
                        {
                            "request_id": request_id,
                            "dataset_role": contract.role,
                            "provider": contract.provider,
                            "dataset_code": contract.dataset_code,
                            "panel_kind": contract.panel_kind,
                            "classification": contract.classification,
                            "economy": economy["eurostat_code"],
                            "armilar_code": economy["armilar_code"],
                            "category_or_division": category,
                            "unit": unit,
                            "time_window": contract.time_window,
                            "live_fetch_allowed_in_pr": "false",
                            "use_in_v0104": "ACQUISITION_AND_REPLAY_REQUIREMENT",
                        }
                    )
    return tuple(rows)


def _receipt_contract_rows(policy: DualPanelPolicy) -> tuple[dict[str, str], ...]:
    fields = policy.payload["raw_receipt_contract"]["required_fields"]
    return tuple({"field": field, "required": "true", "source": "raw_receipt_contract"} for field in fields)


def _observation_contract_rows(policy: DualPanelPolicy) -> tuple[dict[str, str], ...]:
    rows = [
        {"field": field, "required": "true", "forbidden": "false"}
        for field in policy.payload["normalized_observation_contract"]["required_fields"]
    ]
    rows.extend(
        {"field": field, "required": "false", "forbidden": "true"}
        for field in policy.payload["normalized_observation_contract"]["forbidden_fields"]
    )
    return tuple(rows)


def _coverage_rows(policy: DualPanelPolicy) -> tuple[dict[str, str], ...]:
    coverage = policy.payload["coverage_contract"]
    rows: list[dict[str, str]] = []
    for dimension in coverage["required_dimensions"]:
        rows.append({"kind": "dimension", "value": dimension, "required": "true"})
    for status in coverage["required_statuses"]:
        rows.append({"kind": "status", "value": status, "required": "true"})
    return tuple(rows)


def _lineage_rows(policy: DualPanelPolicy) -> tuple[dict[str, str], ...]:
    return (
        {
            "lineage_step": "raw_provider_response",
            "required_evidence": "exact bytes, retrieval timestamp, request URL, SHA-256",
            "may_rewrite_history": "false",
        },
        {
            "lineage_step": "normalised_observation",
            "required_evidence": "raw receipt id, parser version, classification, unit, period",
            "may_rewrite_history": "false",
        },
        {
            "lineage_step": "dual_panel_coverage",
            "required_evidence": "explicit OBSERVED/MISSING/QUARANTINED status for each declared cell",
            "may_rewrite_history": "false",
        },
        {
            "lineage_step": "transition_backtest_input",
            "required_evidence": "verified dual panel only after v0.10.4 replay passes",
            "may_rewrite_history": "false",
        },
    )


def _write_manifest(output_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(output_dir.iterdir()):
        if path.name == "MANIFEST.sha256" or not path.is_file():
            continue
        hashes[path.name] = sha256_file(path)
    with (output_dir / "MANIFEST.sha256").open("w", encoding="utf-8", newline="") as handle:
        for name, digest in hashes.items():
            handle.write(f"{digest}  {name}\n")
    hashes["MANIFEST.sha256"] = sha256_file(output_dir / "MANIFEST.sha256")
    return hashes


def build_dual_panel_scaffold(policy_path: Path, output_dir: Path, *, created_at: str) -> dict[str, Any]:
    policy = DualPanelPolicy.load(policy_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DualPanelError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    requests = acquisition_requests(policy)
    _write_csv(output_dir / "acquisition_request_register.csv", REQUEST_FIELDNAMES, requests)
    _write_csv(
        output_dir / "dataset_receipt_contract.csv",
        ("field", "required", "source"),
        _receipt_contract_rows(policy),
    )
    _write_csv(
        output_dir / "normalised_observation_contract.csv",
        ("field", "required", "forbidden"),
        _observation_contract_rows(policy),
    )
    _write_csv(
        output_dir / "dual_panel_coverage_contract.csv",
        ("kind", "value", "required"),
        _coverage_rows(policy),
    )
    _write_csv(
        output_dir / "dual_panel_lineage_contract.csv",
        ("lineage_step", "required_evidence", "may_rewrite_history"),
        _lineage_rows(policy),
    )
    summary = {
        "status": STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "policy_sha256": policy.policy_sha256,
        "dataset_contract_count": len(policy.dataset_contracts),
        "economy_count": len(policy.universe["economies"]),
        "legacy_category_count": len(policy.universe["legacy_categories"]),
        "replacement_division_count": len(policy.universe["replacement_divisions"]),
        "request_count": len(requests),
        "committed_observation_count": 0,
        "live_2026_observation_count": 0,
        "gate_count_open": sum(bool(value) for value in policy.gates.values()),
        "output_file_count": len(EXPECTED_OUTPUT_FILES),
        "next_milestone": NEXT_MILESTONE,
    }
    (output_dir / "dual_panel_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = _write_manifest(output_dir)
    summary["audit_manifest_sha256"] = manifest["MANIFEST.sha256"]
    (output_dir / "dual_panel_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = _write_manifest(output_dir)
    summary["audit_manifest_sha256"] = manifest["MANIFEST.sha256"]
    (output_dir / "dual_panel_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_manifest(output_dir)
    return summary


def verify_dual_panel_scaffold(policy_path: Path, output_dir: Path) -> dict[str, Any]:
    policy = DualPanelPolicy.load(policy_path)
    expected = set(EXPECTED_OUTPUT_FILES)
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual != expected:
        raise DualPanelError(f"audit file set mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    manifest_path = output_dir / "MANIFEST.sha256"
    manifest: dict[str, str] = {}
    with manifest_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split("  ")
            if len(parts) != 2:
                raise DualPanelError(f"invalid manifest line {line_number}")
            digest, name = parts
            manifest[name] = digest
    expected_manifest_files = expected - {"MANIFEST.sha256"}
    if set(manifest) != expected_manifest_files:
        raise DualPanelError("manifest file set mismatch")
    for name, digest in manifest.items():
        if sha256_file(output_dir / name) != digest:
            raise DualPanelError(f"manifest hash mismatch: {name}")
    summary = _read_json(output_dir / "dual_panel_summary.json")
    if summary.get("status") != STATUS:
        raise DualPanelError("summary status mismatch")
    if summary.get("policy_sha256") != policy.policy_sha256:
        raise DualPanelError("summary policy hash mismatch")
    if summary.get("committed_observation_count") != 0:
        raise DualPanelError("v0.10.4 scaffold must not commit observations")
    if summary.get("live_2026_observation_count") != 0:
        raise DualPanelError("v0.10.4 scaffold must not commit live 2026 observations")
    if summary.get("gate_count_open") != 0:
        raise DualPanelError("v0.10.4 scaffold must not open gates")
    with (output_dir / "acquisition_request_register.csv").open(encoding="utf-8", newline="") as handle:
        requests = list(csv.DictReader(handle))
    if len(requests) != summary.get("request_count"):
        raise DualPanelError("request count mismatch")
    if any(row["live_fetch_allowed_in_pr"] != "false" for row in requests):
        raise DualPanelError("live fetch cannot be allowed in PR request register")
    return summary


def _default_policy(root: Path) -> Path:
    return root / "config" / "ecoicop_dual_panel_v0104.json"


def _cmd_validate_policy(args: argparse.Namespace) -> int:
    policy = DualPanelPolicy.load(args.policy)
    print(STATUS)
    print(f"policy_sha256={policy.policy_sha256}")
    print(f"dataset_contract_count={len(policy.dataset_contracts)}")
    print(f"economy_count={len(policy.universe['economies'])}")
    print(f"legacy_category_count={len(policy.universe['legacy_categories'])}")
    print(f"replacement_division_count={len(policy.universe['replacement_divisions'])}")
    print(f"gate_count_open={sum(bool(value) for value in policy.gates.values())}")
    return 0


def _cmd_build_scaffold(args: argparse.Namespace) -> int:
    summary = build_dual_panel_scaffold(args.policy, args.output_dir, created_at=args.created_at)
    print(STATUS)
    print(f"request_count={summary['request_count']}")
    print(f"committed_observation_count={summary['committed_observation_count']}")
    print(f"live_2026_observation_count={summary['live_2026_observation_count']}")
    print(f"audit_manifest_sha256={summary['audit_manifest_sha256']}")
    return 0


def _cmd_verify_scaffold(args: argparse.Namespace) -> int:
    summary = verify_dual_panel_scaffold(args.policy, args.output_dir)
    print(STATUS)
    print(f"request_count={summary['request_count']}")
    print(f"committed_observation_count={summary['committed_observation_count']}")
    print(f"live_2026_observation_count={summary['live_2026_observation_count']}")
    print(f"audit_manifest_sha256={summary.get('audit_manifest_sha256')}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARMILAR v0.10.4 ECOICOP dual-panel contract")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-policy")
    validate.add_argument("--policy", type=Path, default=None)
    validate.set_defaults(func=_cmd_validate_policy)

    build = subparsers.add_parser("build-scaffold")
    build.add_argument("--policy", type=Path, default=None)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--created-at", default="2026-07-09T00:00:00Z")
    build.set_defaults(func=_cmd_build_scaffold)

    verify = subparsers.add_parser("verify-scaffold")
    verify.add_argument("--policy", type=Path, default=None)
    verify.add_argument("--output-dir", type=Path, required=True)
    verify.set_defaults(func=_cmd_verify_scaffold)

    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    if args.policy is None:
        args.policy = _default_policy(root)
    else:
        args.policy = args.policy.resolve()
    try:
        return args.func(args)
    except DualPanelError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_V0104_INVALID: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
