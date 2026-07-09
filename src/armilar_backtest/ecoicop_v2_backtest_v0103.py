"""Executable protocol for the ARMILAR ECOICOP v1/v2 transition backtest.

Version 0.10.3 defines contracts only. It does not acquire observations, execute an
empirical backtest, select a transition strategy, amend the constitution, or extend
ARM-O into 2026.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
VERSION = "0.10.3"
NEXT_MILESTONE = "V0104_DUAL_PANEL_ACQUISITION_AND_VERIFICATION"

ALLOWED_MAPPING_STATES = (
    "EXACT_EQUIVALENCE",
    "DETERMINISTIC_AGGREGATION",
    "SPLIT_REQUIRES_EVIDENCE",
    "MATERIAL_RECLASSIFICATION",
    "NO_VALID_AUTOMATIC_MAPPING",
)
EXPECTED_STRATEGIES = ("T0", "T1", "T2", "T3")
EXPECTED_REPLACEMENT_CODES = tuple(f"CP{number:02d}" for number in range(1, 14))
EXPECTED_LEGACY_CODES = tuple(f"CP{number:02d}" for number in range(1, 13))
EXPECTED_DATASET_ROLES = (
    "LEGACY_MONTHLY_INDEX",
    "LEGACY_ITEM_WEIGHTS",
    "REPLACEMENT_MONTHLY_INDEX_AND_RATES",
    "REPLACEMENT_ITEM_WEIGHTS",
    "REPLACEMENT_FIRST_PUBLISHED_DATA",
    "CLASSIFICATION_AND_CORRESPONDENCE",
    "COUNTRY_COMPILATION_METADATA",
)
EXPECTED_TRANSFORMATION_DIMENSIONS = (
    "CLASSIFICATION",
    "INDEX_REFERENCE_BASE",
    "WEIGHTS",
    "PRODUCT_COVERAGE",
    "RETROSPECTIVE_RECONSTRUCTION",
    "LINKING_METHOD",
)
EXPECTED_METRICS = (
    "LEVEL_DISCONTINUITY_BP",
    "MONTHLY_INFLATION_DIFFERENCE_BP",
    "ANNUAL_INFLATION_DIFFERENCE_BP",
    "CONTRIBUTION_L1_DIFFERENCE_BP",
    "ECONOMY_RMSE_BP",
    "CATEGORY_RMSE_BP",
    "WORLD_AGGREGATE_RMSE_BP",
    "LINK_PERIOD_SENSITIVITY_BP",
    "CP08_IMPACT_BP",
    "CP09_IMPACT_BP",
    "CP13_IMPACT_BP",
    "BACK_SERIES_DEPENDENCE_BP",
    "DIRECTLY_COMPARABLE_WEIGHT_SHARE",
    "EXCLUDED_OR_UNRESOLVED_WEIGHT_SHARE",
)
EXPECTED_AUDIT_FILES = (
    "completion_gate_register.csv",
    "dataset_register.csv",
    "mapping_matrix.csv",
    "metric_register.csv",
    "protocol_summary.json",
    "strategy_register.csv",
    "transformation_dimension_register.csv",
)


class ProtocolError(ValueError):
    """Raised when a v0.10.3 contract or generated audit is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError(f"JSON object required: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ProtocolError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _require_exact_keys(payload: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual_set = set(payload)
    if actual_set != expected_set:
        raise ProtocolError(
            f"{label} keys mismatch: missing={sorted(expected_set - actual_set)}, "
            f"extra={sorted(actual_set - expected_set)}"
        )


def _require_list(payload: Any, label: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ProtocolError(f"{label} must be a list")
    return payload


def _require_dict(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProtocolError(f"{label} must be an object")
    return payload


def _require_unique(values: Sequence[str], label: str) -> None:
    if len(set(values)) != len(values):
        raise ProtocolError(f"{label} contains duplicates")


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in fieldnames})


@dataclass(frozen=True)
class MappingRow:
    mapping_key: str
    legacy_codes: tuple[str, ...]
    replacement_code: str
    state: str
    automatic_use_allowed: bool
    evidence_required: tuple[str, ...]
    reason: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MappingRow":
        _require_exact_keys(
            payload,
            (
                "mapping_key",
                "legacy_codes",
                "replacement_code",
                "state",
                "automatic_use_allowed",
                "evidence_required",
                "reason",
            ),
            "mapping row",
        )
        legacy_codes = tuple(str(value) for value in _require_list(payload["legacy_codes"], "legacy_codes"))
        evidence = tuple(
            str(value) for value in _require_list(payload["evidence_required"], "evidence_required")
        )
        row = cls(
            mapping_key=str(payload["mapping_key"]),
            legacy_codes=legacy_codes,
            replacement_code=str(payload["replacement_code"]),
            state=str(payload["state"]),
            automatic_use_allowed=payload["automatic_use_allowed"],
            evidence_required=evidence,
            reason=str(payload["reason"]),
        )
        if not row.mapping_key or not row.reason:
            raise ProtocolError("mapping key and reason must be non-empty")
        if not row.legacy_codes or any(code not in EXPECTED_LEGACY_CODES for code in row.legacy_codes):
            raise ProtocolError(f"invalid legacy code set for {row.mapping_key}")
        _require_unique(row.legacy_codes, f"legacy codes for {row.mapping_key}")
        if row.replacement_code not in EXPECTED_REPLACEMENT_CODES:
            raise ProtocolError(f"invalid replacement code for {row.mapping_key}")
        if row.state not in ALLOWED_MAPPING_STATES:
            raise ProtocolError(f"invalid state for {row.mapping_key}: {row.state}")
        if not isinstance(row.automatic_use_allowed, bool):
            raise ProtocolError(f"automatic_use_allowed must be boolean for {row.mapping_key}")
        if row.automatic_use_allowed:
            raise ProtocolError(f"automatic mapping is forbidden in v0.10.3: {row.mapping_key}")
        if not row.evidence_required:
            raise ProtocolError(f"evidence requirements missing for {row.mapping_key}")
        _require_unique(row.evidence_required, f"evidence requirements for {row.mapping_key}")
        return row


@dataclass(frozen=True)
class ProtocolBundle:
    policy_path: Path
    mapping_path: Path
    policy: dict[str, Any]
    mapping: dict[str, Any]
    mapping_rows: tuple[MappingRow, ...]

    @classmethod
    def load(cls, policy_path: Path, mapping_path: Path) -> "ProtocolBundle":
        policy_path = policy_path.resolve()
        mapping_path = mapping_path.resolve()
        bundle = cls(
            policy_path=policy_path,
            mapping_path=mapping_path,
            policy=_read_json(policy_path),
            mapping=_read_json(mapping_path),
            mapping_rows=(),
        )
        rows = validate_mapping_document(bundle.mapping)
        object.__setattr__(bundle, "mapping_rows", rows)
        validate_protocol_document(bundle.policy, bundle.mapping)
        return bundle

    @property
    def policy_sha256(self) -> str:
        return sha256_file(self.policy_path)

    @property
    def mapping_sha256(self) -> str:
        return sha256_file(self.mapping_path)


def validate_mapping_document(mapping: Mapping[str, Any]) -> tuple[MappingRow, ...]:
    _require_exact_keys(
        mapping,
        (
            "mapping_id",
            "mapping_version",
            "source_classification",
            "target_classification",
            "grain",
            "allowed_states",
            "state_semantics",
            "rows",
            "global_rules",
        ),
        "mapping document",
    )
    if mapping["mapping_id"] != "ARMILAR_ECOICOP_V1_V2_MAPPING_CANDIDATES_V0103":
        raise ProtocolError("unexpected mapping id")
    if mapping["mapping_version"] != VERSION:
        raise ProtocolError("unexpected mapping version")
    if mapping["source_classification"] != "ECOICOP_V1_PRE_2026":
        raise ProtocolError("unexpected source classification")
    if mapping["target_classification"] != "ECOICOP_V2_FROM_2026":
        raise ProtocolError("unexpected target classification")
    if mapping["grain"] != "DIVISION_WITH_ITEM_LEVEL_PROOF_REQUIRED":
        raise ProtocolError("unexpected mapping grain")

    allowed_states = tuple(str(value) for value in _require_list(mapping["allowed_states"], "allowed_states"))
    if set(allowed_states) != set(ALLOWED_MAPPING_STATES) or len(allowed_states) != len(
        ALLOWED_MAPPING_STATES
    ):
        raise ProtocolError("mapping allowed states differ from the v0.10.3 state machine")

    semantics = _require_dict(mapping["state_semantics"], "state_semantics")
    _require_exact_keys(semantics, ALLOWED_MAPPING_STATES, "state semantics")
    if any(not isinstance(value, str) or not value for value in semantics.values()):
        raise ProtocolError("every mapping state requires non-empty semantics")

    rows_payload = _require_list(mapping["rows"], "mapping rows")
    rows = tuple(MappingRow.from_payload(_require_dict(row, "mapping row")) for row in rows_payload)
    if len(rows) != 13:
        raise ProtocolError("mapping must contain exactly thirteen replacement-division rows")
    replacement_codes = tuple(row.replacement_code for row in rows)
    _require_unique(replacement_codes, "replacement codes")
    if set(replacement_codes) != set(EXPECTED_REPLACEMENT_CODES):
        raise ProtocolError("mapping does not cover every ECOICOP v2 division exactly once")
    mapping_keys = tuple(row.mapping_key for row in rows)
    _require_unique(mapping_keys, "mapping keys")
    represented_legacy = {code for row in rows for code in row.legacy_codes}
    if represented_legacy != set(EXPECTED_LEGACY_CODES):
        raise ProtocolError("mapping does not represent every legacy division")

    by_replacement = {row.replacement_code: row for row in rows}
    for code in ("CP07", "CP08", "CP09"):
        if by_replacement[code].state != "MATERIAL_RECLASSIFICATION":
            raise ProtocolError(f"{code} must be marked MATERIAL_RECLASSIFICATION")
    for code in ("CP12", "CP13"):
        row = by_replacement[code]
        if row.state != "SPLIT_REQUIRES_EVIDENCE" or row.legacy_codes != ("CP12",):
            raise ProtocolError(f"{code} must be an evidence-dependent split from legacy CP12")

    rules = _require_dict(mapping["global_rules"], "global_rules")
    _require_exact_keys(
        rules,
        (
            "same_code_is_not_proof",
            "item_level_correspondence_required",
            "weight_preservation_required",
            "price_relative_reconciliation_required",
            "automatic_use_allowed",
            "cp13_drop_allowed",
            "silent_category_expansion_allowed",
        ),
        "global rules",
    )
    required_true = (
        "same_code_is_not_proof",
        "item_level_correspondence_required",
        "weight_preservation_required",
        "price_relative_reconciliation_required",
    )
    if any(rules[key] is not True for key in required_true):
        raise ProtocolError("mapping proof requirements must remain enabled")
    required_false = (
        "automatic_use_allowed",
        "cp13_drop_allowed",
        "silent_category_expansion_allowed",
    )
    if any(rules[key] is not False for key in required_false):
        raise ProtocolError("automatic mapping, CP13 dropping and silent expansion must remain forbidden")
    return tuple(sorted(rows, key=lambda row: row.replacement_code))


def validate_protocol_document(policy: Mapping[str, Any], mapping: Mapping[str, Any]) -> None:
    _require_exact_keys(
        policy,
        (
            "policy_id",
            "policy_version",
            "status",
            "predecessor",
            "constitutional_constraints",
            "scope",
            "declared_universe",
            "dataset_contracts",
            "transformation_dimensions",
            "strategies",
            "metrics",
            "completion_gates",
            "decision_output_contract",
            "prohibitions",
            "gates",
        ),
        "protocol document",
    )
    if policy["policy_id"] != "ARMILAR_ECOICOP_V2_BACKTEST_PROTOCOL_V0103":
        raise ProtocolError("unexpected protocol id")
    if policy["policy_version"] != VERSION or policy["status"] != STATUS:
        raise ProtocolError("unexpected protocol version or status")

    predecessor = _require_dict(policy["predecessor"], "predecessor")
    _require_exact_keys(
        predecessor,
        ("policy_path", "policy_sha256", "checker_status", "commit"),
        "predecessor",
    )
    if predecessor["policy_path"] != "config/ecoicop_v2_transition_v0102.json":
        raise ProtocolError("v0.10.2 predecessor policy path changed")
    if predecessor["policy_sha256"] != "8ae44a982a2ae88fa6e33c23bb95437dc4f91e0f17896190d2bbbfbaa6ff5557":
        raise ProtocolError("v0.10.2 predecessor policy hash changed")
    if predecessor["checker_status"] != "ECOICOP_V2_TRANSITION_V0102_VALID":
        raise ProtocolError("unexpected predecessor checker status")
    if predecessor["commit"] != "215bba966f2a376d2cd4370297512d440b0dbb7d":
        raise ProtocolError("unexpected predecessor commit")

    constraints = _require_dict(policy["constitutional_constraints"], "constitutional_constraints")
    if constraints.get("constitution_path") != "constitution/ARMILAR_RESEARCH_CORE_V1.json":
        raise ProtocolError("Research Core constitution path changed")
    if any(value for key, value in constraints.items() if key != "constitution_path"):
        raise ProtocolError("a constitutional or release constraint is open")

    scope = _require_dict(policy["scope"], "scope")
    if scope.get("define_protocol_only") is not True:
        raise ProtocolError("v0.10.3 must remain protocol-only")
    forbidden_scope_true = (
        "acquire_live_data",
        "acquire_2026_observations",
        "execute_empirical_backtest",
        "select_transition_strategy",
        "amend_constitution",
        "extend_arm_o",
        "generate_2026_targets",
    )
    if any(scope.get(key) is not False for key in forbidden_scope_true):
        raise ProtocolError("v0.10.3 scope contains a forbidden empirical or constitutional action")

    universe = _require_dict(policy["declared_universe"], "declared_universe")
    if universe.get("economies") != ["DE", "ES", "FR", "IT", "PT"]:
        raise ProtocolError("declared v0.8.7 five-economy universe changed")
    if universe.get("legacy_panel_end") != "2025-12":
        raise ProtocolError("legacy panel must remain frozen at December 2025")
    if universe.get("first_live_reference_period") != "2026-01":
        raise ProtocolError("unexpected first live reference period")
    if universe.get("legacy_category_count") != 12 or universe.get("replacement_category_count") != 13:
        raise ProtocolError("category counts must remain 12 and 13")

    datasets = _require_list(policy["dataset_contracts"], "dataset_contracts")
    roles = tuple(str(_require_dict(row, "dataset contract").get("role")) for row in datasets)
    _require_unique(roles, "dataset roles")
    if set(roles) != set(EXPECTED_DATASET_ROLES):
        raise ProtocolError("dataset role register is incomplete or contains unknown roles")
    by_role = {row["role"]: row for row in datasets}
    expected_codes = {
        "LEGACY_MONTHLY_INDEX": "prc_hicp_midx",
        "LEGACY_ITEM_WEIGHTS": "prc_hicp_inw",
        "REPLACEMENT_MONTHLY_INDEX_AND_RATES": "prc_hicp_minr",
        "REPLACEMENT_ITEM_WEIGHTS": "prc_hicp_iw",
        "REPLACEMENT_FIRST_PUBLISHED_DATA": "prc_hicp_fpd",
        "CLASSIFICATION_AND_CORRESPONDENCE": "ECOICOP_V1_V2_CORRESPONDENCE",
        "COUNTRY_COMPILATION_METADATA": "prc_hicp_esms",
    }
    if any(by_role[role].get("dataset_code") != code for role, code in expected_codes.items()):
        raise ProtocolError("one or more official dataset codes changed")
    if any(row.get("use_in_v0103") not in {"METADATA_ONLY", "REGISTERED_NOT_ACQUIRED"} for row in datasets):
        raise ProtocolError("v0.10.3 cannot acquire or use empirical observations")

    dimensions = _require_list(policy["transformation_dimensions"], "transformation_dimensions")
    dimension_ids = tuple(str(_require_dict(row, "dimension").get("dimension_id")) for row in dimensions)
    _require_unique(dimension_ids, "transformation dimensions")
    if set(dimension_ids) != set(EXPECTED_TRANSFORMATION_DIMENSIONS):
        raise ProtocolError("transformation dimensions are incomplete")
    if any(row.get("isolated") is not True or row.get("silent_combination_forbidden") is not True for row in dimensions):
        raise ProtocolError("every transformation dimension must be isolated and fail closed")

    strategies = _require_list(policy["strategies"], "strategies")
    strategy_ids = tuple(str(_require_dict(row, "strategy").get("strategy_id")) for row in strategies)
    if tuple(sorted(strategy_ids)) != EXPECTED_STRATEGIES:
        raise ProtocolError("strategy register must contain exactly T0, T1, T2 and T3")
    if any(row.get("automatic_selection_allowed") is not False for row in strategies):
        raise ProtocolError("no transition strategy may be selected automatically")
    if next(row for row in strategies if row["strategy_id"] == "T0").get("extends_to_2026") is not False:
        raise ProtocolError("T0 cannot extend to 2026")

    metrics = _require_list(policy["metrics"], "metrics")
    metric_ids = tuple(str(_require_dict(row, "metric").get("metric_id")) for row in metrics)
    _require_unique(metric_ids, "metric ids")
    if set(metric_ids) != set(EXPECTED_METRICS):
        raise ProtocolError("metric register differs from the predeclared v0.10.3 metrics")
    if any(row.get("required_for_completion") is not True for row in metrics):
        raise ProtocolError("all v0.10.3 metrics must be required for completion")

    completion_gates = _require_list(policy["completion_gates"], "completion_gates")
    gate_ids = tuple(str(_require_dict(row, "completion gate").get("gate_id")) for row in completion_gates)
    _require_unique(gate_ids, "completion gate ids")
    if any(row.get("opens_transition") is not False for row in completion_gates):
        raise ProtocolError("a protocol completion gate cannot ratify the transition")

    decision = _require_dict(policy["decision_output_contract"], "decision_output_contract")
    if decision.get("automatic_winner_allowed") is not False:
        raise ProtocolError("automatic winner selection is forbidden")
    if decision.get("next_milestone_after_protocol") != NEXT_MILESTONE:
        raise ProtocolError("unexpected next milestone")

    prohibitions = tuple(str(value) for value in _require_list(policy["prohibitions"], "prohibitions"))
    _require_unique(prohibitions, "prohibitions")
    required_prohibitions = {
        "NO_LIVE_2026_ACQUISITION_IN_V0103",
        "NO_EMPIRICAL_BACKTEST_CLAIM_IN_V0103",
        "NO_CONSTITUTIONAL_TRANSITION_DECISION_IN_V0103",
        "NO_ARM_O_EXTENSION_IN_V0103",
        "NO_AUTOMATIC_SAME_CODE_EQUIVALENCE",
        "NO_AUTOMATIC_DROP_OF_CP13",
    }
    if not required_prohibitions.issubset(prohibitions):
        raise ProtocolError("one or more mandatory prohibitions are missing")

    gates = _require_dict(policy["gates"], "gates")
    if any(value is not False for value in gates.values()):
        raise ProtocolError("every release, training and monetary gate must remain closed")

    if mapping.get("mapping_version") != policy["policy_version"]:
        raise ProtocolError("policy and mapping versions differ")


def _summary(bundle: ProtocolBundle, created_at: str) -> dict[str, Any]:
    if not isinstance(created_at, str) or not created_at.endswith("Z") or "T" not in created_at:
        raise ProtocolError("created_at must be an explicit UTC timestamp ending in Z")
    policy = bundle.policy
    return {
        "status": STATUS,
        "policy_version": VERSION,
        "created_at": created_at,
        "policy_sha256": bundle.policy_sha256,
        "mapping_sha256": bundle.mapping_sha256,
        "strategy_count": len(policy["strategies"]),
        "mapping_row_count": len(bundle.mapping_rows),
        "automatic_mapping_count": sum(row.automatic_use_allowed for row in bundle.mapping_rows),
        "required_metric_count": sum(row["required_for_completion"] for row in policy["metrics"]),
        "dataset_contract_count": len(policy["dataset_contracts"]),
        "transformation_dimension_count": len(policy["transformation_dimensions"]),
        "completion_gate_count": len(policy["completion_gates"]),
        "empirical_observation_count": 0,
        "live_2026_observation_count": 0,
        "open_gate_count": sum(policy["gates"].values()),
        "classification_transition_ratified": policy["gates"]["classification_transition_ratified"],
        "arm_o_2026_extension_allowed": policy["gates"]["arm_o_2026_extension_allowed"],
        "backtest_execution_claim_allowed": policy["gates"]["backtest_execution_claim_allowed"],
        "automatic_winner_allowed": policy["decision_output_contract"]["automatic_winner_allowed"],
        "next_milestone": NEXT_MILESTONE,
    }


def _render_audit(bundle: ProtocolBundle, output_dir: Path, created_at: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = _summary(bundle, created_at)
    (output_dir / "protocol_summary.json").write_bytes(_canonical_json(summary))

    _write_csv(
        output_dir / "mapping_matrix.csv",
        (
            "mapping_key",
            "legacy_codes",
            "replacement_code",
            "state",
            "automatic_use_allowed",
            "evidence_required",
            "reason",
        ),
        (
            {
                "mapping_key": row.mapping_key,
                "legacy_codes": "|".join(row.legacy_codes),
                "replacement_code": row.replacement_code,
                "state": row.state,
                "automatic_use_allowed": str(row.automatic_use_allowed).lower(),
                "evidence_required": "|".join(row.evidence_required),
                "reason": row.reason,
            }
            for row in bundle.mapping_rows
        ),
    )

    _write_csv(
        output_dir / "strategy_register.csv",
        (
            "strategy_id",
            "name",
            "output_category_count",
            "uses_reconstructed_back_series",
            "preserves_legacy_history",
            "extends_to_2026",
            "constitutional_decision_required",
            "automatic_selection_allowed",
            "description",
        ),
        (
            {
                **row,
                "uses_reconstructed_back_series": str(row["uses_reconstructed_back_series"]).lower(),
                "preserves_legacy_history": str(row["preserves_legacy_history"]).lower(),
                "extends_to_2026": str(row["extends_to_2026"]).lower(),
                "constitutional_decision_required": str(row["constitutional_decision_required"]).lower(),
                "automatic_selection_allowed": str(row["automatic_selection_allowed"]).lower(),
            }
            for row in sorted(bundle.policy["strategies"], key=lambda item: item["strategy_id"])
        ),
    )

    _write_csv(
        output_dir / "metric_register.csv",
        ("metric_id", "unit", "grain", "formula", "direction", "required_for_completion"),
        (
            {
                **row,
                "grain": "|".join(row["grain"]),
                "required_for_completion": str(row["required_for_completion"]).lower(),
            }
            for row in sorted(bundle.policy["metrics"], key=lambda item: item["metric_id"])
        ),
    )

    _write_csv(
        output_dir / "dataset_register.csv",
        (
            "role",
            "provider",
            "dataset_code",
            "classification",
            "time_semantics",
            "permitted_period_start",
            "permitted_period_end",
            "required_units",
            "acquisition_milestone",
            "use_in_v0103",
        ),
        (
            {**row, "required_units": "|".join(row["required_units"])}
            for row in sorted(bundle.policy["dataset_contracts"], key=lambda item: item["role"])
        ),
    )

    _write_csv(
        output_dir / "transformation_dimension_register.csv",
        ("dimension_id", "isolated", "required_comparison", "silent_combination_forbidden"),
        (
            {
                **row,
                "isolated": str(row["isolated"]).lower(),
                "silent_combination_forbidden": str(row["silent_combination_forbidden"]).lower(),
            }
            for row in sorted(
                bundle.policy["transformation_dimensions"], key=lambda item: item["dimension_id"]
            )
        ),
    )

    _write_csv(
        output_dir / "completion_gate_register.csv",
        ("gate_id", "condition", "opens_transition"),
        (
            {**row, "opens_transition": str(row["opens_transition"]).lower()}
            for row in sorted(bundle.policy["completion_gates"], key=lambda item: item["gate_id"])
        ),
    )

    manifest_lines = [
        f"{sha256_file(output_dir / name)} {name}" for name in sorted(EXPECTED_AUDIT_FILES)
    ]
    (output_dir / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    return summary


def build_protocol_audit(
    *, policy_path: Path, mapping_path: Path, output_dir: Path, created_at: str
) -> dict[str, Any]:
    """Validate the contracts and materialise a deterministic protocol audit."""
    bundle = ProtocolBundle.load(policy_path, mapping_path)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ProtocolError(f"output directory already exists: {output_dir}")
    return _render_audit(bundle, output_dir, created_at)


def _read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split(" ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or any(char not in "0123456789abcdef" for char in parts[0]):
            raise ProtocolError(f"invalid manifest line {number}")
        digest, name = parts
        if not name or "/" in name or "\\" in name or name in entries:
            raise ProtocolError(f"invalid or duplicate manifest path on line {number}")
        entries[name] = digest
    return entries


def verify_protocol_audit(
    audit_dir: Path, *, policy_path: Path, mapping_path: Path
) -> dict[str, Any]:
    """Verify hashes and byte-for-byte reproducibility of a v0.10.3 protocol audit."""
    audit_dir = audit_dir.resolve()
    if not audit_dir.is_dir():
        raise ProtocolError(f"audit directory missing: {audit_dir}")
    actual_files = {path.name for path in audit_dir.iterdir() if path.is_file()}
    expected_files = set(EXPECTED_AUDIT_FILES) | {"MANIFEST.sha256"}
    if actual_files != expected_files:
        raise ProtocolError(
            f"audit file set mismatch: missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    entries = _read_manifest(audit_dir / "MANIFEST.sha256")
    if set(entries) != set(EXPECTED_AUDIT_FILES):
        raise ProtocolError("audit manifest file set mismatch")
    for name, digest in entries.items():
        if sha256_file(audit_dir / name) != digest:
            raise ProtocolError(f"audit hash mismatch: {name}")

    summary = _read_json(audit_dir / "protocol_summary.json")
    created_at = summary.get("created_at")
    if not isinstance(created_at, str):
        raise ProtocolError("audit summary created_at missing")
    bundle = ProtocolBundle.load(policy_path, mapping_path)
    expected_summary = _summary(bundle, created_at)
    if summary != expected_summary:
        raise ProtocolError("audit summary differs from the validated source contracts")

    temp_root = Path(tempfile.mkdtemp(prefix="armilar-v0103-verify-"))
    try:
        regenerated = temp_root / "audit"
        _render_audit(bundle, regenerated, created_at)
        for name in expected_files:
            if (audit_dir / name).read_bytes() != (regenerated / name).read_bytes():
                raise ProtocolError(f"audit is not byte reproducible: {name}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return summary


def _default_mapping_for(policy_path: Path) -> Path:
    return policy_path.with_name("ecoicop_v1_v2_mapping_candidates_v0103.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-policy", help="validate protocol and mapping")
    validate_parser.add_argument("--policy", type=Path, required=True)
    validate_parser.add_argument("--mapping", type=Path)

    build_parser = subparsers.add_parser("build-audit", help="materialise deterministic protocol audit")
    build_parser.add_argument("--policy", type=Path, required=True)
    build_parser.add_argument("--mapping", type=Path)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--created-at", required=True)

    verify_parser = subparsers.add_parser("verify-audit", help="verify a protocol audit")
    verify_parser.add_argument("--audit-dir", type=Path, required=True)
    verify_parser.add_argument("--policy", type=Path, required=True)
    verify_parser.add_argument("--mapping", type=Path)

    args = parser.parse_args(argv)
    mapping_path = args.mapping or _default_mapping_for(args.policy)
    try:
        if args.command == "validate-policy":
            bundle = ProtocolBundle.load(args.policy, mapping_path)
            payload = _summary(bundle, "1970-01-01T00:00:00Z")
        elif args.command == "build-audit":
            payload = build_protocol_audit(
                policy_path=args.policy,
                mapping_path=mapping_path,
                output_dir=args.output_dir,
                created_at=args.created_at,
            )
        else:
            payload = verify_protocol_audit(
                args.audit_dir,
                policy_path=args.policy,
                mapping_path=mapping_path,
            )
    except (OSError, ProtocolError) as exc:
        print(f"ECOICOP_V2_BACKTEST_PROTOCOL_V0103_INVALID: {exc}")
        return 1
    print(STATUS)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
