from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

PROPOSAL_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json")
PROPOSAL_MD_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.md")
PROPOSAL_SCHEMA_RELATIVE_PATH = Path("schemas/research_core_ratification_proposal.schema.json")
PROPOSAL_MANIFEST_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.sha256")
PROXY_ANNEX_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json")
PROXY_ANNEX_MD_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.md")
PROXY_ANNEX_SCHEMA_RELATIVE_PATH = Path("schemas/research_core_proxy_exposure.schema.json")
CONSTITUTION_RELATIVE_PATH = Path("constitution/archive/ARMILAR_RESEARCH_CORE_V1_0.3.0-draft.json")
BASKET_RELATIVE_PATH = Path("basket/ARMILAR_RESEARCH_CORE_V1.csv")

EXPECTED_CONSTITUTION_HASH = "3e97eb4ca423f14203c92092d310527d9bc1fbcdcfb6438e46e01401d1496734"
EXPECTED_BASKET_HASH = "5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c"
EXPECTED_PROXY_TOTAL = "0.589731681350816432896035605"
EXPECTED_ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
EXPECTED_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
EXPECTED_PROXY_CATEGORIES = ("CP04", "CP06", "CP09", "CP10", "CP12")
EXPECTED_DECISIONS = (
    "normalization_base",
    "official_formula",
    "vintage_and_revision_policy",
    "precision_and_rounding",
    "exact_series_semantics",
    "hfce_hicp_conceptual_treatment",
    "constitutional_amendment_process",
)

TEXT_MANIFEST_PATHS = (
    BASKET_RELATIVE_PATH,
    PROPOSAL_RELATIVE_PATH,
    PROPOSAL_MD_RELATIVE_PATH,
    PROXY_ANNEX_RELATIVE_PATH,
    PROXY_ANNEX_MD_RELATIVE_PATH,
    Path("docs/DECISION_RESEARCH_CORE_NORMALIZATION_BASE.md"),
    Path("docs/DECISION_RESEARCH_CORE_OFFICIAL_FORMULA.md"),
    Path("docs/DECISION_RESEARCH_CORE_VINTAGE_AND_REVISION_POLICY.md"),
    Path("docs/DECISION_RESEARCH_CORE_PRECISION_AND_ROUNDING.md"),
    Path("docs/DECISION_RESEARCH_CORE_SERIES_SEMANTICS.md"),
    Path("docs/DECISION_RESEARCH_CORE_HFCE_HICP_TREATMENT.md"),
    Path("docs/DECISION_RESEARCH_CORE_AMENDMENT_PROCESS.md"),
    PROPOSAL_SCHEMA_RELATIVE_PATH,
    PROXY_ANNEX_SCHEMA_RELATIVE_PATH,
    Path("scripts/check_research_core_ratification.py"),
)
MANIFEST_PATHS = tuple(sorted(TEXT_MANIFEST_PATHS, key=lambda p: p.as_posix()))
UTF8_BOM = b"\xef\xbb\xbf"


class RatificationProposalError(ValueError):
    pass


