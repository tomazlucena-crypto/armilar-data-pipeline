from __future__ import annotations

import html
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Protocol

from .acquire import AcquisitionRecord, fetch_url
from .config import Step2Config
from .util import write_csv, write_json, write_sha256sums


NORMALIZED_FIELDS = [
    "economy_code", "economy_name", "reference_period", "armilar_category",
    "original_item_code", "original_item_name", "value", "currency", "unit",
    "sector", "transaction", "classification", "source_authority",
    "source_file", "source_url", "retrieved_at", "source_hash",
    "derivation_method", "data_class", "quality_flags",
]

STATUS_FIELDS = [
    "economy_code", "economy_name", "adapter_id", "status", "data_class",
    "accepted_rows", "failure_count", "source_url", "blocking_reason",
]

EVIDENCE_FIELDS = [
    "economy_code", "source_id", "source_authority", "source_url",
    "reference_period", "concept", "granularity", "machine_readable",
    "status", "rejection_reason",
]

MAPPING_FIELDS = [
    "economy_code", "original_item_code", "original_item_name",
    "armilar_category", "mapping_type", "status", "reason",
]

RECONCILIATION_FIELDS = [
    "economy_code", "reference_period", "source_total", "accepted_total",
    "excluded_total", "reconstructed_total", "difference", "status",
]

FAILURE_FIELDS = ["economy_code", "adapter_id", "stage", "error_type", "error"]

STEP2I_ECONOMIES = ("CHN", "IND", "RUT", "IDN", "BRA")
STEP2I_PROXY_CATEGORIES = ("CP04", "CP06", "CP09", "CP10", "CP12")

CELL_STATUS_FIELDS = [
    "economy_code", "economy_name", "armilar_category", "cell_class",
    "source_id", "source_authority", "reference_period", "value_status",
    "admissible_to_exact_matrix", "blocking_reason", "quality_flags",
]

SOURCE_ATTEMPT_FIELDS = [
    "economy_code", "category", "source_family", "authority", "dataset", "url",
    "access_method", "retrieval_status", "status_code", "content_type",
    "file_signature", "byte_size", "reference_period", "institutional_sector",
    "transaction_code", "classification", "current_prices", "currency", "unit",
    "npish_treatment", "government_treatment", "imputed_rent_treatment",
    "candidate_class", "rejection_reason", "retrieved_at", "sha256",
]

SOURCE_FAMILY_FIELDS = [
    "economy_code", "economy_name", "source_family", "family_order",
    "attempts_recorded", "best_status", "best_dataset", "best_url",
    "remaining_gap", "can_support_exact_matrix",
]

METHODOLOGICAL_STATES = (
    "EXACT_OFFICIAL",
    "OFFICIAL_DERIVED_NO_ALLOCATION",
    "OFFICIAL_EXPERIMENTAL_ALLOCATION",
    "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
    "ACCESS_BLOCKED",
    "SOURCE_NOT_MACHINE_READABLE",
    "CONCEPT_AMBIGUOUS",
    "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT",
)

FINAL_AUDIT_REQUIRED_STATES = {"UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT"}

SOURCE_FAMILIES = (
    (1, "official_national_accounts_api"),
    (2, "official_csv_xls_xlsx"),
    (3, "official_statistical_database"),
    (4, "official_supply_and_use_tables"),
    (5, "official_input_output_tables"),
    (6, "official_structured_publications"),
    (7, "survey_or_cpi_class_c_only"),
    (8, "official_classifications_methodology"),
    (9, "exhaustive_unavailability_documentation"),
)

COMPLETION_ECONOMY_FIELDS = [
    "economy_code", "economy_name", "accepted_categories",
    "experimental_categories", "unavailable_categories", "coverage_added_cells",
    "decision", "sources_examined", "remaining_blockers",
]

INDIA_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "evidence_location", "source_retrieved_at", "source_sha256",
    "review_mode",
]

INDIA_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

RUSSIA_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]

RUSSIA_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

CHINA_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]

CHINA_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

INDONESIA_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
INDONESIA_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

BRAZIL_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
BRAZIL_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

EGYPT_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
EGYPT_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

PAKISTAN_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
PAKISTAN_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

NIGERIA_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
NIGERIA_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

BANGLADESH_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
BANGLADESH_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

VIETNAM_GATE_FIELDS = [
    "criterion", "status", "evidence", "source_id", "source_authority",
    "source_url", "source_retrieved_at", "source_sha256", "review_mode",
]
VIETNAM_GATE_STATUSES = {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}

STEP2H_EXCEPTION_FIELDS = [
    "economy_code", "economy_name", "armilar_category", "decision",
    "current_status", "resolution_attempted", "reason",
]

STEP2I_EXTRA_ATTEMPTS = {
    "CHN": [
        ("National Bureau of Statistics of China", "NBS_DATA_PORTAL", "https://data.stats.gov.cn/english/easyquery.htm?cn=C01", "2021", "national data portal", "SOURCE_FAMILY_SEARCH", "No exact S14/P31DC twelve-category household-purpose table was identified in adapter inputs."),
        ("National Bureau of Statistics of China", "CHINA_STATISTICAL_YEARBOOK_2022", "https://www.stats.gov.cn/sj/ndsj/2022/indexeh.htm", "2021", "statistical yearbook", "SOURCE_FAMILY_SEARCH", "Yearbook family does not provide an accepted exact twelve-category national-accounts HFCE table in adapter inputs."),
    ],
    "IDN": [
        ("Badan Pusat Statistik", "BPS_STATISTICS_TABLES_EXPENDITURE", "https://www.bps.go.id/en/statistics-table?subject=531", "2021", "official statistics tables", "SOURCE_FAMILY_SEARCH", "No alternative exact twelve-category household-purpose table was integrated."),
        ("Badan Pusat Statistik", "BPS_SUPPLY_USE_OR_NATIONAL_ACCOUNTS_SEARCH", "https://www.bps.go.id/en", "2021", "national accounts and supply-use source family", "SOURCE_FAMILY_SEARCH", "No exact COICOP-HH bridge without allocation was found in adapter inputs."),
    ],
    "BRA": [
        ("Instituto Brasileiro de Geografia e Estatistica", "IBGE_SIDRA_NATIONAL_ACCOUNTS", "https://sidra.ibge.gov.br/pesquisa/cnt/tabelas", "2021", "SIDRA national accounts tables", "SOURCE_FAMILY_SEARCH", "No accepted exact household-purpose COICOP table was integrated."),
        ("Instituto Brasileiro de Geografia e Estatistica", "IBGE_CONTAS_NACIONAIS_SOURCE_FAMILY", "https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais.html", "2021", "national accounts source family", "SOURCE_FAMILY_SEARCH", "Product/resource-use sources require many-to-many product-to-COICOP allocation and remain unavailable for exact weights."),
    ],
}


@dataclass(frozen=True)
class AdapterResult:
    status_rows: list[dict[str, Any]]
    evidence_rows: list[dict[str, Any]]
    normalized_rows: list[dict[str, Any]]
    mapping_rows: list[dict[str, Any]]
    reconciliation_rows: list[dict[str, Any]]
    failure_rows: list[dict[str, Any]]
    acquisition_records: list[AcquisitionRecord]
    cell_status_rows: list[dict[str, Any]] | None = None
    source_attempt_rows: list[dict[str, Any]] | None = None
    source_family_rows: list[dict[str, Any]] | None = None
    completion_rows: list[dict[str, Any]] | None = None
    india_gate_rows: list[dict[str, Any]] | None = None
    russia_gate_rows: list[dict[str, Any]] | None = None
    china_gate_rows: list[dict[str, Any]] | None = None
    indonesia_gate_rows: list[dict[str, Any]] | None = None
    brazil_gate_rows: list[dict[str, Any]] | None = None
    egypt_gate_rows: list[dict[str, Any]] | None = None
    pakistan_gate_rows: list[dict[str, Any]] | None = None
    nigeria_gate_rows: list[dict[str, Any]] | None = None
    bangladesh_gate_rows: list[dict[str, Any]] | None = None
    vietnam_gate_rows: list[dict[str, Any]] | None = None
    step2h_exception_rows: list[dict[str, Any]] | None = None


class CountryAdapter(Protocol):
    economy_code: str
    economy_name: str
    adapter_id: str

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        ...


def registered_adapters() -> dict[str, CountryAdapter]:
    adapters: list[CountryAdapter] = [
        IndiaMospiAdapter(),
        RussiaRosstatAuditAdapter(),
        ChinaNbsAuditAdapter(),
        IndonesiaBpsAuditAdapter(),
        BrazilIbgeAuditAdapter(),
        EgyptCapmasAuditAdapter(),
        PakistanPbsAuditAdapter(),
        NigeriaNbsAuditAdapter(),
        BangladeshBbsAuditAdapter(),
        VietnamNsoAuditAdapter(),
        BelarusBelstatExceptionAuditAdapter(),
        KuwaitCsbExceptionAuditAdapter(),
        SaudiGastatExceptionAuditAdapter(),
        BonaireCbsExceptionAuditAdapter(),
        LiberiaLisgisExceptionAuditAdapter(),
    ]
    return {adapter.economy_code: adapter for adapter in adapters}


def run_country_adapters(
    config: Step2Config,
    *,
    run_root: Path,
    cache_root: Path,
    economy_codes: Iterable[str] | None = None,
) -> AdapterResult:
    registry = registered_adapters()
    selected = [code.upper() for code in (economy_codes or registry.keys())]
    combined = _empty_result()
    for code in selected:
        adapter = registry.get(code)
        if adapter is None:
            combined.failure_rows.append({
                "economy_code": code, "adapter_id": "", "stage": "registry",
                "error_type": "KeyError", "error": f"No adapter registered for {code}",
            })
            continue
        try:
            result = adapter.acquire_and_parse(config, run_root, cache_root)
        except Exception as exc:
            result = AdapterResult(
                status_rows=[{
                    "economy_code": adapter.economy_code, "economy_name": adapter.economy_name,
                    "adapter_id": adapter.adapter_id, "status": "FAILED", "data_class": "UNAVAILABLE",
                    "accepted_rows": 0, "failure_count": 1, "source_url": "",
                    "blocking_reason": str(exc),
                }],
                evidence_rows=[], normalized_rows=[], mapping_rows=[], reconciliation_rows=[],
                failure_rows=[{
                    "economy_code": adapter.economy_code, "adapter_id": adapter.adapter_id,
                    "stage": "adapter", "error_type": type(exc).__name__, "error": str(exc),
                }],
                acquisition_records=[],
            )
        _extend(combined, result)
    return combined


def run_country_adapters_only(
    config: Step2Config,
    *,
    run_root: Path,
    cache_root: Path,
    economy_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    result = run_country_adapters(config, run_root=run_root, cache_root=cache_root, economy_codes=economy_codes)
    write_country_outputs(run_root / "outputs", result)
    write_json(run_root / "manifest.json", {
        "schema_version": "1.0",
        "programme": "armilar-country",
        "pipeline_version": config.pipeline_version,
        "source_files": [record.as_dict(run_root) for record in result.acquisition_records],
    })
    write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
    return {
        "adapters_run": len(result.status_rows),
        "accepted_rows": len(result.normalized_rows),
        "failures": len(result.failure_rows),
    }


def write_country_outputs(out: Path, result: AdapterResult) -> None:
    write_csv(out / "country_adapter_status.csv", STATUS_FIELDS, result.status_rows)
    write_csv(out / "country_source_evidence.csv", EVIDENCE_FIELDS, result.evidence_rows)
    write_csv(out / "country_normalized_rows.csv", NORMALIZED_FIELDS, result.normalized_rows)
    write_csv(out / "country_mapping_audit.csv", MAPPING_FIELDS, result.mapping_rows)
    write_csv(out / "country_reconciliation_audit.csv", RECONCILIATION_FIELDS, result.reconciliation_rows)
    write_csv(out / "country_adapter_failures.csv", FAILURE_FIELDS, result.failure_rows)
    write_csv(out / "country_cell_status.csv", CELL_STATUS_FIELDS, result.cell_status_rows or [])
    write_csv(out / "country_source_attempts.csv", SOURCE_ATTEMPT_FIELDS, result.source_attempt_rows or [])
    write_csv(out / "country_source_family_coverage.csv", SOURCE_FAMILY_FIELDS, result.source_family_rows or [])
    write_csv(out / "step2i_economy_summary.csv", COMPLETION_ECONOMY_FIELDS, result.completion_rows or [])
    write_csv(out / "india_methodology_gate_audit.csv", INDIA_GATE_FIELDS, result.india_gate_rows or [])
    write_csv(out / "russia_methodology_gate_audit.csv", RUSSIA_GATE_FIELDS, result.russia_gate_rows or [])
    write_csv(out / "china_methodology_gate_audit.csv", CHINA_GATE_FIELDS, result.china_gate_rows or [])
    write_csv(out / "indonesia_methodology_gate_audit.csv", INDONESIA_GATE_FIELDS, result.indonesia_gate_rows or [])
    write_csv(out / "brazil_methodology_gate_audit.csv", BRAZIL_GATE_FIELDS, result.brazil_gate_rows or [])
    write_csv(out / "egypt_methodology_gate_audit.csv", EGYPT_GATE_FIELDS, result.egypt_gate_rows or [])
    write_csv(out / "pakistan_methodology_gate_audit.csv", PAKISTAN_GATE_FIELDS, result.pakistan_gate_rows or [])
    write_csv(out / "nigeria_methodology_gate_audit.csv", NIGERIA_GATE_FIELDS, result.nigeria_gate_rows or [])
    write_csv(out / "bangladesh_methodology_gate_audit.csv", BANGLADESH_GATE_FIELDS, result.bangladesh_gate_rows or [])
    write_csv(out / "vietnam_methodology_gate_audit.csv", VIETNAM_GATE_FIELDS, result.vietnam_gate_rows or [])
    write_csv(out / "step2h_exception_audit.csv", STEP2H_EXCEPTION_FIELDS, result.step2h_exception_rows or step2h_exception_rows())
    write_json(out / "step2i_completion_summary.json", step2i_completion_summary(result))
    write_json(out / "step2i_audit_summary.json", step2i_audit_summary(result))
    write_step2i_report(out / "STEP_2I_COMPLETION_REPORT.md", result)
    write_step2i_audit_report(out / "STEP_2I_AUDIT_REPORT.md", result)
    write_india_method_gate_report(out / "INDIA_METHOD_GATE_REPORT.md", result.india_gate_rows or [])
    write_russia_method_gate_report(out / "RUSSIA_METHOD_GATE_REPORT.md", result.russia_gate_rows or [])
    write_china_method_gate_report(out / "CHINA_METHOD_GATE_REPORT.md", result.china_gate_rows or [])
    write_country_method_gate_report(out / "INDONESIA_METHOD_GATE_REPORT.md", "Indonesia", "0.6.13", result.indonesia_gate_rows or [], validate_indonesia_methodology_gate_rows)
    write_country_method_gate_report(out / "BRAZIL_METHOD_GATE_REPORT.md", "Brazil", "0.6.13", result.brazil_gate_rows or [], validate_brazil_methodology_gate_rows)
    write_country_method_gate_report(out / "EGYPT_METHOD_GATE_REPORT.md", "Egypt", "0.6.13", result.egypt_gate_rows or [], validate_egypt_methodology_gate_rows)
    write_country_method_gate_report(out / "PAKISTAN_METHOD_GATE_REPORT.md", "Pakistan", "0.6.13", result.pakistan_gate_rows or [], validate_pakistan_methodology_gate_rows)
    write_country_method_gate_report(out / "NIGERIA_METHOD_GATE_REPORT.md", "Nigeria", "0.6.13", result.nigeria_gate_rows or [], validate_nigeria_methodology_gate_rows)
    write_country_method_gate_report(out / "BANGLADESH_METHOD_GATE_REPORT.md", "Bangladesh", "0.6.13", result.bangladesh_gate_rows or [], validate_bangladesh_methodology_gate_rows)
    write_country_method_gate_report(out / "VIETNAM_METHOD_GATE_REPORT.md", "Viet Nam", "0.6.13", result.vietnam_gate_rows or [], validate_vietnam_methodology_gate_rows)


class IndiaMospiAdapter:
    economy_code = "IND"
    economy_name = "India"
    adapter_id = "IND_MOSPI_NAS2024_STATEMENT_5_1"
    source_authority = "Ministry of Statistics and Programme Implementation"
    source_url = "https://www.mospi.gov.in/sites/default/files/reports_and_publication/statistical_publication/National_Accounts/NAS2024/5.1.xlsx"
    methodology_source_id = "IND_MOSPI_PFCE_CHAPTER_22"
    methodology_url = "https://mospi.gov.in/sites/default/files/reports_and_publication/statistical_manual/Chapter%2022.pdf"
    methodology_location = "Chapter 22, paragraphs 22.1-22.3"
    reviewed_methodology_sha256 = "8439d936cea6a451ed0f60c964feaf3c3635ec62c398cc952f1e0ec148f6da62"
    reference_period = "2021-22"

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        raw_root = run_root / "raw" / "country_adapters" / self.economy_code
        workbook_path = raw_root / self.adapter_id / "5.1.xlsx"
        methodology_path = raw_root / self.methodology_source_id / "chapter22_pfce.pdf"
        try:
            workbook_record = fetch_url(
                config,
                source_id=self.adapter_id,
                url=self.source_url,
                destination=workbook_path,
                cache_path=cache_root / "country_adapters" / self.economy_code / "5.1.xlsx",
                accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.1",
            )
        except Exception as exc:
            blocking = f"Official MoSPI workbook acquisition failed in this run: {type(exc).__name__}: {exc}"
            attempts = india_access_blocked_attempt_rows(
                blocking, source_id=self.adapter_id, source_url=self.source_url,
                dataset="IND_MOSPI_NAS2024_STATEMENT_5_1",
            )
            return AdapterResult(
                status_rows=[{
                    "economy_code": self.economy_code, "economy_name": self.economy_name,
                    "adapter_id": self.adapter_id, "status": "ACCESS_BLOCKED",
                    "data_class": "ACCESS_BLOCKED", "accepted_rows": 0,
                    "failure_count": 1, "source_url": self.source_url, "blocking_reason": blocking,
                }],
                evidence_rows=[{
                    "economy_code": self.economy_code, "source_id": self.adapter_id,
                    "source_authority": self.source_authority, "source_url": self.source_url,
                    "reference_period": self.reference_period, "concept": "PFCE classified by item",
                    "granularity": "12 Armilar groups plus narcotics split", "machine_readable": "unknown_this_run",
                    "status": "ACCESS_BLOCKED", "rejection_reason": blocking,
                }],
                normalized_rows=[], mapping_rows=[], reconciliation_rows=[],
                failure_rows=[{
                    "economy_code": self.economy_code, "adapter_id": self.adapter_id,
                    "stage": "workbook_acquisition", "error_type": type(exc).__name__, "error": str(exc),
                }],
                acquisition_records=[],
                cell_status_rows=step2i_cell_rows(
                    self.economy_code, self.economy_name, self.adapter_id, self.source_authority,
                    self.reference_period, "ACCESS_BLOCKED", blocking,
                ),
                source_attempt_rows=attempts,
                source_family_rows=source_family_rows(self.economy_code, self.economy_name, attempts, blocking),
                completion_rows=[completion_row(self.economy_code, self.economy_name, blocking, 1, "ACCESS_BLOCKED")],
                india_gate_rows=india_methodology_gate_rows(),
            )

        try:
            methodology_record = fetch_url(
                config,
                source_id=self.methodology_source_id,
                url=self.methodology_url,
                destination=methodology_path,
                cache_path=cache_root / "country_adapters" / self.economy_code / "chapter22_pfce.pdf",
                accept="application/pdf,*/*;q=0.1",
            )
        except Exception as exc:
            blocking = f"Official MoSPI methodology acquisition failed in this run: {type(exc).__name__}: {exc}"
            attempts = india_source_attempt_rows(workbook_record, None, blocking)
            return AdapterResult(
                status_rows=[{
                    "economy_code": self.economy_code, "economy_name": self.economy_name,
                    "adapter_id": self.adapter_id, "status": "ACCESS_BLOCKED",
                    "data_class": "ACCESS_BLOCKED", "accepted_rows": 0,
                    "failure_count": 1, "source_url": self.source_url, "blocking_reason": blocking,
                }],
                evidence_rows=[{
                    "economy_code": self.economy_code, "source_id": self.adapter_id,
                    "source_authority": self.source_authority, "source_url": self.source_url,
                    "reference_period": self.reference_period, "concept": "PFCE classified by item",
                    "granularity": "12 Armilar groups plus narcotics split", "machine_readable": "true",
                    "status": "DOCUMENTATION_ACCESS_BLOCKED", "rejection_reason": blocking,
                }],
                normalized_rows=[], mapping_rows=[], reconciliation_rows=[],
                failure_rows=[{
                    "economy_code": self.economy_code, "adapter_id": self.adapter_id,
                    "stage": "methodology_acquisition", "error_type": type(exc).__name__, "error": str(exc),
                }],
                acquisition_records=[workbook_record],
                cell_status_rows=step2i_cell_rows(
                    self.economy_code, self.economy_name, self.adapter_id, self.source_authority,
                    self.reference_period, "ACCESS_BLOCKED", blocking,
                ),
                source_attempt_rows=attempts,
                source_family_rows=source_family_rows(self.economy_code, self.economy_name, attempts, blocking),
                completion_rows=[completion_row(self.economy_code, self.economy_name, blocking, 2, "ACCESS_BLOCKED")],
                india_gate_rows=india_methodology_gate_rows(workbook_record=workbook_record),
            )

        if methodology_record.sha256 != self.reviewed_methodology_sha256:
            blocking = (
                "The acquired MoSPI methodology file has not been reviewed for this exact SHA-256. "
                "Its conceptual conclusions cannot be reused silently; manual review is required."
            )
            attempts = india_source_attempt_rows(
                workbook_record, methodology_record, blocking, methodology_reviewed=False,
            )
            gate_rows = india_methodology_gate_rows(
                workbook_record=workbook_record, methodology_record=methodology_record,
                methodology_reviewed=False,
            )
            return AdapterResult(
                status_rows=[{
                    "economy_code": self.economy_code, "economy_name": self.economy_name,
                    "adapter_id": self.adapter_id, "status": "METHODOLOGY_REVIEW_REQUIRED",
                    "data_class": "CONCEPT_AMBIGUOUS", "accepted_rows": 0,
                    "failure_count": 0, "source_url": self.methodology_url,
                    "blocking_reason": blocking,
                }],
                evidence_rows=[{
                    "economy_code": self.economy_code, "source_id": self.methodology_source_id,
                    "source_authority": self.source_authority, "source_url": self.methodology_url,
                    "reference_period": "METHODOLOGY", "concept": "PFCE institutional-sector boundary",
                    "granularity": self.methodology_location, "machine_readable": "documentary_evidence",
                    "status": "ACQUIRED_REVIEW_REQUIRED", "rejection_reason": blocking,
                }],
                normalized_rows=[], mapping_rows=[], reconciliation_rows=[], failure_rows=[],
                acquisition_records=[workbook_record, methodology_record],
                cell_status_rows=step2i_cell_rows(
                    self.economy_code, self.economy_name, self.adapter_id, self.source_authority,
                    self.reference_period, "CONCEPT_AMBIGUOUS", blocking,
                ),
                source_attempt_rows=attempts,
                source_family_rows=source_family_rows(self.economy_code, self.economy_name, attempts, blocking),
                completion_rows=[completion_row(
                    self.economy_code, self.economy_name, blocking, 2, "CONCEPT_AMBIGUOUS",
                )],
                india_gate_rows=gate_rows,
            )

        parsed = parse_india_statement_5_1(workbook_path)
        _candidate_rows, mapping = build_india_rows(parsed, workbook_record, run_root)
        reconciliation = reconcile_india(parsed)
        gate_rows = india_methodology_gate_rows(
            workbook_record=workbook_record, methodology_record=methodology_record,
        )
        validate_india_methodology_gate_rows(gate_rows)
        blocking = (
            "MoSPI Statement 5.1 is machine-readable and supports exact category aggregation plus "
            "an explicit narcotics exclusion. MoSPI methodology defines PFCE as expenditure of "
            "households and NPISH combined and states that the two are not separately available. "
            "The table reports fiscal year 2021-22 rather than calendar year 2021. It is therefore "
            "not admissible to the strict S14/P31DC Armilar 2021 exact matrix."
        )
        attempts = india_source_attempt_rows(workbook_record, methodology_record, blocking)
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code, "economy_name": self.economy_name,
                "adapter_id": self.adapter_id, "status": "REJECTED_BY_CONFIRMED_METHOD_GATE",
                "data_class": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
                "accepted_rows": 0, "failure_count": 0, "source_url": self.source_url,
                "blocking_reason": blocking,
            }],
            evidence_rows=[
                {
                    "economy_code": self.economy_code, "source_id": self.adapter_id,
                    "source_authority": self.source_authority, "source_url": self.source_url,
                    "reference_period": self.reference_period, "concept": "PFCE classified by item",
                    "granularity": "12 Armilar groups plus narcotics split", "machine_readable": "true",
                    "status": "ACQUIRED_BUT_REJECTED", "rejection_reason": blocking,
                },
                {
                    "economy_code": self.economy_code, "source_id": self.methodology_source_id,
                    "source_authority": self.source_authority, "source_url": self.methodology_url,
                    "reference_period": "METHODOLOGY", "concept": "PFCE institutional-sector boundary",
                    "granularity": self.methodology_location, "machine_readable": "documentary_evidence",
                    "status": "ACQUIRED_DOCUMENTATION", "rejection_reason": blocking,
                },
            ],
            normalized_rows=[],
            mapping_rows=mapping,
            reconciliation_rows=[reconciliation],
            failure_rows=[],
            acquisition_records=[workbook_record, methodology_record],
            cell_status_rows=step2i_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id, self.source_authority,
                self.reference_period, "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", blocking,
            ),
            source_attempt_rows=attempts,
            source_family_rows=source_family_rows(self.economy_code, self.economy_name, attempts, blocking),
            completion_rows=[completion_row(
                self.economy_code, self.economy_name, blocking, 2,
                "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
            )],
            india_gate_rows=gate_rows,
        )


