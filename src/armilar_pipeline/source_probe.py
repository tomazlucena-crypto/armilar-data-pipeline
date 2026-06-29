from __future__ import annotations

import csv
import html
import re
import shutil
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .acquire import AcquisitionError, AcquisitionRecord, fetch_url
from .config import Step2Config
from .util import normalize_text, utc_now, write_csv, write_json, write_sha256sums


CLASS_RANK = {
    "A_CANDIDATE": 4,
    "B_CANDIDATE": 3,
    "C_ONLY": 2,
    "D_UNAVAILABLE": 1,
}

METHODOLOGICAL_STATES = {
    "EXACT_OFFICIAL",
    "OFFICIAL_DERIVED_NO_ALLOCATION",
    "OFFICIAL_EXPERIMENTAL_ALLOCATION",
    "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
    "ACCESS_BLOCKED",
    "SOURCE_NOT_MACHINE_READABLE",
    "CONCEPT_AMBIGUOUS",
    "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT",
}

SOURCE_FAMILIES = (
    (1, "official_national_accounts_api"),
    (2, "official_csv_xls_xlsx"),
    (3, "official_statistical_database"),
    (4, "official_supply_and_use_tables"),
    (5, "official_structured_publications"),
    (6, "survey_or_cpi_class_c_only"),
)
FAMILY_ORDER = {family: order for order, family in SOURCE_FAMILIES}
EXHAUSTIVE_CORE_FAMILIES = {family for order, family in SOURCE_FAMILIES if order <= 5}

DATASET_RESOURCE_TYPES = {
    "API_RESPONSE",
    "DATA_FILE",
    "DATABASE_QUERY",
    "HTML_TABLE",
}
DISCOVERY_RESOURCE_TYPES = {
    "LANDING_PAGE",
    "DOCUMENTATION",
    "PUBLICATION_PAGE",
    "PUBLICATION_FILE",
}


@dataclass(frozen=True)
class SourceCandidate:
    economy_code: str
    economy_name: str
    source_id: str
    source_authority: str
    source_title: str
    source_url: str
    access_method: str
    source_family: str
    family_order: int
    resource_type: str
    evidence_role: str
    reference_period: str
    national_accounts_or_survey: str
    institutional_sector: str
    transaction_code: str
    classification: str
    category_coverage: str
    current_prices_available: str
    currency: str
    unit: str
    npish_excluded: str
    government_excluded: str
    imputed_rent_included: str
    machine_readable: str
    methodological_candidate_class: str
    methodological_state: str
    confidence: str
    integration_cost: str
    blocking_reason: str
    expected_content_types: tuple[str, ...]
    required_markers: tuple[str, ...]
    notes: str

    def as_dict(self) -> dict[str, Any]:
        row = dict(self.__dict__)
        row["expected_content_types"] = "|".join(self.expected_content_types)
        row["required_markers"] = "|".join(self.required_markers)
        return row


