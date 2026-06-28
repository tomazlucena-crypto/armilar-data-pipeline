from __future__ import annotations

import csv
import html
import re
import shutil
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .acquire import AcquisitionRecord, fetch_url
from .config import Step2Config
from .util import normalize_text, write_csv, write_json, write_sha256sums


CLASS_RANK = {
    "A_CANDIDATE": 4,
    "B_CANDIDATE": 3,
    "C_ONLY": 2,
    "D_UNAVAILABLE": 1,
}


@dataclass(frozen=True)
class SourceCandidate:
    economy_code: str
    economy_name: str
    source_id: str
    source_authority: str
    source_url: str
    access_method: str
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
        result.append(SourceCandidate(
            economy_code=(row.get("economy_code") or "").strip().upper(),
            economy_name=(row.get("economy_name") or "").strip(),
            source_id=source_id,
            source_authority=(row.get("source_authority") or "").strip(),
            source_url=(row.get("source_url") or "").strip(),
            access_method=(row.get("access_method") or "").strip(),
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
            confidence=(row.get("confidence") or "").strip(),
            integration_cost=(row.get("integration_cost") or "").strip(),
            blocking_reason=(row.get("blocking_reason") or "").strip(),
            expected_content_types=tuple(item.strip().lower() for item in (row.get("expected_content_types") or "").split("|") if item.strip()),
            required_markers=tuple(normalize_text(item) for item in (row.get("required_markers") or "").split("|") if item.strip()),
            notes=(row.get("notes") or "").strip(),
        ))
    return result