class RussiaRosstatAuditAdapter:
    economy_code = "RUT"
    economy_name = "Russian Federation"
    adapter_id = "RUT_ROSSTAT_FEDSTAT_SOURCE_AUDIT"
    source_authority = "Federal State Statistics Service"
    reference_period = "2021"

    source_specs = (
        {
            "source_id": "RUT_FEDSTAT_HFCE_31414",
            "url": "https://www.fedstat.ru/indicator/31414",
            "filename": "fedstat_indicator_31414.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_statistical_database",
            "concept": "Household final consumption expenditure aggregate",
            "classification": "FEDSTAT_INDICATOR_AGGREGATE",
        },
        {
            "source_id": "RUT_ROSSTAT_SUT_2021_XLSX",
            "url": "https://rosstat.gov.ru/storage/mediabank/Rezultaty_RB_2021.xlsx",
            "filename": "Rezultaty_RB_2021.xlsx",
            "accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.1",
            "family": "official_supply_and_use_tables",
            "concept": "2021 supply and use tables",
            "classification": "SUT_PRODUCT_CLASSIFICATION",
        },
        {
            "source_id": "RUT_ROSSTAT_HBS_2021",
            "url": "https://rosstat.gov.ru/bgd/regl/b21_102/",
            "filename": "household_income_expenditure_2021.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "Household budget survey expenditure by purpose",
            "classification": "KIPC_DH_HOUSEHOLD_SURVEY",
        },
        {
            "source_id": "RUT_ROSSTAT_KIPC_DH_CLASSIFICATION",
            "url": "https://rosstat.gov.ru/storage/mediabank/KIPC_DX.docx",
            "filename": "KIPC_DX.docx",
            "accept": "application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "KIPC-DH classification documentation",
            "classification": "CLASSIFICATION_ONLY",
        },
        {
            "source_id": "RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022",
            "url": "https://rosstat.gov.ru/storage/mediabank/Nac-sch_2015-2022.pdf",
            "filename": "Nac-sch_2015-2022.pdf",
            "accept": "application/pdf,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "National Accounts of Russia 2015-2022",
            "classification": "OFFICIAL_NATIONAL_ACCOUNTS_PUBLICATION",
        },
    )
    core_source_ids = {
        "RUT_FEDSTAT_HFCE_31414",
        "RUT_ROSSTAT_SUT_2021_XLSX",
        "RUT_ROSSTAT_HBS_2021",
    }

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        raw_root = run_root / "raw" / "country_adapters" / self.economy_code
        records: dict[str, AcquisitionRecord] = {}
        analyses: dict[str, dict[str, Any]] = {}
        errors: dict[str, Exception] = {}
        failure_rows: list[dict[str, Any]] = []
        for spec in self.source_specs:
            source_id = str(spec["source_id"])
            destination = raw_root / source_id / str(spec["filename"])
            try:
                record = fetch_url(
                    config,
                    source_id=source_id,
                    url=str(spec["url"]),
                    destination=destination,
                    cache_path=cache_root / "country_adapters" / self.economy_code / str(spec["filename"]),
                    accept=str(spec["accept"]),
                )
                records[source_id] = record
                analyses[source_id] = analyse_russia_source(source_id, destination, record.content_type or "")
            except Exception as exc:
                errors[source_id] = exc
                failure_rows.append({
                    "economy_code": self.economy_code,
                    "adapter_id": self.adapter_id,
                    "stage": f"acquisition_or_validation:{source_id}",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })

        core_blocked = sorted(self.core_source_ids & set(errors))
        unexpected = sorted(
            source_id for source_id in self.core_source_ids & set(analyses)
            if (
                not analyses[source_id].get("expected_evidence_confirmed", False)
                or analyses[source_id].get("decision") == "REVIEW_REQUIRED"
            )
        )
        if core_blocked:
            decision = "ACCESS_BLOCKED"
            status = "ACCESS_BLOCKED"
            blocking = (
                "The current run could not acquire or validate all critical official Russian source families: "
                + ", ".join(core_blocked)
                + ". The absence of an admissible exact table cannot be treated as proven while these attempts are blocked."
            )
        elif unexpected:
            decision = "CONCEPT_AMBIGUOUS"
            status = "SOURCE_CONTENT_REVIEW_REQUIRED"
            blocking = (
                "Acquired official Russian resources did not match the reviewed structural markers for: "
                + ", ".join(unexpected)
                + ". No source is admitted until the changed content is reviewed."
            )
        else:
            decision = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            status = "REJECTED_BY_CONFIRMED_SOURCE_GATES"
            blocking = (
                "Fedstat indicator 31414 provides aggregate household final consumption expenditure and current prices but no purpose dimension; "
                "the 2021 Rosstat supply-use workbook is product-based and requires a product-to-COICOP allocation, with household/NPISH scope not proven at the required category level; "
                "the KIPC-DH purpose detail is a household-budget survey and remains Class C. No exact 2021 current-price S14/P31DC twelve-purpose source passed the gates."
            )

        attempts = russia_source_attempt_rows(records, analyses, errors, blocking)
        gates = russia_methodology_gate_rows(records, analyses, errors)
        validate_russia_methodology_gate_rows(gates)
        evidence_rows = russia_evidence_rows(records, analyses, errors, blocking)
        source_url = str(self.source_specs[0]["url"])
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code,
                "economy_name": self.economy_name,
                "adapter_id": self.adapter_id,
                "status": status,
                "data_class": decision,
                "accepted_rows": 0,
                "failure_count": len(failure_rows),
                "source_url": source_url,
                "blocking_reason": blocking,
            }],
            evidence_rows=evidence_rows,
            normalized_rows=[],
            mapping_rows=russia_mapping_audit_rows(analyses),
            reconciliation_rows=[],
            failure_rows=failure_rows,
            acquisition_records=[records[key] for key in sorted(records)],
            cell_status_rows=step2i_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id,
                self.source_authority, self.reference_period, decision, blocking,
            ),
            source_attempt_rows=attempts,
            source_family_rows=source_family_rows(
                self.economy_code, self.economy_name, attempts, blocking,
            ),
            completion_rows=[completion_row(
                self.economy_code, self.economy_name, blocking,
                len(self.source_specs), decision,
            )],
            russia_gate_rows=gates,
        )


class ChinaNbsAuditAdapter:
    economy_code = "CHN"
    economy_name = "China"
    adapter_id = "CHN_NBS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "National Bureau of Statistics of China"
    reference_period = "2021"

    source_specs = (
        {
            "source_id": "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION",
            "url": "https://www.stats.gov.cn/english/PressRelease/202201/t20220118_1826649.html",
            "filename": "household_consumption_2021.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "Household survey consumption expenditure in eight groups",
            "classification": "HOUSEHOLD_SURVEY_EIGHT_GROUPS",
        },
        {
            "source_id": "CHN_NBS_YEARBOOK_2022_INDEX",
            "url": "https://www.stats.gov.cn/sj/ndsj/2022/indexeh.htm",
            "filename": "china_statistical_yearbook_2022.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "Official 2022 yearbook table inventory",
            "classification": "YEARBOOK_TABLE_INVENTORY",
        },
        {
            "source_id": "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF",
            "url": "https://www.stats.gov.cn/sj/ndsj/2022/html/sme03.htm",
            "filename": "national_accounts_brief_2022.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_supply_and_use_tables",
            "concept": "National accounts and 2020 input-output explanatory notes",
            "classification": "INPUT_OUTPUT_PRODUCT_TABLES_2020",
        },
        {
            "source_id": "CHN_NBS_2021_GDP_FINAL_VERIFICATION",
            "url": "https://www.stats.gov.cn/english/PressRelease/202212/t20221227_1891279.html",
            "filename": "gdp_final_verification_2021.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_national_accounts_api",
            "concept": "Final verification of 2021 GDP at current prices",
            "classification": "GDP_AGGREGATE_PUBLICATION",
        },
        {
            "source_id": "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_NOTES",
            "url": "https://www.stats.gov.cn/sj/ndsj/2022/html/zbe03.pdf",
            "filename": "national_accounts_notes.pdf",
            "accept": "application/pdf,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "National accounts explanatory notes",
            "classification": "METHODOLOGY_DOCUMENTATION",
        },
        {
            "source_id": "CHN_NBS_YEARBOOK_2022_HOUSEHOLD_SURVEY_NOTES",
            "url": "https://www.stats.gov.cn/sj/ndsj/2022/html/zbe06.pdf",
            "filename": "household_survey_notes.pdf",
            "accept": "application/pdf,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "Household survey explanatory notes",
            "classification": "SURVEY_METHODOLOGY_DOCUMENTATION",
        },
    )
    core_source_ids = {
        "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION",
        "CHN_NBS_YEARBOOK_2022_INDEX",
        "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF",
        "CHN_NBS_2021_GDP_FINAL_VERIFICATION",
    }

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        raw_root = run_root / "raw" / "country_adapters" / self.economy_code
        records: dict[str, AcquisitionRecord] = {}
        analyses: dict[str, dict[str, Any]] = {}
        errors: dict[str, Exception] = {}
        failure_rows: list[dict[str, Any]] = []
        for spec in self.source_specs:
            source_id = str(spec["source_id"])
            destination = raw_root / source_id / str(spec["filename"])
            try:
                record = fetch_url(
                    config,
                    source_id=source_id,
                    url=str(spec["url"]),
                    destination=destination,
                    cache_path=cache_root / "country_adapters" / self.economy_code / str(spec["filename"]),
                    accept=str(spec["accept"]),
                )
                records[source_id] = record
                analyses[source_id] = analyse_china_source(source_id, destination, record.content_type or "")
            except Exception as exc:
                errors[source_id] = exc
                failure_rows.append({
                    "economy_code": self.economy_code,
                    "adapter_id": self.adapter_id,
                    "stage": f"acquisition_or_validation:{source_id}",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })

        core_blocked = sorted(self.core_source_ids & set(errors))
        unexpected = sorted(
            source_id for source_id in self.core_source_ids & set(analyses)
            if (
                not analyses[source_id].get("expected_evidence_confirmed", False)
                or analyses[source_id].get("decision") == "REVIEW_REQUIRED"
            )
        )
        if core_blocked:
            decision = "ACCESS_BLOCKED"
            status = "ACCESS_BLOCKED"
            blocking = (
                "The current run could not acquire or validate all critical official Chinese source families: "
                + ", ".join(core_blocked)
                + ". A closed source decision is not permitted while these attempts remain blocked."
            )
        elif unexpected:
            decision = "CONCEPT_AMBIGUOUS"
            status = "SOURCE_CONTENT_REVIEW_REQUIRED"
            blocking = (
                "Acquired official Chinese resources did not match the reviewed structural markers for: "
                + ", ".join(unexpected)
                + ". No source is admitted until the changed content is reviewed."
            )
        else:
            decision = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            status = "REJECTED_BY_CONFIRMED_SOURCE_GATES"
            blocking = (
                "The 2021 NBS household-consumption release is a sample survey with eight combined groups; "
                "the 2022 statistical yearbook inventories household-consumption and input-output tables but its input-output benchmark is 2020; "
                "the national-accounts brief describes product-based input-output tables; and the final 2021 GDP verification is aggregate. "
                "No acquired source supplies 2021 current-price S14/P31 household consumption by the twelve Armilar purposes without allocation."
            )

        attempts = china_source_attempt_rows(records, analyses, errors, blocking)
        gates = china_methodology_gate_rows(records, analyses, errors)
        validate_china_methodology_gate_rows(gates)
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code,
                "economy_name": self.economy_name,
                "adapter_id": self.adapter_id,
                "status": status,
                "data_class": decision,
                "accepted_rows": 0,
                "failure_count": len(failure_rows),
                "source_url": str(self.source_specs[0]["url"]),
                "blocking_reason": blocking,
            }],
            evidence_rows=china_evidence_rows(records, analyses, errors, blocking),
            normalized_rows=[],
            mapping_rows=china_mapping_audit_rows(analyses),
            reconciliation_rows=[],
            failure_rows=failure_rows,
            acquisition_records=[records[key] for key in sorted(records)],
            cell_status_rows=step2i_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id,
                self.source_authority, self.reference_period, decision, blocking,
            ),
            source_attempt_rows=attempts,
            source_family_rows=source_family_rows(
                self.economy_code, self.economy_name, attempts, blocking,
            ),
            completion_rows=[completion_row(
                self.economy_code, self.economy_name, blocking,
                len(self.source_specs), decision,
            )],
            china_gate_rows=gates,
        )


class Step2IDecisionAdapter:
    def __init__(
        self, economy_code: str, economy_name: str, adapter_id: str,
        authority: str, source_url: str, reference_period: str,
        concept: str, granularity: str, data_class: str, reason: str,
    ) -> None:
        self.economy_code = economy_code
        self.economy_name = economy_name
        self.adapter_id = adapter_id
        self.authority = authority
        self.source_url = source_url
        self.reference_period = reference_period
        self.concept = concept
        self.granularity = granularity
        self.data_class = data_class
        self.reason = reason

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        attempt = step2i_attempt_template(
            self.economy_code, "*", self.authority, self.adapter_id, self.source_url,
            self.reference_period, self.concept, self.granularity, self.reason,
        )
        source_attempts = expand_attempt_categories([attempt] + [
            step2i_attempt_template(self.economy_code, "*", authority, dataset, url, period, concept, classification, reason)
            for authority, dataset, url, period, concept, classification, reason in STEP2I_EXTRA_ATTEMPTS.get(self.economy_code, [])
        ])
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code, "economy_name": self.economy_name,
                "adapter_id": self.adapter_id, "status": "BLOCKED_BY_SOURCE_GATE",
                "data_class": self.data_class, "accepted_rows": 0, "failure_count": 0,
                "source_url": self.source_url, "blocking_reason": self.reason,
            }],
            evidence_rows=[{
                "economy_code": self.economy_code, "source_id": self.adapter_id,
                "source_authority": self.authority, "source_url": self.source_url,
                "reference_period": self.reference_period, "concept": self.concept,
                "granularity": self.granularity, "machine_readable": "not accepted",
                "status": "REJECTED", "rejection_reason": self.reason,
            }],
            normalized_rows=[], mapping_rows=[], reconciliation_rows=[], failure_rows=[], acquisition_records=[],
            cell_status_rows=step2i_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id, self.authority,
                self.reference_period, self.data_class, self.reason,
            ),
            source_attempt_rows=source_attempts,
            source_family_rows=source_family_rows(self.economy_code, self.economy_name, source_attempts, self.reason),
            completion_rows=[completion_row(self.economy_code, self.economy_name, self.reason, len({row["dataset"] for row in source_attempts}), self.data_class)],
        )


class AuditOnlyAdapter(Step2IDecisionAdapter):
    pass


