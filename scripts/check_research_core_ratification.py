from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROPOSAL_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json")
PROPOSAL_MD_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.md")
PROPOSAL_SCHEMA_RELATIVE_PATH = Path("schemas/research_core_ratification_proposal.schema.json")
PROPOSAL_MANIFEST_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.sha256")
CONSTITUTION_RELATIVE_PATH = Path("constitution/ARMILAR_RESEARCH_CORE_V1.json")
EXPECTED_CONSTITUTION_HASH = "e5f1747c24b9e5cab5ffc894b472543e4e2ee3e3b8429ecd6be94475645b714f"
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
    PROPOSAL_RELATIVE_PATH,
    PROPOSAL_MD_RELATIVE_PATH,
    PROPOSAL_SCHEMA_RELATIVE_PATH,
    Path("docs/DECISION_RESEARCH_CORE_NORMALIZATION_BASE.md"),
    Path("docs/DECISION_RESEARCH_CORE_OFFICIAL_FORMULA.md"),
    Path("docs/DECISION_RESEARCH_CORE_VINTAGE_AND_REVISION_POLICY.md"),
    Path("docs/DECISION_RESEARCH_CORE_PRECISION_AND_ROUNDING.md"),
    Path("docs/DECISION_RESEARCH_CORE_SERIES_SEMANTICS.md"),
    Path("docs/DECISION_RESEARCH_CORE_HFCE_HICP_TREATMENT.md"),
    Path("docs/DECISION_RESEARCH_CORE_AMENDMENT_PROCESS.md"),
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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RatificationProposalError(f"cannot load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RatificationProposalError(f"JSON root must be an object: {path}")
    return payload


def validate(root: Path) -> dict[str, Any]:
    proposal_path = root / PROPOSAL_RELATIVE_PATH
    constitution_path = root / CONSTITUTION_RELATIVE_PATH
    proposal = load_json(proposal_path)
    constitution = load_json(constitution_path)
    schema = load_json(root / PROPOSAL_SCHEMA_RELATIVE_PATH)

    if digest(constitution_path) != EXPECTED_CONSTITUTION_HASH:
        raise RatificationProposalError("target constitution hash changed")
    if proposal.get("target_constitution_sha256") != EXPECTED_CONSTITUTION_HASH:
        raise RatificationProposalError("proposal target hash mismatch")
    if proposal.get("proposal_status") != "PROPOSED":
        raise RatificationProposalError("proposal must remain PROPOSED")
    if proposal.get("approval_status") != "NOT_APPROVED":
        raise RatificationProposalError("proposal cannot approve itself")
    if proposal.get("required_human_approval") is not True:
        raise RatificationProposalError("explicit human approval must be required")
    if constitution.get("constitution_status") != "DRAFT":
        raise RatificationProposalError("canonical constitution must remain DRAFT in proposal PR")
    gates = constitution.get("release_gates")
    if not isinstance(gates, dict) or any(gates.values()):
        raise RatificationProposalError("all canonical release gates must remain false")
    pending = constitution.get("pending_decisions")
    if not isinstance(pending, list):
        raise RatificationProposalError("canonical pending decisions are missing")
    pending_ids = tuple(item.get("id") for item in pending)
    if pending_ids != EXPECTED_DECISIONS or any(item.get("status") != "PENDING_RATIFICATION" for item in pending):
        raise RatificationProposalError("canonical pending decisions changed")
    decisions = proposal.get("decisions")
    if not isinstance(decisions, list):
        raise RatificationProposalError("proposal decisions are missing")
    decision_ids = tuple(item.get("id") for item in decisions)
    if decision_ids != EXPECTED_DECISIONS:
        raise RatificationProposalError("proposal decision set or order is invalid")
    for item in decisions:
        if item.get("status") != "PROPOSED":
            raise RatificationProposalError(f"decision is not PROPOSED: {item.get('id')}")
        record = item.get("decision_record")
        if not isinstance(record, str) or not (root / record).is_file():
            raise RatificationProposalError(f"missing decision record: {record}")
        if not item.get("summary") or not isinstance(item.get("executable_contract"), dict):
            raise RatificationProposalError(f"incomplete decision: {item.get('id')}")
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
    if not (root / PROPOSAL_MD_RELATIVE_PATH).is_file():
        raise RatificationProposalError("human-readable proposal is missing")
    return proposal


def render_manifest(root: Path) -> bytes:
    lines = [f"{digest(root / path)}  {path.as_posix()}" for path in MANIFEST_PATHS]
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