def run_source_probes(
    config: Step2Config,
    *,
    candidates_path: Path,
    run_root: Path,
    cache_root: Path,
) -> SourceProbeResult:
    candidates = load_source_candidates(candidates_path)
    acquisition_records: list[AcquisitionRecord] = []
    candidate_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    raw_root = run_root / "raw" / "source_probe"

    for candidate in candidates:
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
            acquisition_records.append(record)
            signature_status, signature_reason = _validate_signature(destination, record.content_type, candidate.expected_content_types)
            marker_status, missing_markers = _validate_markers(destination, candidate.required_markers)
            accessible = signature_status == "PASS" and marker_status in {"PASS", "NOT_APPLICABLE"}
            runtime_class = candidate.methodological_candidate_class if accessible else "D_UNAVAILABLE"
            candidate_rows.append({
                **candidate.as_dict(),
                "retrieval_status": "ACCESSIBLE" if accessible else "CONTENT_VALIDATION_FAILED",
                "acquisition_freshness": record.status,
                "http_status": record.status_code if record.status_code is not None else "",
                "final_url": record.final_url,
                "content_type": record.content_type or "",
                "bytes": record.bytes,
                "source_hash": record.sha256,
                "retrieved_at": record.retrieved_at,
                "local_file": destination.relative_to(run_root).as_posix(),
                "signature_status": signature_status,
                "signature_reason": signature_reason,
                "marker_status": marker_status,
                "missing_markers": "|".join(missing_markers),
                "runtime_candidate_class": runtime_class,
                "runtime_blocking_reason": candidate.blocking_reason if accessible else f"SOURCE_CONTENT_NOT_VALIDATED:{signature_reason or '|'.join(missing_markers)}",
            })
        except Exception as exc:
            failure_rows.append({
                "economy_code": candidate.economy_code,
                "source_id": candidate.source_id,
                "source_url": candidate.source_url,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            candidate_rows.append({
                **candidate.as_dict(),
                "retrieval_status": "FAILED",
                "acquisition_freshness": "",
                "http_status": "",
                "final_url": "",
                "content_type": "",
                "bytes": "",
                "source_hash": "",
                "retrieved_at": "",
                "local_file": "",
                "signature_status": "NOT_RUN",
                "signature_reason": "",
                "marker_status": "NOT_RUN",
                "missing_markers": "",
                "runtime_candidate_class": "D_UNAVAILABLE",
                "runtime_blocking_reason": f"SOURCE_ACQUISITION_FAILED:{type(exc).__name__}",
            })

    economy_rows = _economy_summary(candidate_rows)
    counts: dict[str, int] = {key: 0 for key in CLASS_RANK}
    for row in economy_rows:
        counts[str(row["best_runtime_candidate_class"])] += 1
    summary = {
        "economies_probed": len(economy_rows),
        "source_candidates_probed": len(candidate_rows),
        "source_candidates_accessible": sum(1 for row in candidate_rows if row["retrieval_status"] == "ACCESSIBLE"),
        "source_candidates_failed": len(failure_rows),
        "economy_class_counts": counts,
        "a_or_b_candidate_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] in {"A_CANDIDATE", "B_CANDIDATE"}),
        "c_only_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] == "C_ONLY"),
        "d_unavailable_economies": sum(1 for row in economy_rows if row["best_runtime_candidate_class"] == "D_UNAVAILABLE"),
    }
    return SourceProbeResult(acquisition_records, candidate_rows, economy_rows, failure_rows, summary)


def _economy_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["economy_code"]), []).append(row)
    output: list[dict[str, Any]] = []
    for code, candidates in sorted(grouped.items()):
        ordered = sorted(
            candidates,
            key=lambda row: (
                CLASS_RANK.get(str(row["runtime_candidate_class"]), 0),
                1 if row["retrieval_status"] == "ACCESSIBLE" else 0,
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
        output.append({
            "economy_code": code,
            "economy_name": best["economy_name"],
            "best_methodological_candidate_class": best_declared["methodological_candidate_class"],
            "best_methodological_source_id": best_declared["source_id"],
            "best_runtime_candidate_class": best["runtime_candidate_class"],
            "best_source_id": best["source_id"],
            "best_source_authority": best["source_authority"],
            "best_source_url": best["source_url"],
            "retrieval_status": best["retrieval_status"],
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
            "accessible_candidate_count": sum(1 for item in candidates if item["retrieval_status"] == "ACCESSIBLE"),
            "candidate_count": len(candidates),
        })
    return output


def _extension_for(url: str, content_types: tuple[str, ...]) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".html", ".htm", ".csv", ".json", ".xlsx", ".xls", ".pdf", ".zip", ".ods"}:
        return suffix
    joined = " ".join(content_types)
    if "spreadsheetml" in joined:
        return ".xlsx"
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
    data = path.read_bytes()[:512]
    suffix = path.suffix.lower()
    actual = (content_type or "").lower()
    if expected and actual and not any(item in actual for item in expected):
        # Official sites sometimes label XLSX/PDF as octet-stream. Permit a valid file signature.
        if "octet-stream" not in actual:
            return "FAIL", f"UNEXPECTED_CONTENT_TYPE:{actual}"
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        return "FAIL", "INVALID_PDF_SIGNATURE"
    if suffix in {".xlsx", ".zip", ".ods"} and not data.startswith(b"PK"):
        return "FAIL", "INVALID_ZIP_CONTAINER_SIGNATURE"
    if suffix in {".html", ".htm"} and b"<" not in data:
        return "FAIL", "INVALID_HTML_SIGNATURE"
    if path.stat().st_size == 0:
        return "FAIL", "EMPTY_RESPONSE"
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
) -> dict[str, Any]:
    """Run only the Step 2H0 source feasibility probes.

    This command is deliberately independent from the ICP matrix builder so a
    blocked national source cannot delay or invalidate the global acquisition.
    """
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    result = run_source_probes(
        config, candidates_path=config.source_probe_candidates_path,
        run_root=run_root, cache_root=cache_root,
    )
    out = run_root / "outputs"
    candidate_fields = sorted({key for row in result.candidate_rows for key in row}) if result.candidate_rows else ["source_id"]
    economy_fields = sorted({key for row in result.economy_rows for key in row}) if result.economy_rows else ["economy_code"]
    write_csv(out / "source_probe_candidate_results.csv", candidate_fields, result.candidate_rows)
    write_csv(out / "source_probe_economy_summary.csv", economy_fields, result.economy_rows)
    write_csv(out / "source_probe_failures.csv", ["economy_code", "source_id", "source_url", "error_type", "error"], result.failure_rows)
    write_json(out / "source_probe_summary.json", result.summary)
    write_json(run_root / "manifest.json", {
        "schema_version": "1.0",
        "pipeline_version": config.pipeline_version,
        "programme": "armilar-source-probe",
        "source_files": [record.as_dict(run_root) for record in result.acquisition_records],
        "summary": result.summary,
    })
    write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
    return result.summary
