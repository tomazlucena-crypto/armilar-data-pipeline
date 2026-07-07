"""ARMILAR v0.10.2 ECOICOP v2 transition audit.

This module turns the 2026 Eurostat HICP classification change into a fail-closed,
executable contract.  It does not extend ARM-O, alter the Research Core basket,
or claim semantic equivalence between ECOICOP version 1 and version 2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")
LEGACY_CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
V2_DIVISIONS = tuple(f"CP{i:02d}" for i in range(1, 14))
MATERIAL_RECLASSIFICATIONS = ("CP08", "CP09")
LEGACY_SPLIT_DIVISION = "CP12"
NEW_DIVISION = "CP13"
REPLACEMENT_BACK_SERIES_START = "1996-01"
REPLACEMENT_BACK_SERIES_END = "2025-12"
FIRST_LIVE_REFERENCE_PERIOD = "2026-01"
STATUS = "ECOICOP_V2_TRANSITION_BLOCKED_PENDING_EXPLICIT_DECISION"
REQUIRED_NEXT_DECISION = "EXPLICIT_CONSTITUTIONAL_TRANSITION_DECISION_AND_BACKTEST"
MATRIX_COLUMNS = (
    "replacement_division",
    "legacy_division",
    "transition_class",
    "automatic_use_allowed",
    "reason",
)


class EcoicopTransitionError(RuntimeError):
    """Raised when the transition audit cannot prove its frozen invariants."""


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _canonical_text_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise EcoicopTransitionError(f"UTF-8 BOM forbidden: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EcoicopTransitionError(f"invalid UTF-8: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    if not path.is_file():
        raise EcoicopTransitionError(f"required file missing: {path}")
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_canonical_text_bytes(path).decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EcoicopTransitionError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EcoicopTransitionError(f"JSON object required: {path}")
    return payload


def _parse_utc(value: str, field: str) -> str:
    if not UTC_RE.fullmatch(value):
        raise EcoicopTransitionError(f"{field} must be an explicit UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EcoicopTransitionError(f"invalid {field}: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EcoicopTransitionError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved = root.resolve()
    if candidate != resolved and resolved not in candidate.parents:
        raise EcoicopTransitionError(f"path escapes root: {relative}")
    return candidate


def _csv_bytes(rows: Sequence[Mapping[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(MATRIX_COLUMNS),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in MATRIX_COLUMNS})
    return stream.getvalue().encode("utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != MATRIX_COLUMNS:
                raise EcoicopTransitionError("transition matrix columns changed")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise EcoicopTransitionError(f"cannot read CSV: {path}") from exc


def _manifest_entries(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256_path(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.sha256"
    }


def _write_manifest(root: Path) -> None:
    entries = _manifest_entries(root)
    text = "".join(f"{digest}  {relative}\n" for relative, digest in entries.items())
    (root / "MANIFEST.sha256").write_text(text, encoding="utf-8", newline="\n")


def _verify_manifest(root: Path) -> dict[str, str]:
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise EcoicopTransitionError("MANIFEST.sha256 missing")
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^ ].*)", line)
        if match is None:
            raise EcoicopTransitionError(f"invalid manifest line {number}")
        digest, relative = match.groups()
        if relative in entries:
            raise EcoicopTransitionError(f"duplicate manifest entry: {relative}")
        target = _safe_child(root, relative)
        if not target.is_file() or _sha256_path(target) != digest:
            raise EcoicopTransitionError(f"manifest mismatch: {relative}")
        entries[relative] = digest
    if entries != _manifest_entries(root):
        raise EcoicopTransitionError("manifest file set mismatch")
    return entries


@dataclass(frozen=True, slots=True)
class TransitionPolicy:
    policy_id: str
    policy_version: str
    constitution_path: str
    legacy_source_policy_path: str
    legacy_dataset: str
    replacement_dataset: str
    legacy_classification: str
    replacement_classification: str
    legacy_end_period: str
    replacement_reference_base: str
    replacement_back_series_start_period: str
    replacement_back_series_end_period: str
    first_live_reference_period: str
    legacy_categories: tuple[str, ...]
    replacement_divisions: tuple[str, ...]
    materially_revised_divisions: tuple[str, ...]
    split_legacy_division: str
    new_division: str
    direct_extension_allowed: bool
    same_code_semantic_equivalence_assumed: bool
    drop_new_division_allowed: bool
    silent_category_expansion_allowed: bool
    back_series_automatic_substitution_allowed: bool
    required_next_decision: str
    official_evidence: tuple[Mapping[str, str], ...]
    gates: Mapping[str, bool]

    @classmethod
    def load(cls, path: Path) -> "TransitionPolicy":
        payload = _read_json(path)
        required = {
            "policy_id",
            "policy_version",
            "constitution_path",
            "legacy_source_policy_path",
            "legacy_dataset",
            "replacement_dataset",
            "legacy_classification",
            "replacement_classification",
            "legacy_end_period",
            "replacement_reference_base",
            "replacement_back_series_start_period",
            "replacement_back_series_end_period",
            "first_live_reference_period",
            "legacy_categories",
            "replacement_divisions",
            "materially_revised_divisions",
            "split_legacy_division",
            "new_division",
            "direct_extension_allowed",
            "same_code_semantic_equivalence_assumed",
            "drop_new_division_allowed",
            "silent_category_expansion_allowed",
            "back_series_automatic_substitution_allowed",
            "required_next_decision",
            "official_evidence",
            "gates",
        }
        if set(payload) != required:
            raise EcoicopTransitionError(
                "policy keys mismatch; "
                f"missing={sorted(required-set(payload))}, extra={sorted(set(payload)-required)}"
            )
        if payload["policy_id"] != "ARMILAR_ECOICOP_V2_TRANSITION_AUDIT_V0102":
            raise EcoicopTransitionError("unexpected policy_id")
        if payload["policy_version"] != "0.10.2":
            raise EcoicopTransitionError("policy_version must be 0.10.2")
        if payload["legacy_dataset"] != "prc_hicp_midx":
            raise EcoicopTransitionError("legacy dataset changed")
        if payload["replacement_dataset"] != "prc_hicp_minr":
            raise EcoicopTransitionError("replacement dataset must be prc_hicp_minr")
        if payload["legacy_classification"] != "ECOICOP_V1_PRE_2026":
            raise EcoicopTransitionError("legacy classification changed")
        if payload["replacement_classification"] != "ECOICOP_V2_FROM_2026":
            raise EcoicopTransitionError("replacement classification changed")
        if payload["legacy_end_period"] != "2025-12":
            raise EcoicopTransitionError("legacy end period must remain 2025-12")
        if payload["replacement_reference_base"] != "2025=100":
            raise EcoicopTransitionError("replacement reference base must be 2025=100")
        if payload["replacement_back_series_start_period"] != REPLACEMENT_BACK_SERIES_START:
            raise EcoicopTransitionError("replacement back series must start at 1996-01")
        if payload["replacement_back_series_end_period"] != REPLACEMENT_BACK_SERIES_END:
            raise EcoicopTransitionError("replacement back series must end at 2025-12")
        if payload["first_live_reference_period"] != FIRST_LIVE_REFERENCE_PERIOD:
            raise EcoicopTransitionError("first live reference period must be 2026-01")
        if tuple(payload["legacy_categories"]) != LEGACY_CATEGORIES:
            raise EcoicopTransitionError("legacy categories must remain CP01-CP12")
        if tuple(payload["replacement_divisions"]) != V2_DIVISIONS:
            raise EcoicopTransitionError("replacement divisions must be CP01-CP13")
        if tuple(payload["materially_revised_divisions"]) != MATERIAL_RECLASSIFICATIONS:
            raise EcoicopTransitionError("material reclassification set changed")
        if payload["split_legacy_division"] != LEGACY_SPLIT_DIVISION:
            raise EcoicopTransitionError("split legacy division must be CP12")
        if payload["new_division"] != NEW_DIVISION:
            raise EcoicopTransitionError("new division must be CP13")
        false_fields = (
            "direct_extension_allowed",
            "same_code_semantic_equivalence_assumed",
            "drop_new_division_allowed",
            "silent_category_expansion_allowed",
            "back_series_automatic_substitution_allowed",
        )
        for field in false_fields:
            if payload[field] is not False:
                raise EcoicopTransitionError(f"{field} must remain false")
        if payload["required_next_decision"] != REQUIRED_NEXT_DECISION:
            raise EcoicopTransitionError("required next decision changed")
        evidence = payload["official_evidence"]
        if not isinstance(evidence, list) or len(evidence) < 3:
            raise EcoicopTransitionError("at least three official evidence records are required")
        evidence_ids: set[str] = set()
        frozen_evidence: list[Mapping[str, str]] = []
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"evidence_id", "url", "claim"}:
                raise EcoicopTransitionError("official evidence record malformed")
            evidence_id = str(item["evidence_id"])
            url = str(item["url"])
            claim = str(item["claim"])
            if evidence_id in evidence_ids or not evidence_id or not claim:
                raise EcoicopTransitionError("official evidence ids and claims must be unique and non-empty")
            if not url.startswith("https://ec.europa.eu/eurostat/"):
                raise EcoicopTransitionError("official evidence must use an Eurostat HTTPS URL")
            evidence_ids.add(evidence_id)
            frozen_evidence.append({"evidence_id": evidence_id, "url": url, "claim": claim})
        required_evidence = {
            "EUROSTAT_HICP_2026_QA",
            "EUROSTAT_HICP_ESMS",
            "EUROSTAT_HICP_DATABASE_INFORMATION",
        }
        if not required_evidence.issubset(evidence_ids):
            raise EcoicopTransitionError("required official evidence records missing")
        gates = payload["gates"]
        expected_gates = {
            "classification_transition_ratified",
            "arm_o_2026_extension_allowed",
            "backtest_execution_claim_allowed",
            "research_release_allowed",
            "model_training_allowed",
            "arm_l_use_allowed",
            "shadow_production_allowed",
            "monetary_use_allowed",
        }
        if not isinstance(gates, dict) or set(gates) != expected_gates:
            raise EcoicopTransitionError("transition gate set mismatch")
        if any(bool(gates[name]) for name in expected_gates):
            raise EcoicopTransitionError("all v0.10.2 gates must remain false")
        return cls(
            policy_id=str(payload["policy_id"]),
            policy_version="0.10.2",
            constitution_path=str(payload["constitution_path"]),
            legacy_source_policy_path=str(payload["legacy_source_policy_path"]),
            legacy_dataset="prc_hicp_midx",
            replacement_dataset="prc_hicp_minr",
            legacy_classification="ECOICOP_V1_PRE_2026",
            replacement_classification="ECOICOP_V2_FROM_2026",
            legacy_end_period="2025-12",
            replacement_reference_base="2025=100",
            replacement_back_series_start_period=REPLACEMENT_BACK_SERIES_START,
            replacement_back_series_end_period=REPLACEMENT_BACK_SERIES_END,
            first_live_reference_period=FIRST_LIVE_REFERENCE_PERIOD,
            legacy_categories=LEGACY_CATEGORIES,
            replacement_divisions=V2_DIVISIONS,
            materially_revised_divisions=MATERIAL_RECLASSIFICATIONS,
            split_legacy_division=LEGACY_SPLIT_DIVISION,
            new_division=NEW_DIVISION,
            direct_extension_allowed=False,
            same_code_semantic_equivalence_assumed=False,
            drop_new_division_allowed=False,
            silent_category_expansion_allowed=False,
            back_series_automatic_substitution_allowed=False,
            required_next_decision=REQUIRED_NEXT_DECISION,
            official_evidence=tuple(frozen_evidence),
            gates={name: False for name in sorted(expected_gates)},
        )


def _transition_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for division in V2_DIVISIONS:
        if division in MATERIAL_RECLASSIFICATIONS:
            transition_class = "MATERIAL_RECLASSIFICATION"
            legacy = division
            reason = "Eurostat identifies divisions 08 and 09 as significantly revised under COICOP 2018."
        elif division == LEGACY_SPLIT_DIVISION:
            transition_class = "LEGACY_DIVISION_SPLIT"
            legacy = LEGACY_SPLIT_DIVISION
            reason = "Legacy CP12 is no longer a one-to-one division because ECOICOP v2 separates CP12 and CP13."
        elif division == NEW_DIVISION:
            transition_class = "LEGACY_DIVISION_SPLIT_NEW_BRANCH"
            legacy = LEGACY_SPLIT_DIVISION
            reason = "CP13 is a new published division derived from the former miscellaneous scope and cannot be dropped or silently folded into the frozen basket."
        else:
            transition_class = "CODE_CONTINUITY_REQUIRES_BACKSERIES_AUDIT"
            legacy = division
            reason = "A matching division code alone does not prove item-level semantic equivalence."
        rows.append(
            {
                "replacement_division": division,
                "legacy_division": legacy,
                "transition_class": transition_class,
                "automatic_use_allowed": "false",
                "reason": reason,
            }
        )
    return rows


def _validate_repository_inputs(root: Path, policy: TransitionPolicy) -> dict[str, Any]:
    constitution_path = _safe_child(root, policy.constitution_path)
    legacy_path = _safe_child(root, policy.legacy_source_policy_path)
    constitution = _read_json(constitution_path)
    legacy = _read_json(legacy_path)
    basket_categories = tuple(constitution.get("basket_categories") or ())
    if basket_categories != LEGACY_CATEGORIES:
        raise EcoicopTransitionError("Research Core basket categories changed")
    prohibitions = set(constitution.get("prohibitions") or ())
    required_prohibitions = {
        "SILENT_CATEGORY_EXPANSION",
        "AUTOMATIC_WEIGHT_CHANGES",
        "AUTOMATIC_GATE_ACTIVATION",
    }
    if not required_prohibitions.issubset(prohibitions):
        raise EcoicopTransitionError("Research Core transition prohibitions are incomplete")
    release_gates = constitution.get("release_gates")
    if not isinstance(release_gates, dict) or any(bool(value) for value in release_gates.values()):
        raise EcoicopTransitionError("Research Core release gates must remain closed")
    if legacy.get("policy_version") != "0.8.7":
        raise EcoicopTransitionError("legacy source policy version changed")
    if legacy.get("dataset") != policy.legacy_dataset:
        raise EcoicopTransitionError("legacy source policy dataset mismatch")
    if legacy.get("classification_version") != policy.legacy_classification:
        raise EcoicopTransitionError("legacy source policy classification mismatch")
    if legacy.get("end_period") != policy.legacy_end_period:
        raise EcoicopTransitionError("legacy source policy end period mismatch")
    if tuple(legacy.get("source_categories") or ()) != LEGACY_CATEGORIES:
        raise EcoicopTransitionError("legacy source policy category grid changed")
    if bool(legacy.get("research_release_allowed")) or bool(legacy.get("monetary_release_allowed")):
        raise EcoicopTransitionError("legacy source policy gates must remain closed")
    return {
        "constitution_sha256": _sha256_path(constitution_path),
        "legacy_source_policy_sha256": _sha256_path(legacy_path),
        "constitution_status": constitution.get("constitution_status"),
        "basket_category_count": len(basket_categories),
    }


def build_transition_audit(
    *, policy_path: Path, root: Path, output_dir: Path, created_at: str
) -> dict[str, Any]:
    policy = TransitionPolicy.load(policy_path)
    created_at = _parse_utc(created_at, "created_at")
    inputs = _validate_repository_inputs(root, policy)
    rows = _transition_rows()
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "0.10.2",
        "status": STATUS,
        "created_at": created_at,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "legacy_dataset": policy.legacy_dataset,
        "replacement_dataset": policy.replacement_dataset,
        "legacy_classification": policy.legacy_classification,
        "replacement_classification": policy.replacement_classification,
        "legacy_end_period": policy.legacy_end_period,
        "replacement_reference_base": policy.replacement_reference_base,
        "replacement_back_series_start_period": policy.replacement_back_series_start_period,
        "replacement_back_series_end_period": policy.replacement_back_series_end_period,
        "first_live_reference_period": policy.first_live_reference_period,
        "replacement_back_series_available": True,
        "legacy_category_count": len(policy.legacy_categories),
        "replacement_division_count": len(policy.replacement_divisions),
        "material_reclassification_count": len(policy.materially_revised_divisions),
        "split_legacy_division": policy.split_legacy_division,
        "new_division": policy.new_division,
        "automatic_use_allowed_count": 0,
        "direct_extension_allowed": False,
        "same_code_semantic_equivalence_assumed": False,
        "drop_new_division_allowed": False,
        "silent_category_expansion_allowed": False,
        "back_series_automatic_substitution_allowed": False,
        "required_next_decision": policy.required_next_decision,
        "official_evidence_count": len(policy.official_evidence),
        "constitution_sha256": inputs["constitution_sha256"],
        "legacy_source_policy_sha256": inputs["legacy_source_policy_sha256"],
        "gates": dict(policy.gates),
    }
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EcoicopTransitionError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        (staging / "ecoicop_v2_transition_matrix.csv").write_bytes(_csv_bytes(rows))
        (staging / "ecoicop_v2_transition_summary.json").write_bytes(
            _canonical_json_bytes(summary)
        )
        (staging / "official_evidence.json").write_bytes(
            _canonical_json_bytes({"evidence": list(policy.official_evidence)})
        )
        _write_manifest(staging)
        verify_transition_audit(
            staging,
            policy_path=policy_path,
            root=root,
        )
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return summary


def verify_transition_audit(
    path: Path, *, policy_path: Path, root: Path
) -> dict[str, Any]:
    policy = TransitionPolicy.load(policy_path)
    _validate_repository_inputs(root, policy)
    entries = _verify_manifest(path)
    expected_files = {
        "ecoicop_v2_transition_matrix.csv",
        "ecoicop_v2_transition_summary.json",
        "official_evidence.json",
    }
    if set(entries) != expected_files:
        raise EcoicopTransitionError("transition audit file set mismatch")
    summary = _read_json(path / "ecoicop_v2_transition_summary.json")
    if summary.get("status") != STATUS:
        raise EcoicopTransitionError("unexpected transition status")
    if summary.get("policy_id") != policy.policy_id or summary.get("policy_version") != policy.policy_version:
        raise EcoicopTransitionError("transition policy mismatch")
    if summary.get("legacy_category_count") != 12 or summary.get("replacement_division_count") != 13:
        raise EcoicopTransitionError("transition category counts changed")
    if summary.get("material_reclassification_count") != 2:
        raise EcoicopTransitionError("material reclassification count changed")
    false_fields = (
        "direct_extension_allowed",
        "same_code_semantic_equivalence_assumed",
        "drop_new_division_allowed",
        "silent_category_expansion_allowed",
        "back_series_automatic_substitution_allowed",
    )
    if any(summary.get(field) is not False for field in false_fields):
        raise EcoicopTransitionError("transition safety field opened")
    if summary.get("automatic_use_allowed_count") != 0:
        raise EcoicopTransitionError("automatic transition use was opened")
    if summary.get("required_next_decision") != REQUIRED_NEXT_DECISION:
        raise EcoicopTransitionError("required next decision changed")
    if summary.get("gates") != dict(policy.gates):
        raise EcoicopTransitionError("transition gates mismatch")
    rows = _read_csv(path / "ecoicop_v2_transition_matrix.csv")
    if len(rows) != 13 or tuple(row["replacement_division"] for row in rows) != V2_DIVISIONS:
        raise EcoicopTransitionError("transition matrix division grid mismatch")
    if any(row["automatic_use_allowed"] != "false" for row in rows):
        raise EcoicopTransitionError("automatic transition row opened")
    by_division = {row["replacement_division"]: row for row in rows}
    for division in MATERIAL_RECLASSIFICATIONS:
        if by_division[division]["transition_class"] != "MATERIAL_RECLASSIFICATION":
            raise EcoicopTransitionError(f"material reclassification lost: {division}")
    if by_division["CP12"]["transition_class"] != "LEGACY_DIVISION_SPLIT":
        raise EcoicopTransitionError("CP12 split classification lost")
    if by_division["CP13"]["transition_class"] != "LEGACY_DIVISION_SPLIT_NEW_BRANCH":
        raise EcoicopTransitionError("CP13 split-branch classification lost")
    if by_division["CP13"]["legacy_division"] != "CP12":
        raise EcoicopTransitionError("CP13 legacy relationship lost")
    if summary.get("replacement_back_series_available") is not True:
        raise EcoicopTransitionError("replacement back-series availability changed")
    if summary.get("replacement_back_series_start_period") != REPLACEMENT_BACK_SERIES_START:
        raise EcoicopTransitionError("replacement back-series start changed")
    if summary.get("replacement_back_series_end_period") != REPLACEMENT_BACK_SERIES_END:
        raise EcoicopTransitionError("replacement back-series end changed")
    if summary.get("first_live_reference_period") != FIRST_LIVE_REFERENCE_PERIOD:
        raise EcoicopTransitionError("first live reference period changed")
    evidence = _read_json(path / "official_evidence.json")
    if evidence.get("evidence") != list(policy.official_evidence):
        raise EcoicopTransitionError("official evidence changed")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-policy")
    validate.add_argument("--policy", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--policy", type=Path, required=True)
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--created-at", required=True)
    verify = sub.add_parser("verify-audit")
    verify.add_argument("--policy", type=Path, required=True)
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--audit", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-policy":
            policy = TransitionPolicy.load(args.policy)
            payload = {
                "status": "ECOICOP_V2_TRANSITION_POLICY_V0102_VALID",
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "gates": dict(policy.gates),
            }
        elif args.command == "audit":
            payload = build_transition_audit(
                policy_path=args.policy,
                root=args.root,
                output_dir=args.output,
                created_at=args.created_at,
            )
        elif args.command == "verify-audit":
            payload = verify_transition_audit(
                args.audit,
                policy_path=args.policy,
                root=args.root,
            )
        else:  # pragma: no cover
            raise EcoicopTransitionError("unknown command")
    except EcoicopTransitionError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