@dataclass
class SourceProbeResult:
    acquisition_records: list[AcquisitionRecord]
    candidate_rows: list[dict[str, Any]]
    economy_rows: list[dict[str, Any]]
    family_rows: list[dict[str, Any]]
    failure_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def load_source_candidates(path: Path) -> list[SourceCandidate]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: list[SourceCandidate] = []
    seen: set[str] = set()
    for row in rows:
        source_id = (row.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source_probe_candidates.csv contains a blank source_id")
        if source_id in seen:
            raise ValueError(f"Duplicate source probe source_id: {source_id}")
        seen.add(source_id)
        candidate_class = (row.get("methodological_candidate_class") or "").strip()
        if candidate_class not in CLASS_RANK:
            raise ValueError(f"Invalid candidate class for {source_id}: {candidate_class}")
        source_family = (row.get("source_family") or "official_structured_publications").strip()
        if source_family not in FAMILY_ORDER:
            raise ValueError(f"Invalid source family for {source_id}: {source_family}")
        methodological_state = (row.get("methodological_state") or _default_state(candidate_class)).strip()
        if methodological_state not in METHODOLOGICAL_STATES:
            raise ValueError(f"Invalid methodological state for {source_id}: {methodological_state}")
        resource_type = (row.get("resource_type") or _infer_resource_type(row)).strip().upper()
        evidence_role = (row.get("evidence_role") or "DATASET").strip().upper()
        result.append(SourceCandidate(
            economy_code=(row.get("economy_code") or "").strip().upper(),
            economy_name=(row.get("economy_name") or "").strip(),
            source_id=source_id,
            source_authority=(row.get("source_authority") or "").strip(),
            source_title=(row.get("source_title") or "").strip(),
            source_url=(row.get("source_url") or "").strip(),
            access_method=(row.get("access_method") or "").strip(),
            source_family=source_family,
            family_order=int((row.get("family_order") or FAMILY_ORDER[source_family]).strip() if isinstance(row.get("family_order"), str) else row.get("family_order") or FAMILY_ORDER[source_family]),
            resource_type=resource_type,
            evidence_role=evidence_role,
            reference_period=(row.get("reference_period") or "").strip(),
            national_accounts_or_survey=(row.get("national_accounts_or_survey") or "").strip(),
            institutional_sector=(row.get("institutional_sector") or "").strip(),
            transaction_code=(row.get("transaction_code") or "").strip(),
            classification=(row.get("classification") or "").strip(),
            category_coverage=(row.get("category_coverage") or "").strip(),
            current_prices_available=(row.get("current_prices_available") or "").strip(),
            currency=(row.get("currency") or "").strip(),
            unit=(row.get("unit") or "").strip(),
            npish_excluded=(row.get("npish_excluded") or "").strip(),
            government_excluded=(row.get("government_excluded") or "").strip(),
            imputed_rent_included=(row.get("imputed_rent_included") or "").strip(),
            machine_readable=(row.get("machine_readable") or "").strip(),
            methodological_candidate_class=candidate_class,
            methodological_state=methodological_state,
            confidence=(row.get("confidence") or "").strip(),
            integration_cost=(row.get("integration_cost") or "").strip(),
            blocking_reason=(row.get("blocking_reason") or "").strip(),
            expected_content_types=tuple(item.strip().lower() for item in (row.get("expected_content_types") or "").split("|") if item.strip()),
            required_markers=tuple(normalize_text(item) for item in (row.get("required_markers") or "").split("|") if item.strip()),
            notes=(row.get("notes") or "").strip(),
        ))
    return result


def _default_state(candidate_class: str) -> str:
    return {
        "A_CANDIDATE": "EXACT_OFFICIAL",
        "B_CANDIDATE": "CONCEPT_AMBIGUOUS",
        "C_ONLY": "OFFICIAL_EXPERIMENTAL_ALLOCATION",
        "D_UNAVAILABLE": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
    }[candidate_class]


def _infer_resource_type(row: dict[str, str]) -> str:
    url = (row.get("source_url") or "").lower()
    method = (row.get("access_method") or "").upper()
    if method.startswith("API") or ".json" in url:
        return "API_RESPONSE"
    if any(url.endswith(suffix) for suffix in (".xlsx", ".xls", ".csv", ".zip", ".ods")):
        return "DATA_FILE"
    if url.endswith(".pdf"):
        return "PUBLICATION_FILE"
    if "database" in method or "query" in method:
        return "DATABASE_QUERY"
    return "HTML_TABLE"


def run_source_probes(
    config: Step2Config,
    *,
    candidates_path: Path,
    run_root: Path,
    cache_root: Path,
    economy_codes: list[str] | tuple[str, ...] | None = None,
) -> SourceProbeResult:
    candidates = load_source_candidates(candidates_path)
    selected = {code.strip().upper() for code in (economy_codes or []) if code.strip()}
    if selected:
        candidates = [candidate for candidate in candidates if candidate.economy_code in selected]
        missing = selected - {candidate.economy_code for candidate in candidates}
        if missing:
            raise ValueError(f"Unknown source-probe economy codes: {', '.join(sorted(missing))}")

    acquisition_records: list[AcquisitionRecord] = []
    candidate_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    def execute(candidate: SourceCandidate):
        return _probe_candidate(
            config, candidate=candidate, run_root=run_root, cache_root=cache_root
        )

    # executor.map preserves registry order, so outputs remain deterministic even
    # though network-bound acquisitions run concurrently.
    max_workers = max(1, min(config.source_probe_max_workers, len(candidates) or 1))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="armilar-source-probe") as executor:
        results = list(executor.map(execute, candidates))
    for record, candidate_row, failure_row in results:
        if record is not None:
            acquisition_records.append(record)
        candidate_rows.append(candidate_row)
        if failure_row is not None:
            failure_rows.append(failure_row)

    family_rows = _source_family_coverage(candidate_rows)
    economy_rows = _economy_summary(candidate_rows, family_rows)
    counts: dict[str, int] = {key: 0 for key in CLASS_RANK}
    state_counts: dict[str, int] = {}
    for row in economy_rows:
        counts[str(row["best_runtime_candidate_class"])] += 1
        state = str(row["audit_state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    summary = {
        "schema_version": "2.1",
        "pipeline_version": config.pipeline_version,
        "economies_probed": len(economy_rows),
        "source_candidates_probed": len(candidate_rows),
        "source_probe_max_workers": max_workers,
        "source_candidates_acquired_as_datasets": sum(1 for row in candidate_rows if row["retrieval_status"] == "ACQUIRED_DATASET"),
        "source_candidates_acquired_as_discovery_only": sum(1 for row in candidate_rows if row["retrieval_status"] == "ACQUIRED_DISCOVERY_EVIDENCE"),
        "source_candidates_acquired_as_documentation": sum(1 for row in candidate_rows if row["retrieval_status"] == "ACQUIRED_DOCUMENTATION_EVIDENCE"),
        "source_candidates_access_blocked": sum(1 for row in candidate_rows if row["retrieval_status"] == "ACCESS_BLOCKED"),
        "source_candidates_content_validation_failed": sum(1 for row in candidate_rows if row["retrieval_status"] == "CONTENT_VALIDATION_FAILED"),
        "source_candidates_failed": len(failure_rows),
        "economy_class_counts": counts,
        "economy_audit_state_counts": state_counts,
        "a_or_b_candidate_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] in {"A_CANDIDATE", "B_CANDIDATE"}),
        "c_only_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] == "C_ONLY"),
        "d_unavailable_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] == "D_UNAVAILABLE"),
        "economies_with_complete_core_family_probe": sum(1 for row in economy_rows if row["core_family_probe_complete"]),
        "uninvestigated_core_family_count": sum(1 for row in family_rows if row["core_family"] and row["audit_status"] == "NOT_INVESTIGATED"),
        "definitive_unavailability_decisions": sum(1 for row in economy_rows if row["audit_state"] == "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT"),
        "classification_note": "D_UNAVAILABLE is a provisional source-probe class. Definitive unavailability requires the separate UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT state and documentary proof.",
    }
    return SourceProbeResult(acquisition_records, candidate_rows, economy_rows, family_rows, failure_rows, summary)


def _probe_candidate(
    config: Step2Config,
    *,
    candidate: SourceCandidate,
    run_root: Path,
    cache_root: Path,
) -> tuple[AcquisitionRecord | None, dict[str, Any], dict[str, Any] | None]:
    raw_root = run_root / "raw" / "source_probe"
    extension = _extension_for(candidate.source_url, candidate.expected_content_types)
    destination = raw_root / candidate.economy_code / candidate.source_id / f"source{extension}"
    cache_path = cache_root / "source_probe" / candidate.economy_code / candidate.source_id / f"source{extension}"
    accept = _accept_header(candidate.expected_content_types)
    try:
        record = fetch_url(
            config,
            source_id=f"source_probe_{candidate.source_id}",
            url=candidate.source_url,
            destination=destination,
            cache_path=cache_path,
            accept=accept,
        )
        try:
            signature_status, signature_reason = _validate_signature(destination, record.content_type, candidate.expected_content_types)
            marker_status, missing_markers = _validate_markers(destination, candidate.required_markers)
        except Exception as exc:
            signature_status, signature_reason = "FAIL", f"VALIDATION_EXCEPTION:{type(exc).__name__}"
            marker_status, missing_markers = "NOT_RUN", []
        accessible = signature_status == "PASS" and marker_status in {"PASS", "NOT_APPLICABLE"}
        dataset_evidence = accessible and _qualifies_as_dataset_evidence(candidate)
        if dataset_evidence:
            retrieval_status = "ACQUIRED_DATASET"
            runtime_class = candidate.methodological_candidate_class
            runtime_state = candidate.methodological_state
            evidence_status = "QUALIFYING_DATASET"
            runtime_reason = candidate.blocking_reason
        elif accessible and candidate.evidence_role == "DOCUMENTATION":
            retrieval_status = "ACQUIRED_DOCUMENTATION_EVIDENCE"
            runtime_class = "D_UNAVAILABLE"
            runtime_state = candidate.methodological_state
            evidence_status = "DOCUMENTATION_ONLY"
            runtime_reason = candidate.blocking_reason or "OFFICIAL_DOCUMENTATION_DOES_NOT_CONSTITUTE_A_DATASET"
        elif accessible:
            retrieval_status = "ACQUIRED_DISCOVERY_EVIDENCE"
            runtime_class = "D_UNAVAILABLE"
            runtime_state = (
                "SOURCE_NOT_MACHINE_READABLE"
                if candidate.resource_type == "PUBLICATION_FILE"
                else "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            )
            evidence_status = "DISCOVERY_ONLY"
            runtime_reason = _discovery_rejection_reason(candidate)
        else:
            retrieval_status = "CONTENT_VALIDATION_FAILED"
            runtime_class = "D_UNAVAILABLE"
            runtime_state = "SOURCE_NOT_MACHINE_READABLE"
            evidence_status = "INVALID_CONTENT"
            runtime_reason = f"SOURCE_CONTENT_NOT_VALIDATED:{signature_reason or '|'.join(missing_markers)}"
        row = {
            **candidate.as_dict(),
            "retrieval_status": retrieval_status,
            "acquisition_freshness": record.status,
            "http_status": record.status_code if record.status_code is not None else "",
            "final_url": record.final_url,
            "content_type": record.content_type or "",
            "bytes": record.bytes,
            "source_hash": record.sha256,
            "retrieved_at": record.retrieved_at,
            "local_file": destination.relative_to(run_root).as_posix(),
            "failure_receipt": "",
            "attempt_count": len(record.attempt_errors) + 1,
            "attempt_errors": "|".join(record.attempt_errors),
            "signature_status": signature_status,
            "signature_reason": signature_reason,
            "marker_status": marker_status,
            "missing_markers": "|".join(missing_markers),
            "dataset_evidence_status": evidence_status,
            "homepage_rejected_as_dataset": candidate.resource_type == "LANDING_PAGE",
            "runtime_candidate_class": runtime_class,
            "runtime_methodological_state": _guard_exhaustive_state(runtime_state, False),
            "runtime_blocking_reason": runtime_reason,
            "decision_is_provisional": runtime_state not in {"EXACT_OFFICIAL", "OFFICIAL_DERIVED_NO_ALLOCATION"},
        }
        return record, row, None
    except Exception as exc:
        retrieved_at, attempt_errors = _failure_details(exc)
        receipt_path = raw_root / candidate.economy_code / candidate.source_id / "failure_receipt.json"
        receipt = {
            "schema_version": "1.0",
            "source_id": candidate.source_id,
            "economy_code": candidate.economy_code,
            "source_authority": candidate.source_authority,
            "source_title": candidate.source_title,
            "requested_url": candidate.source_url,
            "retrieval_status": "ACCESS_BLOCKED",
            "retrieved_at": retrieved_at,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "attempt_errors": list(attempt_errors),
            "content_received": False,
            "sha256": "",
        }
        write_json(receipt_path, receipt)
        failure_row = {
            "economy_code": candidate.economy_code,
            "source_id": candidate.source_id,
            "source_title": candidate.source_title,
            "source_url": candidate.source_url,
            "retrieval_status": "ACCESS_BLOCKED",
            "retrieved_at": retrieved_at,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "attempt_errors": "|".join(attempt_errors),
            "failure_receipt": receipt_path.relative_to(run_root).as_posix(),
        }
        row = {
            **candidate.as_dict(),
            "retrieval_status": "ACCESS_BLOCKED",
            "acquisition_freshness": "",
            "http_status": _http_status_from_attempts(attempt_errors),
            "final_url": "",
            "content_type": "",
            "bytes": "",
            "source_hash": "",
            "retrieved_at": retrieved_at,
            "local_file": "",
            "failure_receipt": receipt_path.relative_to(run_root).as_posix(),
            "attempt_count": len(attempt_errors),
            "attempt_errors": "|".join(attempt_errors),
            "signature_status": "NOT_RUN",
            "signature_reason": "",
            "marker_status": "NOT_RUN",
            "missing_markers": "",
            "dataset_evidence_status": "NOT_ACQUIRED",
            "homepage_rejected_as_dataset": candidate.resource_type == "LANDING_PAGE",
            "runtime_candidate_class": "D_UNAVAILABLE",
            "runtime_methodological_state": "ACCESS_BLOCKED",
            "runtime_blocking_reason": f"SOURCE_ACQUISITION_FAILED:{type(exc).__name__}",
            "decision_is_provisional": True,
        }
        return None, row, failure_row


def _qualifies_as_dataset_evidence(candidate: SourceCandidate) -> bool:
    if candidate.evidence_role != "DATASET":
        return False
    if candidate.resource_type not in DATASET_RESOURCE_TYPES:
        return False
    if candidate.resource_type == "LANDING_PAGE":
        return False
    return True


def _discovery_rejection_reason(candidate: SourceCandidate) -> str:
    if candidate.resource_type == "LANDING_PAGE":
        return "LANDING_PAGE_IS_DISCOVERY_EVIDENCE_NOT_A_DATASET"
    if candidate.resource_type == "PUBLICATION_FILE":
        return "PUBLICATION_FILE_NOT_MACHINE_PARSED_BY_SOURCE_PROBE"
    if candidate.evidence_role != "DATASET":
        return "SOURCE_IS_DOCUMENTATION_OR_DISCOVERY_EVIDENCE_ONLY"
    return "SOURCE_DID_NOT_QUALIFY_AS_MACHINE_READABLE_DATASET_EVIDENCE"


def _failure_details(exc: Exception) -> tuple[str, tuple[str, ...]]:
    if isinstance(exc, AcquisitionError):
        return exc.retrieved_at, exc.attempt_errors
    return utc_now(), (f"{type(exc).__name__}:{exc}",)


def _http_status_from_attempts(attempts: tuple[str, ...]) -> str:
    for attempt in reversed(attempts):
        match = re.search(r"HTTP Error\s+(\d{3})", attempt)
        if match:
            return match.group(1)
    return ""


def _guard_exhaustive_state(state: str, exhaustive_proof: bool) -> str:
    if state == "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT" and not exhaustive_proof:
        return "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
    return state


def _source_family_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_economy: dict[str, list[dict[str, Any]]] = {}
    economy_names: dict[str, str] = {}
    for row in rows:
        code = str(row["economy_code"])
        by_economy.setdefault(code, []).append(row)
        economy_names[code] = str(row.get("economy_name", ""))
    output: list[dict[str, Any]] = []
    for code in sorted(by_economy):
        economy_rows = by_economy[code]
        for order, family in SOURCE_FAMILIES:
            candidates = [row for row in economy_rows if row.get("source_family") == family]
            statuses = {str(row.get("retrieval_status", "")) for row in candidates}
            if not candidates:
                audit_status = "NOT_INVESTIGATED"
            elif "ACQUIRED_DATASET" in statuses:
                audit_status = "DATASET_ACQUIRED"
            elif "ACQUIRED_DOCUMENTATION_EVIDENCE" in statuses:
                audit_status = "DOCUMENTATION_ONLY"
            elif "ACQUIRED_DISCOVERY_EVIDENCE" in statuses:
                audit_status = "DISCOVERY_ONLY"
            elif "CONTENT_VALIDATION_FAILED" in statuses:
                audit_status = "SOURCE_NOT_MACHINE_READABLE"
            elif statuses == {"ACCESS_BLOCKED"}:
                audit_status = "ACCESS_BLOCKED"
            else:
                audit_status = "ATTEMPTED_NO_ADMISSIBLE_DATASET"
            methodological = sorted(
                (str(row.get("methodological_candidate_class", "D_UNAVAILABLE")) for row in candidates),
                key=lambda item: CLASS_RANK.get(item, 0),
                reverse=True,
            )
            runtime = sorted(
                (str(row.get("runtime_candidate_class", "D_UNAVAILABLE")) for row in candidates),
                key=lambda item: CLASS_RANK.get(item, 0),
                reverse=True,
            )
            output.append({
                "economy_code": code,
                "economy_name": economy_names[code],
                "source_family": family,
                "family_order": order,
                "core_family": family in EXHAUSTIVE_CORE_FAMILIES,
                "configured_candidates": len(candidates),
                "real_attempts": len(candidates),
                "acquired_dataset_count": sum(1 for row in candidates if row.get("retrieval_status") == "ACQUIRED_DATASET"),
                "acquired_discovery_count": sum(1 for row in candidates if row.get("retrieval_status") == "ACQUIRED_DISCOVERY_EVIDENCE"),
                "acquired_documentation_count": sum(1 for row in candidates if row.get("retrieval_status") == "ACQUIRED_DOCUMENTATION_EVIDENCE"),
                "access_blocked_count": sum(1 for row in candidates if row.get("retrieval_status") == "ACCESS_BLOCKED"),
                "content_validation_failure_count": sum(1 for row in candidates if row.get("retrieval_status") == "CONTENT_VALIDATION_FAILED"),
                "best_methodological_candidate_class": methodological[0] if methodological else "",
                "best_runtime_candidate_class": runtime[0] if runtime else "",
                "audit_status": audit_status,
                "family_evidence_resolved": audit_status in {"DATASET_ACQUIRED", "DOCUMENTATION_ONLY", "SOURCE_NOT_MACHINE_READABLE", "ATTEMPTED_NO_ADMISSIBLE_DATASET"},
                "uninvestigated": not candidates,
                "candidate_source_ids": "|".join(sorted(str(row["source_id"]) for row in candidates)),
            })
    return output


def _economy_summary(rows: list[dict[str, Any]], family_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    families_by_economy: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["economy_code"]), []).append(row)
    for row in family_rows:
        families_by_economy.setdefault(str(row["economy_code"]), []).append(row)
    output: list[dict[str, Any]] = []
    for code, candidates in sorted(grouped.items()):
        ordered = sorted(
            candidates,
            key=lambda row: (
                CLASS_RANK.get(str(row["runtime_candidate_class"]), 0),
                CLASS_RANK.get(str(row["methodological_candidate_class"]), 0),
                1 if row["retrieval_status"] == "ACQUIRED_DATASET" else 0,
                str(row["source_id"]),
            ),
            reverse=True,
        )
        best = ordered[0]
        best_declared = sorted(
            candidates,
            key=lambda row: (CLASS_RANK.get(str(row["methodological_candidate_class"]), 0), str(row["source_id"])),
            reverse=True,
        )[0]
        family_coverage = families_by_economy.get(code, [])
        core_rows = [row for row in family_coverage if row["core_family"]]
        core_attempt_coverage_complete = bool(core_rows) and all(row["audit_status"] != "NOT_INVESTIGATED" for row in core_rows)
        core_complete = bool(core_rows) and all(bool(row["family_evidence_resolved"]) for row in core_rows)
        explicit_exhaustive = any(row.get("methodological_state") == "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT" for row in candidates)
        exhaustive_allowed = core_complete and explicit_exhaustive and all(
            row["audit_status"] not in {"ACCESS_BLOCKED", "NOT_INVESTIGATED"} for row in core_rows
        )
        audit_state = _economy_audit_state(candidates, best, exhaustive_allowed)
        output.append({
            "economy_code": code,
            "economy_name": best["economy_name"],
            "best_methodological_candidate_class": best_declared["methodological_candidate_class"],
            "best_methodological_source_id": best_declared["source_id"],
            "best_runtime_candidate_class": best["runtime_candidate_class"],
            "best_source_id": best["source_id"],
            "best_source_authority": best["source_authority"],
            "best_source_title": best["source_title"],
            "best_source_url": best["source_url"],
            "retrieval_status": best["retrieval_status"],
            "audit_state": audit_state,
            "decision_is_provisional": audit_state not in {"EXACT_OFFICIAL", "OFFICIAL_DERIVED_NO_ALLOCATION", "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT"},
            "definitive_unavailability_allowed": exhaustive_allowed,
            "core_family_attempt_coverage_complete": core_attempt_coverage_complete,
            "core_family_probe_complete": core_complete,
            "core_families_attempted": sum(1 for row in core_rows if row["audit_status"] != "NOT_INVESTIGATED"),
            "core_families_resolved": sum(1 for row in core_rows if row["family_evidence_resolved"]),
            "core_families_required": len(EXHAUSTIVE_CORE_FAMILIES),
            "uninvestigated_core_families": "|".join(sorted(row["source_family"] for row in core_rows if row["audit_status"] == "NOT_INVESTIGATED")),
            "reference_period": best["reference_period"],
            "national_accounts_or_survey": best["national_accounts_or_survey"],
            "institutional_sector": best["institutional_sector"],
            "transaction_code": best["transaction_code"],
            "classification": best["classification"],
            "category_coverage": best["category_coverage"],
            "machine_readable": best["machine_readable"],
            "confidence": best["confidence"],
            "integration_cost": best["integration_cost"],
            "blocking_reason": best["runtime_blocking_reason"],
            "acquired_dataset_count": sum(1 for item in candidates if item["retrieval_status"] == "ACQUIRED_DATASET"),
            "accessible_discovery_count": sum(1 for item in candidates if item["retrieval_status"] == "ACQUIRED_DISCOVERY_EVIDENCE"),
            "documentation_evidence_count": sum(1 for item in candidates if item["retrieval_status"] == "ACQUIRED_DOCUMENTATION_EVIDENCE"),
            "access_blocked_count": sum(1 for item in candidates if item["retrieval_status"] == "ACCESS_BLOCKED"),
            "candidate_count": len(candidates),
        })
    return output


def _economy_audit_state(candidates: list[dict[str, Any]], best: dict[str, Any], exhaustive_allowed: bool) -> str:
    if best["runtime_candidate_class"] in {"A_CANDIDATE", "B_CANDIDATE", "C_ONLY"}:
        return _guard_exhaustive_state(str(best["runtime_methodological_state"]), exhaustive_allowed)
    states = {str(row.get("runtime_methodological_state", "")) for row in candidates}
    if exhaustive_allowed:
        return "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT"
    if states == {"ACCESS_BLOCKED"}:
        return "ACCESS_BLOCKED"
    if "SOURCE_NOT_MACHINE_READABLE" in states:
        return "SOURCE_NOT_MACHINE_READABLE"
    return "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"


def _extension_for(url: str, content_types: tuple[str, ...]) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".html", ".htm", ".csv", ".json", ".xlsx", ".xls", ".pdf", ".zip", ".ods"}:
        return suffix
    joined = " ".join(content_types)
    if "spreadsheetml" in joined:
        return ".xlsx"
    if "ms-excel" in joined:
        return ".xls"
    if "pdf" in joined:
        return ".pdf"
    if "json" in joined:
        return ".json"
    if "csv" in joined:
        return ".csv"
    return ".html"