def parse_india_statement_5_1(path: Path) -> dict[str, dict[str, Any]]:
    if not zipfile.is_zipfile(path):
        raise ValueError("India Statement 5.1 is not a valid XLSX zip container")
    sheet_rows = _xlsx_rows(path)
    header = sheet_rows.get(7, {})
    value_col = next((col for col, value in header.items() if str(value).strip() == "2021-22"), None)
    name_col = "AA"
    code_col = "AB"
    if value_col is None:
        raise ValueError("India Statement 5.1 does not expose current-price 2021-22 column")
    parsed: dict[str, dict[str, Any]] = {}
    for row in sheet_rows.values():
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        value = str(row.get(value_col, "")).strip()
        if code and name and value:
            try:
                parsed[code] = {"name": name, "value": Decimal(value)}
            except Exception:
                continue
    required = {"1", "2", "2.1", "2.2", "2.3", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"}
    missing = sorted(required - parsed.keys())
    if missing:
        raise ValueError("India Statement 5.1 missing required item codes: " + ",".join(missing))
    return parsed


def build_india_rows(parsed: dict[str, dict[str, Any]], record: AcquisitionRecord, run_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping_specs = [
        ("1", "CP01", "ONE_TO_ONE"),
        ("2.1", "CP02", "MANY_TO_ONE_EXACT"),
        ("2.2", "CP02", "MANY_TO_ONE_EXACT"),
        ("3", "CP03", "ONE_TO_ONE"),
        ("4", "CP04", "ONE_TO_ONE"),
        ("5", "CP05", "ONE_TO_ONE"),
        ("6", "CP06", "ONE_TO_ONE"),
        ("7", "CP07", "ONE_TO_ONE"),
        ("8", "CP08", "ONE_TO_ONE"),
        ("9", "CP09", "ONE_TO_ONE"),
        ("10", "CP10", "ONE_TO_ONE"),
        ("11", "CP11", "ONE_TO_ONE"),
        ("12", "CP12", "ONE_TO_ONE"),
    ]
    rows: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    grouped: dict[str, list[str]] = {}
    for code, category, mapping_type in mapping_specs:
        grouped.setdefault(category, []).append(code)
        mapping.append({
            "economy_code": "IND", "original_item_code": code,
            "original_item_name": parsed[code]["name"], "armilar_category": category,
            "mapping_type": mapping_type, "status": "PASS",
            "reason": "Item belongs wholly to one Armilar category.",
        })
    mapping.append({
        "economy_code": "IND", "original_item_code": "2.3",
        "original_item_name": parsed["2.3"]["name"], "armilar_category": "",
        "mapping_type": "EXCLUDED", "status": "PASS",
        "reason": "Narcotics are explicitly excluded by Armilar methodology.",
    })
    for category, codes in sorted(grouped.items()):
        value = sum((parsed[code]["value"] for code in codes), Decimal("0"))
        rows.append({
            "economy_code": "IND", "economy_name": "India",
            "reference_period": "2021-22", "armilar_category": category,
            "original_item_code": "+".join(codes),
            "original_item_name": " + ".join(parsed[code]["name"] for code in codes),
            "value": value, "currency": "INR", "unit": "crore",
            "sector": "PRIVATE_FINAL_CONSUMPTION_EXPENDITURE",
            "transaction": "PFCE", "classification": "MOSPI_NAS_ITEM",
            "source_authority": "Ministry of Statistics and Programme Implementation",
            "source_file": record.path.relative_to(run_root).as_posix(),
            "source_url": record.url, "retrieved_at": record.retrieved_at,
            "source_hash": record.sha256,
            "derivation_method": "OFFICIAL_ITEM_SUM_EXCLUDING_NARCOTICS",
            "data_class": "OFFICIAL_EXACT_DERIVATION",
            "quality_flags": "",
        })
    return rows, mapping


def reconcile_india(parsed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    accepted_codes = ["1", "2.1", "2.2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    accepted_total = sum((parsed[code]["value"] for code in accepted_codes), Decimal("0"))
    excluded = parsed["2.3"]["value"]
    source_total = parsed["13"]["value"]
    reconstructed = accepted_total + excluded
    difference = source_total - reconstructed
    return {
        "economy_code": "IND", "reference_period": "2021-22",
        "source_total": source_total, "accepted_total": accepted_total,
        "excluded_total": excluded, "reconstructed_total": reconstructed,
        "difference": difference, "status": "PASS" if difference == 0 else "FAIL",
    }


def _xlsx_rows(path: Path) -> dict[int, dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names or "xl/worksheets/sheet1.xml" not in names:
            raise ValueError("XLSX workbook is missing required workbook or sheet XML")
        strings: list[str] = []
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                strings.append("".join(t.text or "" for t in item.findall(".//a:t", ns)))
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: dict[int, dict[str, str]] = {}
    for cell in root.findall(".//a:c", ns):
        ref = cell.attrib.get("r", "")
        col = "".join(ch for ch in ref if ch.isalpha())
        row_number = int("".join(ch for ch in ref if ch.isdigit()) or 0)
        value_node = cell.find("a:v", ns)
        text = ""
        if value_node is not None and value_node.text is not None:
            text = value_node.text
            if cell.attrib.get("t") == "s":
                text = strings[int(text)]
        rows.setdefault(row_number, {})[col] = text
    return rows


def _empty_result() -> AdapterResult:
    return AdapterResult(
        status_rows=[], evidence_rows=[], normalized_rows=[], mapping_rows=[],
        reconciliation_rows=[], failure_rows=[], acquisition_records=[],
        cell_status_rows=[], source_attempt_rows=[], source_family_rows=[],
        completion_rows=[], india_gate_rows=[], russia_gate_rows=[],
        china_gate_rows=[], indonesia_gate_rows=[], brazil_gate_rows=[],
        egypt_gate_rows=[], pakistan_gate_rows=[], nigeria_gate_rows=[], bangladesh_gate_rows=[], vietnam_gate_rows=[], step2h_exception_rows=[],
    )


def _extend(target: AdapterResult, source: AdapterResult) -> None:
    target.status_rows.extend(source.status_rows)
    target.evidence_rows.extend(source.evidence_rows)
    target.normalized_rows.extend(source.normalized_rows)
    target.mapping_rows.extend(source.mapping_rows)
    target.reconciliation_rows.extend(source.reconciliation_rows)
    target.failure_rows.extend(source.failure_rows)
    target.acquisition_records.extend(source.acquisition_records)
    target.cell_status_rows.extend(source.cell_status_rows or [])
    target.source_attempt_rows.extend(source.source_attempt_rows or [])
    target.source_family_rows.extend(source.source_family_rows or [])
    target.completion_rows.extend(source.completion_rows or [])
    target.india_gate_rows.extend(source.india_gate_rows or [])
    target.russia_gate_rows.extend(source.russia_gate_rows or [])
    target.china_gate_rows.extend(source.china_gate_rows or [])
    target.indonesia_gate_rows.extend(source.indonesia_gate_rows or [])
    target.brazil_gate_rows.extend(source.brazil_gate_rows or [])
    target.egypt_gate_rows.extend(source.egypt_gate_rows or [])
    target.pakistan_gate_rows.extend(source.pakistan_gate_rows or [])
    target.nigeria_gate_rows.extend(source.nigeria_gate_rows or [])
    target.bangladesh_gate_rows.extend(source.bangladesh_gate_rows or [])
    target.vietnam_gate_rows.extend(source.vietnam_gate_rows or [])
    target.step2h_exception_rows.extend(source.step2h_exception_rows or [])


def step2i_cell_rows(
    economy_code: str,
    economy_name: str,
    source_id: str,
    authority: str,
    reference_period: str,
    cell_class: str,
    blocking_reason: str,
) -> list[dict[str, Any]]:
    return [{
        "economy_code": economy_code,
        "economy_name": economy_name,
        "armilar_category": category,
        "cell_class": cell_class,
        "source_id": source_id,
        "source_authority": authority,
        "reference_period": reference_period,
        "value_status": "NOT_ADMISSIBLE",
        "admissible_to_exact_matrix": False,
        "blocking_reason": blocking_reason,
        "quality_flags": "STEP2I_DECISION|FAIL_CLOSED|NO_ALLOCATION",
    } for category in STEP2I_PROXY_CATEGORIES]


def completion_row(
    economy_code: str,
    economy_name: str,
    blocker: str,
    sources_examined: int,
    decision: str = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
) -> dict[str, Any]:
    if decision in FINAL_AUDIT_REQUIRED_STATES:
        raise ValueError("UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT requires complete documented family coverage")
    return {
        "economy_code": economy_code,
        "economy_name": economy_name,
        "accepted_categories": "",
        "experimental_categories": "",
        "unavailable_categories": "|".join(STEP2I_PROXY_CATEGORIES),
        "coverage_added_cells": 0,
        "decision": decision,
        "sources_examined": sources_examined,
        "remaining_blockers": blocker,
    }


def source_family_rows(
    economy_code: str,
    economy_name: str,
    attempts: list[dict[str, Any]],
    remaining_gap: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    attempts_by_family: dict[str, list[dict[str, Any]]] = {family: [] for _, family in SOURCE_FAMILIES}
    for attempt in attempts:
        explicit_family = str(attempt.get("source_family") or "").strip()
        if explicit_family in attempts_by_family:
            attempts_by_family[explicit_family].append(attempt)
            continue
        dataset = str(attempt.get("dataset") or "").upper()
        classification = str(attempt.get("classification") or "").upper()
        if "API" in dataset or "SIDRA" in dataset:
            attempts_by_family["official_national_accounts_api"].append(attempt)
        elif any(token in dataset for token in ("INPUT_OUTPUT", "INPUT-OUTPUT", "IO_TABLE")):
            attempts_by_family["official_input_output_tables"].append(attempt)
        elif any(token in dataset for token in ("SUPPLY", "USE", "SUT", "TRU")):
            attempts_by_family["official_supply_and_use_tables"].append(attempt)
        elif "DATABASE" in classification or "FEDSTAT" in dataset or "STATBANK" in dataset or "BASE" in dataset:
            attempts_by_family["official_statistical_database"].append(attempt)
        elif any(token in dataset for token in ("XLS", "XLSX", "CSV", "STATEMENT", "DOWNLOAD")):
            attempts_by_family["official_csv_xls_xlsx"].append(attempt)
        elif "SURVEY" in classification or "CPI" in classification or "HBS" in classification or "HIECS" in classification:
            attempts_by_family["survey_or_cpi_class_c_only"].append(attempt)
        elif "METHODOLOGY" in classification or "CLASSIFICATION" in classification:
            attempts_by_family["official_classifications_methodology"].append(attempt)
        else:
            attempts_by_family["official_structured_publications"].append(attempt)
    for order, family in SOURCE_FAMILIES:
        family_attempts = attempts_by_family.get(family, [])
        best = family_attempts[0] if family_attempts else {}
        best_status = str(best.get("retrieval_status") or "NOT_INVESTIGATED_IN_CURRENT_PROBE")
        can_support = "false"
        result.append({
            "economy_code": economy_code,
            "economy_name": economy_name,
            "source_family": family,
            "family_order": order,
            "attempts_recorded": len(family_attempts),
            "best_status": best_status,
            "best_dataset": best.get("dataset", ""),
            "best_url": best.get("url", ""),
            "remaining_gap": remaining_gap if not family_attempts else str(best.get("rejection_reason") or remaining_gap),
            "can_support_exact_matrix": can_support,
        })
    return result


def step2i_attempt_template(
    economy_code: str,
    category: str,
    authority: str,
    dataset: str,
    url: str,
    reference_period: str,
    concept: str,
    classification: str,
    rejection_reason: str,
) -> dict[str, Any]:
    return {
        "economy_code": economy_code,
        "category": category,
        "source_family": "official_structured_publications",
        "authority": authority,
        "dataset": dataset,
        "url": url,
        "access_method": "OFFICIAL_WEB_SOURCE_AUDIT",
        "retrieval_status": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
        "status_code": "",
        "content_type": "",
        "file_signature": "",
        "byte_size": "",
        "reference_period": reference_period,
        "institutional_sector": "UNCONFIRMED_STRICT_S14" if economy_code == "IND" else "NOT_CONFIRMED_AS_STRICT_S14",
        "transaction_code": "NOT_CONFIRMED_AS_P31DC",
        "classification": classification,
        "current_prices": "UNKNOWN",
        "currency": "UNKNOWN",
        "unit": "UNKNOWN",
        "npish_treatment": "NOT_CONFIRMED_EXCLUDED",
        "government_treatment": "NOT_CONFIRMED_EXCLUDED",
        "imputed_rent_treatment": "NOT_CONFIRMED",
        "candidate_class": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
        "rejection_reason": rejection_reason,
        "retrieved_at": "NOT_RETRIEVED_IN_STEP2I_AUDIT",
        "sha256": "",
    }


def india_source_attempt_rows(
    workbook_record: AcquisitionRecord,
    methodology_record: AcquisitionRecord | None,
    rejection_reason: str,
    *,
    methodology_reviewed: bool = True,
) -> list[dict[str, Any]]:
    workbook = step2i_attempt_template(
        "IND", "*", "Ministry of Statistics and Programme Implementation",
        "IND_MOSPI_NAS2024_STATEMENT_5_1", workbook_record.url, "2021-22",
        "PFCE classified by item", "MOSPI_NAS_ITEM", rejection_reason,
    )
    workbook.update({
        "retrieval_status": workbook_record.status,
        "status_code": workbook_record.status_code or "",
        "content_type": workbook_record.content_type or "",
        "file_signature": "XLSX_ZIP_CONTAINER",
        "byte_size": workbook_record.bytes,
        "institutional_sector": "HOUSEHOLDS_AND_NPISH_COMBINED",
        "transaction_code": "PFCE_P31_COMBINED_S14_S15",
        "current_prices": "CONFIRMED",
        "currency": "INR",
        "unit": "crore",
        "npish_treatment": "CONFIRMED_INCLUDED_AND_NOT_SEPARABLE",
        "government_treatment": "CONFIRMED_EXCLUDED_FROM_PFCE",
        "imputed_rent_treatment": "CONFIRMED_INCLUDED",
        "candidate_class": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
        "retrieved_at": workbook_record.retrieved_at,
        "sha256": workbook_record.sha256,
    })
    if not methodology_reviewed:
        workbook.update({
            "institutional_sector": "UNCONFIRMED_STRICT_S14",
            "transaction_code": "PFCE_SCOPE_REVIEW_REQUIRED",
            "npish_treatment": "REVIEW_REQUIRED",
            "government_treatment": "REVIEW_REQUIRED",
            "imputed_rent_treatment": "REVIEW_REQUIRED",
            "candidate_class": "CONCEPT_AMBIGUOUS",
        })
    if methodology_record is None:
        methodology = step2i_attempt_template(
            "IND", "*", "Ministry of Statistics and Programme Implementation",
            IndiaMospiAdapter.methodology_source_id, IndiaMospiAdapter.methodology_url,
            "METHODOLOGY", "PFCE institutional-sector boundary", "OFFICIAL_METHODOLOGY",
            rejection_reason,
        )
        methodology.update({
            "retrieval_status": "ACCESS_BLOCKED",
            "candidate_class": "ACCESS_BLOCKED",
            "retrieved_at": "ACQUISITION_FAILED_NO_RAW_FILE",
        })
    else:
        methodology = step2i_attempt_template(
            "IND", "*", "Ministry of Statistics and Programme Implementation",
            IndiaMospiAdapter.methodology_source_id, methodology_record.url,
            "METHODOLOGY", "PFCE institutional-sector boundary", "OFFICIAL_METHODOLOGY",
            rejection_reason,
        )
        methodology.update({
            "retrieval_status": methodology_record.status,
            "status_code": methodology_record.status_code or "",
            "content_type": methodology_record.content_type or "",
            "file_signature": "PDF_SIGNATURE",
            "byte_size": methodology_record.bytes,
            "institutional_sector": "HOUSEHOLDS_AND_NPISH_COMBINED",
            "transaction_code": "PFCE_P31_COMBINED_S14_S15",
            "current_prices": "CONCEPT_APPLIES_TO_CURRENT_AND_CONSTANT_PRICE_SERIES",
            "currency": "NOT_APPLICABLE",
            "unit": "NOT_APPLICABLE",
            "npish_treatment": "CONFIRMED_INCLUDED_AND_NOT_SEPARABLE",
            "government_treatment": "CONFIRMED_EXCLUDED_FROM_PFCE",
            "imputed_rent_treatment": "CONFIRMED_INCLUDED",
            "candidate_class": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
            "retrieved_at": methodology_record.retrieved_at,
            "sha256": methodology_record.sha256,
        })
        if not methodology_reviewed:
            methodology.update({
                "retrieval_status": "ACQUIRED_REVIEW_REQUIRED",
                "institutional_sector": "UNREVIEWED_DOCUMENT_VERSION",
                "transaction_code": "PFCE_SCOPE_REVIEW_REQUIRED",
                "npish_treatment": "REVIEW_REQUIRED",
                "government_treatment": "REVIEW_REQUIRED",
                "imputed_rent_treatment": "REVIEW_REQUIRED",
                "candidate_class": "CONCEPT_AMBIGUOUS",
            })
    return expand_attempt_categories([workbook, methodology])


def india_access_blocked_attempt_rows(
    rejection_reason: str,
    *,
    source_id: str,
    source_url: str,
    dataset: str,
) -> list[dict[str, Any]]:
    row = step2i_attempt_template(
        "IND", "*", "Ministry of Statistics and Programme Implementation",
        dataset, source_url, "2021-22",
        "PFCE classified by item" if source_id == IndiaMospiAdapter.adapter_id else "PFCE methodology",
        "MOSPI_NAS_ITEM" if source_id == IndiaMospiAdapter.adapter_id else "OFFICIAL_METHODOLOGY",
        rejection_reason,
    )
    row.update({
        "retrieval_status": "ACCESS_BLOCKED",
        "candidate_class": "ACCESS_BLOCKED",
        "retrieved_at": "ACQUISITION_FAILED_NO_RAW_FILE",
    })
    return expand_attempt_categories([row])


def expand_attempt_categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for row in rows:
        if row.get("category") != "*":
            expanded.append(row)
            continue
        for category in STEP2I_PROXY_CATEGORIES:
            item = dict(row)
            item["category"] = category
            expanded.append(item)
    return expanded



def _decode_text_file(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gb2312", "cp1251", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _office_xml_text(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Office file is not a valid ZIP container: {path.name}")
    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".xml"):
                continue
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            chunks.extend(part.strip() for part in root.itertext() if part and part.strip())
    return " ".join(chunks)


def _normalise_russian_text(value: str) -> str:
    value = html.unescape(value).lower().replace("ё", "е")
    return re.sub(r"\s+", " ", value).strip()



def _normalise_china_text(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def analyse_china_source(source_id: str, path: Path, content_type: str = "") -> dict[str, Any]:
    if source_id in {
        "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_NOTES",
        "CHN_NBS_YEARBOOK_2022_HOUSEHOLD_SURVEY_NOTES",
    }:
        valid_pdf = path.read_bytes()[:5] == b"%PDF-"
        return {
            "source_kind": "OFFICIAL_PUBLICATION_PDF",
            "expected_evidence_confirmed": valid_pdf,
            "valid_pdf_signature": valid_pdf,
            "machine_readable": False,
            "decision": "SOURCE_NOT_MACHINE_READABLE" if valid_pdf else "REVIEW_REQUIRED",
        }

    text = _normalise_china_text(_decode_text_file(path))
    if source_id == "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION":
        categories = (
            "food, tobacco and liquor", "clothing", "residence",
            "household facilities, articles and services",
            "transportation and telecommunication",
            "education, culture and recreation",
            "health care and medical services",
            "miscellaneous goods and services",
        )
        survey = any(token in text for token in (
            "sampling survey", "survey households", "household income and expenditure and living conditions survey",
        ))
        eight_groups = all(token in text for token in categories)
        year = "2021" in text
        return {
            "source_kind": "OFFICIAL_HOUSEHOLD_SURVEY",
            "expected_evidence_confirmed": survey and eight_groups and year,
            "household_survey": survey,
            "eight_group_classification": eight_groups,
            "reference_2021": year,
            "combined_food_tobacco_alcohol": "food, tobacco and liquor" in text,
            "combined_education_culture_recreation": "education, culture and recreation" in text,
            "machine_readable": True,
            "decision": "REJECT_CLASS_C_EIGHT_GROUP_SURVEY" if survey and eight_groups and year else "REVIEW_REQUIRED",
        }
    if source_id == "CHN_NBS_YEARBOOK_2022_INDEX":
        yearbook = "china statistical yearbook 2022" in text or "中国统计年鉴-2022" in text
        household_table = "3-13 household consumption expenditure" in text or "居民消费支出" in text
        io_2020 = (
            "3-21 intermediate use part of 2020 input-output table" in text
            or "3-22 final use part of 2020 input-output table" in text
            or ("2020" in text and "input-output table" in text)
            or ("2020" in text and "投入产出表" in text)
        )
        return {
            "source_kind": "OFFICIAL_YEARBOOK_INDEX",
            "expected_evidence_confirmed": yearbook and household_table and io_2020,
            "yearbook_2022": yearbook,
            "household_consumption_table_inventory": household_table,
            "input_output_reference_2020": io_2020,
            "machine_readable": True,
            "decision": "DISCOVERY_INVENTORY_ONLY" if yearbook and household_table and io_2020 else "REVIEW_REQUIRED",
        }
    if source_id == "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF":
        io = "input-output table" in text or "投入产出表" in text
        year_2020 = "2020" in text
        product = any(token in text for token in (
            "products", "goods and services", "product classification", "产品", "货物和服务",
        ))
        competitive = any(token in text for token in (
            "competitive input-output", "non-competitive input-output", "竞争型", "非竞争型",
        ))
        return {
            "source_kind": "OFFICIAL_INPUT_OUTPUT_METHODOLOGY",
            "expected_evidence_confirmed": io and year_2020 and (product or competitive),
            "input_output_table": io,
            "reference_2020": year_2020,
            "product_classification": product or competitive,
            "purpose_classification": any(token in text for token in ("coicop", "by purpose", "按目的")),
            "machine_readable": True,
            "decision": "REJECT_WRONG_YEAR_PRODUCT_IO" if io and year_2020 and (product or competitive) else "REVIEW_REQUIRED",
        }
    if source_id == "CHN_NBS_2021_GDP_FINAL_VERIFICATION":
        final_verification = "final verification of gdp in 2021" in text
        current_price = "current price" in text
        expenditure = "expenditure approach" in text or "final consumption expenditure" in text
        purpose = any(token in text for token in ("coicop", "household consumption by purpose", "12 categories"))
        return {
            "source_kind": "OFFICIAL_NATIONAL_ACCOUNTS_PUBLICATION",
            "expected_evidence_confirmed": final_verification and current_price and expenditure,
            "reference_2021": final_verification,
            "current_prices": current_price,
            "expenditure_approach": expenditure,
            "purpose_dimension": purpose,
            "machine_readable": True,
            "decision": "REJECT_AGGREGATE_ONLY" if final_verification and current_price and expenditure and not purpose else "REVIEW_REQUIRED",
        }
    raise ValueError(f"Unknown Chinese source id: {source_id}")


def china_source_attempt_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in ChinaNbsAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        row = step2i_attempt_template(
            "CHN", "*", ChinaNbsAuditAdapter.source_authority,
            source_id, str(spec["url"]), "2021", str(spec["concept"]),
            str(spec["classification"]), rejection_reason,
        )
        if source_id in errors:
            row.update({
                "retrieval_status": "ACCESS_BLOCKED",
                "candidate_class": "ACCESS_BLOCKED",
                "retrieved_at": "ACQUISITION_FAILED_NO_RAW_FILE",
                "rejection_reason": f"{type(errors[source_id]).__name__}: {errors[source_id]}",
            })
        else:
            record = records[source_id]
            analysis = analyses[source_id]
            suffix = Path(str(spec["filename"])).suffix.lower()
            signature = {".pdf": "PDF_SIGNATURE", ".html": "HTML_DOCUMENT"}.get(suffix, "BINARY_CONTENT")
            decision = str(analysis.get("decision") or "REVIEW_REQUIRED")
            retrieval = {
                "REJECT_CLASS_C_EIGHT_GROUP_SURVEY": "ACQUIRED_CLASS_C_SURVEY",
                "DISCOVERY_INVENTORY_ONLY": "ACQUIRED_DISCOVERY_INVENTORY",
                "REJECT_WRONG_YEAR_PRODUCT_IO": "ACQUIRED_REJECTED_WRONG_YEAR_PRODUCT_IO",
                "REJECT_AGGREGATE_ONLY": "ACQUIRED_AGGREGATE_ONLY",
                "SOURCE_NOT_MACHINE_READABLE": "ACQUIRED_NOT_MACHINE_READABLE",
            }.get(decision, "ACQUIRED_REVIEW_REQUIRED")
            row.update({
                "retrieval_status": retrieval,
                "status_code": record.status_code or "",
                "content_type": record.content_type or "",
                "file_signature": signature,
                "byte_size": record.bytes,
                "retrieved_at": record.retrieved_at,
                "sha256": record.sha256,
                "candidate_class": "CONCEPT_AMBIGUOUS" if decision == "REVIEW_REQUIRED" else "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
            })
            if source_id == "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION":
                row.update({
                    "institutional_sector": "HOUSEHOLD_SURVEY_RESPONDENTS",
                    "transaction_code": "SURVEY_CONSUMPTION_EXPENDITURE_NOT_P31DC",
                    "classification": "EIGHT_GROUP_SURVEY_CLASSIFICATION",
                    "current_prices": "NOMINAL_PER_CAPITA_SURVEY_EXPENDITURE",
                    "currency": "CNY", "unit": "yuan_per_capita",
                    "npish_treatment": "OUTSIDE_SURVEY_CONCEPT",
                    "government_treatment": "OUTSIDE_SURVEY_CONCEPT",
                    "imputed_rent_treatment": "SURVEY_NOT_PROVEN_EQUIVALENT_TO_SNA",
                })
            elif source_id == "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF":
                row.update({
                    "institutional_sector": "MULTIPLE_FINAL_USE_SECTORS",
                    "transaction_code": "INPUT_OUTPUT_FINAL_USE",
                    "classification": "PRODUCT_TABLES_NOT_PURPOSES",
                    "current_prices": "OFFICIAL_INPUT_OUTPUT_TABLE_FAMILY",
                    "currency": "CNY", "unit": "YEARBOOK_TABLE_UNIT",
                    "npish_treatment": "NOT_CONFIRMED_AT_PURPOSE_LEVEL",
                    "government_treatment": "SEPARATE_FINAL_USE_EXPECTED_NOT_PURPOSE_GATE",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_PURPOSE_LEVEL",
                })
            elif source_id == "CHN_NBS_2021_GDP_FINAL_VERIFICATION":
                row.update({
                    "institutional_sector": "TOTAL_ECONOMY_AGGREGATES",
                    "transaction_code": "GDP_EXPENDITURE_APPROACH_AGGREGATE",
                    "classification": "NO_HOUSEHOLD_PURPOSE_DIMENSION",
                    "current_prices": "CONFIRMED", "currency": "CNY", "unit": "100_million_yuan",
                    "npish_treatment": "NOT_EXPOSED_AT_PURPOSE_LEVEL",
                    "government_treatment": "NOT_EXPOSED_AT_PURPOSE_LEVEL",
                    "imputed_rent_treatment": "NOT_EXPOSED_AT_PURPOSE_LEVEL",
                })
            else:
                row.update({
                    "institutional_sector": "DOCUMENTATION_OR_INVENTORY_ONLY",
                    "transaction_code": "NOT_AN_EXACT_DATASET",
                    "current_prices": "NOT_APPLICABLE_OR_NOT_PROVEN",
                    "currency": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
                    "npish_treatment": "NOT_PROVEN_AT_CATEGORY_LEVEL",
                    "government_treatment": "NOT_PROVEN_AT_CATEGORY_LEVEL",
                    "imputed_rent_treatment": "DOCUMENTATION_ONLY",
                })
        rows.append(row)
    return expand_attempt_categories(rows)


def china_evidence_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in ChinaNbsAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        if source_id in errors:
            status = "ACCESS_BLOCKED"
            machine = "unknown_this_run"
            reason = f"{type(errors[source_id]).__name__}: {errors[source_id]}"
        else:
            decision = str(analyses[source_id].get("decision") or "REVIEW_REQUIRED")
            status = "ACQUIRED_BUT_REJECTED" if decision.startswith("REJECT_") else decision
            machine = str(bool(analyses[source_id].get("machine_readable"))).lower()
            reason = rejection_reason
        rows.append({
            "economy_code": "CHN",
            "source_id": source_id,
            "source_authority": ChinaNbsAuditAdapter.source_authority,
            "source_url": str(spec["url"]),
            "reference_period": "2021",
            "concept": str(spec["concept"]),
            "granularity": str(spec["classification"]),
            "machine_readable": machine,
            "status": status,
            "rejection_reason": reason,
        })
    return rows


def china_mapping_audit_rows(analyses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    survey = analyses.get("CHN_NBS_2021_HOUSEHOLD_CONSUMPTION", {})
    if survey.get("eight_group_classification"):
        rows.extend([
            {
                "economy_code": "CHN", "original_item_code": "FOOD_TOBACCO_LIQUOR",
                "original_item_name": "Food, tobacco and liquor", "armilar_category": "CP01|CP02",
                "mapping_type": "ONE_SURVEY_GROUP_TO_MULTIPLE_ARMILAR_CATEGORIES",
                "status": "REJECTED", "reason": "CP01 and CP02 cannot be separated without an allocation.",
            },
            {
                "economy_code": "CHN", "original_item_code": "EDUCATION_CULTURE_RECREATION",
                "original_item_name": "Education, culture and recreation", "armilar_category": "CP09|CP10",
                "mapping_type": "ONE_SURVEY_GROUP_TO_MULTIPLE_ARMILAR_CATEGORIES",
                "status": "REJECTED", "reason": "CP09 and CP10 cannot be separated without an allocation.",
            },
        ])
    io = analyses.get("CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF", {})
    if io.get("product_classification"):
        rows.append({
            "economy_code": "CHN", "original_item_code": "INPUT_OUTPUT_PRODUCTS_2020",
            "original_item_name": "NBS 2020 input-output products", "armilar_category": "",
            "mapping_type": "MANY_TO_MANY_PRODUCT_TO_COICOP_REQUIRED",
            "status": "REJECTED", "reason": "The product table is for 2020 and requires an unapproved product-to-purpose allocation.",
        })
    return rows


def china_methodology_gate_rows(
    records: dict[str, AcquisitionRecord] | None = None,
    analyses: dict[str, dict[str, Any]] | None = None,
    errors: dict[str, Exception] | None = None,
) -> list[dict[str, Any]]:
    records = records or {}
    analyses = analyses or {}
    errors = errors or {}

    def source(source_id: str, review_mode: str) -> dict[str, Any]:
        spec = next(spec for spec in ChinaNbsAuditAdapter.source_specs if spec["source_id"] == source_id)
        record = records.get(source_id)
        return {
            "source_id": source_id,
            "source_authority": ChinaNbsAuditAdapter.source_authority,
            "source_url": str(spec["url"]),
            "source_retrieved_at": record.retrieved_at if record else "",
            "source_sha256": record.sha256 if record else "",
            "review_mode": review_mode,
        }

    survey_id = "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION"
    index_id = "CHN_NBS_YEARBOOK_2022_INDEX"
    io_id = "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF"
    gdp_id = "CHN_NBS_2021_GDP_FINAL_VERIFICATION"
    survey = analyses.get(survey_id, {})
    index = analyses.get(index_id, {})
    io = analyses.get(io_id, {})
    gdp = analyses.get(gdp_id, {})

    def blocked(source_id: str) -> bool:
        return source_id in errors

    rows = [
        {
            "criterion": "official_2021_household_survey_available",
            "status": "CONFIRMED" if survey.get("household_survey") and survey.get("reference_2021") else ("NOT_FOUND" if blocked(survey_id) else "AMBIGUOUS"),
            "evidence": "The NBS release reports 2021 household consumption from a national household sample survey." if survey.get("household_survey") else "The 2021 survey source was not structurally confirmed in this run.",
            **source(survey_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "survey_has_twelve_armilar_categories",
            "status": "CONTRADICTED" if survey.get("eight_group_classification") else ("NOT_FOUND" if blocked(survey_id) else "AMBIGUOUS"),
            "evidence": "The survey publishes eight groups, combining food with tobacco and alcohol and combining education with culture and recreation." if survey.get("eight_group_classification") else "The survey classification was not structurally confirmed.",
            **source(survey_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "survey_is_national_accounts_s14_p31",
            "status": "CONTRADICTED" if survey.get("household_survey") else ("NOT_FOUND" if blocked(survey_id) else "AMBIGUOUS"),
            "evidence": "The values are collected through a household income and expenditure survey and cannot be substituted for national-accounts S14/P31 expenditure." if survey.get("household_survey") else "The survey concept was not structurally confirmed.",
            **source(survey_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "yearbook_relevant_table_families_identified",
            "status": "CONFIRMED" if index.get("household_consumption_table_inventory") and index.get("input_output_reference_2020") else ("NOT_FOUND" if blocked(index_id) else "AMBIGUOUS"),
            "evidence": "The 2022 yearbook inventory lists a household-consumption table and 2020 input-output tables." if index.get("household_consumption_table_inventory") else "The yearbook table inventory was not structurally confirmed.",
            **source(index_id, "STRUCTURED_YEARBOOK_INDEX_VALIDATION"),
        },
        {
            "criterion": "input_output_reference_year_matches_2021",
            "status": "CONTRADICTED" if io.get("reference_2020") else ("NOT_FOUND" if blocked(io_id) else "AMBIGUOUS"),
            "evidence": "The input-output benchmark described in the 2022 yearbook is 2020, not 2021." if io.get("reference_2020") else "The input-output reference year was not confirmed.",
            **source(io_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "input_output_is_exact_purpose_classification",
            "status": "CONTRADICTED" if io.get("product_classification") and not io.get("purpose_classification") else ("NOT_FOUND" if blocked(io_id) else "AMBIGUOUS"),
            "evidence": "The input-output source is product-oriented and does not expose a COICOP purpose dimension; conversion would require allocation." if io.get("product_classification") and not io.get("purpose_classification") else "The input-output classification was not conclusively confirmed.",
            **source(io_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "current_price_2021_national_accounts_aggregate_available",
            "status": "CONFIRMED" if gdp.get("reference_2021") and gdp.get("current_prices") else ("NOT_FOUND" if blocked(gdp_id) else "AMBIGUOUS"),
            "evidence": "The final 2021 GDP verification publishes official current-price national-accounts aggregates." if gdp.get("reference_2021") and gdp.get("current_prices") else "The current-price 2021 national-accounts aggregate was not structurally confirmed.",
            **source(gdp_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "twelve_purpose_categories_in_2021_national_accounts",
            "status": "CONTRADICTED" if gdp.get("reference_2021") and not gdp.get("purpose_dimension") and index.get("input_output_reference_2020") else ("NOT_FOUND" if blocked(gdp_id) or blocked(index_id) else "AMBIGUOUS"),
            "evidence": "The acquired 2021 national-accounts publication is aggregate and the yearbook purpose-relevant alternatives do not provide a 2021 twelve-purpose S14 table." if gdp.get("reference_2021") and not gdp.get("purpose_dimension") and index.get("input_output_reference_2020") else "A 2021 twelve-purpose national-accounts table was not conclusively assessed in this run.",
            **source(gdp_id, "CROSS_SOURCE_METHOD_GATE"),
        },
        {
            "criterion": "narcotics_excludable_without_allocation",
            "status": "CONTRADICTED" if survey.get("combined_food_tobacco_alcohol") else ("NOT_FOUND" if blocked(survey_id) else "AMBIGUOUS"),
            "evidence": "The survey combines food, tobacco and alcohol, so CP02 and narcotics cannot be isolated without an allocation." if survey.get("combined_food_tobacco_alcohol") else "Narcotics separability was not confirmed.",
            **source(survey_id, "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "exact_armilar_source_available",
            "status": (
                "CONTRADICTED" if (
                    survey.get("decision") == "REJECT_CLASS_C_EIGHT_GROUP_SURVEY"
                    and index.get("decision") == "DISCOVERY_INVENTORY_ONLY"
                    and io.get("decision") == "REJECT_WRONG_YEAR_PRODUCT_IO"
                    and gdp.get("decision") == "REJECT_AGGREGATE_ONLY"
                ) else "NOT_FOUND" if any(source_id in errors for source_id in ChinaNbsAuditAdapter.core_source_ids)
                else "AMBIGUOUS"
            ),
            "evidence": "The confirmed survey, yearbook, input-output and national-accounts resources each fail at least one exact-matrix gate; none supplies 2021 current-price S14/P31 by twelve purposes without allocation." if (survey.get("decision") == "REJECT_CLASS_C_EIGHT_GROUP_SURVEY" and index.get("decision") == "DISCOVERY_INVENTORY_ONLY" and io.get("decision") == "REJECT_WRONG_YEAR_PRODUCT_IO" and gdp.get("decision") == "REJECT_AGGREGATE_ONLY") else "The complete critical Chinese source chain was not validated in this run.",
            **source(gdp_id, "CROSS_SOURCE_METHOD_GATE"),
        },
    ]
    validate_china_methodology_gate_rows(rows)
    return rows


def validate_china_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    required = {
        "official_2021_household_survey_available",
        "survey_has_twelve_armilar_categories",
        "survey_is_national_accounts_s14_p31",
        "yearbook_relevant_table_families_identified",
        "input_output_reference_year_matches_2021",
        "input_output_is_exact_purpose_classification",
        "current_price_2021_national_accounts_aggregate_available",
        "twelve_purpose_categories_in_2021_national_accounts",
        "narcotics_excludable_without_allocation",
        "exact_armilar_source_available",
    }
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError("China methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - CHINA_GATE_STATUSES)
    if invalid:
        raise ValueError("China methodology audit contains invalid statuses: " + ",".join(invalid))
    if by_criterion["exact_armilar_source_available"]["status"] == "CONTRADICTED":
        if by_criterion["survey_is_national_accounts_s14_p31"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires the survey concept to be rejected")
        if by_criterion["input_output_reference_year_matches_2021"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires the input-output reference-year mismatch to be confirmed")
        if by_criterion["twelve_purpose_categories_in_2021_national_accounts"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires the acquired 2021 national-accounts source to lack the purpose dimension")

def analyse_russia_source(source_id: str, path: Path, content_type: str = "") -> dict[str, Any]:
    if source_id == "RUT_FEDSTAT_HFCE_31414":
        text = _normalise_russian_text(_decode_text_file(path))
        aggregate = "расходы на конечное потребление домашних хозяйств" in text
        current_prices = "текущие цены" in text
        year = "2021" in text
        purpose_dimension = any(token in text for token in ("кипц-дх", "coicop", "по целям", "purpose"))
        return {
            "source_kind": "OFFICIAL_DATABASE_INDICATOR",
            "expected_evidence_confirmed": aggregate and current_prices and year,
            "aggregate_hfce": aggregate,
            "current_prices": current_prices,
            "reference_2021": year,
            "purpose_dimension": purpose_dimension,
            "machine_readable": True,
            "decision": "REJECT_AGGREGATE_ONLY" if aggregate and not purpose_dimension else "REVIEW_REQUIRED",
        }
    if source_id == "RUT_ROSSTAT_SUT_2021_XLSX":
        text = _normalise_russian_text(_office_xml_text(path))
        year = "2021" in text
        sut = any(token in text for token in ("таблиц ресурсов и использования", "таблицы ресурсов и использования", "ресурсы и использование", "supply and use"))
        product = any(token in text for token in ("окпд", "продукт", "товаров и услуг"))
        combined = any(token in text for token in (
            "домашних хозяйств и некоммерческих организаций",
            "домашние хозяйства и нкоодх",
            "households and npish",
        ))
        purpose = any(token in text for token in ("кипц-дх", "coicop", "по целям"))
        return {
            "source_kind": "OFFICIAL_SUPPLY_USE_WORKBOOK",
            "expected_evidence_confirmed": year and sut and product,
            "reference_2021": year,
            "supply_use_table": sut,
            "product_classification": product,
            "households_npish_combined_marker": combined,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_ALLOCATION_REQUIRED" if year and sut and product and not purpose else "REVIEW_REQUIRED",
        }
    if source_id == "RUT_ROSSTAT_HBS_2021":
        text = _normalise_russian_text(_decode_text_file(path))
        hbs = any(token in text for token in (
            "доходы, расходы и потребление домашних хозяйств",
            "обследован", "бюджет", "household budget",
        ))
        purpose = any(token in text for token in ("кипц-дх", "классификатор индивидуального потребления", "coicop"))
        year = "2021" in text
        return {
            "source_kind": "OFFICIAL_HOUSEHOLD_SURVEY",
            "expected_evidence_confirmed": hbs and purpose and year,
            "household_survey": hbs,
            "purpose_classification": purpose,
            "reference_2021": year,
            "machine_readable": True,
            "decision": "REJECT_CLASS_C_SURVEY" if hbs and purpose and year else "REVIEW_REQUIRED",
        }
    if source_id == "RUT_ROSSTAT_KIPC_DH_CLASSIFICATION":
        text = _normalise_russian_text(_office_xml_text(path))
        classification = any(token in text for token in ("кипц-дх", "классификатор индивидуального потребления"))
        return {
            "source_kind": "OFFICIAL_CLASSIFICATION_DOCUMENT",
            "expected_evidence_confirmed": classification,
            "classification_document": classification,
            "machine_readable": True,
            "decision": "DOCUMENTATION_ONLY" if classification else "REVIEW_REQUIRED",
        }
    if source_id == "RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022":
        signature = path.read_bytes()[:5]
        valid_pdf = signature == b"%PDF-"
        return {
            "source_kind": "OFFICIAL_PUBLICATION_PDF",
            "expected_evidence_confirmed": valid_pdf,
            "valid_pdf_signature": valid_pdf,
            "machine_readable": False,
            "decision": "SOURCE_NOT_MACHINE_READABLE" if valid_pdf else "REVIEW_REQUIRED",
        }
    raise ValueError(f"Unknown Russian source id: {source_id}")


def russia_source_attempt_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in RussiaRosstatAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        row = step2i_attempt_template(
            "RUT", "*", RussiaRosstatAuditAdapter.source_authority,
            source_id, str(spec["url"]), "2021", str(spec["concept"]),
            str(spec["classification"]), rejection_reason,
        )
        if source_id in errors:
            row.update({
                "retrieval_status": "ACCESS_BLOCKED",
                "candidate_class": "ACCESS_BLOCKED",
                "retrieved_at": "ACQUISITION_FAILED_NO_RAW_FILE",
                "rejection_reason": f"{type(errors[source_id]).__name__}: {errors[source_id]}",
            })
        else:
            record = records[source_id]
            analysis = analyses[source_id]
            signature = {
                ".xlsx": "XLSX_ZIP_CONTAINER",
                ".docx": "DOCX_ZIP_CONTAINER",
                ".pdf": "PDF_SIGNATURE",
                ".html": "HTML_DOCUMENT",
            }.get(Path(str(spec["filename"])).suffix.lower(), "BINARY_CONTENT")
            decision = str(analysis.get("decision") or "REVIEW_REQUIRED")
            retrieval = {
                "REJECT_AGGREGATE_ONLY": "ACQUIRED_AGGREGATE_ONLY",
                "REJECT_ALLOCATION_REQUIRED": "ACQUIRED_REJECTED_ALLOCATION_REQUIRED",
                "REJECT_CLASS_C_SURVEY": "ACQUIRED_CLASS_C_SURVEY",
                "DOCUMENTATION_ONLY": "ACQUIRED_DOCUMENTATION_ONLY",
                "SOURCE_NOT_MACHINE_READABLE": "ACQUIRED_NOT_MACHINE_READABLE",
            }.get(decision, "ACQUIRED_REVIEW_REQUIRED")
            row.update({
                "retrieval_status": retrieval,
                "status_code": record.status_code or "",
                "content_type": record.content_type or "",
                "file_signature": signature,
                "byte_size": record.bytes,
                "retrieved_at": record.retrieved_at,
                "sha256": record.sha256,
                "candidate_class": (
                    "CONCEPT_AMBIGUOUS" if decision == "REVIEW_REQUIRED"
                    else "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
                ),
            })
            if source_id == "RUT_FEDSTAT_HFCE_31414":
                row.update({
                    "institutional_sector": "HOUSEHOLDS_S14_AGGREGATE",
                    "transaction_code": "P31DC_AGGREGATE",
                    "classification": "NO_PURPOSE_DIMENSION",
                    "current_prices": "CONFIRMED" if analysis.get("current_prices") else "NOT_CONFIRMED",
                    "currency": "RUB",
                    "unit": "OFFICIAL_INDICATOR_UNIT_REQUIRES_RUNTIME_METADATA",
                    "npish_treatment": "AGGREGATE_HOUSEHOLD_INDICATOR",
                    "government_treatment": "EXCLUDED_FROM_HOUSEHOLD_AGGREGATE",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_CATEGORY_LEVEL",
                })
            elif source_id == "RUT_ROSSTAT_SUT_2021_XLSX":
                row.update({
                    "institutional_sector": "HOUSEHOLDS_SCOPE_NOT_PROVEN_AT_PURPOSE_LEVEL",
                    "transaction_code": "FINAL_CONSUMPTION_IN_SUT",
                    "classification": "PRODUCT_CLASSIFICATION_REQUIRES_BRIDGE",
                    "current_prices": "OFFICIAL_SUT_CURRENT_PRICE_TABLE_FAMILY",
                    "currency": "RUB",
                    "unit": "WORKBOOK_METADATA_REQUIRED",
                    "npish_treatment": (
                        "COMBINED_MARKER_FOUND" if analysis.get("households_npish_combined_marker")
                        else "NOT_CONFIRMED_EXCLUDED"
                    ),
                    "government_treatment": "SEPARATE_USE_COLUMNS_EXPECTED_NOT_CATEGORY_GATE",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_CATEGORY_LEVEL",
                })
            elif source_id == "RUT_ROSSTAT_HBS_2021":
                row.update({
                    "institutional_sector": "HOUSEHOLD_SURVEY_RESPONDENTS",
                    "transaction_code": "SURVEY_CONSUMER_EXPENDITURE_NOT_P31DC",
                    "classification": "KIPC_DH_SURVEY",
                    "current_prices": "SURVEY_EXPENDITURE_VALUES_OR_SHARES",
                    "currency": "RUB",
                    "unit": "SURVEY_PUBLICATION_UNIT",
                    "npish_treatment": "OUTSIDE_SURVEY_CONCEPT",
                    "government_treatment": "OUTSIDE_SURVEY_CONCEPT",
                    "imputed_rent_treatment": "NOT_PROVEN_EQUIVALENT_TO_SNA",
                })
            else:
                row.update({
                    "institutional_sector": "DOCUMENTATION_ONLY",
                    "transaction_code": "NOT_A_DATASET",
                    "current_prices": "NOT_APPLICABLE",
                    "currency": "NOT_APPLICABLE",
                    "unit": "NOT_APPLICABLE",
                    "npish_treatment": "DOCUMENTATION_ONLY",
                    "government_treatment": "DOCUMENTATION_ONLY",
                    "imputed_rent_treatment": "DOCUMENTATION_ONLY",
                })
        rows.append(row)
    return expand_attempt_categories(rows)


def russia_evidence_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in RussiaRosstatAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        if source_id in errors:
            status = "ACCESS_BLOCKED"
            machine = "unknown_this_run"
            reason = f"{type(errors[source_id]).__name__}: {errors[source_id]}"
        else:
            decision = str(analyses[source_id].get("decision") or "REVIEW_REQUIRED")
            status = "ACQUIRED_BUT_REJECTED" if decision.startswith("REJECT_") else decision
            machine = str(bool(analyses[source_id].get("machine_readable"))).lower()
            reason = rejection_reason
        rows.append({
            "economy_code": "RUT",
            "source_id": source_id,
            "source_authority": RussiaRosstatAuditAdapter.source_authority,
            "source_url": str(spec["url"]),
            "reference_period": "2021",
            "concept": str(spec["concept"]),
            "granularity": str(spec["classification"]),
            "machine_readable": machine,
            "status": status,
            "rejection_reason": reason,
        })
    return rows


def russia_mapping_audit_rows(analyses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if analyses.get("RUT_ROSSTAT_SUT_2021_XLSX", {}).get("product_classification"):
        rows.append({
            "economy_code": "RUT",
            "original_item_code": "SUT_PRODUCTS",
            "original_item_name": "Rosstat 2021 supply-use products",
            "armilar_category": "",
            "mapping_type": "MANY_TO_MANY_PRODUCT_TO_COICOP_REQUIRED",
            "status": "REJECTED",
            "reason": "Exact Armilar weights cannot be created through an unapproved product-to-purpose allocation.",
        })
    if analyses.get("RUT_ROSSTAT_HBS_2021", {}).get("purpose_classification"):
        rows.append({
            "economy_code": "RUT",
            "original_item_code": "KIPC_DH",
            "original_item_name": "Household survey expenditure by purpose",
            "armilar_category": "CP01-CP12",
            "mapping_type": "CLASSIFICATION_COMPATIBLE_CONCEPT_INCOMPATIBLE",
            "status": "REJECTED",
            "reason": "Purpose classification does not convert a household survey into S14/P31DC national-accounts expenditure.",
        })
    return rows


def russia_methodology_gate_rows(
    records: dict[str, AcquisitionRecord] | None = None,
    analyses: dict[str, dict[str, Any]] | None = None,
    errors: dict[str, Exception] | None = None,
) -> list[dict[str, Any]]:
    records = records or {}
    analyses = analyses or {}
    errors = errors or {}

    def source(source_id: str, review_mode: str) -> dict[str, Any]:
        spec = next(spec for spec in RussiaRosstatAuditAdapter.source_specs if spec["source_id"] == source_id)
        record = records.get(source_id)
        return {
            "source_id": source_id,
            "source_authority": RussiaRosstatAuditAdapter.source_authority,
            "source_url": str(spec["url"]),
            "source_retrieved_at": record.retrieved_at if record else "",
            "source_sha256": record.sha256 if record else "",
            "review_mode": review_mode,
        }

    fedstat = analyses.get("RUT_FEDSTAT_HFCE_31414", {})
    sut = analyses.get("RUT_ROSSTAT_SUT_2021_XLSX", {})
    hbs = analyses.get("RUT_ROSSTAT_HBS_2021", {})
    fedstat_blocked = "RUT_FEDSTAT_HFCE_31414" in errors
    sut_blocked = "RUT_ROSSTAT_SUT_2021_XLSX" in errors
    hbs_blocked = "RUT_ROSSTAT_HBS_2021" in errors

    rows = [
        {
            "criterion": "aggregate_household_hfce_available",
            "status": "CONFIRMED" if fedstat.get("aggregate_hfce") else ("NOT_FOUND" if fedstat_blocked else "AMBIGUOUS"),
            "evidence": "Fedstat indicator 31414 identifies household final consumption expenditure at aggregate level." if fedstat.get("aggregate_hfce") else "The aggregate Fedstat source was not acquired and structurally confirmed in this run.",
            **source("RUT_FEDSTAT_HFCE_31414", "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "current_prices_2021_available_at_aggregate",
            "status": "CONFIRMED" if fedstat.get("current_prices") and fedstat.get("reference_2021") else ("NOT_FOUND" if fedstat_blocked else "AMBIGUOUS"),
            "evidence": "The Fedstat indicator exposes current prices and 2021 among its official dimensions." if fedstat.get("current_prices") and fedstat.get("reference_2021") else "Current-price 2021 aggregate evidence was not structurally confirmed in this run.",
            **source("RUT_FEDSTAT_HFCE_31414", "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "twelve_purpose_categories_in_national_accounts",
            "status": "CONTRADICTED" if fedstat.get("aggregate_hfce") and not fedstat.get("purpose_dimension") else ("NOT_FOUND" if fedstat_blocked else "AMBIGUOUS"),
            "evidence": "Fedstat indicator 31414 has aggregate, price-type, territory and period dimensions but no KIPC-DH/COICOP purpose dimension." if fedstat.get("aggregate_hfce") and not fedstat.get("purpose_dimension") else "The existence of a twelve-purpose national-accounts dimension was not confirmed.",
            **source("RUT_FEDSTAT_HFCE_31414", "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "sut_is_exact_purpose_classification",
            "status": "CONTRADICTED" if sut.get("product_classification") and not sut.get("purpose_classification") else ("NOT_FOUND" if sut_blocked else "AMBIGUOUS"),
            "evidence": "The 2021 SUT workbook is structured by products; converting it to COICOP purposes would require an allocation bridge." if sut.get("product_classification") and not sut.get("purpose_classification") else "The SUT classification could not be conclusively assessed in this run.",
            **source("RUT_ROSSTAT_SUT_2021_XLSX", "STRUCTURED_XLSX_TEXT_INVENTORY"),
        },
        {
            "criterion": "npish_excluded_at_required_category_level",
            "status": "CONTRADICTED" if sut.get("households_npish_combined_marker") else ("NOT_FOUND" if sut_blocked else "AMBIGUOUS"),
            "evidence": "The SUT text inventory contains a combined households-and-NPISH final-consumption marker, so strict S14 exclusion is not proven at category level." if sut.get("households_npish_combined_marker") else "No category-level NPISH exclusion was confirmed.",
            **source("RUT_ROSSTAT_SUT_2021_XLSX", "STRUCTURED_XLSX_TEXT_INVENTORY"),
        },
        {
            "criterion": "purpose_detail_available_in_household_survey",
            "status": "CONFIRMED" if hbs.get("household_survey") and hbs.get("purpose_classification") else ("NOT_FOUND" if hbs_blocked else "AMBIGUOUS"),
            "evidence": "Rosstat household-budget results expose purpose detail using KIPC-DH." if hbs.get("household_survey") and hbs.get("purpose_classification") else "KIPC-DH survey detail was not structurally confirmed in this run.",
            **source("RUT_ROSSTAT_HBS_2021", "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "household_survey_is_national_accounts_p31dc",
            "status": "CONTRADICTED" if hbs.get("household_survey") else ("NOT_FOUND" if hbs_blocked else "AMBIGUOUS"),
            "evidence": "The KIPC-DH publication is household-survey evidence and cannot substitute for national-accounts S14/P31DC values." if hbs.get("household_survey") else "The survey concept was not structurally confirmed in this run.",
            **source("RUT_ROSSTAT_HBS_2021", "STRUCTURED_HTML_MARKER_VALIDATION"),
        },
        {
            "criterion": "exact_armilar_source_available",
            "status": (
                "CONTRADICTED" if (
                    fedstat.get("decision") == "REJECT_AGGREGATE_ONLY"
                    and sut.get("decision") == "REJECT_ALLOCATION_REQUIRED"
                    and hbs.get("decision") == "REJECT_CLASS_C_SURVEY"
                )
                else "NOT_FOUND" if any(source_id in errors for source_id in RussiaRosstatAuditAdapter.core_source_ids)
                else "AMBIGUOUS"
            ),
            "evidence": "The confirmed aggregate, SUT and survey sources each fail a distinct exact-matrix gate; none supplies 2021 current-price S14/P31DC by twelve purposes without allocation." if (fedstat.get("decision") == "REJECT_AGGREGATE_ONLY" and sut.get("decision") == "REJECT_ALLOCATION_REQUIRED" and hbs.get("decision") == "REJECT_CLASS_C_SURVEY") else "The complete critical source chain was not validated in this run.",
            **source("RUT_FEDSTAT_HFCE_31414", "CROSS_SOURCE_METHOD_GATE"),
        },
    ]
    validate_russia_methodology_gate_rows(rows)
    return rows


def validate_russia_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    required = {
        "aggregate_household_hfce_available",
        "current_prices_2021_available_at_aggregate",
        "twelve_purpose_categories_in_national_accounts",
        "sut_is_exact_purpose_classification",
        "npish_excluded_at_required_category_level",
        "purpose_detail_available_in_household_survey",
        "household_survey_is_national_accounts_p31dc",
        "exact_armilar_source_available",
    }
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError("Russia methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - RUSSIA_GATE_STATUSES)
    if invalid:
        raise ValueError("Russia methodology audit contains invalid statuses: " + ",".join(invalid))
    if by_criterion["exact_armilar_source_available"]["status"] == "CONTRADICTED":
        if by_criterion["twelve_purpose_categories_in_national_accounts"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires confirmed absence of a purpose dimension in the aggregate source")
        if by_criterion["household_survey_is_national_accounts_p31dc"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires the survey concept to be rejected")

def india_methodology_gate_rows(
    *,
    workbook_record: AcquisitionRecord | None = None,
    methodology_record: AcquisitionRecord | None = None,
    methodology_reviewed: bool = True,
) -> list[dict[str, Any]]:
    workbook_source = {
        "source_id": IndiaMospiAdapter.adapter_id,
        "source_authority": IndiaMospiAdapter.source_authority,
        "source_url": IndiaMospiAdapter.source_url,
        "evidence_location": "Statement 5.1 header and current-price 2021-22 column",
        "source_retrieved_at": workbook_record.retrieved_at if workbook_record else "",
        "source_sha256": workbook_record.sha256 if workbook_record else "",
        "review_mode": "STRUCTURED_WORKBOOK_VALIDATION",
    }
    methodology_source = {
        "source_id": IndiaMospiAdapter.methodology_source_id,
        "source_authority": IndiaMospiAdapter.source_authority,
        "source_url": IndiaMospiAdapter.methodology_url,
        "evidence_location": IndiaMospiAdapter.methodology_location,
        "source_retrieved_at": methodology_record.retrieved_at if methodology_record else "",
        "source_sha256": methodology_record.sha256 if methodology_record else "",
        "review_mode": "MANUAL_OFFICIAL_DOCUMENT_REVIEW" if methodology_reviewed else "HASH_CHANGE_REVIEW_REQUIRED",
    }
    methodology_available = methodology_record is not None and methodology_reviewed
    rows = [
        {
            "criterion": "represents_households_S14",
            "status": "CONTRADICTED" if methodology_available else "AMBIGUOUS",
            "evidence": (
                "MoSPI defines PFCE as expenditure of resident households and NPISH and says the two are estimated together and are not available separately."
                if methodology_available else
                "The workbook alone does not prove a strict S14-only boundary."
            ),
            **(methodology_source if methodology_available else workbook_source),
        },
        {
            "criterion": "corresponds_to_P31_HFCE",
            "status": "CONTRADICTED" if methodology_available else "AMBIGUOUS",
            "evidence": (
                "The source is a P31-type final-consumption measure for households and NPISH combined, not strict household S14 HFCE/P31DC."
                if methodology_available else
                "The workbook title establishes PFCE but does not prove strict S14/P31DC compatibility."
            ),
            **(methodology_source if methodology_available else workbook_source),
        },
        {
            "criterion": "excludes_NPISH",
            "status": "CONTRADICTED" if methodology_available else "NOT_FOUND",
            "evidence": (
                "Official methodology explicitly includes NPISH and states that household and NPISH final consumption are not separately available."
                if methodology_available else
                "No NPISH exclusion statement is present in the workbook."
            ),
            **(methodology_source if methodology_available else workbook_source),
        },
        {
            "criterion": "excludes_government_consumption",
            "status": "CONFIRMED" if methodology_available else "AMBIGUOUS",
            "evidence": (
                "The commodity-flow method deducts consumption on government account and other final uses outside households and NPISH."
                if methodology_available else
                "The workbook is labelled private final consumption but the detailed method was not acquired in this run."
            ),
            **(methodology_source if methodology_available else workbook_source),
        },
        {
            "criterion": "includes_imputed_rent",
            "status": "CONFIRMED",
            "evidence": (
                "Official methodology includes imputed gross rent of owner-occupied dwellings."
                if methodology_available else
                "The workbook contains gross rentals for housing, including the housing rent component."
            ),
            **(methodology_source if methodology_available else workbook_source),
        },
        {
            "criterion": "narcotics_separable",
            "status": "CONFIRMED",
            "evidence": "Statement 5.1 exposes alcohol, tobacco and narcotics as separate item codes 2.1, 2.2 and 2.3.",
            **workbook_source,
        },
        {
            "criterion": "current_prices",
            "status": "CONFIRMED",
            "evidence": "The workbook has an explicit current-price block in INR crore.",
            **workbook_source,
        },
        {
            "criterion": "reference_period_2021_22_available",
            "status": "CONFIRMED",
            "evidence": "The workbook exposes fiscal year 2021-22 and the adapter preserves that label.",
            **workbook_source,
        },
        {
            "criterion": "compatible_with_armilar_calendar_2021",
            "status": "CONTRADICTED",
            "evidence": "Fiscal year 2021-22 is not calendar year 2021; no interpolation or silent temporal conversion is permitted.",
            **workbook_source,
        },
    ]
    validate_india_methodology_gate_rows(rows)
    return rows


def validate_india_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    required = {
        "represents_households_S14", "corresponds_to_P31_HFCE", "excludes_NPISH",
        "excludes_government_consumption", "includes_imputed_rent", "narcotics_separable",
        "current_prices", "reference_period_2021_22_available",
        "compatible_with_armilar_calendar_2021",
    }
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError("India methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - INDIA_GATE_STATUSES)
    if invalid:
        raise ValueError("India methodology audit contains invalid statuses: " + ",".join(invalid))
    if by_criterion["excludes_NPISH"]["status"] == "CONTRADICTED":
        if by_criterion["represents_households_S14"]["status"] != "CONTRADICTED":
            raise ValueError("NPISH inclusion must contradict the strict S14 criterion")


def step2h_exception_rows() -> list[dict[str, Any]]:
    return [
        {"economy_code": "BLR", "economy_name": "Belarus", "armilar_category": "CP02", "decision": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "CP02 cannot be reconstructed without both alcohol and tobacco strict HFCE cells or an official narcotics-excluding aggregate."},
        {"economy_code": "KWT", "economy_name": "Kuwait", "armilar_category": "CP02", "decision": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "No modelled alcohol/tobacco split is allowed."},
        {"economy_code": "SAU", "economy_name": "Saudi Arabia", "armilar_category": "CP02", "decision": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "No modelled alcohol/tobacco split is allowed."},
        {"economy_code": "BON", "economy_name": "Bonaire", "armilar_category": "*", "decision": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "current_status": "0/12 categories available", "resolution_attempted": "Participant registry and Source 90 cells audited.", "reason": "No public official twelve-category allocation or proxy-numerator source accepted."},
        {"economy_code": "LBR", "economy_name": "Liberia", "armilar_category": "CP04|CP06|CP09|CP10|CP12", "decision": "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "current_status": "SUPPLEMENTAL_NOMINAL_SOURCE_FAILED_UNIT_RECONCILIATION", "resolution_attempted": "UNData supplemental source compared against direct Source 90 categories.", "reason": "Median supplemental-to-Source90 ratio is incompatible; using it would risk a unit or concept error."},
    ]


def step2i_completion_summary(result: AdapterResult) -> dict[str, Any]:
    rows = result.completion_rows or []
    by_code = {row["economy_code"]: row for row in rows if row["economy_code"] in STEP2I_ECONOMIES}
    non_admissible_cells = len([
        row for row in (result.cell_status_rows or [])
        if row.get("admissible_to_exact_matrix") in {False, "False", "false"}
    ])
    return {
        "schema_version": "1.1",
        "pipeline_version": "0.6.8",
        "step": "2I",
        "status": "DIAGNOSTIC_INFRASTRUCTURE_COMPLETE_SOURCE_AUDIT_ONGOING",
        "status_label": "Step 2I diagnostic infrastructure complete; source audit ongoing",
        "economies_required": list(STEP2I_ECONOMIES),
        "economies_decided": sorted(by_code),
        "accepted_cells_added_to_exact_matrix": 0,
        "experimental_cells": 0,
        "non_admissible_cells": non_admissible_cells,
        "unavailable_after_exhaustive_audit_cells": 0,
        "weights_final_remains_empty": True,
        "monetary_release_allowed": False,
        "global_12_category_matrix_complete": False,
        "step2j_started": False,
        "summary_by_economy": by_code,
        "step2h_exceptions": step2h_exception_rows(),
    }


def step2i_audit_summary(result: AdapterResult) -> dict[str, Any]:
    summary = step2i_completion_summary(result)
    attempts = result.source_attempt_rows or []
    acquired = [row for row in attempts if row.get("sha256")]
    blocked = [row for row in attempts if row.get("retrieval_status") == "ACCESS_BLOCKED"]
    ambiguous = [row for row in (result.cell_status_rows or []) if row.get("cell_class") == "CONCEPT_AMBIGUOUS"]
    return {
        **summary,
        "audit_outputs": {
            "country_source_attempts": len(attempts),
            "country_source_family_coverage": len(result.source_family_rows or []),
            "country_source_evidence": len(result.evidence_rows or []),
        },
        "sources_acquired_with_hash": len(acquired),
        "access_blocked_attempts": len(blocked),
        "concept_ambiguous_cells": len(ambiguous),
        "final_unavailability_used": False,
        "methodological_states": list(METHODOLOGICAL_STATES),
    }


def write_step2i_report(path: Path, result: AdapterResult) -> None:
    _write_step2i_report_common(path, result, title="Step 2I audit report")


def write_step2i_audit_report(path: Path, result: AdapterResult) -> None:
    _write_step2i_report_common(path, result, title="Step 2I corrective audit report")


def _write_step2i_report_common(path: Path, result: AdapterResult, *, title: str) -> None:
    summary = step2i_completion_summary(result)
    lines = [
        f"# {title}",
        "",
        "Generated: deterministic v0.6.13 Step 2I report",
        "",
        "## Version mapping",
        "",
        "| Version | Project step | Meaning |",
        "|---|---|---|",
        "| 0.4.0 | Step 2H | Gap resolver and source probe |",
        "| 0.5.0 | Step 2I start | National adapter architecture and first audits |",
        "| 0.6.0 | Step 2I infrastructure | Initial diagnostic closure, now treated as over-certain |",
        "| 0.6.1 | Step 2I corrective audit | Diagnostic infrastructure complete; source audit ongoing |",
        "| 0.6.2 | Step 2H0 hardening | Dataset/discovery separation and direct PPP proxy audit |",
        "| 0.6.3 | Step 2H0 India evidence closure | India documentary rejection and evidence-linked methodology gates |",
        "| 0.6.4 | Step 2H0 Russia evidence closure | Fedstat aggregate, SUT product and HBS purpose concepts separated |",
        "| 0.6.5 | Step 2H0 China evidence closure | Survey, yearbook, input-output and GDP aggregate concepts separated |",
        "| 0.6.6 | Step 2H0 Indonesia audit | Grouped BPS, SUT, input-output and Class C concepts separated |",
        "| 0.6.7 | Step 2H0 Brazil audit | SIDRA, SCN, CEI, TRU and Class C concepts separated |",
        "| 0.6.8 | Step 2H0 Egypt audit | CAPMAS catalogue, historical SUT and HIECS concepts separated |",
        "| 0.6.9 | Step 2H0 Pakistan audit | PBS aggregate national accounts, fiscal period and HIES survey concepts separated |",
        "| 0.6.10 | Step 2H0 Nigeria audit | NBS aggregate expenditure reports and 2019 survey detail separated |",
        "| 0.6.11 | Step 2H0 Bangladesh audit | BBS aggregate portals and HIES 2022 survey evidence separated |",
        "| 0.6.12 | Step 2H0 Viet Nam audit | NSO aggregate final-consumption releases and VHLSS surveys separated |",
        "| 0.6.13 | Step 2H exception audits | Belarus, Kuwait, Saudi Arabia, Bonaire and Liberia exceptions made executable |",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status_label']}`",
        "- No economy is marked `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.",
        "- `weights_final.csv` remains empty.",
        "- Step 2J has not been started.",
        "",
        "## Step 2I decisions",
        "",
    ]
    for row in result.completion_rows or []:
        if row["economy_code"] not in STEP2I_ECONOMIES:
            continue
        lines.append(
            f"- {row['economy_code']} {row['economy_name']}: decision `{row['decision']}`, "
            f"accepted `{row['accepted_categories'] or 'none'}`, non-admissible `{row['unavailable_categories']}`. "
            f"Blocker: {row['remaining_blockers']}"
        )
    lines.extend([
        "",
        "## Coverage",
        "",
        f"- Exact cells added: `{summary['accepted_cells_added_to_exact_matrix']}`",
        "- Coverage change: `0` complete economies; all gates remain fail-closed.",
        "",
        "## Source-family coverage",
        "",
    ])
    for row in result.source_family_rows or []:
        if row["economy_code"] in STEP2I_ECONOMIES and row["attempts_recorded"]:
            lines.append(f"- {row['economy_code']} `{row['source_family']}`: {row['attempts_recorded']} attempt(s), best status `{row['best_status']}`.")
    lines.extend(["", "## Step 2H exceptions", ""])
    for row in step2h_exception_rows():
        lines.append(f"- {row['economy_code']} {row['armilar_category']}: `{row['decision']}` - {row['reason']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def write_india_method_gate_report(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        validate_india_methodology_gate_rows(rows)
    lines = [
        "# India method gate report",
        "",
        "Pipeline version: `0.6.8`",
        "",
        "This report records the strict Armilar admissibility decision for MoSPI PFCE Statement 5.1.",
        "The source remains outside the exact matrix whenever a material criterion is contradicted or unresolved.",
        "",
        "| Criterion | Status | Evidence source | Evidence |",
        "|---|---|---|---|",
    ]
    for row in rows:
        source = str(row.get("source_id") or "")
        evidence = str(row.get("evidence") or "").replace("|", "\\|")
        lines.append(f"| `{row.get('criterion', '')}` | `{row.get('status', '')}` | `{source}` | {evidence} |")
    if not rows:
        lines.append("| No gate evidence acquired in this run | `NOT_FOUND` |  |  |")
    lines.extend([
        "",
        "## Decision",
        "",
        "MoSPI PFCE cannot enter the strict exact matrix because the official methodology combines resident households and NPISH, while Statement 5.1 reports fiscal 2021-22 rather than calendar 2021.",
        "No NPISH allocation or calendar-year interpolation is permitted.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_russia_method_gate_report(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        validate_russia_methodology_gate_rows(rows)
    lines = [
        "# Russia method gate report",
        "",
        "Pipeline version: `0.6.8`",
        "",
        "This report records the strict Armilar admissibility decision for the official Rosstat and Fedstat source chain.",
        "An aggregate national-accounts indicator, product-based SUT data and purpose-classified survey data are kept conceptually separate.",
        "",
        "| Criterion | Status | Evidence source | Evidence |",
        "|---|---|---|---|",
    ]
    for row in rows:
        source = str(row.get("source_id") or "")
        evidence = str(row.get("evidence") or "").replace("|", "\\|")
        lines.append(f"| `{row.get('criterion', '')}` | `{row.get('status', '')}` | `{source}` | {evidence} |")
    if not rows:
        lines.append("| No gate evidence acquired in this run | `NOT_FOUND` |  |  |")
    lines.extend([
        "",
        "## Decision",
        "",
        "No Russian source is admitted to the strict exact matrix in this probe.",
        "Fedstat indicator 31414 is aggregate-only, the 2021 SUT workbook requires a product-to-purpose allocation, and KIPC-DH purpose detail comes from a household survey rather than S14/P31DC national accounts.",
        "No product allocation, survey-share substitution or NPISH assumption is permitted.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_china_method_gate_report(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        validate_china_methodology_gate_rows(rows)
    lines = [
        "# China method gate report",
        "",
        "Pipeline version: `0.6.8`",
        "",
        "This report records the strict Armilar admissibility decision for the official NBS source chain.",
        "Household-survey detail, national-accounts aggregates and input-output product tables remain conceptually separate.",
        "",
        "| Criterion | Status | Evidence source | Evidence |",
        "|---|---|---|---|",
    ]
    for row in rows:
        source = str(row.get("source_id") or "")
        evidence = str(row.get("evidence") or "").replace("|", "\\|")
        lines.append(f"| `{row.get('criterion', '')}` | `{row.get('status', '')}` | `{source}` | {evidence} |")
    if not rows:
        lines.append("| No gate evidence acquired in this run | `NOT_FOUND` |  |  |")
    lines.extend([
        "", "## Decision", "",
        "No Chinese source is admitted to the strict exact matrix in this probe.",
        "The eight-group household survey is not national-accounts S14/P31 and combines Armilar categories; the yearbook input-output benchmark is 2020 and product-based; the acquired 2021 national-accounts publication is aggregate.",
        "No survey-share split, product allocation, narcotics estimate or temporal substitution is permitted.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def classify_cell(row: dict[str, Any]) -> str:
    data_class = str(row.get("data_class") or "")
    quality = set(str(row.get("quality_flags") or "").split("|"))
    if data_class in {"EXACT_OFFICIAL", "OFFICIAL_EXACT_DERIVATION", "OFFICIAL_DERIVED_NO_ALLOCATION"}:
        if "EXPERIMENTAL_ALLOCATION" in quality:
            return "OFFICIAL_EXPERIMENTAL_ALLOCATION"
        if "NO_ALLOCATION" in quality or str(row.get("derivation_method", "")).startswith("OFFICIAL"):
            return "OFFICIAL_DERIVED_NO_ALLOCATION"
        return "EXACT_OFFICIAL"
    if data_class == "EXPERIMENTAL_ALLOCATION":
        return "OFFICIAL_EXPERIMENTAL_ALLOCATION"
    if data_class in METHODOLOGICAL_STATES:
        return data_class
    return "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"


def validate_mixed_provider_cells(rows: list[dict[str, Any]]) -> tuple[bool, str]:
    if not rows:
        return False, "NO_ROWS"
    seen: set[str] = set()
    reference_periods: set[str] = set()
    currencies: set[str] = set()
    units: set[str] = set()
    for row in rows:
        category = str(row.get("armilar_category") or "")
        if not category:
            return False, "MISSING_CATEGORY"
        if category in seen:
            return False, f"DUPLICATE_CATEGORY:{category}"
        seen.add(category)
        reference_periods.add(str(row.get("reference_period") or ""))
        currencies.add(str(row.get("currency") or ""))
        units.add(str(row.get("unit") or ""))
        if str(row.get("sector")) != "S14":
            return False, "INCOMPATIBLE_SECTOR"
        if str(row.get("transaction")) != "P31DC":
            return False, "INCOMPATIBLE_TRANSACTION"
        if str(row.get("data_class")) not in {"EXACT_OFFICIAL", "OFFICIAL_EXACT_DERIVATION", "OFFICIAL_DERIVED_NO_ALLOCATION"}:
            return False, "INCOMPATIBLE_DATA_CLASS"
        flags = set(str(row.get("quality_flags") or "").split("|"))
        required = {"CURRENT_PRICES", "NPISH_EXCLUDED", "GOVERNMENT_EXCLUDED", "NO_ALLOCATION"}
        missing = required - flags
        if missing:
            return False, "MISSING_QUALITY_FLAGS:" + "|".join(sorted(missing))
        for field in ("source_authority", "source_file", "source_url", "source_hash"):
            if not row.get(field):
                return False, f"MISSING_PROVENANCE:{field}"
    if len(reference_periods) != 1:
        return False, "INCOMPATIBLE_REFERENCE_PERIOD"
    if len(currencies) != 1:
        return False, "INCOMPATIBLE_CURRENCY"
    if len(units) != 1:
        return False, "INCOMPATIBLE_UNIT"
    return True, "PASS"

# ---------------------------------------------------------------------------
# Reusable Step 2H0 official source-family audits (v0.6.6+)
# ---------------------------------------------------------------------------

ALL_ARMILAR_CATEGORIES = tuple(f"CP{number:02d}" for number in range(1, 13))


def _normalise_audit_text(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _file_signature(path: Path) -> str:
    payload = path.read_bytes()[:8]
    if payload.startswith(b"%PDF"):
        return "PDF"
    if payload.startswith(b"PK\x03\x04"):
        return "ZIP_OR_OOXML"
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "CSV_TEXT"
    if suffix in {".html", ".htm"}:
        return "HTML_TEXT"
    return suffix.lstrip(".").upper() or "BINARY"


def _analyse_source_spec(spec: dict[str, Any], path: Path, content_type: str = "") -> dict[str, Any]:
    if path.suffix.lower() in {".xlsx", ".xlsm", ".docx"} and zipfile.is_zipfile(path):
        source_text = _office_xml_text(path)
    else:
        source_text = _decode_text_file(path)
    text = _normalise_audit_text(source_text)
    markers = tuple(_normalise_audit_text(str(marker)) for marker in spec.get("required_markers", ()))
    marker_hits = {marker: marker in text for marker in markers}
    expected = all(marker_hits.values()) if markers else path.exists() and path.stat().st_size > 0
    return {
        "source_id": str(spec["source_id"]),
        "expected_evidence_confirmed": expected,
        "marker_hits": marker_hits,
        "decision": str(spec.get("source_decision") or "REJECT_NON_EXACT_SOURCE_FAMILY"),
        "concept": str(spec.get("concept") or ""),
        "classification": str(spec.get("classification") or ""),
        "source_family": str(spec.get("family") or "official_structured_publications"),
        "content_type": content_type,
        "file_signature": _file_signature(path),
        "machine_readable": str(spec.get("machine_readable") or "partly"),
        "reference_period": str(spec.get("reference_period") or "2021"),
        "institutional_sector": str(spec.get("institutional_sector") or "NOT_CONFIRMED_AS_STRICT_S14"),
        "transaction_code": str(spec.get("transaction_code") or "NOT_CONFIRMED_AS_P31DC"),
        "current_prices": str(spec.get("current_prices") or "UNKNOWN"),
        "currency": str(spec.get("currency") or "UNKNOWN"),
        "unit": str(spec.get("unit") or "UNKNOWN"),
        "npish_treatment": str(spec.get("npish_treatment") or "NOT_CONFIRMED_EXCLUDED"),
        "government_treatment": str(spec.get("government_treatment") or "NOT_CONFIRMED_EXCLUDED"),
        "imputed_rent_treatment": str(spec.get("imputed_rent_treatment") or "NOT_CONFIRMED"),
        "rejection_reason": str(spec.get("rejection_reason") or "Source does not satisfy all exact Armilar gates."),
    }


def _audit_source_attempt_rows(
    adapter: "OfficialFamilyAuditAdapter",
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    blocking: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in adapter.source_specs:
        source_id = str(spec["source_id"])
        record = records.get(source_id)
        analysis = analyses.get(source_id, {})
        error = errors.get(source_id)
        rows.append({
            "economy_code": adapter.economy_code,
            "category": "*",
            "source_family": str(spec["family"]),
            "authority": adapter.source_authority,
            "dataset": source_id,
            "url": str(spec["url"]),
            "access_method": "REAL_HTTP_OR_EQUIVALENT_ACQUISITION",
            "retrieval_status": "ACCESS_BLOCKED" if error else (
                "ACQUIRED_REJECTED" if analysis.get("expected_evidence_confirmed") else "SOURCE_CONTENT_REVIEW_REQUIRED"
            ),
            "status_code": record.status_code if record and record.status_code is not None else "",
            "content_type": record.content_type or "" if record else "",
            "file_signature": analysis.get("file_signature", ""),
            "byte_size": record.bytes if record else "",
            "reference_period": str(spec.get("reference_period") or adapter.reference_period),
            "institutional_sector": analysis.get("institutional_sector", str(spec.get("institutional_sector") or "UNKNOWN")),
            "transaction_code": analysis.get("transaction_code", str(spec.get("transaction_code") or "UNKNOWN")),
            "classification": str(spec.get("classification") or ""),
            "current_prices": analysis.get("current_prices", str(spec.get("current_prices") or "UNKNOWN")),
            "currency": analysis.get("currency", str(spec.get("currency") or "UNKNOWN")),
            "unit": analysis.get("unit", str(spec.get("unit") or "UNKNOWN")),
            "npish_treatment": analysis.get("npish_treatment", str(spec.get("npish_treatment") or "UNKNOWN")),
            "government_treatment": analysis.get("government_treatment", str(spec.get("government_treatment") or "UNKNOWN")),
            "imputed_rent_treatment": analysis.get("imputed_rent_treatment", str(spec.get("imputed_rent_treatment") or "UNKNOWN")),
            "candidate_class": "ACCESS_BLOCKED" if error else (
                "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE" if analysis.get("expected_evidence_confirmed") else "CONCEPT_AMBIGUOUS"
            ),
            "rejection_reason": (
                f"{type(error).__name__}: {error}" if error else analysis.get("rejection_reason", blocking)
            ),
            "retrieved_at": record.retrieved_at if record else "",
            "sha256": record.sha256 if record else "",
        })
    return rows


def _audit_evidence_rows(
    adapter: "OfficialFamilyAuditAdapter",
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in adapter.source_specs:
        source_id = str(spec["source_id"])
        analysis = analyses.get(source_id, {})
        error = errors.get(source_id)
        rows.append({
            "economy_code": adapter.economy_code,
            "source_id": source_id,
            "source_authority": adapter.source_authority,
            "source_url": str(spec["url"]),
            "reference_period": str(spec.get("reference_period") or adapter.reference_period),
            "concept": str(spec.get("concept") or ""),
            "granularity": str(spec.get("classification") or ""),
            "machine_readable": analysis.get("machine_readable", str(spec.get("machine_readable") or "unknown")),
            "status": "ACCESS_BLOCKED" if error else (
                "ACQUIRED_BUT_REJECTED" if analysis.get("expected_evidence_confirmed") else "ACQUIRED_REVIEW_REQUIRED"
            ),
            "rejection_reason": f"{type(error).__name__}: {error}" if error else analysis.get("rejection_reason", ""),
        })
    return rows


def _audit_mapping_rows(adapter: "OfficialFamilyAuditAdapter", analyses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in adapter.source_specs:
        source_id = str(spec["source_id"])
        analysis = analyses.get(source_id)
        if not analysis:
            continue
        rows.append({
            "economy_code": adapter.economy_code,
            "original_item_code": source_id,
            "original_item_name": str(spec.get("concept") or ""),
            "armilar_category": "",
            "mapping_type": "NO_EXACT_MAPPING_PERMITTED",
            "status": "REJECTED" if analysis.get("expected_evidence_confirmed") else "REVIEW_REQUIRED",
            "reason": analysis.get("rejection_reason", ""),
        })
    return rows


def country_audit_cell_rows(
    economy_code: str,
    economy_name: str,
    source_id: str,
    authority: str,
    reference_period: str,
    decision: str,
    blocking_reason: str,
    categories: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [{
        "economy_code": economy_code,
        "economy_name": economy_name,
        "armilar_category": category,
        "cell_class": decision,
        "source_id": source_id,
        "source_authority": authority,
        "reference_period": reference_period,
        "value_status": "NO_VALUE_ADMITTED",
        "admissible_to_exact_matrix": False,
        "blocking_reason": blocking_reason,
        "quality_flags": "SOURCE_FAMILY_AUDIT|ZERO_EXACT_ROWS",
    } for category in categories]


def country_audit_completion_row(
    economy_code: str,
    economy_name: str,
    blocking: str,
    sources_examined: int,
    decision: str,
    categories: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "economy_code": economy_code,
        "economy_name": economy_name,
        "accepted_categories": "",
        "experimental_categories": "",
        "unavailable_categories": "|".join(categories),
        "coverage_added_cells": 0,
        "decision": decision,
        "sources_examined": sources_examined,
        "remaining_blockers": blocking,
    }


class OfficialFamilyAuditAdapter:
    economy_code = ""
    economy_name = ""
    adapter_id = ""
    source_authority = ""
    reference_period = "2021"
    source_specs: tuple[dict[str, Any], ...] = ()
    core_source_ids: set[str] = set()
    audit_categories: tuple[str, ...] = ALL_ARMILAR_CATEGORIES
    exception_category = ""
    exception_current_status = ""
    exception_resolution_attempted = ""
    exception_reason = ""

    def build_gate_rows(
        self,
        records: dict[str, AcquisitionRecord],
        analyses: dict[str, dict[str, Any]],
        errors: dict[str, Exception],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def validate_gate_rows(self, rows: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    def closed_rejection_reason(self) -> str:
        raise NotImplementedError

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        raw_root = run_root / "raw" / "country_adapters" / self.economy_code
        records: dict[str, AcquisitionRecord] = {}
        analyses: dict[str, dict[str, Any]] = {}
        errors: dict[str, Exception] = {}
        failure_rows: list[dict[str, Any]] = []
        for spec in self.source_specs:
            source_id = str(spec["source_id"])
            destination = raw_root / source_id / str(spec["filename"])
            try:
                record = fetch_url(
                    config,
                    source_id=source_id,
                    url=str(spec["url"]),
                    destination=destination,
                    cache_path=cache_root / "country_adapters" / self.economy_code / str(spec["filename"]),
                    accept=str(spec.get("accept") or "*/*"),
                )
                records[source_id] = record
                analyses[source_id] = _analyse_source_spec(spec, destination, record.content_type or "")
            except Exception as exc:
                errors[source_id] = exc
                failure_rows.append({
                    "economy_code": self.economy_code,
                    "adapter_id": self.adapter_id,
                    "stage": f"acquisition_or_validation:{source_id}",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
        core_blocked = sorted(self.core_source_ids & set(errors))
        unexpected = sorted(
            source_id for source_id in self.core_source_ids & set(analyses)
            if not analyses[source_id].get("expected_evidence_confirmed", False)
        )
        if core_blocked:
            decision = "ACCESS_BLOCKED"
            status = "ACCESS_BLOCKED"
            blocking = (
                f"The current run could not acquire or validate all critical official {self.economy_name} source families: "
                + ", ".join(core_blocked)
                + ". A closed source decision is not permitted while these attempts remain blocked."
            )
        elif unexpected:
            decision = "CONCEPT_AMBIGUOUS"
            status = "SOURCE_CONTENT_REVIEW_REQUIRED"
            blocking = (
                f"Acquired official {self.economy_name} resources did not match the reviewed structural markers for: "
                + ", ".join(unexpected)
                + ". No source is admitted until the changed content is reviewed."
            )
        else:
            decision = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            status = "REJECTED_BY_CONFIRMED_SOURCE_GATES"
            blocking = self.closed_rejection_reason()
        attempts = _audit_source_attempt_rows(self, records, analyses, errors, blocking)
        gates = self.build_gate_rows(records, analyses, errors)
        self.validate_gate_rows(gates)
        gate_kwargs: dict[str, Any] = {}
        if self.economy_code == "IDN":
            gate_kwargs["indonesia_gate_rows"] = gates
        elif self.economy_code == "BRA":
            gate_kwargs["brazil_gate_rows"] = gates
        elif self.economy_code == "EGY":
            gate_kwargs["egypt_gate_rows"] = gates
        elif self.economy_code == "PAK":
            gate_kwargs["pakistan_gate_rows"] = gates
        elif self.economy_code == "NGA":
            gate_kwargs["nigeria_gate_rows"] = gates
        elif self.economy_code == "BGD":
            gate_kwargs["bangladesh_gate_rows"] = gates
        elif self.economy_code == "VNM":
            gate_kwargs["vietnam_gate_rows"] = gates
        if self.exception_category:
            gate_kwargs["step2h_exception_rows"] = [{
                "economy_code": self.economy_code,
                "economy_name": self.economy_name,
                "armilar_category": self.exception_category,
                "decision": decision,
                "current_status": self.exception_current_status,
                "resolution_attempted": self.exception_resolution_attempted,
                "reason": blocking if decision != "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE" else self.exception_reason,
            }]
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code,
                "economy_name": self.economy_name,
                "adapter_id": self.adapter_id,
                "status": status,
                "data_class": decision,
                "accepted_rows": 0,
                "failure_count": len(failure_rows),
                "source_url": str(self.source_specs[0]["url"]),
                "blocking_reason": blocking,
            }],
            evidence_rows=_audit_evidence_rows(self, records, analyses, errors),
            normalized_rows=[],
            mapping_rows=_audit_mapping_rows(self, analyses),
            reconciliation_rows=[],
            failure_rows=failure_rows,
            acquisition_records=[records[key] for key in sorted(records)],
            cell_status_rows=country_audit_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id,
                self.source_authority, self.reference_period, decision, blocking,
                self.audit_categories,
            ),
            source_attempt_rows=attempts,
            source_family_rows=source_family_rows(self.economy_code, self.economy_name, attempts, blocking),
            completion_rows=[country_audit_completion_row(
                self.economy_code, self.economy_name, blocking,
                len(self.source_specs), decision, self.audit_categories,
            )],
            **gate_kwargs,
        )


def _gate_source(
    adapter: OfficialFamilyAuditAdapter,
    source_id: str,
    records: dict[str, AcquisitionRecord],
    review_mode: str = "STRUCTURAL_MARKER_VALIDATION",
) -> dict[str, Any]:
    spec = next(spec for spec in adapter.source_specs if spec["source_id"] == source_id)
    record = records.get(source_id)
    return {
        "source_id": source_id,
        "source_authority": adapter.source_authority,
        "source_url": str(spec["url"]),
        "source_retrieved_at": record.retrieved_at if record else "",
        "source_sha256": record.sha256 if record else "",
        "review_mode": review_mode,
    }


def _validate_country_gate_rows(
    rows: list[dict[str, Any]],
    required: set[str],
    statuses: set[str],
    country: str,
) -> None:
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError(f"{country} methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - statuses)
    if invalid:
        raise ValueError(f"{country} methodology audit contains invalid statuses: " + ",".join(invalid))
    final = by_criterion.get("exact_armilar_source_available", {})
    if final.get("status") == "CONTRADICTED":
        underlying = [row for key, row in by_criterion.items() if key != "exact_armilar_source_available"]
        if not any(row.get("status") == "CONTRADICTED" for row in underlying):
            raise ValueError(f"{country} exact-source rejection requires at least one confirmed underlying contradiction")


class IndonesiaBpsAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "IDN"
    economy_name = "Indonesia"
    adapter_id = "IDN_BPS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Badan Pusat Statistik"
    reference_period = "2021"
    audit_categories = STEP2I_PROXY_CATEGORIES
    source_specs = (
        {"source_id":"IDN_BPS_GDP_EXPENDITURE_2020_2024","url":"https://www.bps.go.id/en/publication/2025/05/28/2a1c585ebbd574dd91afed67/gross-domestic-product-of-indonesia-by-expenditure--2020-2024.html","filename":"gdp_by_expenditure_2020_2024.html","accept":"text/html,*/*;q=0.1","family":"official_structured_publications","concept":"GDP by expenditure publication with grouped household consumption","classification":"HFCE_REGROUPED_PUBLICATION","required_markers":("gross domestic product of indonesia by expenditure","household consumption"),"source_decision":"REJECT_GROUPED_PURPOSES","rejection_reason":"The publication groups household consumption rather than supplying twelve Armilar purposes and cannot be split without allocation.","reference_period":"2020-2024","current_prices":"MIXED","currency":"IDR","unit":"PUBLICATION_TABLES"},
        {"source_id":"IDN_BPS_STATISTICS_TABLES_EXPENDITURE","url":"https://www.bps.go.id/en/statistics-table?subject=531","filename":"statistics_tables_expenditure.html","accept":"text/html,*/*;q=0.1","family":"official_statistical_database","concept":"BPS official expenditure-side statistics tables","classification":"BPS_DATABASE_DISCOVERY","required_markers":("statistics table","expenditure"),"source_decision":"DISCOVERY_ONLY","rejection_reason":"The table portal is discovery evidence and no pinned exact 2021 S14/P31DC twelve-purpose query is identified."},
        {"source_id":"IDN_BPS_NATIONAL_ACCOUNTS_DOWNLOAD_SEARCH","url":"https://www.bps.go.id/en/publication?keyword=gross%20domestic%20product%20expenditure","filename":"national_accounts_download_search.html","accept":"text/html,*/*;q=0.1","family":"official_csv_xls_xlsx","concept":"Downloadable national-accounts publication search","classification":"DOWNLOAD_DISCOVERY_ONLY","required_markers":("publication","gross domestic product"),"source_decision":"DISCOVERY_ONLY","rejection_reason":"Publication search evidence is not a machine-readable exact dataset."},
        {"source_id":"IDN_BPS_SUPPLY_USE_TABLES","url":"https://www.bps.go.id/en/publication?keyword=supply%20use%20table","filename":"supply_use_tables_search.html","accept":"text/html,*/*;q=0.1","family":"official_supply_and_use_tables","concept":"BPS supply and use table family","classification":"SUT_PRODUCT_TABLE_DISCOVERY","required_markers":("supply","use"),"source_decision":"REJECT_PRODUCT_TO_PURPOSE_ALLOCATION","rejection_reason":"Supply-use evidence is product-based and cannot be converted to exact purpose weights through many-to-many allocation."},
        {"source_id":"IDN_BPS_INPUT_OUTPUT_TABLES","url":"https://www.bps.go.id/en/publication?keyword=input%20output%20table","filename":"input_output_tables_search.html","accept":"text/html,*/*;q=0.1","family":"official_input_output_tables","concept":"BPS input-output table family","classification":"INPUT_OUTPUT_PRODUCT_TABLE_DISCOVERY","required_markers":("input","output"),"source_decision":"REJECT_PRODUCT_TO_PURPOSE_ALLOCATION","rejection_reason":"Input-output evidence is product-based and cannot provide exact COICOP purpose weights without allocation."},
        {"source_id":"IDN_BPS_SURVEY_OR_CPI_CLASS_C","url":"https://www.bps.go.id/en/statistics-table?subject=3","filename":"survey_or_cpi_class_c.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Household survey or CPI evidence","classification":"SURVEY_OR_CPI_CLASS_C_ONLY","required_markers":("statistics table",),"source_decision":"REJECT_CLASS_C","rejection_reason":"Survey and CPI evidence cannot replace national-accounts expenditure weights."},
        {"source_id":"IDN_BPS_CLASSIFICATION_METHODOLOGY","url":"https://www.bps.go.id/en/publication?keyword=classification%20coicop","filename":"classification_methodology_search.html","accept":"text/html,*/*;q=0.1","family":"official_classifications_methodology","concept":"Classification and methodology documents","classification":"CLASSIFICATION_METHODOLOGY_DISCOVERY","required_markers":("publication",),"source_decision":"DOCUMENTATION_ONLY","rejection_reason":"Classification documentation does not itself provide admissible expenditure values."},
    )
    core_source_ids = {"IDN_BPS_GDP_EXPENDITURE_2020_2024","IDN_BPS_STATISTICS_TABLES_EXPENDITURE","IDN_BPS_SUPPLY_USE_TABLES","IDN_BPS_INPUT_OUTPUT_TABLES"}
    def closed_rejection_reason(self) -> str:
        return "The BPS expenditure publication is grouped rather than twelve-purpose; database and download pages remain discovery evidence; SUT and input-output families are product-based; survey/CPI evidence is Class C. No exact 2021 current-price S14/P31DC twelve-purpose source passed the gates."
    def build_gate_rows(self, records, analyses, errors):
        def state(source_id, contradiction=False):
            if source_id in errors: return "NOT_FOUND"
            if analyses.get(source_id,{}).get("expected_evidence_confirmed"): return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows=[
            {"criterion":"official_grouped_hfce_publication_available","status":state("IDN_BPS_GDP_EXPENDITURE_2020_2024"),"evidence":"BPS publishes GDP by expenditure with grouped household-consumption categories.",**_gate_source(self,"IDN_BPS_GDP_EXPENDITURE_2020_2024",records)},
            {"criterion":"twelve_armilar_purposes_available","status":state("IDN_BPS_GDP_EXPENDITURE_2020_2024",True),"evidence":"The reviewed publication is grouped and cannot be split into twelve purposes without allocation.",**_gate_source(self,"IDN_BPS_GDP_EXPENDITURE_2020_2024",records)},
            {"criterion":"sut_is_exact_purpose_source","status":state("IDN_BPS_SUPPLY_USE_TABLES",True),"evidence":"The SUT family is product-based and does not prove an exact COICOP-purpose table.",**_gate_source(self,"IDN_BPS_SUPPLY_USE_TABLES",records)},
            {"criterion":"input_output_is_exact_purpose_source","status":state("IDN_BPS_INPUT_OUTPUT_TABLES",True),"evidence":"Input-output tables are product-based and require prohibited allocation.",**_gate_source(self,"IDN_BPS_INPUT_OUTPUT_TABLES",records)},
            {"criterion":"survey_or_cpi_can_supply_exact_weights","status":state("IDN_BPS_SURVEY_OR_CPI_CLASS_C",True),"evidence":"Survey or CPI data remains Class C and cannot supply exact national-accounts weights.",**_gate_source(self,"IDN_BPS_SURVEY_OR_CPI_CLASS_C",records)},
        ]
        exact="NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"No reviewed source supplies strict S14/P31DC current-price 2021 values across twelve purposes without allocation.",**_gate_source(self,"IDN_BPS_GDP_EXPENDITURE_2020_2024",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows
    def validate_gate_rows(self, rows): validate_indonesia_methodology_gate_rows(rows)


class BrazilIbgeAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "BRA"
    economy_name = "Brazil"
    adapter_id = "BRA_IBGE_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Instituto Brasileiro de Geografia e Estatistica"
    reference_period = "2021"
    audit_categories = STEP2I_PROXY_CATEGORIES
    source_specs = (
        {"source_id":"BRA_IBGE_SIDRA_CNT_TABLES","url":"https://sidra.ibge.gov.br/pesquisa/cnt/tabelas","filename":"sidra_cnt_tables.html","accept":"text/html,*/*;q=0.1","family":"official_national_accounts_api","concept":"SIDRA national-accounts table discovery","classification":"SIDRA_DISCOVERY","required_markers":("sidra","contas nacionais"),"source_decision":"DISCOVERY_ONLY","rejection_reason":"SIDRA landing evidence does not pin an exact 2021 household-purpose table."},
        {"source_id":"BRA_IBGE_SISTEMA_CONTAS_NACIONAIS","url":"https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9052-sistema-de-contas-nacionais-brasil.html","filename":"sistema_contas_nacionais.html","accept":"text/html,*/*;q=0.1","family":"official_structured_publications","concept":"Sistema de Contas Nacionais","classification":"SCN_PUBLICATION_FAMILY","required_markers":("sistema de contas nacionais","ibge"),"source_decision":"REJECT_NO_EXACT_PURPOSE_TABLE","rejection_reason":"The SCN publication family does not expose a pinned strict S14/P31DC twelve-purpose table in this probe."},
        {"source_id":"BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS","url":"https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9052-sistema-de-contas-nacionais-brasil.html?=&t=resultados","filename":"contas_economicas_integradas.html","accept":"text/html,*/*;q=0.1","family":"official_statistical_database","concept":"Contas Economicas Integradas","classification":"INSTITUTIONAL_ACCOUNTS","required_markers":("contas economicas integradas",),"source_decision":"REJECT_INSTITUTIONAL_NOT_PURPOSE","rejection_reason":"Integrated economic accounts identify institutional flows, not twelve consumption purposes."},
        {"source_id":"BRA_IBGE_TABELAS_RECURSOS_USOS","url":"https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9052-sistema-de-contas-nacionais-brasil.html?=&t=resultados","filename":"tabelas_recursos_usos.html","accept":"text/html,*/*;q=0.1","family":"official_supply_and_use_tables","concept":"Tabelas de Recursos e Usos","classification":"TRU_PRODUCT_TABLES","required_markers":("tabelas de recursos e usos",),"source_decision":"REJECT_PRODUCT_TO_PURPOSE_ALLOCATION","rejection_reason":"TRU is product/resource-use evidence; exact COICOP weights would require many-to-many allocation."},
        {"source_id":"BRA_IBGE_DOWNLOADABLE_SCN_TABLES","url":"https://www.ibge.gov.br/estatisticas/downloads-estatisticas.html","filename":"downloadable_scn_tables.html","accept":"text/html,*/*;q=0.1","family":"official_csv_xls_xlsx","concept":"Downloadable SCN tables","classification":"DOWNLOAD_DISCOVERY_ONLY","required_markers":("downloads",),"source_decision":"DISCOVERY_ONLY","rejection_reason":"A downloads page is not a pinned exact dataset."},
        {"source_id":"BRA_IBGE_POF_IPCA_CLASS_C","url":"https://www.ibge.gov.br/estatisticas/sociais/populacao/24786-pesquisa-de-orcamentos-familiares-2.html","filename":"pof_ipca_class_c.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"POF household-budget survey and IPCA evidence","classification":"SURVEY_OR_CPI_CLASS_C_ONLY","required_markers":("pesquisa de orcamentos familiares",),"source_decision":"REJECT_CLASS_C","rejection_reason":"POF/IPCA shares cannot substitute for exact national-accounts weights."},
        {"source_id":"BRA_IBGE_CLASSIFICACOES_METODOLOGIA","url":"https://www.ibge.gov.br/estatisticas/metodos-e-classificacoes/classificacoes-e-listas-estatisticas.html","filename":"classificacoes_metodologia.html","accept":"text/html,*/*;q=0.1","family":"official_classifications_methodology","concept":"IBGE classifications and methodology","classification":"METHODOLOGY_DOCUMENTATION","required_markers":("classificacoes", "ibge"),"source_decision":"DOCUMENTATION_ONLY","rejection_reason":"Methodology documentation does not itself supply expenditure values."},
    )
    core_source_ids = {"BRA_IBGE_SIDRA_CNT_TABLES","BRA_IBGE_SISTEMA_CONTAS_NACIONAIS","BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS","BRA_IBGE_TABELAS_RECURSOS_USOS"}
    def closed_rejection_reason(self) -> str:
        return "SIDRA and SCN remain discovery/publication-family evidence, CEI is institutional rather than purpose-classified, TRU is product-based, and POF/IPCA is Class C. No exact 2021 current-price strict-household twelve-purpose source passed the gates."
    def build_gate_rows(self, records, analyses, errors):
        def state(source_id, contradiction=False):
            if source_id in errors: return "NOT_FOUND"
            if analyses.get(source_id,{}).get("expected_evidence_confirmed"): return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows=[
            {"criterion":"sidra_national_accounts_family_identified","status":state("BRA_IBGE_SIDRA_CNT_TABLES"),"evidence":"The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only.",**_gate_source(self,"BRA_IBGE_SIDRA_CNT_TABLES",records)},
            {"criterion":"scn_exact_twelve_purpose_table_identified","status":state("BRA_IBGE_SISTEMA_CONTAS_NACIONAIS",True),"evidence":"The SCN publication family does not pin a strict twelve-purpose S14 table in this probe.",**_gate_source(self,"BRA_IBGE_SISTEMA_CONTAS_NACIONAIS",records)},
            {"criterion":"cei_is_purpose_classified_hfce","status":state("BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS",True),"evidence":"CEI is institutional-account evidence rather than household consumption by purpose.",**_gate_source(self,"BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS",records)},
            {"criterion":"tru_is_exact_purpose_source","status":state("BRA_IBGE_TABELAS_RECURSOS_USOS",True),"evidence":"TRU is product-based and cannot be mapped exactly to COICOP without allocation.",**_gate_source(self,"BRA_IBGE_TABELAS_RECURSOS_USOS",records)},
            {"criterion":"pof_or_ipca_can_supply_exact_weights","status":state("BRA_IBGE_POF_IPCA_CLASS_C",True),"evidence":"POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights.",**_gate_source(self,"BRA_IBGE_POF_IPCA_CLASS_C",records)},
        ]
        exact="NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution.",**_gate_source(self,"BRA_IBGE_SISTEMA_CONTAS_NACIONAIS",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows
    def validate_gate_rows(self, rows): validate_brazil_methodology_gate_rows(rows)


class EgyptCapmasAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "EGY"
    economy_name = "Egypt"
    adapter_id = "EGY_CAPMAS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Central Agency for Public Mobilization and Statistics"
    reference_period = "2021"
    audit_categories = ALL_ARMILAR_CATEGORIES
    source_specs = (
        {"source_id":"EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG","url":"https://censusinfo.capmas.gov.eg/Metadata-en-v4.2/index.php/catalog/National_Accounts?reset=reset","filename":"national_accounts_catalog.html","accept":"text/html,*/*;q=0.1","family":"official_statistical_database","concept":"CAPMAS National Accounts collection","classification":"CATALOGUE_INVENTORY","required_markers":("national accounts","supply and use tables 2017 2018"),"source_decision":"REJECT_NO_2021_EXACT_TABLE_IN_INVENTORY","rejection_reason":"The official catalogue inventory lists historical SUT and input-output studies but no 2021 twelve-purpose S14/P31 table.","currency":"EGP"},
        {"source_id":"EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV","url":"https://censusinfo.capmas.gov.eg/Metadata-en-v4.2/index.php/catalog/export/csv?collection%5B%5D=National_Accounts&ps=5000","filename":"national_accounts_catalog.csv","accept":"text/csv,text/plain,*/*;q=0.1","family":"official_csv_xls_xlsx","concept":"Machine-readable National Accounts catalogue inventory","classification":"CATALOGUE_INVENTORY_CSV","required_markers":("supply and use tables 2017 2018","input output tables"),"source_decision":"REJECT_INVENTORY_WITHOUT_2021_EXACT_DATASET","rejection_reason":"The CSV is an inventory, not expenditure values, and does not identify a 2021 exact-purpose table.","machine_readable":"true","currency":"EGP"},
        {"source_id":"EGY_CAPMAS_SUT_2017_2018_METHOD","url":"https://censusinfo.capmas.gov.eg/Metadata-en-v4.2/index.php/catalog/518/study-description","filename":"sut_2017_2018_study_description.html","accept":"text/html,*/*;q=0.1","family":"official_supply_and_use_tables","concept":"Supply and Use Tables 2017/2018","classification":"SUT_PRODUCT_ACTIVITY_TABLES","required_markers":("supply and use tables","2017 2018","products"),"source_decision":"REJECT_WRONG_YEAR_PRODUCT_SUT","rejection_reason":"The SUT benchmark is 2017/2018 and organised by products and activities, not a 2021 twelve-purpose table.","reference_period":"2017-18","current_prices":"true","currency":"EGP","unit":"OFFICIAL_SUT"},
        {"source_id":"EGY_CAPMAS_HIECS_2021","url":"https://www.censusinfo.capmas.gov.eg/metadata-en-v4.2/index.php/catalog/747/overview","filename":"hiecs_2021_overview.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Survey of Income, Expenditure and Consumption 2021","classification":"HIECS_HOUSEHOLD_SURVEY","required_markers":("survey of income expenditure and consumption 2021","survey by sample"),"source_decision":"REJECT_CLASS_C_SURVEY","rejection_reason":"HIECS is a sample household survey rather than national-accounts S14/P31 expenditure.","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","current_prices":"true","currency":"EGP","unit":"SURVEY_MICRODATA","npish_treatment":"SURVEY_OUT_OF_SCOPE","government_treatment":"SURVEY_OUT_OF_SCOPE"},
        {"source_id":"EGY_CAPMAS_CENTRAL_DATA_CATALOG","url":"https://www.censusinfo.capmas.gov.eg/Metadata-en-v4.2/index.php/catalog/?sort_by=titl&sort_order=desc","filename":"central_data_catalog.html","accept":"text/html,*/*;q=0.1","family":"official_structured_publications","concept":"CAPMAS Central Data Catalog","classification":"DISCOVERY_CATALOGUE","required_markers":("central data catalog",),"source_decision":"DISCOVERY_ONLY","rejection_reason":"The central catalogue is discovery evidence, not a pinned dataset."},
    )
    core_source_ids = {"EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG","EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV","EGY_CAPMAS_SUT_2017_2018_METHOD","EGY_CAPMAS_HIECS_2021"}
    def closed_rejection_reason(self) -> str:
        return "The CAPMAS National Accounts catalogue and its CSV inventory identify only historical SUT/input-output studies, the latest relevant SUT benchmark is 2017/2018 and product/activity-based, and HIECS 2021 is a sample household survey. No current-price 2021 strict S14/P31 twelve-purpose national-accounts source passed the gates."
    def build_gate_rows(self, records, analyses, errors):
        def state(source_id, contradiction=False):
            if source_id in errors: return "NOT_FOUND"
            if analyses.get(source_id,{}).get("expected_evidence_confirmed"): return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows=[
            {"criterion":"national_accounts_catalogue_acquired","status":state("EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG"),"evidence":"The official CAPMAS National Accounts collection was acquired and its study inventory reviewed.",**_gate_source(self,"EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG",records)},
            {"criterion":"machine_readable_catalogue_inventory_acquired","status":state("EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV"),"evidence":"The official catalogue CSV inventory was acquired as machine-readable source-family evidence.",**_gate_source(self,"EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV",records)},
            {"criterion":"sut_reference_period_matches_2021","status":state("EGY_CAPMAS_SUT_2017_2018_METHOD",True),"evidence":"The identified CAPMAS SUT benchmark is 2017/2018 rather than 2021.",**_gate_source(self,"EGY_CAPMAS_SUT_2017_2018_METHOD",records)},
            {"criterion":"sut_is_exact_purpose_classification","status":state("EGY_CAPMAS_SUT_2017_2018_METHOD",True),"evidence":"The SUT is organised around products and activities, not twelve household purposes.",**_gate_source(self,"EGY_CAPMAS_SUT_2017_2018_METHOD",records)},
            {"criterion":"hiecs_is_national_accounts_s14_p31","status":state("EGY_CAPMAS_HIECS_2021",True),"evidence":"HIECS 2021 is explicitly a sample survey and cannot be substituted for national-accounts S14/P31.",**_gate_source(self,"EGY_CAPMAS_HIECS_2021",records)},
            {"criterion":"hiecs_reference_period_matches_2021","status":state("EGY_CAPMAS_HIECS_2021"),"evidence":"HIECS is a 2021 survey, but the matching year does not cure the conceptual mismatch.",**_gate_source(self,"EGY_CAPMAS_HIECS_2021",records)},
        ]
        exact="NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"The catalogues, historical product-based SUT and 2021 survey each fail at least one exact Armilar gate; none supplies current-price 2021 S14/P31 by twelve purposes.",**_gate_source(self,"EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows
    def validate_gate_rows(self, rows): validate_egypt_methodology_gate_rows(rows)



class PakistanPbsAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "PAK"
    economy_name = "Pakistan"
    adapter_id = "PAK_PBS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Pakistan Bureau of Statistics"
    reference_period = "2021-22"
    audit_categories = ALL_ARMILAR_CATEGORIES
    source_specs = (
        {
            "source_id": "PAK_PBS_NATIONAL_ACCOUNTS_PAGE",
            "url": "https://www.pbs.gov.pk/national-accounts-2/",
            "filename": "national_accounts.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "Annual national accounts and expenditure on GDP",
            "classification": "SNA_2008_AGGREGATE_EXPENDITURE",
            "required_markers": ("annual national accounts", "expenditure on gdp", "current and constant"),
            "source_decision": "REJECT_AGGREGATE_ONLY",
            "rejection_reason": "The national-accounts portal confirms aggregate expenditure-GDP series but does not expose HFCE by twelve household purposes.",
            "institutional_sector": "HOUSEHOLDS_AGGREGATE",
            "transaction_code": "HFCE_AGGREGATE",
            "current_prices": "true",
            "currency": "PKR",
            "unit": "OFFICIAL_NATIONAL_ACCOUNTS_UNIT",
            "npish_treatment": "SEPARATE_IN_METHODOLOGY_NOT_IN_PURPOSE_TABLE",
            "government_treatment": "SEPARATE_AGGREGATE",
        },
        {
            "source_id": "PAK_PBS_NATIONAL_ACCOUNTS_XLSX",
            "url": "https://www.pbs.gov.pk/wp-content/uploads/2020/07/National-Accounts-Annual-Tables-2024-25-Updated-March-2026.xlsx",
            "filename": "national_accounts_annual_tables.xlsx",
            "accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.1",
            "family": "official_csv_xls_xlsx",
            "concept": "Annual national accounts tables",
            "classification": "SNA_2008_AGGREGATE_EXPENDITURE_XLSX",
            "required_markers": ("household final consumption expenditure", "2021-22"),
            "source_decision": "REJECT_AGGREGATE_FISCAL_YEAR_TABLE",
            "rejection_reason": "The workbook supplies aggregate HFCE for fiscal 2021-22, not calendar-2021 expenditure by twelve purposes.",
            "reference_period": "2021-22",
            "institutional_sector": "HOUSEHOLDS_AGGREGATE",
            "transaction_code": "HFCE_AGGREGATE",
            "current_prices": "true",
            "currency": "PKR",
            "unit": "million rupees",
            "npish_treatment": "SEPARATE_AGGREGATE",
            "government_treatment": "SEPARATE_AGGREGATE",
            "machine_readable": "true",
        },
        {
            "source_id": "PAK_PBS_NATIONAL_ACCOUNTS_FAQ",
            "url": "https://www.pbs.gov.pk/docs/national-accounts/",
            "filename": "national_accounts_faq.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "official_classifications_methodology",
            "concept": "National accounts scope and demand-side methodology",
            "classification": "SNA_2008_METHODOLOGY",
            "required_markers": ("demand side", "current and constant prices", "final consumption expenditure of households"),
            "source_decision": "CONFIRM_AGGREGATE_SCOPE_ONLY",
            "rejection_reason": "The methodology confirms aggregate household final consumption as a GDP component but no purpose-classified table.",
            "reference_period": "METHODOLOGY",
            "institutional_sector": "HOUSEHOLDS_AGGREGATE",
            "transaction_code": "HFCE_AGGREGATE",
            "current_prices": "true",
            "currency": "PKR",
        },
        {
            "source_id": "PAK_PBS_HIES_2018_19",
            "url": "https://www.pbs.gov.pk/hies/",
            "filename": "hies.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "Household Integrated Economic Survey 2018-19",
            "classification": "HIES_COICOP_HOUSEHOLD_SURVEY",
            "required_markers": ("hies pslm 2018-19", "consumption expenditure", "coicop"),
            "source_decision": "REJECT_CLASS_C_WRONG_PERIOD_SURVEY",
            "rejection_reason": "HIES provides COICOP household-survey shares for 2018-19, not national-accounts S14/P31 values for 2021.",
            "reference_period": "2018-19",
            "institutional_sector": "HOUSEHOLD_SURVEY",
            "transaction_code": "NOT_SNA_P31",
            "current_prices": "true",
            "currency": "PKR",
            "unit": "survey household expenditure",
            "npish_treatment": "OUTSIDE_SURVEY_SCOPE",
            "government_treatment": "OUTSIDE_SURVEY_SCOPE",
        },
        {
            "source_id": "PAK_PBS_NATIONAL_ACCOUNTS_METHODOLOGY_PDF",
            "url": "https://www.pbs.gov.pk/wp-content/uploads/2020/07/National-Accounts-of-Pakistan-Backward-Revisions-for-the-Years-1999-2000-to-2014-15-on-the-base-year-2015-16.pdf",
            "filename": "national_accounts_methodology.pdf",
            "accept": "application/pdf,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "Backward-series national-accounts methodology",
            "classification": "OFFICIAL_METHODOLOGY_PDF",
            "required_markers": (),
            "source_decision": "DOCUMENTATION_ONLY",
            "rejection_reason": "The methodology documents separate aggregate HFCE and NPISH compilation but is not a purpose-classified 2021 dataset.",
            "reference_period": "METHODOLOGY",
            "institutional_sector": "HOUSEHOLDS_AND_NPISH_SEPARATELY_DESCRIBED",
            "transaction_code": "HFCE_AND_NPISH_AGGREGATES",
            "current_prices": "true",
            "currency": "PKR",
            "machine_readable": "false",
        },
    )
    core_source_ids = {
        "PAK_PBS_NATIONAL_ACCOUNTS_PAGE",
        "PAK_PBS_NATIONAL_ACCOUNTS_XLSX",
        "PAK_PBS_NATIONAL_ACCOUNTS_FAQ",
        "PAK_PBS_HIES_2018_19",
    }

    def closed_rejection_reason(self) -> str:
        return (
            "PBS publishes aggregate annual household final consumption at current and constant prices, including fiscal 2021-22, "
            "while the purpose detail located in HIES is a 2018-19 household survey. The reviewed source chain does not provide "
            "calendar-2021 current-price S14/P31 household expenditure by all twelve Armilar purposes without survey substitution or temporal conversion."
        )

    def build_gate_rows(self, records, analyses, errors):
        def state(source_id: str, contradiction: bool = False) -> str:
            if source_id in errors:
                return "NOT_FOUND"
            if analyses.get(source_id, {}).get("expected_evidence_confirmed"):
                return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows = [
            {"criterion":"annual_national_accounts_source_acquired","status":state("PAK_PBS_NATIONAL_ACCOUNTS_PAGE"),"evidence":"The official PBS annual national-accounts page was acquired and confirms demand-side aggregate series.",**_gate_source(self,"PAK_PBS_NATIONAL_ACCOUNTS_PAGE",records)},
            {"criterion":"machine_readable_2021_22_hfce_aggregate_acquired","status":state("PAK_PBS_NATIONAL_ACCOUNTS_XLSX"),"evidence":"The official annual-tables workbook contains aggregate household final consumption for fiscal 2021-22.",**_gate_source(self,"PAK_PBS_NATIONAL_ACCOUNTS_XLSX",records)},
            {"criterion":"reference_period_matches_calendar_2021","status":state("PAK_PBS_NATIONAL_ACCOUNTS_XLSX",True),"evidence":"The relevant official period is fiscal 2021-22 rather than calendar year 2021.",**_gate_source(self,"PAK_PBS_NATIONAL_ACCOUNTS_XLSX",records)},
            {"criterion":"twelve_armilar_purposes_available_in_national_accounts","status":state("PAK_PBS_NATIONAL_ACCOUNTS_PAGE",True),"evidence":"The reviewed annual national-accounts source family exposes HFCE as an aggregate GDP component, not twelve purposes.",**_gate_source(self,"PAK_PBS_NATIONAL_ACCOUNTS_PAGE",records)},
            {"criterion":"hies_is_national_accounts_s14_p31","status":state("PAK_PBS_HIES_2018_19",True),"evidence":"HIES is a household survey and cannot replace national-accounts S14/P31 expenditure.",**_gate_source(self,"PAK_PBS_HIES_2018_19",records)},
            {"criterion":"hies_reference_period_matches_2021","status":state("PAK_PBS_HIES_2018_19",True),"evidence":"The located detailed HIES tables refer to 2018-19, not 2021.",**_gate_source(self,"PAK_PBS_HIES_2018_19",records)},
        ]
        exact = "NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"No reviewed PBS source combines calendar 2021, current prices, strict household national accounts and twelve-purpose coverage.",**_gate_source(self,"PAK_PBS_NATIONAL_ACCOUNTS_PAGE",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows

    def validate_gate_rows(self, rows):
        validate_pakistan_methodology_gate_rows(rows)


class NigeriaNbsAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "NGA"
    economy_name = "Nigeria"
    adapter_id = "NGA_NBS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "National Bureau of Statistics"
    reference_period = "2021"
    audit_categories = ALL_ARMILAR_CATEGORIES
    source_specs = (
        {
            "source_id": "NGA_NBS_ELIBRARY_REPORT_PAGE",
            "url": "https://www.nigerianstat.gov.ng/elibrary/read/1241168",
            "filename": "gdp_expenditure_2021_report_page.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "GDP expenditure and income approach report",
            "classification": "SNA_AGGREGATE_EXPENDITURE",
            "required_markers": ("household consumption expenditure", "2021", "government consumption expenditure"),
            "source_decision": "REJECT_AGGREGATE_ONLY",
            "rejection_reason": "The official 2021 expenditure-GDP release reports household consumption only as an aggregate component.",
            "institutional_sector": "HOUSEHOLDS_AGGREGATE",
            "transaction_code": "HFCE_AGGREGATE",
            "current_prices": "partly_nominal_and_real",
            "currency": "NGN",
            "unit": "OFFICIAL_REPORT_UNIT",
            "npish_treatment": "SEPARATE_AGGREGATE_IN_EXPENDITURE_ACCOUNTS",
            "government_treatment": "SEPARATE_AGGREGATE",
        },
        {
            "source_id": "NGA_NBS_GDP_EXPENDITURE_2021_PDF",
            "url": "https://www.nigerianstat.gov.ng/pdfuploads/Expenditure%20Report%20Revised_Q2%202020%20-Q3%202021%20and%20Provisional%20Q4%202021.pdf",
            "filename": "gdp_expenditure_2021.pdf",
            "accept": "application/pdf,*/*;q=0.1",
            "family": "official_csv_xls_xlsx",
            "concept": "2021 expenditure-GDP report download",
            "classification": "SNA_AGGREGATE_EXPENDITURE_PDF",
            "required_markers": (),
            "source_decision": "REJECT_NON_MACHINE_READABLE_AGGREGATE",
            "rejection_reason": "The official PDF preserves the 2021 aggregate expenditure evidence but does not provide a machine-readable twelve-purpose table.",
            "institutional_sector": "HOUSEHOLDS_AGGREGATE",
            "transaction_code": "HFCE_AGGREGATE",
            "current_prices": "partly_nominal_and_real",
            "currency": "NGN",
            "unit": "OFFICIAL_REPORT_UNIT",
            "npish_treatment": "SEPARATE_AGGREGATE",
            "government_treatment": "SEPARATE_AGGREGATE",
            "machine_readable": "false",
        },
        {
            "source_id": "NGA_NBS_CONSUMPTION_PATTERN_2019",
            "url": "https://www.nigerianstat.gov.ng/elibrary/read/1094",
            "filename": "consumption_pattern_2019.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "Consumption Expenditure Pattern in Nigeria 2019",
            "classification": "HOUSEHOLD_SURVEY_CONSUMPTION_PATTERN",
            "required_markers": ("consumption expenditure pattern in nigeria 2019", "total household expenditure", "food and non-food"),
            "source_decision": "REJECT_CLASS_C_WRONG_PERIOD_SURVEY",
            "rejection_reason": "The 2019 household-consumption study is survey evidence, has the wrong period and does not constitute national-accounts S14/P31 by twelve purposes.",
            "reference_period": "2019",
            "institutional_sector": "HOUSEHOLD_SURVEY",
            "transaction_code": "NOT_SNA_P31",
            "current_prices": "true",
            "currency": "NGN",
            "unit": "survey expenditure",
            "npish_treatment": "OUTSIDE_SURVEY_SCOPE",
            "government_treatment": "OUTSIDE_SURVEY_SCOPE",
        },
        {
            "source_id": "NGA_NBS_ELIBRARY",
            "url": "https://nigerianstat.gov.ng/elibrary",
            "filename": "elibrary.html",
            "accept": "text/html,*/*;q=0.1",
            "family": "official_statistical_database",
            "concept": "NBS e-library and open-data portal",
            "classification": "DISCOVERY_CATALOGUE",
            "required_markers": ("elibrary", "open data portal"),
            "source_decision": "DISCOVERY_ONLY",
            "rejection_reason": "The portal is source-discovery evidence and not itself an exact dataset.",
        },
    )
    core_source_ids = {
        "NGA_NBS_ELIBRARY_REPORT_PAGE",
        "NGA_NBS_GDP_EXPENDITURE_2021_PDF",
        "NGA_NBS_CONSUMPTION_PATTERN_2019",
    }

    def closed_rejection_reason(self) -> str:
        return (
            "The official 2021 expenditure-GDP release supplies aggregate household consumption, while detailed consumption evidence located in the NBS e-library refers to a 2019 household survey. "
            "No reviewed source supplies current-price 2021 strict S14/P31 expenditure by all twelve Armilar purposes without survey substitution."
        )

    def build_gate_rows(self, records, analyses, errors):
        def state(source_id: str, contradiction: bool = False) -> str:
            if source_id in errors:
                return "NOT_FOUND"
            if analyses.get(source_id, {}).get("expected_evidence_confirmed"):
                return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows = [
            {"criterion":"gdp_expenditure_2021_source_acquired","status":state("NGA_NBS_ELIBRARY_REPORT_PAGE"),"evidence":"The official NBS 2021 expenditure-GDP release was acquired.",**_gate_source(self,"NGA_NBS_ELIBRARY_REPORT_PAGE",records)},
            {"criterion":"household_consumption_is_purpose_classified","status":state("NGA_NBS_ELIBRARY_REPORT_PAGE",True),"evidence":"The report presents household consumption as an aggregate GDP-expenditure component, not twelve purposes.",**_gate_source(self,"NGA_NBS_ELIBRARY_REPORT_PAGE",records)},
            {"criterion":"download_is_machine_readable_twelve_purpose_data","status":state("NGA_NBS_GDP_EXPENDITURE_2021_PDF",True),"evidence":"The official download is a PDF report and does not expose a machine-readable purpose matrix.",**_gate_source(self,"NGA_NBS_GDP_EXPENDITURE_2021_PDF",records)},
            {"criterion":"consumption_pattern_is_national_accounts_s14_p31","status":state("NGA_NBS_CONSUMPTION_PATTERN_2019",True),"evidence":"The consumption-pattern publication is household survey evidence, not national-accounts S14/P31.",**_gate_source(self,"NGA_NBS_CONSUMPTION_PATTERN_2019",records)},
            {"criterion":"consumption_pattern_reference_period_matches_2021","status":state("NGA_NBS_CONSUMPTION_PATTERN_2019",True),"evidence":"The detailed consumption study refers to 2019 rather than 2021.",**_gate_source(self,"NGA_NBS_CONSUMPTION_PATTERN_2019",records)},
        ]
        exact = "NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"The reviewed official sources separate a 2021 aggregate national-accounts component from wrong-period household-survey detail; neither is an exact twelve-purpose matrix.",**_gate_source(self,"NGA_NBS_ELIBRARY_REPORT_PAGE",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows

    def validate_gate_rows(self, rows):
        validate_nigeria_methodology_gate_rows(rows)


class BangladeshBbsAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code = "BGD"
    economy_name = "Bangladesh"
    adapter_id = "BGD_BBS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Bangladesh Bureau of Statistics"
    reference_period = "2021"
    audit_categories = ALL_ARMILAR_CATEGORIES
    source_specs = (
        {
            "source_id":"BGD_BBS_NSDS_PORTAL",
            "url":"https://nsds.bbs.gov.bd/",
            "filename":"nsds_portal.html",
            "accept":"text/html,*/*;q=0.1",
            "family":"official_statistical_database",
            "concept":"BBS national statistical dissemination portal",
            "classification":"AGGREGATE_STATISTICAL_PORTAL",
            "required_markers":("bangladesh bureau of statistics","gross domestic product","million bdt"),
            "source_decision":"REJECT_AGGREGATE_PORTAL_ONLY",
            "rejection_reason":"The official portal exposes aggregate indicators but no pinned current-price 2021 S14/P31 table by twelve purposes.",
            "institutional_sector":"AGGREGATE_NATIONAL_ACCOUNTS",
            "transaction_code":"GDP_AGGREGATE",
            "current_prices":"partly",
            "currency":"BDT",
            "unit":"million bdt",
        },
        {
            "source_id":"BGD_BBS_RELEASE_CALENDAR_NATIONAL_ACCOUNTS",
            "url":"https://nsds.bbs.gov.bd/en/release-calendar",
            "filename":"release_calendar.html",
            "accept":"text/html,*/*;q=0.1",
            "family":"official_structured_publications",
            "concept":"Official release calendar for national accounts",
            "classification":"PUBLICATION_INVENTORY",
            "required_markers":("national accounts statistics","provisional estimates of gdp"),
            "source_decision":"REJECT_INVENTORY_WITHOUT_EXACT_DATASET",
            "rejection_reason":"The release calendar confirms national-accounts publications but does not itself supply twelve-purpose HFCE values.",
            "institutional_sector":"MULTIPLE",
            "transaction_code":"PUBLICATION_INVENTORY",
            "current_prices":"unknown",
            "currency":"BDT",
        },
        {
            "source_id":"BGD_BBS_HIES_DOCUMENTATION",
            "url":"https://nsds.bbs.gov.bd/en/posts/85/Survey%20documentation%20for%20the%20Household%20Income%20and%20Expenditure%20Survey",
            "filename":"hies_documentation.html",
            "accept":"text/html,*/*;q=0.1",
            "family":"survey_or_cpi_class_c_only",
            "concept":"Household Income and Expenditure Survey documentation",
            "classification":"HIES_HOUSEHOLD_SURVEY",
            "required_markers":("household income and expenditure survey","core activities","household"),
            "source_decision":"REJECT_CLASS_C_SURVEY",
            "rejection_reason":"HIES is household-survey evidence and cannot substitute for national-accounts S14/P31 expenditure.",
            "reference_period":"2022",
            "institutional_sector":"HOUSEHOLD_SURVEY",
            "transaction_code":"NOT_SNA_P31",
            "current_prices":"true",
            "currency":"BDT",
            "unit":"survey household expenditure",
            "npish_treatment":"OUTSIDE_SURVEY_SCOPE",
            "government_treatment":"OUTSIDE_SURVEY_SCOPE",
        },
        {
            "source_id":"BGD_BBS_HIES_2022_FINAL_REPORT_PAGE",
            "url":"https://nsds.bbs.gov.bd/en/posts/161/Final%20Report%20of%20Household%20Income%20and%20Expenditure%20Survey%20%28HIES%29%202016",
            "filename":"hies_2022_final_report_page.html",
            "accept":"text/html,*/*;q=0.1",
            "family":"official_structured_publications",
            "concept":"Final Report of HIES 2022",
            "classification":"HIES_2022_PUBLICATION",
            "required_markers":("final report","household income and expenditure survey","2022"),
            "source_decision":"REJECT_WRONG_PERIOD_SURVEY_REPORT",
            "rejection_reason":"The final HIES report refers to 2022 and remains a survey publication rather than a 2021 national-accounts purpose matrix.",
            "reference_period":"2022",
            "institutional_sector":"HOUSEHOLD_SURVEY",
            "transaction_code":"NOT_SNA_P31",
            "current_prices":"true",
            "currency":"BDT",
            "unit":"survey report",
        },
        {
            "source_id":"BGD_BBS_PORTAL",
            "url":"https://bbs.portal.gov.bd/",
            "filename":"bbs_portal.html",
            "accept":"text/html,*/*;q=0.1",
            "family":"official_structured_publications",
            "concept":"BBS institutional portal",
            "classification":"DISCOVERY_PORTAL",
            "required_markers":(),
            "source_decision":"DISCOVERY_ONLY",
            "rejection_reason":"The institutional portal is a discovery route, not a dataset.",
        },
    )
    core_source_ids={"BGD_BBS_NSDS_PORTAL","BGD_BBS_RELEASE_CALENDAR_NATIONAL_ACCOUNTS","BGD_BBS_HIES_DOCUMENTATION","BGD_BBS_HIES_2022_FINAL_REPORT_PAGE"}
    def closed_rejection_reason(self)->str:
        return "The BBS dissemination portal and release calendar confirm aggregate national-accounts publications, while the detailed expenditure source located is HIES 2022, a household survey. No reviewed source provides current-price calendar-2021 S14/P31 expenditure by all twelve Armilar purposes."
    def build_gate_rows(self,records,analyses,errors):
        def state(source_id,contradiction=False):
            if source_id in errors:return "NOT_FOUND"
            if analyses.get(source_id,{}).get("expected_evidence_confirmed"):return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows=[
            {"criterion":"official_national_statistics_portal_acquired","status":state("BGD_BBS_NSDS_PORTAL"),"evidence":"The official BBS dissemination portal was acquired.",**_gate_source(self,"BGD_BBS_NSDS_PORTAL",records)},
            {"criterion":"national_accounts_release_family_identified","status":state("BGD_BBS_RELEASE_CALENDAR_NATIONAL_ACCOUNTS"),"evidence":"The official release calendar identifies national-accounts publications.",**_gate_source(self,"BGD_BBS_RELEASE_CALENDAR_NATIONAL_ACCOUNTS",records)},
            {"criterion":"twelve_armilar_purposes_available_in_national_accounts","status":state("BGD_BBS_NSDS_PORTAL",True),"evidence":"The reviewed portal evidence remains aggregate and does not expose twelve-purpose household expenditure.",**_gate_source(self,"BGD_BBS_NSDS_PORTAL",records)},
            {"criterion":"hies_is_national_accounts_s14_p31","status":state("BGD_BBS_HIES_DOCUMENTATION",True),"evidence":"HIES is explicitly a household survey rather than national-accounts S14/P31.",**_gate_source(self,"BGD_BBS_HIES_DOCUMENTATION",records)},
            {"criterion":"hies_reference_period_matches_2021","status":state("BGD_BBS_HIES_2022_FINAL_REPORT_PAGE",True),"evidence":"The located final HIES report refers to 2022 rather than 2021.",**_gate_source(self,"BGD_BBS_HIES_2022_FINAL_REPORT_PAGE",records)},
        ]
        exact="NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"No reviewed BBS source combines 2021, current prices, strict household national accounts and twelve-purpose coverage.",**_gate_source(self,"BGD_BBS_NSDS_PORTAL",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows
    def validate_gate_rows(self,rows):validate_bangladesh_methodology_gate_rows(rows)


class VietnamNsoAuditAdapter(OfficialFamilyAuditAdapter):
    economy_code="VNM"
    economy_name="Viet Nam"
    adapter_id="VNM_NSO_OFFICIAL_SOURCE_AUDIT"
    source_authority="National Statistics Office of Viet Nam"
    reference_period="2021"
    audit_categories=ALL_ARMILAR_CATEGORIES
    source_specs=(
        {"source_id":"VNM_NSO_STATISTICAL_DATA_PORTAL","url":"https://www.nso.gov.vn/en/statistical-data/","filename":"statistical_data.html","accept":"text/html,*/*;q=0.1","family":"official_statistical_database","concept":"NSO statistical data portal","classification":"STATISTICAL_TABLE_CATALOGUE","required_markers":("statistical data","national accounts"),"source_decision":"REJECT_CATALOGUE_WITHOUT_PINNED_EXACT_TABLE","rejection_reason":"The official statistical-data catalogue does not itself provide a pinned 2021 S14/P31 twelve-purpose table.","currency":"VND"},
        {"source_id":"VNM_NSO_SOCIO_ECONOMIC_2021","url":"https://www.nso.gov.vn/en/data-and-statistics/2022/01/socio-economic-situation-in-the-fourth-quarter-and-2021/","filename":"socio_economic_2021.html","accept":"text/html,*/*;q=0.1","family":"official_structured_publications","concept":"Socio-economic situation in fourth quarter and 2021","classification":"GDP_USE_AGGREGATE_RELEASE","required_markers":("gdp use in 2021","final consumption increased","accumulated assets"),"source_decision":"REJECT_AGGREGATE_GROWTH_ONLY","rejection_reason":"The 2021 release reports aggregate final-consumption growth, not household expenditure levels by purpose.","institutional_sector":"ALL_FINAL_CONSUMPTION_AGGREGATE","transaction_code":"FINAL_CONSUMPTION_AGGREGATE","current_prices":"false_growth_rate_only","currency":"VND","unit":"growth rate"},
        {"source_id":"VNM_NSO_VHLSS_2022","url":"https://www.nso.gov.vn/en/default/2024/04/results-of-the-viet-nam-household-living-standards-survey-2022/","filename":"vhlss_2022.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Viet Nam Household Living Standards Survey 2022","classification":"VHLSS_HOUSEHOLD_SURVEY","required_markers":("household living standards survey 2022","living standards","consumption expenditure"),"source_decision":"REJECT_CLASS_C_WRONG_PERIOD_SURVEY","rejection_reason":"VHLSS 2022 is a household survey with the wrong period and cannot replace national-accounts S14/P31.","reference_period":"2022","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","current_prices":"true","currency":"VND","unit":"survey household expenditure","npish_treatment":"OUTSIDE_SURVEY_SCOPE","government_treatment":"OUTSIDE_SURVEY_SCOPE"},
        {"source_id":"VNM_NSO_VHLSS_2020","url":"https://www.nso.gov.vn/en/data-and-statistics/2022/06/results-of-the-viet-nam-household-living-standards-survey-2020/","filename":"vhlss_2020.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Viet Nam Household Living Standards Survey 2020","classification":"VHLSS_HOUSEHOLD_SURVEY","required_markers":("household living standards survey 2020","consumption expenditure"),"source_decision":"REJECT_CLASS_C_WRONG_PERIOD_SURVEY","rejection_reason":"VHLSS 2020 is a household survey and does not match the 2021 national-accounts benchmark.","reference_period":"2020","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","current_prices":"true","currency":"VND","unit":"survey household expenditure","npish_treatment":"OUTSIDE_SURVEY_SCOPE","government_treatment":"OUTSIDE_SURVEY_SCOPE"},
        {"source_id":"VNM_NSO_HOMEPAGE","url":"https://www.nso.gov.vn/en/homepage/","filename":"homepage.html","accept":"text/html,*/*;q=0.1","family":"official_structured_publications","concept":"NSO institutional homepage","classification":"DISCOVERY_PORTAL","required_markers":("national statistics office",),"source_decision":"DISCOVERY_ONLY","rejection_reason":"The homepage is a discovery route, not a dataset."},
    )
    core_source_ids={"VNM_NSO_STATISTICAL_DATA_PORTAL","VNM_NSO_SOCIO_ECONOMIC_2021","VNM_NSO_VHLSS_2022","VNM_NSO_VHLSS_2020"}
    def closed_rejection_reason(self)->str:
        return "The NSO 2021 socio-economic release reports aggregate final-consumption growth, while the located detailed household sources are VHLSS surveys for 2020 and 2022. No reviewed source provides current-price 2021 strict S14/P31 expenditure by all twelve Armilar purposes."
    def build_gate_rows(self,records,analyses,errors):
        def state(source_id,contradiction=False):
            if source_id in errors:return "NOT_FOUND"
            if analyses.get(source_id,{}).get("expected_evidence_confirmed"):return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows=[
            {"criterion":"official_statistical_data_portal_acquired","status":state("VNM_NSO_STATISTICAL_DATA_PORTAL"),"evidence":"The official NSO statistical-data portal was acquired.",**_gate_source(self,"VNM_NSO_STATISTICAL_DATA_PORTAL",records)},
            {"criterion":"2021_final_consumption_release_acquired","status":state("VNM_NSO_SOCIO_ECONOMIC_2021"),"evidence":"The official 2021 socio-economic release was acquired.",**_gate_source(self,"VNM_NSO_SOCIO_ECONOMIC_2021",records)},
            {"criterion":"2021_release_is_household_level_by_purpose","status":state("VNM_NSO_SOCIO_ECONOMIC_2021",True),"evidence":"The release reports aggregate final-consumption growth and no household-purpose levels.",**_gate_source(self,"VNM_NSO_SOCIO_ECONOMIC_2021",records)},
            {"criterion":"vhlss_is_national_accounts_s14_p31","status":state("VNM_NSO_VHLSS_2022",True),"evidence":"VHLSS is a living-standards household survey, not national-accounts S14/P31.",**_gate_source(self,"VNM_NSO_VHLSS_2022",records)},
            {"criterion":"vhlss_reference_period_matches_2021","status":state("VNM_NSO_VHLSS_2022",True),"evidence":"The located VHLSS rounds are 2020 and 2022 rather than 2021.",**_gate_source(self,"VNM_NSO_VHLSS_2022",records)},
        ]
        exact="NOT_FOUND" if any(x in errors for x in self.core_source_ids) else ("CONTRADICTED" if all(analyses.get(x,{}).get("expected_evidence_confirmed") for x in self.core_source_ids) else "AMBIGUOUS")
        rows.append({"criterion":"exact_armilar_source_available","status":exact,"evidence":"No reviewed NSO source combines 2021, current prices, strict household national accounts and twelve-purpose coverage.",**_gate_source(self,"VNM_NSO_STATISTICAL_DATA_PORTAL",records,"CROSS_SOURCE_METHOD_GATE")})
        return rows
    def validate_gate_rows(self,rows):validate_vietnam_methodology_gate_rows(rows)



class Step2HExceptionOfficialAuditAdapter(OfficialFamilyAuditAdapter):
    gate_criteria: tuple[tuple[str, str, bool, str], ...] = ()

    def build_gate_rows(self, records, analyses, errors):
        def state(source_id: str, contradiction: bool = False) -> str:
            if source_id in errors:
                return "NOT_FOUND"
            if analyses.get(source_id, {}).get("expected_evidence_confirmed"):
                return "CONTRADICTED" if contradiction else "CONFIRMED"
            return "AMBIGUOUS"
        rows = []
        for criterion, source_id, contradiction, evidence in self.gate_criteria:
            rows.append({
                "criterion": criterion,
                "status": state(source_id, contradiction),
                "evidence": evidence,
                **_gate_source(self, source_id, records),
            })
        exact = "NOT_FOUND" if any(x in errors for x in self.core_source_ids) else (
            "CONTRADICTED" if all(analyses.get(x, {}).get("expected_evidence_confirmed") for x in self.core_source_ids)
            else "AMBIGUOUS"
        )
        rows.append({
            "criterion": "exact_armilar_source_available",
            "status": exact,
            "evidence": self.closed_rejection_reason(),
            **_gate_source(self, next(iter(sorted(self.core_source_ids))), records, "CROSS_SOURCE_METHOD_GATE"),
        })
        return rows

    def validate_gate_rows(self, rows):
        required = {criterion for criterion, *_ in self.gate_criteria} | {"exact_armilar_source_available"}
        _validate_country_gate_rows(
            rows, required, {"CONFIRMED", "CONTRADICTED", "AMBIGUOUS", "NOT_FOUND"}, self.economy_name
        )


class BelarusBelstatExceptionAuditAdapter(Step2HExceptionOfficialAuditAdapter):
    economy_code = "BLR"
    economy_name = "Belarus"
    adapter_id = "BLR_BELSTAT_CP02_EXCEPTION_AUDIT"
    source_authority = "National Statistical Committee of the Republic of Belarus"
    reference_period = "2021"
    audit_categories = ("CP02",)
    exception_category = "CP02"
    exception_current_status = "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100"
    exception_resolution_attempted = "Belstat 2022 Statistical Yearbook and household living-standards publication audited as official source families."
    exception_reason = "The reviewed official publications do not establish a current-price national-accounts CP02 aggregate excluding narcotics or separate strict-HFCE alcohol and tobacco cells that can be combined without allocation."
    source_specs = (
        {"source_id":"BLR_BELSTAT_YEARBOOK_2022","url":"https://belstat.gov.by/upload/iblock/57e/a76lpm9rtfb8x0l0o2t3wfts61arbk2q.pdf","filename":"statistical_yearbook_2022.pdf","accept":"application/pdf,*/*;q=0.1","family":"official_structured_publications","concept":"Statistical Yearbook of the Republic of Belarus 2022","classification":"MULTI_SOURCE_YEARBOOK","required_markers":(),"source_decision":"REJECT_NO_STRICT_CP02_NATIONAL_ACCOUNTS_CELL","rejection_reason":"The yearbook covers 2021 but does not provide an admissible strict-HFCE CP02 cell with narcotics excluded.","currency":"BYN","unit":"multiple"},
        {"source_id":"BLR_BELSTAT_LIVING_STANDARDS","url":"https://www.belstat.gov.by/upload/iblock/747/h2d3js5a6ro9svs5xv2zi0fb8ov7o41i.pdf","filename":"living_standards.pdf","accept":"application/pdf,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Social Situation and Living Standards household expenditure publication","classification":"HOUSEHOLD_SAMPLE_SURVEY_PUBLICATION","required_markers":(),"source_decision":"REJECT_CLASS_C_SURVEY","rejection_reason":"Household living-standards expenditure is survey evidence and cannot replace national-accounts S14/P31 purpose weights.","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","currency":"BYN"},
    )
    core_source_ids = {"BLR_BELSTAT_YEARBOOK_2022", "BLR_BELSTAT_LIVING_STANDARDS"}
    gate_criteria = (
        ("official_2021_publication_acquired","BLR_BELSTAT_YEARBOOK_2022",False,"The official yearbook covering 2021 was acquired."),
        ("cp02_narcotics_excluded_exactly","BLR_BELSTAT_YEARBOOK_2022",True,"No reviewed exact national-accounts CP02 aggregate excluding narcotics was identified."),
        ("household_survey_can_supply_exact_cp02","BLR_BELSTAT_LIVING_STANDARDS",True,"The living-standards source is survey evidence rather than S14/P31 national accounts."),
    )
    def closed_rejection_reason(self): return self.exception_reason


class KuwaitCsbExceptionAuditAdapter(Step2HExceptionOfficialAuditAdapter):
    economy_code = "KWT"
    economy_name = "Kuwait"
    adapter_id = "KWT_CSB_CP02_EXCEPTION_AUDIT"
    source_authority = "Kuwait Central Statistical Bureau"
    reference_period = "2021"
    audit_categories = ("CP02",)
    exception_category = "CP02"
    exception_current_status = "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100"
    exception_resolution_attempted = "Official 2019/2021 household income and expenditure survey and input-output publication inventories audited."
    exception_reason = "The 2019/2021 detailed source is a household survey, while the official input-output inventory only exposes substantially older product tables. No strict 2021 national-accounts CP02 source excluding narcotics passed the gates."
    source_specs = (
        {"source_id":"KWT_CSB_HIES_2019_2021","url":"https://www.csb.gov.kw/Pages/Statistics_en?ID=16&ParentCatID=+1","filename":"hies_2019_2021.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Household income and expenditure survey 2019/2021","classification":"HOUSEHOLD_SURVEY","required_markers":("household income and expendeture survey 2019/2021","2021"),"source_decision":"REJECT_CLASS_C_SURVEY","rejection_reason":"The detailed 2021 source is a household survey and cannot supply exact national-accounts CP02 weights.","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","currency":"KWD"},
        {"source_id":"KWT_CSB_INPUT_OUTPUT_INVENTORY","url":"https://www.csb.gov.kw/Pages/Statistics_en?ID=26&ParentCatID=+3","filename":"input_output_inventory.html","accept":"text/html,*/*;q=0.1","family":"official_input_output_tables","concept":"National Accounts Statistics Input and Output Tables inventory","classification":"HISTORICAL_PRODUCT_IO_TABLES","required_markers":("input & output tables","2005-2010"),"source_decision":"REJECT_WRONG_PERIOD_PRODUCT_TABLES","rejection_reason":"The listed input-output sources are historical and product-based, not a 2021 purpose-classified CP02 table.","reference_period":"2000-2010","currency":"KWD"},
    )
    core_source_ids = {"KWT_CSB_HIES_2019_2021", "KWT_CSB_INPUT_OUTPUT_INVENTORY"}
    gate_criteria = (
        ("hies_2021_source_acquired","KWT_CSB_HIES_2019_2021",False,"The official 2019/2021 household survey publication was acquired."),
        ("hies_is_national_accounts_s14_p31","KWT_CSB_HIES_2019_2021",True,"The detailed source is a household survey, not national accounts."),
        ("input_output_reference_period_matches_2021","KWT_CSB_INPUT_OUTPUT_INVENTORY",True,"The official inventory lists older input-output tables rather than 2021."),
        ("cp02_narcotics_excluded_exactly","KWT_CSB_HIES_2019_2021",True,"No exact strict-HFCE alcohol+tobacco aggregate excluding narcotics is established."),
    )
    def closed_rejection_reason(self): return self.exception_reason


class SaudiGastatExceptionAuditAdapter(Step2HExceptionOfficialAuditAdapter):
    economy_code = "SAU"
    economy_name = "Saudi Arabia"
    adapter_id = "SAU_GASTAT_CP02_EXCEPTION_AUDIT"
    source_authority = "General Authority for Statistics"
    reference_period = "2021"
    audit_categories = ("CP02",)
    exception_category = "CP02"
    exception_current_status = "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100"
    exception_resolution_attempted = "Official SUT/IO, annual national accounts and household expenditure methodology families audited."
    exception_reason = "GASTAT confirms detailed SUTs and household expenditure surveys, but the reviewed evidence does not establish a 2021 strict-HFCE CP02 purpose cell with tobacco isolated and narcotics excluded without allocation."
    source_specs = (
        {"source_id":"SAU_GASTAT_SUT_IO_2018_2023","url":"https://www.stats.gov.sa/en/w/supply-and-use-input-output-tables-2019","filename":"sut_io_2018_2023.html","accept":"text/html,*/*;q=0.1","family":"official_supply_and_use_tables","concept":"Supply and Use and Input-Output Tables by Divisions 2018-2023","classification":"PRODUCT_DIVISION_SUT_IO","required_markers":("supply and use tables","2018-2023"),"source_decision":"REJECT_PRODUCT_TABLE_WITHOUT_EXACT_PURPOSE_BRIDGE","rejection_reason":"Product-division SUT/IO data do not by themselves provide a strict purpose-classified CP02 cell.","current_prices":"true","currency":"SAR"},
        {"source_id":"SAU_GASTAT_HOUSEHOLD_EXPENDITURE_SURVEY","url":"https://www.stats.gov.sa/en/w/hes-2","filename":"household_expenditure_survey.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Household Expenditure Survey","classification":"COICOP_HOUSEHOLD_SURVEY","required_markers":("field-based household surveys","classification of individual consumption according to purpose"),"source_decision":"REJECT_CLASS_C_SURVEY","rejection_reason":"The source is a household survey used for CPI weights, not an exact national-accounts S14/P31 matrix.","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","currency":"SAR"},
        {"source_id":"SAU_GASTAT_ANNUAL_NA_METHOD","url":"https://www.stats.gov.sa/en/w/methodology-and-quality-report-for-annual-national-accounts","filename":"annual_national_accounts_method.html","accept":"text/html,*/*;q=0.1","family":"official_classifications_methodology","concept":"Annual National Accounts methodology","classification":"SNA_2008_METHOD_DOCUMENT","required_markers":("annual national accounts","supply and use"),"source_decision":"METHODOLOGY_ONLY","rejection_reason":"The methodology documents the accounts but is not a 2021 purpose-value dataset.","currency":"SAR"},
    )
    core_source_ids = {"SAU_GASTAT_SUT_IO_2018_2023", "SAU_GASTAT_HOUSEHOLD_EXPENDITURE_SURVEY", "SAU_GASTAT_ANNUAL_NA_METHOD"}
    gate_criteria = (
        ("sut_family_acquired","SAU_GASTAT_SUT_IO_2018_2023",False,"The official SUT/IO family was acquired."),
        ("sut_is_exact_purpose_cp02_source","SAU_GASTAT_SUT_IO_2018_2023",True,"The tables are organised by product divisions and require a bridge to household purposes."),
        ("survey_is_national_accounts_s14_p31","SAU_GASTAT_HOUSEHOLD_EXPENDITURE_SURVEY",True,"The household expenditure source is a field survey."),
        ("cp02_narcotics_excluded_exactly","SAU_GASTAT_HOUSEHOLD_EXPENDITURE_SURVEY",True,"No exact 2021 strict-HFCE CP02 cell excluding narcotics is established."),
    )
    def closed_rejection_reason(self): return self.exception_reason


class BonaireCbsExceptionAuditAdapter(Step2HExceptionOfficialAuditAdapter):
    economy_code = "BON"
    economy_name = "Bonaire"
    adapter_id = "BON_CBS_TWELVE_CATEGORY_EXCEPTION_AUDIT"
    source_authority = "Statistics Netherlands"
    reference_period = "2021"
    audit_categories = ALL_ARMILAR_CATEGORIES
    exception_category = "*"
    exception_current_status = "0/12 categories available in exact Source 90 matrix"
    exception_resolution_attempted = "CBS Caribbean Netherlands CPI weights and Bonaire GDP tables audited separately."
    exception_reason = "CBS publishes twelve CPI product-group weights for Caribbean Netherlands and aggregate Bonaire GDP, but CPI weights are not national-accounts S14/P31 expenditure values and the GDP table is not purpose-classified HFCE."
    source_specs = (
        {"source_id":"BON_CBS_CPI_WEIGHTS","url":"https://www.cbs.nl/en-gb/figures/detail/84046ENG","filename":"cpi_weights.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"Caribbean Netherlands CPI and weighting coefficients","classification":"CPI_12_PRODUCT_GROUPS","required_markers":("12 product groups","weighting coefficient"),"source_decision":"REJECT_CPI_WEIGHTS_AS_EXACT_HFCE","rejection_reason":"The twelve-group weights are CPI expenditure weights, not national-accounts S14/P31 values.","institutional_sector":"CPI_HOUSEHOLD_BASKET","transaction_code":"CPI_WEIGHTS","currency":"USD"},
        {"source_id":"BON_CBS_GDP","url":"https://www.cbs.nl/en-gb/figures/detail/84789ENG","filename":"gdp.html","accept":"text/html,*/*;q=0.1","family":"official_statistical_database","concept":"Bonaire gross domestic product","classification":"GDP_AGGREGATE","required_markers":("gross domestic product","bonaire"),"source_decision":"REJECT_GDP_WITHOUT_PURPOSE_HFCE","rejection_reason":"The GDP table contains macroeconomic aggregates and no twelve-purpose household consumption matrix.","current_prices":"true","currency":"USD"},
    )
    core_source_ids = {"BON_CBS_CPI_WEIGHTS", "BON_CBS_GDP"}
    gate_criteria = (
        ("twelve_group_cpi_weights_available","BON_CBS_CPI_WEIGHTS",False,"CBS publishes twelve CPI product groups with weighting coefficients."),
        ("cpi_weights_are_national_accounts_s14_p31","BON_CBS_CPI_WEIGHTS",True,"CPI weights are not national-accounts expenditure values."),
        ("bonaire_gdp_is_purpose_classified_hfce","BON_CBS_GDP",True,"The GDP table is not household consumption by purpose."),
    )
    def closed_rejection_reason(self): return self.exception_reason


class LiberiaLisgisExceptionAuditAdapter(Step2HExceptionOfficialAuditAdapter):
    economy_code = "LBR"
    economy_name = "Liberia"
    adapter_id = "LBR_LISGIS_UNIT_CONCEPT_EXCEPTION_AUDIT"
    source_authority = "Liberia Institute of Statistics and Geo-Information Services"
    reference_period = "2021"
    audit_categories = ("CP04","CP06","CP09","CP10","CP12")
    exception_category = "CP04|CP06|CP09|CP10|CP12"
    exception_current_status = "SUPPLEMENTAL_NOMINAL_SOURCE_FAILED_UNIT_RECONCILIATION"
    exception_resolution_attempted = "LISGIS 2016-2022 GDP report and official HIES publication family audited for unit, currency and sector concepts."
    exception_reason = "The GDP report separates expenditure aggregates but does not supply a compatible twelve-purpose S14 matrix, while HIES is survey evidence. The existing supplemental nominal rows remain unreconciled in unit or concept and are excluded."
    source_specs = (
        {"source_id":"LBR_LISGIS_GDP_2016_2022","url":"https://lisgis.gov.lr/admin_area/nationalaccount/gdp20162022.pdf","filename":"gdp_2016_2022.pdf","accept":"application/pdf,*/*;q=0.1","family":"official_structured_publications","concept":"Liberia GDP Report 2016-2022","classification":"EXPENDITURE_GDP_AGGREGATES","required_markers":(),"source_decision":"REJECT_AGGREGATE_MULTI_SECTOR_CONSUMPTION","rejection_reason":"The report discusses household, government and NPISH final consumption at aggregate level, not strict S14 values by twelve purposes.","institutional_sector":"HOUSEHOLDS_GOVERNMENT_NPISH_AGGREGATES","transaction_code":"FINAL_CONSUMPTION_AGGREGATES","current_prices":"true","currency":"LRD_OR_USD_REQUIRES_TABLE_LEVEL_CONFIRMATION","unit":"REPORT_SPECIFIC"},
        {"source_id":"LBR_LISGIS_HIES_PORTAL","url":"https://lisgis.gov.lr/","filename":"lisgis_hies_portal.html","accept":"text/html,*/*;q=0.1","family":"survey_or_cpi_class_c_only","concept":"LISGIS Household Income and Expenditure Survey publications","classification":"HIES_SURVEY_PUBLICATION_FAMILY","required_markers":("household income and expenditure survey",),"source_decision":"REJECT_CLASS_C_SURVEY","rejection_reason":"HIES is survey evidence and cannot resolve the national-accounts unit/concept mismatch as exact weights.","institutional_sector":"HOUSEHOLD_SURVEY","transaction_code":"NOT_SNA_P31","currency":"LRD"},
    )
    core_source_ids = {"LBR_LISGIS_GDP_2016_2022", "LBR_LISGIS_HIES_PORTAL"}
    gate_criteria = (
        ("official_gdp_report_acquired","LBR_LISGIS_GDP_2016_2022",False,"The official 2016-2022 GDP report was acquired."),
        ("gdp_report_is_twelve_purpose_s14_matrix","LBR_LISGIS_GDP_2016_2022",True,"The report provides expenditure aggregates rather than a twelve-purpose S14 matrix."),
        ("currency_and_unit_identified_for_supplemental_rows","LBR_LISGIS_GDP_2016_2022",True,"The prior supplemental rows cannot be reconciled to a unique compatible currency/unit/concept from the reviewed source."),
        ("hies_can_resolve_exact_national_accounts_weights","LBR_LISGIS_HIES_PORTAL",True,"HIES is survey evidence and cannot substitute for national accounts."),
    )
    def closed_rejection_reason(self): return self.exception_reason


def validate_indonesia_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"official_grouped_hfce_publication_available","twelve_armilar_purposes_available","sut_is_exact_purpose_source","input_output_is_exact_purpose_source","survey_or_cpi_can_supply_exact_weights","exact_armilar_source_available"}, INDONESIA_GATE_STATUSES, "Indonesia")


def validate_brazil_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"sidra_national_accounts_family_identified","scn_exact_twelve_purpose_table_identified","cei_is_purpose_classified_hfce","tru_is_exact_purpose_source","pof_or_ipca_can_supply_exact_weights","exact_armilar_source_available"}, BRAZIL_GATE_STATUSES, "Brazil")


def validate_egypt_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"national_accounts_catalogue_acquired","machine_readable_catalogue_inventory_acquired","sut_reference_period_matches_2021","sut_is_exact_purpose_classification","hiecs_is_national_accounts_s14_p31","hiecs_reference_period_matches_2021","exact_armilar_source_available"}, EGYPT_GATE_STATUSES, "Egypt")

def validate_pakistan_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"annual_national_accounts_source_acquired","machine_readable_2021_22_hfce_aggregate_acquired","reference_period_matches_calendar_2021","twelve_armilar_purposes_available_in_national_accounts","hies_is_national_accounts_s14_p31","hies_reference_period_matches_2021","exact_armilar_source_available"}, PAKISTAN_GATE_STATUSES, "Pakistan")

def validate_nigeria_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"gdp_expenditure_2021_source_acquired","household_consumption_is_purpose_classified","download_is_machine_readable_twelve_purpose_data","consumption_pattern_is_national_accounts_s14_p31","consumption_pattern_reference_period_matches_2021","exact_armilar_source_available"}, NIGERIA_GATE_STATUSES, "Nigeria")

def validate_bangladesh_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"official_national_statistics_portal_acquired","national_accounts_release_family_identified","twelve_armilar_purposes_available_in_national_accounts","hies_is_national_accounts_s14_p31","hies_reference_period_matches_2021","exact_armilar_source_available"}, BANGLADESH_GATE_STATUSES, "Bangladesh")

def validate_vietnam_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    _validate_country_gate_rows(rows, {"official_statistical_data_portal_acquired","2021_final_consumption_release_acquired","2021_release_is_household_level_by_purpose","vhlss_is_national_accounts_s14_p31","vhlss_reference_period_matches_2021","exact_armilar_source_available"}, VIETNAM_GATE_STATUSES, "Viet Nam")


def write_country_method_gate_report(path: Path, country: str, version: str, rows: list[dict[str, Any]], validator: Any) -> None:
    if rows:
        validator(rows)
    lines = [
        f"# {country} method gate report",
        "",
        f"Pipeline version: `{version}`",
        "",
        "This report preserves the official source-family evidence and the strict Armilar admissibility decision.",
        "A blocked source or changed structural marker prevents a closed rejection.",
        "",
        "| Criterion | Status | Evidence source | SHA-256 | Evidence |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        evidence = str(row.get("evidence") or "").replace("|", "\\|")
        lines.append(f"| `{row.get('criterion','')}` | `{row.get('status','')}` | `{row.get('source_id','')}` | `{row.get('source_sha256','')}` | {evidence} |")
    if not rows:
        lines.append("| No gate evidence acquired in this run | `NOT_FOUND` |  |  |  |")
    lines.extend(["", "## Decision", "", "No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