def canonical_text(payload: bytes) -> bytes:
    if payload.startswith(UTF8_BOM):
        raise RatificationProposalError("UTF-8 BOM is not permitted")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RatificationProposalError("proposal input is not UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_text(path.read_bytes())).hexdigest()


def raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RatificationProposalError(f"cannot load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RatificationProposalError(f"JSON root must be an object: {path}")
    return payload


def _sum_decimal(rows: list[dict[str, str]], field: str) -> str:
    return str(sum((Decimal(row[field]) for row in rows), Decimal("0")))


def derive_proxy_annex(root: Path) -> dict[str, Any]:
    path = root / BASKET_RELATIVE_PATH
    if digest(path) != EXPECTED_BASKET_HASH:
        raise RatificationProposalError("committed basket canonical hash changed")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    proxy_rows = [row for row in rows if row.get("evidence_class") == "EXPERIMENTAL_RESEARCH"]
    proxy_rows.sort(key=lambda row: (row["economy_code"], row["category_code"]))
    if len(proxy_rows) != 25:
        raise RatificationProposalError("expected exactly 25 experimental proxy cells")
    economies = sorted({row["economy_code"] for row in proxy_rows})
    categories = sorted({row["category_code"] for row in proxy_rows})
    if tuple(economies) != EXPECTED_ECONOMIES:
        raise RatificationProposalError("proxy-economy set changed")
    if tuple(categories) != EXPECTED_PROXY_CATEGORIES:
        raise RatificationProposalError("proxy-category set changed")
    by_category = {
        category: _sum_decimal([row for row in proxy_rows if row["category_code"] == category], "fixed_universe_weight")
        for category in categories
    }
    by_economy = {
        economy: _sum_decimal([row for row in proxy_rows if row["economy_code"] == economy], "fixed_universe_weight")
        for economy in economies
    }
    cells = [
        {
            "economy_code": row["economy_code"],
            "category_code": row["category_code"],
            "fixed_universe_weight": row["fixed_universe_weight"],
            "raw_world_weight": row["raw_world_weight"],
            "ppp_scope": row["ppp_scope"],
            "derivation": row["derivation"],
            "evidence_class": row["evidence_class"],
        }
        for row in proxy_rows
    ]
    return {
        "annex_id": "ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE",
        "annex_version": "0.1.0",
        "proposal_version": "0.2.0",
        "basket_path": BASKET_RELATIVE_PATH.as_posix(),
        "basket_sha256_raw": digest(path),
        "evidence_class": "EXPERIMENTAL_RESEARCH",
        "proxy_basis": "ACTUAL_CONSUMPTION_PPP_USED_AS_RATIFIED_OPTION_B_PROXY_FOR_HFCE_NUMERATOR",
        "cell_count": 25,
        "economies": economies,
        "categories": categories,
        "fixed_universe_weight_total": _sum_decimal(proxy_rows, "fixed_universe_weight"),
        "fixed_universe_weight_by_category": by_category,
        "fixed_universe_weight_by_economy": by_economy,
        "cells": cells,
        "disclosure_rules": {
            "all_research_outputs_must_report_proxy_weight_share": True,
            "all_research_outputs_must_identify_proxy_categories": True,
            "complete_hfce_exactness_claim_allowed": False,
            "proxy_cells_may_be_described_as_exact": False,
        },
    }


def _decision_map(proposal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions = proposal.get("decisions")
    if not isinstance(decisions, list):
        raise RatificationProposalError("proposal decisions are missing")
    ids = tuple(item.get("id") for item in decisions)
    if ids != EXPECTED_DECISIONS:
        raise RatificationProposalError("proposal decision set or order is invalid")
    return {item["id"]: item for item in decisions}


def validate(root: Path) -> dict[str, Any]:
    proposal_path = root / PROPOSAL_RELATIVE_PATH
    constitution_path = root / CONSTITUTION_RELATIVE_PATH
    proposal = load_json(proposal_path)
    constitution = load_json(constitution_path)
    schema = load_json(root / PROPOSAL_SCHEMA_RELATIVE_PATH)
    annex = load_json(root / PROXY_ANNEX_RELATIVE_PATH)
    annex_schema = load_json(root / PROXY_ANNEX_SCHEMA_RELATIVE_PATH)

    if digest(constitution_path) != EXPECTED_CONSTITUTION_HASH:
        raise RatificationProposalError("target constitution hash changed")
    if proposal.get("target_constitution_sha256") != EXPECTED_CONSTITUTION_HASH:
        raise RatificationProposalError("proposal target hash mismatch")
    if proposal.get("proposal_version") != "0.2.0":
        raise RatificationProposalError("proposal version must be 0.2.0")
    if proposal.get("proposal_status") != "PROPOSED":
        raise RatificationProposalError("proposal must remain PROPOSED")
    if proposal.get("approval_status") != "NOT_APPROVED":
        raise RatificationProposalError("proposal cannot approve itself")
    if proposal.get("required_human_approval") is not True:
        raise RatificationProposalError("explicit human approval must be required")

    if constitution.get("constitution_status") != "DRAFT":
        raise RatificationProposalError("canonical constitution must remain DRAFT")
    gates = constitution.get("release_gates")
    if not isinstance(gates, dict) or any(gates.values()):
        raise RatificationProposalError("all canonical release gates must remain false")
    pending = constitution.get("pending_decisions")
    if not isinstance(pending, list):
        raise RatificationProposalError("canonical pending decisions are missing")
    pending_ids = tuple(item.get("id") for item in pending)
    if pending_ids != EXPECTED_DECISIONS or any(item.get("status") != "PENDING_RATIFICATION" for item in pending):
        raise RatificationProposalError("canonical pending decisions changed")

    materialization = constitution.get("basket_materialization")
    if not isinstance(materialization, dict):
        raise RatificationProposalError("basket materialization is missing")
    if materialization.get("source_input") != "constitution/inputs/ARMILAR_RESEARCH_CORE_V1_WEIGHTS_OBSERVED_UNIVERSE_V094.csv":
        raise RatificationProposalError("constitutional input must be the immutable snapshot")
    if materialization.get("source_snapshot_policy") != "IMMUTABLE_CONSTITUTIONAL_INPUT":
        raise RatificationProposalError("constitutional snapshot policy is invalid")
    if materialization.get("mutable_public_latest_allowed_as_constitutional_input") is not False:
        raise RatificationProposalError("public/latest must not be constitutional input")
    if materialization.get("upstream_raw_sha256") != "743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83":
        raise RatificationProposalError("upstream raw provenance hash is invalid")
    if materialization.get("constitutional_snapshot_sha256") != "51ed567c1eea6badd077d2bd1fe1f4009a7ce1b542e16971c79c389a4370042f":
        raise RatificationProposalError("constitutional snapshot hash is invalid")
    if materialization.get("constitutional_snapshot_hash_policy") != "UTF8_WITHOUT_BOM_LF":
        raise RatificationProposalError("constitutional snapshot hash policy is invalid")
    if materialization.get("upstream_raw_hash_is_provenance_metadata") is not True:
        raise RatificationProposalError("upstream raw hash must remain provenance metadata")
    if materialization.get("constitutional_snapshot_hash_is_enforced") is not True:
        raise RatificationProposalError("constitutional snapshot hash must be enforced")

    decisions = _decision_map(proposal)
    for item in decisions.values():
        if item.get("status") != "PROPOSED":
            raise RatificationProposalError(f"decision is not PROPOSED: {item.get('id')}")
        record = item.get("decision_record")
        if not isinstance(record, str) or not (root / record).is_file():
            raise RatificationProposalError(f"missing decision record: {record}")
        if not item.get("summary") or not isinstance(item.get("executable_contract"), dict):
            raise RatificationProposalError(f"incomplete decision: {item.get('id')}")

    formula = decisions["official_formula"]["executable_contract"]
    if formula.get("index_type") != "PPP_ADJUSTED_FIXED_WEIGHT_ARITHMETIC_LASPEYRES_TYPE":
        raise RatificationProposalError("PPP-adjusted Laspeyres-type definition is missing")
    weight_definition = formula.get("weight_definition", {})
    if weight_definition.get("target_concept") != "HFCE_2021_REAL_EXPENDITURE_PPP_ADJUSTED":
        raise RatificationProposalError("weight target concept is invalid")
    if weight_definition.get("proxy_exception") != "AIC_PPP_PROXY_IDENTIFIED_PER_CELL":
        raise RatificationProposalError("proxy exception is not explicit")
    scope = formula.get("basket_scope", {})
    if tuple(scope.get("economies", ())) != EXPECTED_ECONOMIES:
        raise RatificationProposalError("basket economies are not fixed")
    if tuple(scope.get("categories", ())) != EXPECTED_CATEGORIES:
        raise RatificationProposalError("basket categories are not fixed")
    if scope.get("new_economy_or_category_requires_new_basket_version") is not True:
        raise RatificationProposalError("basket scope change is not fail-closed")
    exposure = formula.get("proxy_exposure", {})
    if exposure.get("fixed_universe_weight_total") != EXPECTED_PROXY_TOTAL:
        raise RatificationProposalError("proposal proxy exposure total changed")

    series = decisions["exact_series_semantics"]["executable_contract"]
    arm_l = series.get("ARM-L", {})
    information_set = arm_l.get("information_set", {})
    required_information_fields = (
        "information_cutoff_required",
        "retrieval_cutoff_required",
        "source_registry_version_required",
        "model_version_required",
        "raw_snapshot_ids_required",
        "published_at_required",
        "retrieved_at_required",
        "quality_state_required",
    )
    if any(information_set.get(field) is not True for field in required_information_fields):
        raise RatificationProposalError("ARM-L information set is incomplete")
    if arm_l.get("retroactive_revision_to_match_arm_o_allowed") is not False:
        raise RatificationProposalError("ARM-L may not be retrospectively rewritten")
    schedule = arm_l.get("schedule_policy", {})
    if schedule.get("versioned_release_schedule_contract_required") is not True:
        raise RatificationProposalError("ARM-L schedule contract is missing")
    if schedule.get("constitutional_clock_time_fixed") is not False:
        raise RatificationProposalError("constitution must not hard-code ARM-L clock time")

    treatment = decisions["hfce_hicp_conceptual_treatment"]["executable_contract"]
    if treatment.get("proxy_exposure_weight_total") != EXPECTED_PROXY_TOTAL:
        raise RatificationProposalError("HFCE/HICP decision omits proxy exposure")
    if treatment.get("oohpi_vs_hfce_distinction_required") is not True:
        raise RatificationProposalError("OOHPI distinction is missing")
    if treatment.get("hfce_income_imputed_rent_distinction_required") is not True:
        raise RatificationProposalError("HFCE income/imputed-rent distinction is missing")
    ooh = treatment.get("ooh_sensitivity_requirement", {})
    if ooh.get("required_before_external_research_release") is not True:
        raise RatificationProposalError("OOH sensitivity is not required before external release")
    if ooh.get("required_before_shadow_production") is not True:
        raise RatificationProposalError("OOH sensitivity is not required before shadow")
    if ooh.get("does_not_measure_complete_hfce_hicp_gap") is not True:
        raise RatificationProposalError("OOH sensitivity is overstated")

    amendment = decisions["constitutional_amendment_process"]["executable_contract"]
    classes = amendment.get("change_classes", {})
    expected_classes = {
        "EDITORIAL_PATCH",
        "EVIDENCE_METADATA_PATCH",
        "NUMERICAL_WEIGHT_PATCH",
        "BASKET_SCOPE_CHANGE",
        "CONSTITUTIONAL_METHOD_CHANGE",
    }
    if set(classes) != expected_classes:
        raise RatificationProposalError("change classes are incomplete")
    if amendment.get("explicit_human_approval_required") is not True:
        raise RatificationProposalError("human approval is required")
    if amendment.get("prior_versions_preserved") is not True:
        raise RatificationProposalError("prior versions must be preserved")
    if amendment.get("gates_default_to_false_after_amendment") is not True:
        raise RatificationProposalError("gates must default false after amendment")
    transition = amendment.get("proxy_to_exact_transition", {})
    if transition.get("silent_upgrade_allowed") is not False:
        raise RatificationProposalError("silent proxy-to-exact upgrade is forbidden")
    if transition.get("silent_proxy_to_exact_promotion_allowed") is not False:
        raise RatificationProposalError("silent proxy-to-exact promotion is forbidden")
    if transition.get("same_numeric_weight") != "EVIDENCE_METADATA_PATCH":
        raise RatificationProposalError("evidence-only transition is invalid")
    if transition.get("changed_numeric_weight_same_scope") != "NUMERICAL_WEIGHT_PATCH":
        raise RatificationProposalError("numerical transition is invalid")
    if transition.get("new_economy_or_category") != "BASKET_SCOPE_CHANGE":
        raise RatificationProposalError("scope transition is invalid")

    derived_annex = derive_proxy_annex(root)
    if annex != derived_annex:
        raise RatificationProposalError("proxy annex differs from basket-derived exposure")
    if annex_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise RatificationProposalError("proxy annex schema draft is invalid")
    if annex_schema.get("const") != annex:
        raise RatificationProposalError("proxy annex schema is not closed over the annex")

    effect = proposal.get("ratification_effect")
    if not isinstance(effect, dict):
        raise RatificationProposalError("ratification effect is missing")
    if effect.get("next_constitution_status") != "RATIFIED_FOR_ENGINE_DEVELOPMENT":
        raise RatificationProposalError("unexpected proposed constitution status")
    if effect.get("pending_decisions_after_ratification") != 0:
        raise RatificationProposalError("ratification must close all seven decisions")
    effect_gates = effect.get("release_gates_unchanged")
    if not isinstance(effect_gates, dict) or any(effect_gates.values()):
        raise RatificationProposalError("ratification proposal must keep every gate false")

    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise RatificationProposalError("proposal schema draft is invalid")
    if schema.get("const") != proposal:
        raise RatificationProposalError("proposal schema is not closed over the proposal")
    for path in (PROPOSAL_MD_RELATIVE_PATH, PROXY_ANNEX_MD_RELATIVE_PATH):
        if not (root / path).is_file():
            raise RatificationProposalError(f"human-readable file is missing: {path}")
    for path in (PROPOSAL_RELATIVE_PATH, PROPOSAL_MD_RELATIVE_PATH, PROXY_ANNEX_RELATIVE_PATH, PROXY_ANNEX_MD_RELATIVE_PATH, PROPOSAL_SCHEMA_RELATIVE_PATH, PROXY_ANNEX_SCHEMA_RELATIVE_PATH):
        if not (root / path).is_file():
            raise RatificationProposalError(f"proposal asset is missing: {path}")
    return proposal


def render_manifest(root: Path) -> bytes:
    lines = [f"{digest(root / path)} {path.as_posix()}" for path in MANIFEST_PATHS]
    return ("\n".join(lines) + "\n").encode("utf-8")


def check_manifest(root: Path) -> None:
    expected = render_manifest(root)
    path = root / PROPOSAL_MANIFEST_RELATIVE_PATH
    if not path.is_file():
        raise RatificationProposalError("proposal manifest is missing")
    if canonical_text(path.read_bytes()) != expected:
        raise RatificationProposalError("proposal manifest differs from canonical regeneration")


def write_manifest(root: Path) -> None:
    path = root / PROPOSAL_MANIFEST_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_manifest(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Research Core ratification proposal.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    validate(root)
    if args.write_manifest:
        write_manifest(root)
    check_manifest(root)
    print("RATIFICATION_PROPOSAL_COMPLETE_NOT_APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