def _accept_header(content_types: tuple[str, ...]) -> str:
    if not content_types:
        return "*/*"
    return ",".join(content_types) + ",*/*;q=0.1"


def _validate_signature(path: Path, content_type: str | None, expected: tuple[str, ...]) -> tuple[str, str]:
    if path.stat().st_size == 0:
        return "FAIL", "EMPTY_RESPONSE"
    data = path.read_bytes()[:512]
    suffix = path.suffix.lower()
    actual = (content_type or "").lower()
    if expected and actual and not any(item in actual for item in expected):
        if "octet-stream" not in actual and "binary" not in actual:
            return "FAIL", f"UNEXPECTED_CONTENT_TYPE:{actual}"
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        return "FAIL", "INVALID_PDF_SIGNATURE"
    if suffix == ".xls" and not data.startswith(bytes.fromhex("D0CF11E0")):
        return "FAIL", "INVALID_XLS_SIGNATURE"
    if suffix in {".xlsx", ".zip", ".ods"}:
        if not data.startswith(b"PK") or not zipfile.is_zipfile(path):
            return "FAIL", "INVALID_ZIP_CONTAINER_SIGNATURE"
        if suffix == ".xlsx":
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
            if "xl/workbook.xml" not in names or not any(name.startswith("xl/worksheets/") for name in names):
                return "FAIL", "INVALID_XLSX_STRUCTURE"
    if suffix in {".html", ".htm"} and b"<" not in data:
        return "FAIL", "INVALID_HTML_SIGNATURE"
    if suffix == ".json":
        stripped = data.lstrip()
        if not stripped.startswith((b"{", b"[")):
            return "FAIL", "INVALID_JSON_SIGNATURE"
    return "PASS", ""


