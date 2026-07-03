#!/usr/bin/env python3
"""Fail-closed checker for the ratified ARMILAR Research Core V1 constitution."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

CONSTITUTION_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
DRAFT_ARCHIVE_PATH = Path("constitution/archive/ARMILAR_RESEARCH_CORE_V1_0.3.0-draft.json")
PROPOSAL_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json")
RECORD_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json")
BASKET_PATH = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")
SNAPSHOT_PATH = Path("constitution/inputs/ARMILAR_RESEARCH_CORE_V1_WEIGHTS_OBSERVED_UNIVERSE_V094.csv")
CONSTITUTION_SCHEMA_PATH = Path("schemas/research_core_constitution.schema.json")
RECORD_SCHEMA_PATH = Path("schemas/research_core_ratification_record.schema.json")
MANIFEST_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.sha256")
CHECKER_PATH = Path("scripts/check_research_core_constitution.py")
EXPECTED_CONSTITUTION_HASH = "5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6"
EXPECTED_RECORD_HASH = "365dbf0fe8d42996d805c3961dab90fb2bc8f26935bff5b4c775592f9177d561"
EXPECTED_DRAFT_HASH = "3e97eb4ca423f14203c92092d310527d9bc1fbcdcfb6438e46e01401d1496734"
EXPECTED_PROPOSAL_HASH = "24f5df7e31ff604db11a43457f98e6fab16d27713d3761e4c595fb1a752bc674"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_SNAPSHOT_HASH = "51ed567c1eea6badd077d2bd1fe1f4009a7ce1b542e16971c79c389a4370042f"
EXPECTED_PROXY_TOTAL = "0.589731681350816432896035605"
EXPECTED_APPROVAL_STATEMENT = 'Aprovo as sete decisões metodológicas da proposta ARMILAR_RESEARCH_CORE_V1 para ratificação exclusiva como constituição de desenvolvimento do Research Core, mantendo fechados todos os gates de release, model promotion, shadow production e utilização monetária.'
EXPECTED_APPROVAL_STATEMENT_HASH = "8507bcace2b49b97b74780b5520a499aef4cbe24a1f14e1f8aea2e2984d602dd"
EXPECTED_DECISIONS = ('normalization_base', 'official_formula', 'vintage_and_revision_policy', 'precision_and_rounding', 'exact_series_semantics', 'hfce_hicp_conceptual_treatment', 'constitutional_amendment_process')
EXPECTED_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
EXPECTED_CATEGORIES = tuple(f"CP{index:02d}" for index in range(1, 13))
RATIFIED_STATUS = "RATIFIED_FOR_ENGINE_DEVELOPMENT"
MANIFEST_PATHS = (
    Path("basket/ARMILAR_RESEARCH_CORE_V1.csv"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1.json"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1.md"),
    Path("constitution/archive/ARMILAR_RESEARCH_CORE_V1_0.3.0-draft.json"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.json"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD.md"),
    Path("constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json"),
    Path("constitution/inputs/ARMILAR_RESEARCH_CORE_V1_WEIGHTS_OBSERVED_UNIVERSE_V094.csv"),
    Path("schemas/research_core_constitution.schema.json"),
    Path("schemas/research_core_ratification_record.schema.json"),
    Path("schemas/research_core_proxy_exposure.schema.json"),
    Path("docs/DECISION_RESEARCH_CORE_CONSTITUTION_RATIFICATION.md"),
    Path("docs/ARMILAR_RESEARCH_CORE_V1_SCOPE.md"),
    Path("docs/DECISION_RESEARCH_CORE_V1.md"),
    Path("docs/DECISION_RESEARCH_CORE_BASKET_MATERIALIZATION.md"),
    Path("docs/DECISION_RESEARCH_CORE_CONTRACT_REPAIR.md"),
    Path("docs/DECISION_RESEARCH_CORE_NORMALIZATION_BASE.md"),
    Path("docs/DECISION_RESEARCH_CORE_OFFICIAL_FORMULA.md"),
    Path("docs/DECISION_RESEARCH_CORE_VINTAGE_AND_REVISION_POLICY.md"),
    Path("docs/DECISION_RESEARCH_CORE_PRECISION_AND_ROUNDING.md"),
    Path("docs/DECISION_RESEARCH_CORE_SERIES_SEMANTICS.md"),
    Path("docs/DECISION_RESEARCH_CORE_HFCE_HICP_TREATMENT.md"),
    Path("docs/DECISION_RESEARCH_CORE_AMENDMENT_PROCESS.md"),
    Path("config/eurostat_vertical_v087.json"),
    Path("scripts/materialize_research_core_basket.py"),
    Path("scripts/check_research_core_ratification.py"),
    Path("scripts/check_research_core_constitution.py"),
)
UTF8_BOM = b"\xef\xbb\xbf"


class RatifiedConstitutionError(ValueError):
    pass


def canonical_text(payload: bytes) -> bytes:
    if payload.startswith(UTF8_BOM):
        raise RatifiedConstitutionError("UTF-8 BOM is not permitted")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RatifiedConstitutionError("contract is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_text(path.read_bytes())).hexdigest()


def canonical_object_hash(payload: Any) -> str:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(canonical_text(path.read_bytes()).decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RatifiedConstitutionError(f"cannot load JSON contract: {path}") from exc
    if not isinstance(payload, dict):
        raise RatifiedConstitutionError(f"JSON contract must be an object: {path}")
    return payload


def validate_const_schema(schema: dict[str, Any], payload: dict[str, Any], label: str) -> None:
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise RatifiedConstitutionError(f"{label} schema must be closed")
    if schema.get("required") != list(payload.keys()):
        raise RatifiedConstitutionError(f"{label} schema required fields changed")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(properties) != set(payload):
        raise RatifiedConstitutionError(f"{label} schema properties changed")
    for key, value in payload.items():
        if properties.get(key) != {"const": value}:
            raise RatifiedConstitutionError(f"{label} schema const mismatch: {key}")


def parse_manifest(path: Path) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    for line in canonical_text(path.read_bytes()).decode("utf-8").splitlines():
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise RatifiedConstitutionError("malformed ratification manifest")
        entries[Path(parts[1])] = parts[0]
    return entries


def check_manifest(root: Path) -> None:
    entries = parse_manifest(root / MANIFEST_PATH)
    expected = set(MANIFEST_PATHS)
    if set(entries) != expected:
        raise RatifiedConstitutionError("ratification manifest path set changed")
    for relative in MANIFEST_PATHS:
        path = root / relative
        if not path.is_file():
            raise RatifiedConstitutionError(f"manifest file missing: {relative}")
        if digest(path) != entries[relative]:
            raise RatifiedConstitutionError(f"manifest mismatch: {relative}")


def decision_map(payload: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    decisions = payload.get(field)
    if not isinstance(decisions, list):
        raise RatifiedConstitutionError(f"{field} is missing")
    if tuple(item.get("id") for item in decisions if isinstance(item, dict)) != EXPECTED_DECISIONS:
        raise RatifiedConstitutionError(f"{field} set or order changed")
    return {item["id"]: item for item in decisions}


def without_status(payload: dict[str, Any]) -> dict[str, Any]:
    copy_payload = dict(payload)
    copy_payload.pop("status", None)
    return copy_payload


def validate_checker_is_read_only(root: Path) -> None:
    source = canonical_text((root / CHECKER_PATH).read_bytes()).decode("utf-8")
    tree = ast.parse(source)
    prohibited = {"write_text", "write_bytes", "rename", "unlink", "mkdir", "makedirs"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in prohibited:
            raise RatifiedConstitutionError(f"checker must be read-only: {node.func.attr}")


def validate(root: Path) -> dict[str, Any]:
    for relative in (*MANIFEST_PATHS, MANIFEST_PATH):
        if not (root / relative).is_file():
            raise RatifiedConstitutionError(f"required ratification file is missing: {relative}")

    if digest(root / CONSTITUTION_PATH) != EXPECTED_CONSTITUTION_HASH:
        raise RatifiedConstitutionError("ratified constitution hash changed")
    if digest(root / RECORD_PATH) != EXPECTED_RECORD_HASH:
        raise RatifiedConstitutionError("ratification record hash changed")
    if digest(root / DRAFT_ARCHIVE_PATH) != EXPECTED_DRAFT_HASH:
        raise RatifiedConstitutionError("predecessor constitution archive changed")
    if digest(root / PROPOSAL_PATH) != EXPECTED_PROPOSAL_HASH:
        raise RatifiedConstitutionError("approved proposal changed")
    if digest(root / BASKET_PATH) != EXPECTED_BASKET_HASH:
        raise RatifiedConstitutionError("approved basket changed")
    if digest(root / SNAPSHOT_PATH) != EXPECTED_SNAPSHOT_HASH:
        raise RatifiedConstitutionError("approved constitutional snapshot changed")

    constitution = load_json(root / CONSTITUTION_PATH)
    draft = load_json(root / DRAFT_ARCHIVE_PATH)
    proposal = load_json(root / PROPOSAL_PATH)
    record = load_json(root / RECORD_PATH)
    validate_const_schema(load_json(root / CONSTITUTION_SCHEMA_PATH), constitution, "constitution")
    validate_const_schema(load_json(root / RECORD_SCHEMA_PATH), record, "ratification record")

    if draft.get("constitution_status") != "DRAFT" or draft.get("constitution_version") != "0.3.0-draft":
        raise RatifiedConstitutionError("predecessor archive is not the approved draft")
    if proposal.get("proposal_version") != "0.2.0" or proposal.get("proposal_status") != "PROPOSED":
        raise RatifiedConstitutionError("approved proposal identity changed")
    if proposal.get("approval_status") != "NOT_APPROVED":
        raise RatifiedConstitutionError("historical proposal must not self-approve")
    if proposal.get("target_constitution_sha256") != EXPECTED_DRAFT_HASH:
        raise RatifiedConstitutionError("proposal predecessor hash changed")

    if constitution.get("constitution_id") != "ARMILAR_RESEARCH_CORE_V1":
        raise RatifiedConstitutionError("constitution id changed")
    if constitution.get("constitution_version") != "1.0.0-research":
        raise RatifiedConstitutionError("constitution version changed")
    if constitution.get("constitution_status") != RATIFIED_STATUS:
        raise RatifiedConstitutionError("constitution is not ratified for engine development")
    if constitution.get("schema_version") != "1.3":
        raise RatifiedConstitutionError("constitution schema version changed")
    if constitution.get("economies") != list(EXPECTED_ECONOMIES):
        raise RatifiedConstitutionError("economy universe changed")
    if constitution.get("basket_categories") != list(EXPECTED_CATEGORIES):
        raise RatifiedConstitutionError("basket categories changed")
    if constitution.get("benchmark_categories") != ["CP00"]:
        raise RatifiedConstitutionError("CP00 benchmark contract changed")
    if constitution.get("pending_decisions") != []:
        raise RatifiedConstitutionError("ratified constitution must have zero pending decisions")
    gates = constitution.get("release_gates")
    if not isinstance(gates, dict) or not gates or any(gates.values()):
        raise RatifiedConstitutionError("all release gates must remain false")

    materialization = constitution.get("basket_materialization")
    if not isinstance(materialization, dict):
        raise RatifiedConstitutionError("basket materialization is missing")
    if materialization.get("expected_cell_count") != 60:
        raise RatifiedConstitutionError("basket cell count changed")
    if materialization.get("fixed_universe_weight_sum") != "1.000000000000000000000000000":
        raise RatifiedConstitutionError("fixed weight sum changed")
    if materialization.get("constitutional_snapshot_sha256") != EXPECTED_SNAPSHOT_HASH:
        raise RatifiedConstitutionError("snapshot receipt changed")
    if materialization.get("upstream_raw_sha256") != "743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83":
        raise RatifiedConstitutionError("upstream raw receipt changed")

    proposal_decisions = decision_map(proposal, "decisions")
    ratified_decisions = decision_map(constitution, "ratified_decisions")
    for decision_id in EXPECTED_DECISIONS:
        proposed = proposal_decisions[decision_id]
        ratified = ratified_decisions[decision_id]
        if proposed.get("status") != "PROPOSED" or ratified.get("status") != RATIFIED_STATUS:
            raise RatifiedConstitutionError(f"decision status invalid: {decision_id}")
        if without_status(proposed) != without_status(ratified):
            raise RatifiedConstitutionError(f"ratified decision differs from approved proposal: {decision_id}")

    normalization = ratified_decisions["normalization_base"]["executable_contract"]
    if normalization.get("reference_year") != 2021 or normalization.get("base_value") != "100":
        raise RatifiedConstitutionError("normalization base changed")
    if normalization.get("all_base_months_required") is not True or normalization.get("missing_base_month_policy") != "FAIL_CLOSED":
        raise RatifiedConstitutionError("normalization missing-month policy changed")

    formula = ratified_decisions["official_formula"]["executable_contract"]
    if formula.get("index_type") != "PPP_ADJUSTED_FIXED_WEIGHT_ARITHMETIC_LASPEYRES_TYPE":
        raise RatifiedConstitutionError("official formula changed")
    if formula.get("weight_field") != "fixed_universe_weight" or formula.get("weight_sum") != "1.000000000000000000000000000":
        raise RatifiedConstitutionError("official weight contract changed")
    if formula.get("silent_renormalization_allowed") is not False:
        raise RatifiedConstitutionError("silent renormalization was enabled")
    proxy = formula.get("proxy_exposure") or {}
    if proxy.get("cell_count") != 25 or proxy.get("fixed_universe_weight_total") != EXPECTED_PROXY_TOTAL:
        raise RatifiedConstitutionError("proxy exposure disclosure changed")
    if proxy.get("may_be_claimed_as_exact_hfce_ppp") is not False:
        raise RatifiedConstitutionError("proxy cells were promoted to exact")

    precision = ratified_decisions["precision_and_rounding"]["executable_contract"]
    if precision.get("arithmetic_type") != "DECIMAL" or precision.get("decimal_precision") != 28:
        raise RatifiedConstitutionError("decimal arithmetic contract changed")
    if precision.get("rounding_mode") != "ROUND_HALF_EVEN" or precision.get("intermediate_rounding_allowed") is not False:
        raise RatifiedConstitutionError("rounding contract changed")

    semantics = ratified_decisions["exact_series_semantics"]["executable_contract"]
    if set(semantics) != {"ARM-H", "ARM-L", "ARM-O", "ARM-R", "silent_substitution_allowed"}:
        raise RatifiedConstitutionError("series set changed")
    canonical_series = constitution.get("series")
    if not isinstance(canonical_series, dict) or set(canonical_series) != {"ARM-H", "ARM-L", "ARM-O", "ARM-R"}:
        raise RatifiedConstitutionError("canonical series projection changed")
    for series_id in ("ARM-H", "ARM-L", "ARM-O", "ARM-R"):
        entry = canonical_series.get(series_id)
        if not isinstance(entry, dict):
            raise RatifiedConstitutionError(f"canonical series entry missing: {series_id}")
        if entry.get("status") != RATIFIED_STATUS:
            raise RatifiedConstitutionError(f"canonical series status changed: {series_id}")
        if "provisional_semantics" in entry:
            raise RatifiedConstitutionError(f"provisional semantics survived ratification: {series_id}")
        if entry.get("role") != semantics[series_id].get("meaning"):
            raise RatifiedConstitutionError(f"canonical series role changed: {series_id}")
        if entry.get("semantics") != semantics[series_id]:
            raise RatifiedConstitutionError(f"canonical series semantics changed: {series_id}")
    arm_l = semantics.get("ARM-L") or {}
    information_set = arm_l.get("information_set") or {}
    required_arm_l_fields = (
        "information_cutoff_required",
        "retrieval_cutoff_required",
        "source_registry_version_required",
        "model_version_required",
        "raw_snapshot_ids_required",
        "published_at_required",
        "retrieved_at_required",
        "quality_state_required",
        "uncertainty_bounds_required",
    )
    if any(information_set.get(field) is not True for field in required_arm_l_fields):
        raise RatifiedConstitutionError("ARM-L information-set contract is incomplete")
    if arm_l.get("anchor_arm_o_vintage_required") is not True or arm_l.get("historical_release_mutability") != "IMMUTABLE":
        raise RatifiedConstitutionError("ARM-L anchor or immutability changed")
    if arm_l.get("retroactive_revision_to_match_arm_o_allowed") is not False:
        raise RatifiedConstitutionError("retroactive ARM-L rewrite was enabled")

    hfce = ratified_decisions["hfce_hicp_conceptual_treatment"]["executable_contract"]
    if hfce.get("weight_implementation_limitation") != "25_CELLS_USE_AIC_PPP_PROXY":
        raise RatifiedConstitutionError("HFCE proxy limitation was removed")
    if hfce.get("proxy_exposure_weight_total") != EXPECTED_PROXY_TOTAL:
        raise RatifiedConstitutionError("HFCE proxy total changed")
    ooh = hfce.get("ooh_sensitivity_requirement") or {}
    required_ooh = (
        "does_not_measure_complete_hfce_hicp_gap",
        "may_not_be_presented_as_imputed_rent_equivalence",
        "must_document_frequency_alignment",
        "must_document_ooh_approach",
        "must_document_publication_lag",
        "must_document_weights",
        "required_before_external_research_release",
        "required_before_shadow_production",
    )
    if any(ooh.get(field) is not True for field in required_ooh):
        raise RatifiedConstitutionError("mandatory OOH sensitivity contract is incomplete")

    amendment = ratified_decisions["constitutional_amendment_process"]["executable_contract"]
    change_classes = amendment.get("change_classes") or {}
    expected_classes = {"EDITORIAL_PATCH", "EVIDENCE_METADATA_PATCH", "NUMERICAL_WEIGHT_PATCH", "BASKET_SCOPE_CHANGE", "CONSTITUTIONAL_METHOD_CHANGE"}
    if set(change_classes) != expected_classes:
        raise RatifiedConstitutionError("constitutional change classes changed")
    proxy_transition = amendment.get("proxy_to_exact_transition") or {}
    if proxy_transition.get("silent_upgrade_allowed") is not False or proxy_transition.get("silent_proxy_to_exact_promotion_allowed") is not False:
        raise RatifiedConstitutionError("silent proxy promotion was enabled")
    if amendment.get("retroactive_history_rewrite_allowed") is not False:
        raise RatifiedConstitutionError("retroactive history rewrite was enabled")

    if record.get("ratification_record_id") != "ARMILAR_RESEARCH_CORE_V1_RATIFICATION_RECORD":
        raise RatifiedConstitutionError("ratification record id changed")
    if record.get("approval_status") != "APPROVED":
        raise RatifiedConstitutionError("ratification approval status changed")
    if record.get("approval_timestamp") != "2026-07-03" or record.get("approval_timestamp_precision") != "DATE_ONLY":
        raise RatifiedConstitutionError("approval date changed or an unsupported time was invented")
    if record.get("approval_statement") != EXPECTED_APPROVAL_STATEMENT:
        raise RatifiedConstitutionError("human approval statement changed")
    if record.get("approval_statement_sha256") != EXPECTED_APPROVAL_STATEMENT_HASH:
        raise RatifiedConstitutionError("human approval statement hash changed")
    if record.get("approved_proposal_sha256") != EXPECTED_PROPOSAL_HASH or record.get("approved_proposal_version") != "0.2.0":
        raise RatifiedConstitutionError("approved proposal receipt changed")
    if record.get("approved_constitution_sha256") != EXPECTED_CONSTITUTION_HASH:
        raise RatifiedConstitutionError("approved constitution receipt changed")
    if record.get("approved_predecessor_constitution_sha256") != EXPECTED_DRAFT_HASH:
        raise RatifiedConstitutionError("predecessor receipt changed")
    if record.get("approved_basket_sha256") != EXPECTED_BASKET_HASH or record.get("approved_weight_snapshot_sha256") != EXPECTED_SNAPSHOT_HASH:
        raise RatifiedConstitutionError("basket or snapshot receipt changed")
    if record.get("release_gates") != gates or any(record["release_gates"].values()):
        raise RatifiedConstitutionError("ratification record release gates changed")
    receipts = record.get("decision_receipts")
    if not isinstance(receipts, list) or tuple(item.get("decision_id") for item in receipts) != EXPECTED_DECISIONS:
        raise RatifiedConstitutionError("decision receipts changed")
    for receipt in receipts:
        decision = ratified_decisions[receipt["decision_id"]]
        if receipt.get("status") != RATIFIED_STATUS:
            raise RatifiedConstitutionError("decision receipt status changed")
        if receipt.get("executable_contract_sha256") != canonical_object_hash(decision["executable_contract"]):
            raise RatifiedConstitutionError("decision contract receipt changed")

    ratification = constitution.get("ratification") or {}
    if ratification.get("approval_id") != record.get("approval_id"):
        raise RatifiedConstitutionError("constitution and record approval ids differ")
    if ratification.get("approval_statement") != EXPECTED_APPROVAL_STATEMENT:
        raise RatifiedConstitutionError("constitution approval statement changed")
    if ratification.get("ratification_record") != RECORD_PATH.as_posix():
        raise RatifiedConstitutionError("constitution ratification record path changed")
    if ratification.get("does_not_start_v096") is not True:
        raise RatifiedConstitutionError("ratification improperly starts v0.9.6")

    for relative in constitution.get("source_documents", []):
        if not (root / relative).is_file():
            raise RatifiedConstitutionError(f"constitutional source document missing: {relative}")

    with (root / BASKET_PATH).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 60:
        raise RatifiedConstitutionError("basket row count changed")
    if {row["economy_code"] for row in rows} != set(EXPECTED_ECONOMIES):
        raise RatifiedConstitutionError("basket economy universe changed")
    if {row["category_code"] for row in rows} != set(EXPECTED_CATEGORIES):
        raise RatifiedConstitutionError("basket category universe changed")
    if sum((Decimal(row["fixed_universe_weight"]) for row in rows), Decimal("0")) != Decimal("1.000000000000000000000000000"):
        raise RatifiedConstitutionError("basket fixed weights no longer sum to one")

    validate_checker_is_read_only(root)
    check_manifest(root)
    return constitution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the ratified Research Core constitution.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    validate(args.root.resolve())
    print("RESEARCH_CORE_CONSTITUTION_RATIFIED_FOR_ENGINE_DEVELOPMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
