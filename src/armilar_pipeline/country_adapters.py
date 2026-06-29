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
        AuditOnlyAdapter("EGY", "Egypt", "EGY_CAPMAS_OFFICIAL_SOURCE_AUDIT", "Central Agency for Public Mobilization and Statistics", "https://www.censusinfo.capmas.gov.eg/metadata-en-v4.2/index.php/catalog/747/overview", "2021", "HOUSEHOLD_SURVEY", "survey microdata", "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "Official HIECS is a survey source, not national-accounts S14/P31 current-price HFCE."),
        AuditOnlyAdapter("PAK", "Pakistan", "PAK_PBS_OFFICIAL_SOURCE_AUDIT", "Pakistan Bureau of Statistics", "https://www.pbs.gov.pk/national-accounts-2/", "2021-22", "HFCE_AGGREGATE", "aggregate only", "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "Public national-accounts source does not expose a twelve-category strict household table."),
        AuditOnlyAdapter("NGA", "Nigeria", "NGA_NBS_OFFICIAL_SOURCE_AUDIT", "National Bureau of Statistics", "https://www.nigerianstat.gov.ng/elibrary/read/1241168", "2021", "HFCE_AGGREGATE", "aggregate only", "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "Official expenditure-GDP report publishes aggregate household consumption, not twelve categories."),
        AuditOnlyAdapter("BGD", "Bangladesh", "BGD_BBS_OFFICIAL_SOURCE_AUDIT", "Bangladesh Bureau of Statistics", "https://nsds.bbs.gov.bd/en/posts/85/Survey%20documentation%20for%20the%20Household%20Income%20and%20Expenditure%20Survey", "2022", "HOUSEHOLD_SURVEY", "survey", "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "Official HIES reference year and concept do not satisfy 2021 national-accounts HFCE gates."),
        AuditOnlyAdapter("VNM", "Viet Nam", "VNM_NSO_OFFICIAL_SOURCE_AUDIT", "National Statistics Office of Viet Nam", "https://www.nso.gov.vn/en/default/2024/04/results-of-the-viet-nam-household-living-standards-survey-2022/", "2022", "HOUSEHOLD_SURVEY", "survey", "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", "Official VHLSS is 2022 survey evidence only, not exact 2021 S14/P31 HFCE."),
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
    write_csv(out / "step2h_exception_audit.csv", STEP2H_EXCEPTION_FIELDS, result.step2h_exception_rows or step2h_exception_rows())
    write_json(out / "step2i_completion_summary.json", step2i_completion_summary(result))
    write_json(out / "step2i_audit_summary.json", step2i_audit_summary(result))
    write_step2i_report(out / "STEP_2I_COMPLETION_REPORT.md", result)
    write_step2i_audit_report(out / "STEP_2I_AUDIT_REPORT.md", result)
    write_india_method_gate_report(out / "INDIA_METHOD_GATE_REPORT.md", result.india_gate_rows or [])
    write_russia_method_gate_report(out / "RUSSIA_METHOD_GATE_REPORT.md", result.russia_gate_rows or [])
    write_china_method_gate_report(out / "CHINA_METHOD_GATE_REPORT.md", result.china_gate_rows or [])
    write_indonesia_method_gate_report(out / "INDONESIA_METHOD_GATE_REPORT.md", result.indonesia_gate_rows or [])
    write_brazil_method_gate_report(out / "BRAZIL_METHOD_GATE_REPORT.md", result.brazil_gate_rows or [])


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


class IndonesiaBpsAuditAdapter:
    economy_code = "IDN"
    economy_name = "Indonesia"
    adapter_id = "IDN_BPS_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Badan Pusat Statistik"
    reference_period = "2021"

    source_specs = (
        {
            "source_id": "IDN_BPS_GDP_EXPENDITURE_2020_2024",
            "url": "https://www.bps.go.id/en/publication/2025/05/28/2a1c585ebbd574dd91afed67/gross-domestic-product-of-indonesia-by-expenditure--2020-2024.html",
            "filename": "gdp_by_expenditure_2020_2024.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "GDP by expenditure publication with household consumption groups",
            "classification": "HFCE_REGROUPED_PUBLICATION",
        },
        {
            "source_id": "IDN_BPS_STATISTICS_TABLES_EXPENDITURE",
            "url": "https://www.bps.go.id/en/statistics-table?subject=531",
            "filename": "statistics_tables_expenditure.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_statistical_database",
            "concept": "BPS official statistics tables for expenditure-side national accounts",
            "classification": "BPS_DATABASE_DISCOVERY",
        },
        {
            "source_id": "IDN_BPS_NATIONAL_ACCOUNTS_DOWNLOAD_SEARCH",
            "url": "https://www.bps.go.id/en/publication?keyword=gross%20domestic%20product%20expenditure",
            "filename": "national_accounts_download_search.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_csv_xls_xlsx",
            "concept": "Official downloadable national-accounts publication search",
            "classification": "DOWNLOAD_DISCOVERY_ONLY",
        },
        {
            "source_id": "IDN_BPS_SUPPLY_USE_TABLES",
            "url": "https://www.bps.go.id/en/publication?keyword=supply%20use%20table",
            "filename": "supply_use_tables_search.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_supply_and_use_tables",
            "concept": "Official BPS supply and use table publication family",
            "classification": "SUT_PRODUCT_TABLE_DISCOVERY",
        },
        {
            "source_id": "IDN_BPS_INPUT_OUTPUT_TABLES",
            "url": "https://www.bps.go.id/en/publication?keyword=input%20output%20table",
            "filename": "input_output_tables_search.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_input_output_tables",
            "concept": "Official BPS input-output table publication family",
            "classification": "INPUT_OUTPUT_PRODUCT_TABLE_DISCOVERY",
        },
        {
            "source_id": "IDN_BPS_SURVEY_OR_CPI_CLASS_C",
            "url": "https://www.bps.go.id/en/statistics-table?subject=3",
            "filename": "survey_or_cpi_class_c.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "BPS household survey or CPI evidence",
            "classification": "SURVEY_OR_CPI_CLASS_C_ONLY",
        },
        {
            "source_id": "IDN_BPS_CLASSIFICATION_METHODOLOGY",
            "url": "https://www.bps.go.id/en/publication?keyword=classification%20coicop",
            "filename": "classification_methodology_search.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_classifications_methodology",
            "concept": "Official classification and methodology documents",
            "classification": "CLASSIFICATION_METHODOLOGY_DISCOVERY",
        },
    )
    core_source_ids = {
        "IDN_BPS_GDP_EXPENDITURE_2020_2024",
        "IDN_BPS_STATISTICS_TABLES_EXPENDITURE",
        "IDN_BPS_SUPPLY_USE_TABLES",
        "IDN_BPS_INPUT_OUTPUT_TABLES",
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
                analyses[source_id] = analyse_indonesia_source(source_id, destination, record.content_type or "")
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
                "The current run could not acquire or validate all critical official Indonesian source families: "
                + ", ".join(core_blocked)
                + ". A closed source decision is not permitted while these attempts remain blocked."
            )
        elif unexpected:
            decision = "CONCEPT_AMBIGUOUS"
            status = "SOURCE_CONTENT_REVIEW_REQUIRED"
            blocking = (
                "Acquired official Indonesian resources did not match the reviewed structural markers for: "
                + ", ".join(unexpected)
                + ". No source is admitted until the changed content is reviewed."
            )
        else:
            decision = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            status = "REJECTED_BY_CONFIRMED_SOURCE_GATES"
            blocking = (
                "The acquired BPS expenditure publication exposes household consumption through grouped national-accounts categories rather than twelve Armilar purposes; "
                "BPS statistics-table, downloadable, SUT and input-output families are recorded as official source-family attempts but do not supply an accepted 2021 current-price S14/P31DC twelve-purpose dataset in this probe; "
                "survey or CPI evidence remains Class C only. No grouped category is split and no product-to-COICOP allocation is used."
            )

        attempts = indonesia_source_attempt_rows(records, analyses, errors, blocking)
        gates = indonesia_methodology_gate_rows(records, analyses, errors)
        validate_indonesia_methodology_gate_rows(gates)
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
            evidence_rows=indonesia_evidence_rows(records, analyses, errors, blocking),
            normalized_rows=[],
            mapping_rows=indonesia_mapping_audit_rows(analyses),
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
            indonesia_gate_rows=gates,
        )


class BrazilIbgeAuditAdapter:
    economy_code = "BRA"
    economy_name = "Brazil"
    adapter_id = "BRA_IBGE_OFFICIAL_SOURCE_AUDIT"
    source_authority = "Instituto Brasileiro de Geografia e Estatistica"
    reference_period = "2021"

    source_specs = (
        {
            "source_id": "BRA_IBGE_SIDRA_CNT_TABLES",
            "url": "https://sidra.ibge.gov.br/pesquisa/cnt/tabelas",
            "filename": "sidra_cnt_tables.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_national_accounts_api",
            "concept": "SIDRA national accounts table catalogue",
            "classification": "SIDRA_API_OR_TABLE_DISCOVERY",
        },
        {
            "source_id": "BRA_IBGE_SISTEMA_CONTAS_NACIONAIS",
            "url": "https://www.ibge.gov.br/estatisticas/economicas/comercio/9052-sistema-de-contas-nacionais-brasil.html",
            "filename": "sistema_contas_nacionais.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_structured_publications",
            "concept": "Sistema de Contas Nacionais publication family",
            "classification": "SCN_STRUCTURED_PUBLICATION",
        },
        {
            "source_id": "BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS",
            "url": "https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais.html",
            "filename": "contas_economicas_integradas.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_statistical_database",
            "concept": "Contas Economicas Integradas / national accounts source family",
            "classification": "CEI_INSTITUTIONAL_ACCOUNTS",
        },
        {
            "source_id": "BRA_IBGE_TABELAS_RECURSOS_USOS",
            "url": "https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9052-sistema-de-contas-nacionais-brasil.html",
            "filename": "tabelas_recursos_usos.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_supply_and_use_tables",
            "concept": "Tabelas de Recursos e Usos",
            "classification": "TRU_PRODUCT_TABLES",
        },
        {
            "source_id": "BRA_IBGE_DOWNLOADABLE_SCN_TABLES",
            "url": "https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9052-sistema-de-contas-nacionais-brasil.html?=&t=downloads",
            "filename": "scn_downloads.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_csv_xls_xlsx",
            "concept": "Downloadable SCN tables",
            "classification": "DOWNLOAD_DISCOVERY_ONLY",
        },
        {
            "source_id": "BRA_IBGE_POF_IPCA_CLASS_C",
            "url": "https://www.ibge.gov.br/estatisticas/sociais/rendimento-despesa-e-consumo.html",
            "filename": "pof_ipca_class_c.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "survey_or_cpi_class_c_only",
            "concept": "POF/IPCA survey or price-index evidence",
            "classification": "SURVEY_OR_CPI_CLASS_C_ONLY",
        },
        {
            "source_id": "BRA_IBGE_CLASSIFICACOES_METODOLOGIA",
            "url": "https://www.ibge.gov.br/estatisticas/metodos-e-classificacoes/classificacoes-e-listas-estatisticas.html",
            "filename": "classificacoes_metodologia.html",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "family": "official_classifications_methodology",
            "concept": "IBGE classifications and methodology documents",
            "classification": "CLASSIFICATION_METHODOLOGY_DISCOVERY",
        },
    )
    core_source_ids = {
        "BRA_IBGE_SIDRA_CNT_TABLES",
        "BRA_IBGE_SISTEMA_CONTAS_NACIONAIS",
        "BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS",
        "BRA_IBGE_TABELAS_RECURSOS_USOS",
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
                analyses[source_id] = analyse_brazil_source(source_id, destination, record.content_type or "")
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
                "The current run could not acquire or validate all critical official Brazilian source families: "
                + ", ".join(core_blocked)
                + ". A closed source decision is not permitted while these attempts remain blocked."
            )
        elif unexpected:
            decision = "CONCEPT_AMBIGUOUS"
            status = "SOURCE_CONTENT_REVIEW_REQUIRED"
            blocking = (
                "Acquired official Brazilian resources did not match the reviewed structural markers for: "
                + ", ".join(unexpected)
                + ". No source is admitted until the changed content is reviewed."
            )
        else:
            decision = "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE"
            status = "REJECTED_BY_CONFIRMED_SOURCE_GATES"
            blocking = (
                "IBGE SIDRA/SCN/CEI source families do not expose an accepted 2021 current-price strict household S14/P31DC table by the twelve Armilar purposes in this probe; "
                "TRU and downloadable SCN evidence is product/resource-use based and would require product-to-COICOP allocation; "
                "POF/IPCA evidence remains Class C only. No many-to-many product bridge or survey/CPI share is used."
            )

        attempts = brazil_source_attempt_rows(records, analyses, errors, blocking)
        gates = brazil_methodology_gate_rows(records, analyses, errors)
        validate_brazil_methodology_gate_rows(gates)
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
            evidence_rows=brazil_evidence_rows(records, analyses, errors, blocking),
            normalized_rows=[],
            mapping_rows=brazil_mapping_audit_rows(analyses),
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
            brazil_gate_rows=gates,
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
    return AdapterResult([], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [])


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
        explicit_family = str(attempt.get("source_family") or "")
        if explicit_family in attempts_by_family:
            attempts_by_family[explicit_family].append(attempt)
            continue
        dataset = str(attempt.get("dataset") or "").upper()
        classification = str(attempt.get("classification") or "").upper()
        concept = str(attempt.get("classification") or "").upper()
        if "API" in dataset or "SIDRA" in dataset:
            attempts_by_family["official_national_accounts_api"].append(attempt)
        elif any(token in dataset for token in ("INPUT", "OUTPUT", "IO_")):
            attempts_by_family["official_input_output_tables"].append(attempt)
        elif any(token in dataset for token in ("SUPPLY", "USE", "SUT", "TRU")):
            attempts_by_family["official_supply_and_use_tables"].append(attempt)
        elif "DATABASE" in classification or "FEDSTAT" in dataset or "STATBANK" in dataset or "BASE" in dataset:
            attempts_by_family["official_statistical_database"].append(attempt)
        elif any(token in dataset for token in ("XLS", "XLSX", "CSV", "STATEMENT")):
            attempts_by_family["official_csv_xls_xlsx"].append(attempt)
        elif "SURVEY" in classification or "CPI" in classification or "HBS" in classification:
            attempts_by_family["survey_or_cpi_class_c_only"].append(attempt)
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
        "source_family": "",
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
        row["source_family"] = str(spec["family"])
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


def _normalise_brazil_text(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def analyse_brazil_source(source_id: str, path: Path, content_type: str = "") -> dict[str, Any]:
    text = _normalise_brazil_text(_decode_text_file(path))
    if source_id == "BRA_IBGE_SIDRA_CNT_TABLES":
        sidra = "sidra" in text or "sistema ibge de recuperacao automatica" in text
        national_accounts = any(token in text for token in ("contas nacionais", "national accounts", "cnt"))
        household = any(token in text for token in ("consumo das familias", "household consumption", "families consumption"))
        exact = all(token in text for token in ("coicop", "2021", "s14", "p31"))
        return {
            "source_kind": "OFFICIAL_NATIONAL_ACCOUNTS_DATABASE",
            "expected_evidence_confirmed": sidra and national_accounts,
            "sidra_database": sidra,
            "national_accounts_family": national_accounts,
            "household_consumption_marker": household,
            "exact_dataset_marker": exact,
            "machine_readable": True,
            "decision": "DISCOVERY_DATABASE_ONLY" if sidra and national_accounts and not exact else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_SISTEMA_CONTAS_NACIONAIS":
        scn = "sistema de contas nacionais" in text or "system of national accounts" in text
        year = "2021" in text
        household = "consumo das familias" in text or "household final consumption" in text
        resource_use = any(token in text for token in ("tabelas de recursos e usos", "resources and uses", "resource and use"))
        purpose = any(token in text for token in ("coicop", "by purpose", "por finalidade"))
        return {
            "source_kind": "OFFICIAL_STRUCTURED_SCN_PUBLICATION",
            "expected_evidence_confirmed": scn and (year or household or resource_use),
            "scn_publication_family": scn,
            "reference_2021": year,
            "household_consumption_marker": household,
            "resource_use_tables": resource_use,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_SCN_PRODUCT_OR_GROUPED_PUBLICATION" if scn and (year or household or resource_use) else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS":
        cei = "contas economicas integradas" in text or "integrated economic accounts" in text
        sectors = any(token in text for token in ("setores institucionais", "institutional sectors", "familias"))
        national_accounts = "contas nacionais" in text or "national accounts" in text
        purpose = any(token in text for token in ("coicop", "por finalidade", "by purpose"))
        return {
            "source_kind": "OFFICIAL_INSTITUTIONAL_ACCOUNTS_FAMILY",
            "expected_evidence_confirmed": (cei or national_accounts) and sectors,
            "integrated_accounts": cei,
            "institutional_sector_family": sectors,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_INSTITUTIONAL_ACCOUNTS_NOT_PURPOSE_TABLE" if (cei or national_accounts) and sectors else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_TABELAS_RECURSOS_USOS":
        tru = any(token in text for token in ("tabelas de recursos e usos", "tabela de recursos e usos", "supply and use", "resources and uses"))
        product = any(token in text for token in ("produto", "products", "atividade", "industry"))
        purpose = any(token in text for token in ("coicop", "por finalidade", "by purpose"))
        return {
            "source_kind": "OFFICIAL_SUPPLY_USE_SOURCE_FAMILY",
            "expected_evidence_confirmed": tru,
            "supply_use_family": tru,
            "product_classification": product or tru,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_TRU_ALLOCATION_REQUIRED" if tru else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_DOWNLOADABLE_SCN_TABLES":
        downloads = any(token in text for token in ("download", ".xls", ".xlsx", ".ods", ".csv"))
        scn = "sistema de contas nacionais" in text or "contas nacionais" in text
        exact = all(token in text for token in ("coicop", "2021", "s14", "p31"))
        return {
            "source_kind": "OFFICIAL_DOWNLOAD_DISCOVERY",
            "expected_evidence_confirmed": downloads and scn,
            "downloadable_family": downloads,
            "exact_dataset_marker": exact,
            "machine_readable": True,
            "decision": "DISCOVERY_DOWNLOAD_ONLY" if downloads and scn and not exact else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_POF_IPCA_CLASS_C":
        pof = "pesquisa de orcamentos familiares" in text or "pof" in text
        ipca = "ipca" in text or "indice nacional de precos ao consumidor amplo" in text
        survey_or_cpi = pof or ipca or "consumer price" in text or "household budget" in text
        return {
            "source_kind": "OFFICIAL_CLASS_C_SURVEY_OR_CPI",
            "expected_evidence_confirmed": survey_or_cpi,
            "survey_or_cpi": survey_or_cpi,
            "machine_readable": True,
            "decision": "REJECT_CLASS_C_SURVEY_OR_CPI" if survey_or_cpi else "REVIEW_REQUIRED",
        }
    if source_id == "BRA_IBGE_CLASSIFICACOES_METODOLOGIA":
        ibge = "ibge" in text
        classification = any(token in text for token in ("classificacao", "classification", "metodologia", "methodology", "coicop"))
        return {
            "source_kind": "OFFICIAL_CLASSIFICATION_METHODOLOGY_DISCOVERY",
            "expected_evidence_confirmed": ibge and classification,
            "classification_or_methodology": classification,
            "machine_readable": True,
            "decision": "DOCUMENTATION_DISCOVERY_ONLY" if ibge and classification else "REVIEW_REQUIRED",
        }
    raise ValueError(f"Unknown Brazilian source id: {source_id}")


def brazil_source_attempt_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in BrazilIbgeAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        row = step2i_attempt_template(
            "BRA", "*", BrazilIbgeAuditAdapter.source_authority,
            source_id, str(spec["url"]), "2021", str(spec["concept"]),
            str(spec["classification"]), rejection_reason,
        )
        row["source_family"] = str(spec["family"])
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
            decision = str(analysis.get("decision") or "REVIEW_REQUIRED")
            retrieval = {
                "DISCOVERY_DATABASE_ONLY": "ACQUIRED_DISCOVERY_DATABASE_ONLY",
                "REJECT_SCN_PRODUCT_OR_GROUPED_PUBLICATION": "ACQUIRED_REJECTED_SCN_PUBLICATION",
                "REJECT_INSTITUTIONAL_ACCOUNTS_NOT_PURPOSE_TABLE": "ACQUIRED_REJECTED_INSTITUTIONAL_ACCOUNTS",
                "REJECT_TRU_ALLOCATION_REQUIRED": "ACQUIRED_REJECTED_TRU_ALLOCATION_REQUIRED",
                "DISCOVERY_DOWNLOAD_ONLY": "ACQUIRED_DISCOVERY_DOWNLOAD_ONLY",
                "REJECT_CLASS_C_SURVEY_OR_CPI": "ACQUIRED_CLASS_C_SURVEY_OR_CPI",
                "DOCUMENTATION_DISCOVERY_ONLY": "ACQUIRED_DOCUMENTATION_DISCOVERY_ONLY",
            }.get(decision, "ACQUIRED_REVIEW_REQUIRED")
            row.update({
                "retrieval_status": retrieval,
                "status_code": record.status_code or "",
                "content_type": record.content_type or "",
                "file_signature": "HTML_DOCUMENT",
                "byte_size": record.bytes,
                "retrieved_at": record.retrieved_at,
                "sha256": record.sha256,
                "candidate_class": "CONCEPT_AMBIGUOUS" if decision == "REVIEW_REQUIRED" else "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
            })
            if source_id in {"BRA_IBGE_TABELAS_RECURSOS_USOS", "BRA_IBGE_SISTEMA_CONTAS_NACIONAIS"}:
                row.update({
                    "institutional_sector": "MULTIPLE_FINAL_USE_SECTORS_OR_PUBLICATION_FAMILY",
                    "transaction_code": "FINAL_USE_PRODUCT_TABLE_FAMILY",
                    "classification": "PRODUCT_OR_RESOURCE_USE_TABLES_REQUIRING_PURPOSE_BRIDGE",
                    "current_prices": "NOT_CONFIRMED_AS_EXACT_2021_PURPOSE_TABLE",
                    "currency": "BRL", "unit": "SOURCE_TABLE_UNIT_NOT_ACCEPTED",
                    "npish_treatment": "NOT_CONFIRMED_EXCLUDED_AT_PURPOSE_LEVEL",
                    "government_treatment": "NOT_CONFIRMED_EXCLUDED_AT_PURPOSE_LEVEL",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_PURPOSE_LEVEL",
                })
            elif source_id == "BRA_IBGE_POF_IPCA_CLASS_C":
                row.update({
                    "institutional_sector": "HOUSEHOLD_SURVEY_OR_PRICE_INDEX_SCOPE",
                    "transaction_code": "NOT_NATIONAL_ACCOUNTS_P31DC",
                    "classification": "SURVEY_OR_CPI_CLASS_C_ONLY",
                    "current_prices": "NOT_AN_EXACT_CURRENT_PRICE_NA_TABLE",
                    "currency": "BRL_OR_INDEX", "unit": "SURVEY_VALUE_OR_INDEX",
                    "npish_treatment": "OUTSIDE_SURVEY_OR_CPI_CONCEPT",
                    "government_treatment": "OUTSIDE_SURVEY_OR_CPI_CONCEPT",
                    "imputed_rent_treatment": "NOT_PROVEN_EQUIVALENT_TO_SNA",
                })
            else:
                row.update({
                    "institutional_sector": "DISCOVERY_OR_DOCUMENTATION_ONLY",
                    "transaction_code": "NOT_AN_ACCEPTED_EXACT_DATASET",
                    "current_prices": "NOT_CONFIRMED_AS_EXACT_2021_CURRENT_PRICE_TABLE",
                    "currency": "NOT_ACCEPTED", "unit": "NOT_ACCEPTED",
                    "npish_treatment": "NOT_CONFIRMED_EXCLUDED",
                    "government_treatment": "NOT_CONFIRMED_EXCLUDED",
                    "imputed_rent_treatment": "NOT_CONFIRMED",
                })
        rows.append(row)
    return expand_attempt_categories(rows)


def brazil_evidence_rows(records: dict[str, AcquisitionRecord], analyses: dict[str, dict[str, Any]], errors: dict[str, Exception], rejection_reason: str) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in BrazilIbgeAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        status = "ACCESS_BLOCKED" if source_id in errors else str(analyses[source_id].get("decision", "REVIEW_REQUIRED"))
        rows.append({
            "economy_code": "BRA", "source_id": source_id,
            "source_authority": BrazilIbgeAuditAdapter.source_authority,
            "source_url": spec["url"], "reference_period": "2021",
            "concept": spec["concept"], "granularity": spec["classification"],
            "machine_readable": "unknown" if source_id in errors else str(analyses[source_id].get("machine_readable", "")),
            "status": status,
            "rejection_reason": rejection_reason if source_id not in errors else f"{type(errors[source_id]).__name__}: {errors[source_id]}",
        })
    return rows


def brazil_mapping_audit_rows(analyses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if analyses.get("BRA_IBGE_TABELAS_RECURSOS_USOS", {}).get("product_classification"):
        rows.append({
            "economy_code": "BRA", "original_item_code": "IBGE_TRU_PRODUCTS",
            "original_item_name": "Tabelas de Recursos e Usos product/source tables",
            "armilar_category": "", "mapping_type": "REJECTED_PRODUCT_TO_PURPOSE_ALLOCATION",
            "status": "FAIL", "reason": "TRU product/resource-use tables cannot be transformed into exact COICOP/Armilar weights through many-to-many allocation.",
        })
    if analyses.get("BRA_IBGE_POF_IPCA_CLASS_C", {}).get("survey_or_cpi"):
        rows.append({
            "economy_code": "BRA", "original_item_code": "IBGE_POF_IPCA_CLASS_C",
            "original_item_name": "POF/IPCA survey or CPI family",
            "armilar_category": "", "mapping_type": "REJECTED_CLASS_C_SUBSTITUTION",
            "status": "FAIL", "reason": "Survey/CPI evidence cannot substitute for strict S14/P31DC national-accounts expenditure.",
        })
    return rows


def brazil_methodology_gate_rows(records: dict[str, AcquisitionRecord] | None = None, analyses: dict[str, dict[str, Any]] | None = None, errors: dict[str, Exception] | None = None) -> list[dict[str, Any]]:
    records = records or {}
    analyses = analyses or {}
    errors = errors or {}
    specs = {str(item["source_id"]): item for item in BrazilIbgeAuditAdapter.source_specs}

    def source(source_id: str) -> dict[str, Any]:
        record = records.get(source_id)
        return {
            "source_id": source_id,
            "source_authority": BrazilIbgeAuditAdapter.source_authority,
            "source_url": specs[source_id]["url"],
            "source_retrieved_at": record.retrieved_at if record else "",
            "source_sha256": record.sha256 if record else "",
            "review_mode": "STRUCTURAL_MARKER_REVIEW" if record else "NOT_ACQUIRED_IN_CURRENT_RUN",
        }

    sidra = analyses.get("BRA_IBGE_SIDRA_CNT_TABLES", {})
    scn = analyses.get("BRA_IBGE_SISTEMA_CONTAS_NACIONAIS", {})
    cei = analyses.get("BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS", {})
    tru = analyses.get("BRA_IBGE_TABELAS_RECURSOS_USOS", {})
    class_c = analyses.get("BRA_IBGE_POF_IPCA_CLASS_C", {})
    exact_chain_validated = (
        sidra.get("expected_evidence_confirmed")
        and scn.get("expected_evidence_confirmed")
        and cei.get("expected_evidence_confirmed")
        and tru.get("expected_evidence_confirmed")
    )
    rows = [
        {"criterion": "official_sidra_national_accounts_acquired", "status": "CONFIRMED" if sidra.get("expected_evidence_confirmed") else ("NOT_FOUND" if "BRA_IBGE_SIDRA_CNT_TABLES" in errors else "AMBIGUOUS"), "evidence": "IBGE SIDRA national-accounts table catalogue was acquired as official source-family evidence.", **source("BRA_IBGE_SIDRA_CNT_TABLES")},
        {"criterion": "sidra_exact_s14_p31dc_table_available", "status": "CONTRADICTED" if sidra.get("expected_evidence_confirmed") and not sidra.get("exact_dataset_marker") else "AMBIGUOUS", "evidence": "The SIDRA source family did not expose a reviewed 2021 strict S14/P31DC twelve-purpose table in this probe.", **source("BRA_IBGE_SIDRA_CNT_TABLES")},
        {"criterion": "official_scn_publication_acquired", "status": "CONFIRMED" if scn.get("expected_evidence_confirmed") else ("NOT_FOUND" if "BRA_IBGE_SISTEMA_CONTAS_NACIONAIS" in errors else "AMBIGUOUS"), "evidence": "The IBGE Sistema de Contas Nacionais publication family was acquired and reviewed for household/source-family markers.", **source("BRA_IBGE_SISTEMA_CONTAS_NACIONAIS")},
        {"criterion": "scn_publication_has_twelve_armilar_purposes", "status": "CONTRADICTED" if scn.get("expected_evidence_confirmed") and not scn.get("purpose_classification") else "AMBIGUOUS", "evidence": "The SCN publication family is not accepted as a twelve Armilar-purpose current-price S14/P31DC table.", **source("BRA_IBGE_SISTEMA_CONTAS_NACIONAIS")},
        {"criterion": "cei_is_exact_purpose_classification", "status": "CONTRADICTED" if cei.get("expected_evidence_confirmed") and not cei.get("purpose_classification") else "AMBIGUOUS", "evidence": "Contas Economicas Integradas are institutional-accounts evidence, not an exact twelve-purpose household expenditure table.", **source("BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS")},
        {"criterion": "tru_is_exact_purpose_classification", "status": "CONTRADICTED" if tru.get("expected_evidence_confirmed") and not tru.get("purpose_classification") else "AMBIGUOUS", "evidence": "IBGE TRU evidence is product/resource-use based and cannot be used as exact purpose weights without allocation.", **source("BRA_IBGE_TABELAS_RECURSOS_USOS")},
        {"criterion": "survey_or_cpi_is_exact_national_accounts", "status": "CONTRADICTED" if class_c.get("expected_evidence_confirmed") else "AMBIGUOUS", "evidence": "POF/IPCA evidence is Class C only and cannot substitute for S14/P31DC national accounts.", **source("BRA_IBGE_POF_IPCA_CLASS_C")},
        {"criterion": "exact_armilar_source_available", "status": "CONTRADICTED" if exact_chain_validated else "AMBIGUOUS", "evidence": "No acquired Brazilian source supplies all strict exact gates simultaneously; database discovery, institutional accounts, product tables and survey/CPI sources remain rejected.", **source("BRA_IBGE_SIDRA_CNT_TABLES")},
    ]
    validate_brazil_methodology_gate_rows(rows)
    return rows


def validate_brazil_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    required = {
        "official_sidra_national_accounts_acquired",
        "sidra_exact_s14_p31dc_table_available",
        "official_scn_publication_acquired",
        "scn_publication_has_twelve_armilar_purposes",
        "cei_is_exact_purpose_classification",
        "tru_is_exact_purpose_classification",
        "survey_or_cpi_is_exact_national_accounts",
        "exact_armilar_source_available",
    }
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError("Brazil methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - BRAZIL_GATE_STATUSES)
    if invalid:
        raise ValueError("Brazil methodology audit contains invalid statuses: " + ",".join(invalid))
    if by_criterion["exact_armilar_source_available"]["status"] == "CONTRADICTED":
        if by_criterion["sidra_exact_s14_p31dc_table_available"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires SIDRA exact-table rejection")
        if by_criterion["tru_is_exact_purpose_classification"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires TRU purpose incompatibility")
        if by_criterion["survey_or_cpi_is_exact_national_accounts"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires survey/CPI substitution rejection")


def _normalise_indonesia_text(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def analyse_indonesia_source(source_id: str, path: Path, content_type: str = "") -> dict[str, Any]:
    text = _normalise_indonesia_text(_decode_text_file(path))
    if source_id == "IDN_BPS_GDP_EXPENDITURE_2020_2024":
        publication = "gross domestic product of indonesia by expenditure" in text
        year = "2021" in text and "2020" in text and "2024" in text
        household = "household consumption" in text or "household final consumption" in text
        grouped = any(token in text for token in (
            "7 groups", "seven groups", "health and education", "transport and communication",
            "restaurants and hotels", "food and beverages other than restaurants",
        ))
        purpose = any(token in text for token in ("coicop", "by purpose", "12 categories", "twelve categories"))
        return {
            "source_kind": "OFFICIAL_NATIONAL_ACCOUNTS_PUBLICATION",
            "expected_evidence_confirmed": publication and year and household,
            "national_publication": publication,
            "reference_2021": year,
            "household_consumption": household,
            "grouped_categories": grouped,
            "twelve_purpose_categories": purpose and not grouped,
            "machine_readable": True,
            "decision": "REJECT_GROUPED_NATIONAL_ACCOUNTS" if publication and year and household else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_STATISTICS_TABLES_EXPENDITURE":
        bps = "bps" in text or "badan pusat statistik" in text
        expenditure = "expenditure" in text or "pengeluaran" in text
        statistics_table = "statistics table" in text or "statistical table" in text or "tabel" in text
        exact = all(token in text for token in ("coicop", "2021", "household")) and "12" in text
        return {
            "source_kind": "OFFICIAL_STATISTICAL_DATABASE",
            "expected_evidence_confirmed": bps and expenditure and statistics_table,
            "statistics_table_family": statistics_table,
            "expenditure_subject": expenditure,
            "exact_dataset_marker": exact,
            "machine_readable": True,
            "decision": "DISCOVERY_DATABASE_ONLY" if bps and expenditure and statistics_table and not exact else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_NATIONAL_ACCOUNTS_DOWNLOAD_SEARCH":
        bps = "bps" in text or "badan pusat statistik" in text
        publication_search = "publication" in text or "publikasi" in text
        expenditure = "gross domestic product" in text or "expenditure" in text or "pengeluaran" in text
        return {
            "source_kind": "OFFICIAL_DOWNLOAD_DISCOVERY",
            "expected_evidence_confirmed": bps and publication_search and expenditure,
            "downloadable_family": "download" in text or ".xls" in text or ".xlsx" in text or ".csv" in text,
            "exact_dataset_marker": False,
            "machine_readable": True,
            "decision": "DISCOVERY_DOWNLOAD_ONLY" if bps and publication_search and expenditure else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_SUPPLY_USE_TABLES":
        bps = "bps" in text or "badan pusat statistik" in text
        sut = any(token in text for token in ("supply and use", "supply use", "tabel suplai", "tabel penggunaan"))
        product = any(token in text for token in ("product", "commodity", "produk", "komoditas"))
        purpose = any(token in text for token in ("coicop", "by purpose", "according to purpose"))
        return {
            "source_kind": "OFFICIAL_SUPPLY_USE_SOURCE_FAMILY",
            "expected_evidence_confirmed": bps and sut,
            "supply_use_family": sut,
            "product_classification": product or sut,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_SUT_ALLOCATION_REQUIRED" if bps and sut else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_INPUT_OUTPUT_TABLES":
        bps = "bps" in text or "badan pusat statistik" in text
        io = "input output" in text or "input-output" in text or "tabel input output" in text
        product = any(token in text for token in ("product", "commodity", "produk", "komoditas", "industry"))
        purpose = any(token in text for token in ("coicop", "by purpose", "according to purpose"))
        return {
            "source_kind": "OFFICIAL_INPUT_OUTPUT_SOURCE_FAMILY",
            "expected_evidence_confirmed": bps and io,
            "input_output_family": io,
            "product_classification": product or io,
            "purpose_classification": purpose,
            "machine_readable": True,
            "decision": "REJECT_INPUT_OUTPUT_ALLOCATION_REQUIRED" if bps and io else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_SURVEY_OR_CPI_CLASS_C":
        bps = "bps" in text or "badan pusat statistik" in text
        survey_or_cpi = any(token in text for token in ("consumer price", "cpi", "survey", "susenas", "household"))
        return {
            "source_kind": "OFFICIAL_CLASS_C_SURVEY_OR_CPI",
            "expected_evidence_confirmed": bps and survey_or_cpi,
            "survey_or_cpi": survey_or_cpi,
            "machine_readable": True,
            "decision": "REJECT_CLASS_C_SURVEY_OR_CPI" if bps and survey_or_cpi else "REVIEW_REQUIRED",
        }
    if source_id == "IDN_BPS_CLASSIFICATION_METHODOLOGY":
        bps = "bps" in text or "badan pusat statistik" in text
        classification = any(token in text for token in ("coicop", "classification", "klasifikasi", "methodology", "metadata"))
        return {
            "source_kind": "OFFICIAL_CLASSIFICATION_METHODOLOGY_DISCOVERY",
            "expected_evidence_confirmed": bps and classification,
            "classification_or_methodology": classification,
            "machine_readable": True,
            "decision": "DOCUMENTATION_DISCOVERY_ONLY" if bps and classification else "REVIEW_REQUIRED",
        }
    raise ValueError(f"Unknown Indonesian source id: {source_id}")


def indonesia_source_attempt_rows(
    records: dict[str, AcquisitionRecord],
    analyses: dict[str, dict[str, Any]],
    errors: dict[str, Exception],
    rejection_reason: str,
) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in IndonesiaBpsAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        row = step2i_attempt_template(
            "IDN", "*", IndonesiaBpsAuditAdapter.source_authority,
            source_id, str(spec["url"]), "2021", str(spec["concept"]),
            str(spec["classification"]), rejection_reason,
        )
        row["source_family"] = str(spec["family"])
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
            decision = str(analysis.get("decision") or "REVIEW_REQUIRED")
            retrieval = {
                "REJECT_GROUPED_NATIONAL_ACCOUNTS": "ACQUIRED_REJECTED_GROUPED_NATIONAL_ACCOUNTS",
                "DISCOVERY_DATABASE_ONLY": "ACQUIRED_DISCOVERY_DATABASE_ONLY",
                "DISCOVERY_DOWNLOAD_ONLY": "ACQUIRED_DISCOVERY_DOWNLOAD_ONLY",
                "REJECT_SUT_ALLOCATION_REQUIRED": "ACQUIRED_REJECTED_SUT_ALLOCATION_REQUIRED",
                "REJECT_INPUT_OUTPUT_ALLOCATION_REQUIRED": "ACQUIRED_REJECTED_INPUT_OUTPUT_ALLOCATION_REQUIRED",
                "REJECT_CLASS_C_SURVEY_OR_CPI": "ACQUIRED_CLASS_C_SURVEY_OR_CPI",
                "DOCUMENTATION_DISCOVERY_ONLY": "ACQUIRED_DOCUMENTATION_DISCOVERY_ONLY",
            }.get(decision, "ACQUIRED_REVIEW_REQUIRED")
            row.update({
                "retrieval_status": retrieval,
                "status_code": record.status_code or "",
                "content_type": record.content_type or "",
                "file_signature": "HTML_DOCUMENT",
                "byte_size": record.bytes,
                "retrieved_at": record.retrieved_at,
                "sha256": record.sha256,
                "candidate_class": "CONCEPT_AMBIGUOUS" if decision == "REVIEW_REQUIRED" else "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE",
            })
            if source_id == "IDN_BPS_GDP_EXPENDITURE_2020_2024":
                row.update({
                    "institutional_sector": "HOUSEHOLD_FINAL_CONSUMPTION_SCOPE_NOT_PROVEN_STRICT_S14",
                    "transaction_code": "HFCE_BY_EXPENDITURE_GROUPS_NOT_EXACT_P31DC_PURPOSES",
                    "classification": "GROUPED_EXPENDITURE_PUBLICATION",
                    "current_prices": "PUBLICATION_FAMILY_INCLUDES_CURRENT_PRICE_TABLES",
                    "currency": "IDR", "unit": "PUBLICATION_TABLE_UNIT",
                    "npish_treatment": "NOT_CONFIRMED_EXCLUDED_AT_CATEGORY_LEVEL",
                    "government_treatment": "GOVERNMENT_FINAL_CONSUMPTION_SEPARATE_IN_GDP_EXPENDITURE",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_ARMILAR_CATEGORY_LEVEL",
                })
            elif source_id in {"IDN_BPS_SUPPLY_USE_TABLES", "IDN_BPS_INPUT_OUTPUT_TABLES"}:
                row.update({
                    "institutional_sector": "MULTIPLE_FINAL_USE_SECTORS",
                    "transaction_code": "FINAL_USE_PRODUCT_TABLE_FAMILY",
                    "classification": "PRODUCT_TABLES_REQUIRING_PURPOSE_BRIDGE",
                    "current_prices": "NOT_CONFIRMED_AS_EXACT_2021_PURPOSE_TABLE",
                    "currency": "IDR", "unit": "SOURCE_TABLE_UNIT_NOT_ACCEPTED",
                    "npish_treatment": "NOT_CONFIRMED_EXCLUDED_AT_PURPOSE_LEVEL",
                    "government_treatment": "NOT_CONFIRMED_EXCLUDED_AT_PURPOSE_LEVEL",
                    "imputed_rent_treatment": "NOT_CONFIRMED_AT_PURPOSE_LEVEL",
                })
            elif source_id == "IDN_BPS_SURVEY_OR_CPI_CLASS_C":
                row.update({
                    "institutional_sector": "HOUSEHOLD_SURVEY_OR_PRICE_INDEX_SCOPE",
                    "transaction_code": "NOT_NATIONAL_ACCOUNTS_P31DC",
                    "classification": "SURVEY_OR_CPI_CLASS_C_ONLY",
                    "current_prices": "NOT_AN_EXACT_CURRENT_PRICE_NA_TABLE",
                    "currency": "IDR_OR_INDEX", "unit": "SURVEY_VALUE_OR_INDEX",
                    "npish_treatment": "OUTSIDE_SURVEY_OR_CPI_CONCEPT",
                    "government_treatment": "OUTSIDE_SURVEY_OR_CPI_CONCEPT",
                    "imputed_rent_treatment": "NOT_PROVEN_EQUIVALENT_TO_SNA",
                })
            else:
                row.update({
                    "institutional_sector": "DISCOVERY_OR_DOCUMENTATION_ONLY",
                    "transaction_code": "NOT_AN_ACCEPTED_EXACT_DATASET",
                    "current_prices": "NOT_CONFIRMED_AS_EXACT_2021_CURRENT_PRICE_TABLE",
                    "currency": "NOT_ACCEPTED", "unit": "NOT_ACCEPTED",
                    "npish_treatment": "NOT_CONFIRMED_EXCLUDED",
                    "government_treatment": "NOT_CONFIRMED_EXCLUDED",
                    "imputed_rent_treatment": "NOT_CONFIRMED",
                })
        rows.append(row)
    return expand_attempt_categories(rows)


def indonesia_evidence_rows(records: dict[str, AcquisitionRecord], analyses: dict[str, dict[str, Any]], errors: dict[str, Exception], rejection_reason: str) -> list[dict[str, Any]]:
    specs = {str(spec["source_id"]): spec for spec in IndonesiaBpsAuditAdapter.source_specs}
    rows: list[dict[str, Any]] = []
    for source_id in sorted(specs):
        spec = specs[source_id]
        status = "ACCESS_BLOCKED" if source_id in errors else str(analyses[source_id].get("decision", "REVIEW_REQUIRED"))
        rows.append({
            "economy_code": "IDN", "source_id": source_id,
            "source_authority": IndonesiaBpsAuditAdapter.source_authority,
            "source_url": spec["url"], "reference_period": "2021",
            "concept": spec["concept"], "granularity": spec["classification"],
            "machine_readable": "unknown" if source_id in errors else str(analyses[source_id].get("machine_readable", "")),
            "status": status,
            "rejection_reason": rejection_reason if source_id not in errors else f"{type(errors[source_id]).__name__}: {errors[source_id]}",
        })
    return rows


def indonesia_mapping_audit_rows(analyses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if analyses.get("IDN_BPS_GDP_EXPENDITURE_2020_2024", {}).get("grouped_categories"):
        rows.append({
            "economy_code": "IDN", "original_item_code": "BPS_GROUPED_HFCE",
            "original_item_name": "Grouped household consumption expenditure publication",
            "armilar_category": "", "mapping_type": "REJECTED_GROUPED_CATEGORY",
            "status": "FAIL", "reason": "Known BPS grouped publication cannot be split into twelve Armilar categories without allocation.",
        })
    if analyses.get("IDN_BPS_SUPPLY_USE_TABLES") or analyses.get("IDN_BPS_INPUT_OUTPUT_TABLES"):
        rows.append({
            "economy_code": "IDN", "original_item_code": "BPS_PRODUCT_TABLE_FAMILY",
            "original_item_name": "Supply-use or input-output product tables",
            "armilar_category": "", "mapping_type": "REJECTED_PRODUCT_TO_PURPOSE_ALLOCATION",
            "status": "FAIL", "reason": "Product tables cannot be transformed into exact COICOP/Armilar weights through many-to-many allocation.",
        })
    return rows


def indonesia_methodology_gate_rows(records: dict[str, AcquisitionRecord] | None = None, analyses: dict[str, dict[str, Any]] | None = None, errors: dict[str, Exception] | None = None) -> list[dict[str, Any]]:
    records = records or {}
    analyses = analyses or {}
    errors = errors or {}
    specs = {str(item["source_id"]): item for item in IndonesiaBpsAuditAdapter.source_specs}

    def source(source_id: str) -> dict[str, Any]:
        record = records.get(source_id)
        return {
            "source_id": source_id,
            "source_authority": IndonesiaBpsAuditAdapter.source_authority,
            "source_url": specs[source_id]["url"],
            "source_retrieved_at": record.retrieved_at if record else "",
            "source_sha256": record.sha256 if record else "",
            "review_mode": "STRUCTURAL_MARKER_REVIEW" if record else "NOT_ACQUIRED_IN_CURRENT_RUN",
        }

    publication = analyses.get("IDN_BPS_GDP_EXPENDITURE_2020_2024", {})
    database = analyses.get("IDN_BPS_STATISTICS_TABLES_EXPENDITURE", {})
    sut = analyses.get("IDN_BPS_SUPPLY_USE_TABLES", {})
    io = analyses.get("IDN_BPS_INPUT_OUTPUT_TABLES", {})
    class_c = analyses.get("IDN_BPS_SURVEY_OR_CPI_CLASS_C", {})
    exact_chain_validated = (
        publication.get("expected_evidence_confirmed")
        and database.get("expected_evidence_confirmed")
        and sut.get("expected_evidence_confirmed")
        and io.get("expected_evidence_confirmed")
    )
    rows = [
        {"criterion": "official_national_accounts_publication_acquired", "status": "CONFIRMED" if publication.get("expected_evidence_confirmed") else ("NOT_FOUND" if "IDN_BPS_GDP_EXPENDITURE_2020_2024" in errors else "AMBIGUOUS"), "evidence": "BPS GDP by expenditure publication was acquired and contains household consumption context for 2021.", **source("IDN_BPS_GDP_EXPENDITURE_2020_2024")},
        {"criterion": "twelve_armilar_purpose_categories_available", "status": "CONTRADICTED" if publication.get("grouped_categories") and not publication.get("twelve_purpose_categories") else "AMBIGUOUS", "evidence": "The acquired BPS publication is grouped and cannot supply twelve Armilar purposes without artificial splitting.", **source("IDN_BPS_GDP_EXPENDITURE_2020_2024")},
        {"criterion": "strict_household_s14_p31dc_confirmed", "status": "AMBIGUOUS", "evidence": "The acquired source family does not prove strict S14/P31DC by Armilar category with NPISH excluded.", **source("IDN_BPS_GDP_EXPENDITURE_2020_2024")},
        {"criterion": "current_prices_currency_unit_identified", "status": "AMBIGUOUS", "evidence": "The publication family uses Indonesian rupiah table units, but no accepted exact twelve-category current-price dataset is confirmed.", **source("IDN_BPS_GDP_EXPENDITURE_2020_2024")},
        {"criterion": "official_statistical_database_exact_table_available", "status": "CONTRADICTED" if database.get("expected_evidence_confirmed") and not database.get("exact_dataset_marker") else "AMBIGUOUS", "evidence": "The BPS statistics-table family was acquired as source-family evidence but no exact twelve-purpose dataset marker was confirmed.", **source("IDN_BPS_STATISTICS_TABLES_EXPENDITURE")},
        {"criterion": "sut_is_exact_purpose_classification", "status": "CONTRADICTED" if sut.get("expected_evidence_confirmed") and not sut.get("purpose_classification") else "AMBIGUOUS", "evidence": "BPS SUT evidence is product/source-family evidence and cannot be used as exact purpose weights without allocation.", **source("IDN_BPS_SUPPLY_USE_TABLES")},
        {"criterion": "input_output_is_exact_purpose_classification", "status": "CONTRADICTED" if io.get("expected_evidence_confirmed") and not io.get("purpose_classification") else "AMBIGUOUS", "evidence": "BPS input-output evidence is product/source-family evidence and cannot be used as exact purpose weights without allocation.", **source("IDN_BPS_INPUT_OUTPUT_TABLES")},
        {"criterion": "survey_or_cpi_is_exact_national_accounts", "status": "CONTRADICTED" if class_c.get("expected_evidence_confirmed") else "AMBIGUOUS", "evidence": "Survey/CPI evidence is Class C only and cannot substitute for S14/P31DC national accounts.", **source("IDN_BPS_SURVEY_OR_CPI_CLASS_C")},
        {"criterion": "exact_armilar_source_available", "status": "CONTRADICTED" if exact_chain_validated else "AMBIGUOUS", "evidence": "No acquired Indonesian source supplies all strict exact gates simultaneously; grouped and product-based sources remain rejected.", **source("IDN_BPS_GDP_EXPENDITURE_2020_2024")},
    ]
    validate_indonesia_methodology_gate_rows(rows)
    return rows


def validate_indonesia_methodology_gate_rows(rows: list[dict[str, Any]]) -> None:
    required = {
        "official_national_accounts_publication_acquired",
        "twelve_armilar_purpose_categories_available",
        "strict_household_s14_p31dc_confirmed",
        "current_prices_currency_unit_identified",
        "official_statistical_database_exact_table_available",
        "sut_is_exact_purpose_classification",
        "input_output_is_exact_purpose_classification",
        "survey_or_cpi_is_exact_national_accounts",
        "exact_armilar_source_available",
    }
    by_criterion = {str(row.get("criterion")): row for row in rows}
    missing = sorted(required - set(by_criterion))
    if missing:
        raise ValueError("Indonesia methodology audit is missing criteria: " + ",".join(missing))
    invalid = sorted({str(row.get("status")) for row in rows} - INDONESIA_GATE_STATUSES)
    if invalid:
        raise ValueError("Indonesia methodology audit contains invalid statuses: " + ",".join(invalid))
    if by_criterion["exact_armilar_source_available"]["status"] == "CONTRADICTED":
        if by_criterion["twelve_armilar_purpose_categories_available"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires grouped-purpose rejection")
        if by_criterion["sut_is_exact_purpose_classification"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires SUT purpose incompatibility")
        if by_criterion["input_output_is_exact_purpose_classification"]["status"] != "CONTRADICTED":
            raise ValueError("Exact-source rejection requires input-output purpose incompatibility")


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
        row["source_family"] = str(spec["family"])
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
        "pipeline_version": "0.6.7",
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
        "Generated: deterministic v0.6.7 Step 2I report",
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
        "| 0.6.7 | Step 2H0 Brazil source-family audit | IBGE SIDRA, SCN, CEI, TRU and Class C concepts separated |",
        "| 0.6.6 | Step 2H0 Indonesia evidence audit | BPS grouped, database, SUT, input-output and Class C concepts separated |",
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
        "Pipeline version: `0.6.7`",
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
        "Pipeline version: `0.6.7`",
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
        "Pipeline version: `0.6.7`",
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


def write_indonesia_method_gate_report(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        validate_indonesia_methodology_gate_rows(rows)
    lines = [
        "# Indonesia method gate report",
        "",
        "Pipeline version: `0.6.7`",
        "",
        "This report records the strict Armilar admissibility decision for the official BPS source chain.",
        "Grouped national-accounts publications, BPS database discovery pages, product-based SUT/input-output families and Class C survey/CPI evidence remain conceptually separate.",
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
        "No Indonesian source is admitted to the strict exact matrix in this probe.",
        "The BPS expenditure publication is grouped; BPS SUT and input-output families are product-based or discovery-only in this audit; survey/CPI material is Class C only.",
        "No grouped-category split, product-to-COICOP allocation, survey-share substitution or silent concept conversion is permitted.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_brazil_method_gate_report(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        validate_brazil_methodology_gate_rows(rows)
    lines = [
        "# Brazil method gate report",
        "",
        "Pipeline version: `0.6.7`",
        "",
        "This report records the strict Armilar admissibility decision for the official IBGE source chain.",
        "SIDRA, SCN, CEI, TRU and Class C survey/CPI evidence are kept conceptually separate.",
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
        "No Brazilian source is admitted to the strict exact matrix in this probe.",
        "SIDRA and SCN evidence remains discovery or publication-family evidence; CEI is institutional-accounts evidence; TRU is product/resource-use based; POF/IPCA material is Class C only.",
        "No product-to-COICOP allocation, survey-share substitution or silent concept conversion is permitted.",
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