def _validate_markers(path: Path, markers: tuple[str, ...]) -> tuple[str, list[str]]:
    if not markers:
        return "NOT_APPLICABLE", []
    text = _searchable_text(path)
    if not text:
        return "NOT_APPLICABLE", []
    normalized = normalize_text(text)
    missing = [marker for marker in markers if marker not in normalized]
    return ("PASS", []) if not missing else ("FAIL", missing)


def _searchable_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm", ".csv", ".json", ".txt"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<[^>]+>", " ", raw)
        return html.unescape(raw)
    if suffix in {".xlsx", ".ods"} and zipfile.is_zipfile(path):
        chunks: list[str] = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith(".xml") and ("sharedstrings" in lower or "/worksheets/" in lower or "content.xml" in lower):
                    chunks.append(archive.read(name).decode("utf-8", errors="replace"))
        return re.sub(r"<[^>]+>", " ", " ".join(chunks))
    return ""


def run_source_probe_only(
    config: Step2Config,
    *,
    run_root: Path,
    cache_root: Path,
    economy_codes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run only the Step 2H0 source feasibility probes."""
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    result = run_source_probes(
        config, candidates_path=config.source_probe_candidates_path,
        run_root=run_root, cache_root=cache_root, economy_codes=economy_codes,
    )
    out = run_root / "outputs"
    candidate_fields = sorted({key for row in result.candidate_rows for key in row}) if result.candidate_rows else ["source_id"]
    economy_fields = sorted({key for row in result.economy_rows for key in row}) if result.economy_rows else ["economy_code"]
    family_fields = sorted({key for row in result.family_rows for key in row}) if result.family_rows else ["economy_code", "source_family"]
    failure_fields = sorted({key for row in result.failure_rows for key in row}) if result.failure_rows else ["economy_code", "source_id", "source_url", "retrieval_status", "retrieved_at", "error_type", "error", "attempt_errors", "failure_receipt"]
    write_csv(out / "source_probe_candidate_results.csv", candidate_fields, result.candidate_rows)
    write_csv(out / "source_probe_economy_summary.csv", economy_fields, result.economy_rows)
    write_csv(out / "source_probe_family_coverage.csv", family_fields, result.family_rows)
    write_csv(out / "source_probe_failures.csv", failure_fields, result.failure_rows)
    write_json(out / "source_probe_summary.json", result.summary)
    write_json(run_root / "manifest.json", {
        "schema_version": "2.0",
        "pipeline_version": config.pipeline_version,
        "programme": "armilar-source-probe",
        "source_files": [record.as_dict(run_root) for record in result.acquisition_records],
        "failure_receipts": [row["failure_receipt"] for row in result.failure_rows],
        "summary": result.summary,
    })
    write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
    return result.summary
