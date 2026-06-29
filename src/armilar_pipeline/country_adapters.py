from __future__ import annotations

import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Protocol

from .acquire import AcquisitionRecord, fetch_url
from .config import Step2Config
from .util import utc_now, write_csv, write_json, write_sha256sums


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
    "economy_code", "category", "authority", "dataset", "url",
    "access_method", "retrieval_status", "content_type", "file_signature",
    "reference_period", "institutional_sector", "transaction_code",
    "classification", "current_prices", "currency", "unit",
    "npish_treatment", "government_treatment", "imputed_rent_treatment",
    "candidate_class", "rejection_reason", "retrieved_at", "sha256",
]

COMPLETION_ECONOMY_FIELDS = [
    "economy_code", "economy_name", "accepted_categories",
    "experimental_categories", "unavailable_categories", "coverage_added_cells",
    "decision", "sources_examined", "remaining_blockers",
]

INDIA_GATE_FIELDS = ["criterion", "status", "evidence", "source_id"]

STEP2H_EXCEPTION_FIELDS = [
    "economy_code", "economy_name", "armilar_category", "decision",
    "current_status", "resolution_attempted", "reason",
]

STEP2I_EXTRA_ATTEMPTS = {
    "RUT": [
        ("Federal State Statistics Service", "ROSSTAT_NATIONAL_ACCOUNTS_SECTION", "https://rosstat.gov.ru/statistics/accounts", "2021", "national accounts database/publications", "SOURCE_FAMILY_SEARCH", "National accounts section does not provide an accepted deterministic 2021 S14/P31DC COICOP-HH table in the adapter inputs."),
        ("Federal State Statistics Service", "FEDSTAT_OFFICIAL_STATISTICAL_DATABASE", "https://fedstat.ru/", "2021", "official statistical database", "SOURCE_FAMILY_SEARCH", "No accepted Fedstat indicator with exact 2021 household final consumption by Armilar category has been integrated."),
    ],
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
    completion_rows: list[dict[str, Any]] | None = None
    india_gate_rows: list[dict[str, Any]] | None = None
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
        Step2IDecisionAdapter(
            "RUT", "Russian Federation", "RUT_ROSSTAT_OFFICIAL_SOURCE_AUDIT",
            "Federal State Statistics Service",
            "https://eng.rosstat.gov.ru/storage/mediabank/BRICS_Joint_Statistical_Publication_2025.pdf",
            "2021", "HFCE_BY_PURPOSE_OR_COICOP_HH", "structured source not located",
            "UNAVAILABLE",
            "No deterministic official XLS/XLSX/CSV/SDMX/HTML Rosstat table with 2021 strict household COICOP-HH values has passed the gates.",
        ),
        Step2IDecisionAdapter(
            "CHN", "China", "CHN_NBS_OFFICIAL_SOURCE_AUDIT",
            "National Bureau of Statistics of China",
            "https://www.stats.gov.cn/english/PressRelease/202201/t20220118_1826649.html",
            "2021", "HOUSEHOLD_SURVEY_EIGHT_GROUPS", "8 groups",
            "UNAVAILABLE",
            "Official NBS table is a household survey with eight combined groups, not national-accounts S14/P31 with twelve Armilar categories.",
        ),
        Step2IDecisionAdapter("IDN", "Indonesia", "IDN_BPS_OFFICIAL_SOURCE_AUDIT", "Badan Pusat Statistik", "https://www.bps.go.id/en/publication/2025/05/28/2a1c585ebbd574dd91afed67/gross-domestic-product-of-indonesia-by-expenditure--2020-2024.html", "2021", "HFCE_REGROUPED", "7 groups", "UNAVAILABLE", "Official source identified in probe regroups COICOP and cannot be bridged exactly to twelve Armilar categories."),
        Step2IDecisionAdapter("BRA", "Brazil", "BRA_IBGE_OFFICIAL_SOURCE_AUDIT", "Instituto Brasileiro de Geografia e Estatistica", "https://www.ibge.gov.br/estatisticas/economicas/comercio/9052-sistema-de-contas-nacionais-brasil.html", "2021", "SNA_PRODUCT_TABLES", "product tables", "UNAVAILABLE", "Official product tables would require many-to-many product-to-COICOP allocation."),
        AuditOnlyAdapter("EGY", "Egypt", "EGY_CAPMAS_OFFICIAL_SOURCE_AUDIT", "Central Agency for Public Mobilization and Statistics", "https://www.censusinfo.capmas.gov.eg/metadata-en-v4.2/index.php/catalog/747/overview", "2021", "HOUSEHOLD_SURVEY", "survey microdata", "UNAVAILABLE", "Official HIECS is a survey source, not national-accounts S14/P31 current-price HFCE."),
        AuditOnlyAdapter("PAK", "Pakistan", "PAK_PBS_OFFICIAL_SOURCE_AUDIT", "Pakistan Bureau of Statistics", "https://www.pbs.gov.pk/national-accounts-2/", "2021-22", "HFCE_AGGREGATE", "aggregate only", "UNAVAILABLE", "Public national-accounts source does not expose a twelve-category strict household table."),
        AuditOnlyAdapter("NGA", "Nigeria", "NGA_NBS_OFFICIAL_SOURCE_AUDIT", "National Bureau of Statistics", "https://www.nigerianstat.gov.ng/elibrary/read/1241168", "2021", "HFCE_AGGREGATE", "aggregate only", "UNAVAILABLE", "Official expenditure-GDP report publishes aggregate household consumption, not twelve categories."),
        AuditOnlyAdapter("BGD", "Bangladesh", "BGD_BBS_OFFICIAL_SOURCE_AUDIT", "Bangladesh Bureau of Statistics", "https://nsds.bbs.gov.bd/en/posts/85/Survey%20documentation%20for%20the%20Household%20Income%20and%20Expenditure%20Survey", "2022", "HOUSEHOLD_SURVEY", "survey", "UNAVAILABLE", "Official HIES reference year and concept do not satisfy 2021 national-accounts HFCE gates."),
        AuditOnlyAdapter("VNM", "Viet Nam", "VNM_NSO_OFFICIAL_SOURCE_AUDIT", "National Statistics Office of Viet Nam", "https://www.nso.gov.vn/en/default/2024/04/results-of-the-viet-nam-household-living-standards-survey-2022/", "2022", "HOUSEHOLD_SURVEY", "survey", "UNAVAILABLE", "Official VHLSS is 2022 survey evidence only, not exact 2021 S14/P31 HFCE."),
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
    write_csv(out / "step2i_economy_summary.csv", COMPLETION_ECONOMY_FIELDS, result.completion_rows or [])
    write_csv(out / "india_methodology_gate_audit.csv", INDIA_GATE_FIELDS, result.india_gate_rows or [])
    write_csv(out / "step2h_exception_audit.csv", STEP2H_EXCEPTION_FIELDS, result.step2h_exception_rows or step2h_exception_rows())
    write_json(out / "step2i_completion_summary.json", step2i_completion_summary(result))
    write_step2i_report(out / "STEP_2I_COMPLETION_REPORT.md", result)


class IndiaMospiAdapter:
    economy_code = "IND"
    economy_name = "India"
    adapter_id = "IND_MOSPI_NAS2024_STATEMENT_5_1"
    source_authority = "Ministry of Statistics and Programme Implementation"
    source_url = "https://www.mospi.gov.in/sites/default/files/reports_and_publication/statistical_publication/National_Accounts/NAS2024/5.1.xlsx"
    reference_period = "2021-22"

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        raw = run_root / "raw" / "country_adapters" / self.economy_code / self.adapter_id / "5.1.xlsx"
        record = fetch_url(
            config,
            source_id=self.adapter_id,
            url=self.source_url,
            destination=raw,
            cache_path=cache_root / "country_adapters" / self.economy_code / "5.1.xlsx",
            accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.1",
        )
        parsed = parse_india_statement_5_1(raw)
        rows, mapping = build_india_rows(parsed, record, run_root)
        reconciliation = reconcile_india(parsed)
        boundary_confirmed = False
        gate_rows = india_methodology_gate_rows()
        blocking = (
            "Statement 5.1 is PFCE by item. The workbook supports exact item aggregation, "
            "but the strict households-only S14/P31 boundary and NPISH exclusion are not confirmed in this source file."
        )
        if not boundary_confirmed:
            for row in rows:
                row["data_class"] = "UNAVAILABLE"
                row["quality_flags"] = "PFCE_PRIVATE_BOUNDARY_NOT_STRICT_HOUSEHOLDS_CONFIRMED"
        status = "BLOCKED_BY_METHOD_GATE" if not boundary_confirmed else "ACCEPTED"
        return AdapterResult(
            status_rows=[{
                "economy_code": self.economy_code, "economy_name": self.economy_name,
                "adapter_id": self.adapter_id, "status": status,
                "data_class": "UNAVAILABLE" if not boundary_confirmed else "OFFICIAL_EXACT_DERIVATION",
                "accepted_rows": 0 if not boundary_confirmed else len(rows),
                "failure_count": 0, "source_url": self.source_url, "blocking_reason": blocking if not boundary_confirmed else "",
            }],
            evidence_rows=[{
                "economy_code": self.economy_code, "source_id": self.adapter_id,
                "source_authority": self.source_authority, "source_url": self.source_url,
                "reference_period": self.reference_period, "concept": "PFCE classified by item",
                "granularity": "12 Armilar groups plus narcotics split", "machine_readable": "true",
                "status": status, "rejection_reason": blocking if not boundary_confirmed else "",
            }],
            normalized_rows=[] if not boundary_confirmed else rows,
            mapping_rows=mapping,
            reconciliation_rows=[reconciliation],
            failure_rows=[],
            acquisition_records=[record],
            cell_status_rows=step2i_cell_rows(
                self.economy_code, self.economy_name, self.adapter_id, self.source_authority,
                self.reference_period, "UNAVAILABLE", blocking,
            ),
            source_attempt_rows=india_source_attempt_rows(record, blocking),
            completion_rows=[completion_row(self.economy_code, self.economy_name, blocking, 2)],
            india_gate_rows=gate_rows,
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
                self.reference_period, "UNAVAILABLE", self.reason,
            ),
            source_attempt_rows=source_attempts,
            completion_rows=[completion_row(self.economy_code, self.economy_name, self.reason, len({row["dataset"] for row in source_attempts}))],
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
    return AdapterResult([], [], [], [], [], [], [], [], [], [], [], [])


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
    target.completion_rows.extend(source.completion_rows or [])
    target.india_gate_rows.extend(source.india_gate_rows or [])
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


def completion_row(economy_code: str, economy_name: str, blocker: str, sources_examined: int) -> dict[str, Any]:
    return {
        "economy_code": economy_code,
        "economy_name": economy_name,
        "accepted_categories": "",
        "experimental_categories": "",
        "unavailable_categories": "|".join(STEP2I_PROXY_CATEGORIES),
        "coverage_added_cells": 0,
        "decision": "UNAVAILABLE",
        "sources_examined": sources_examined,
        "remaining_blockers": blocker,
    }


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
        "authority": authority,
        "dataset": dataset,
        "url": url,
        "access_method": "OFFICIAL_WEB_SOURCE_AUDIT",
        "retrieval_status": "DOCUMENTED_NOT_ADMISSIBLE",
        "content_type": "",
        "file_signature": "",
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
        "candidate_class": "UNAVAILABLE",
        "rejection_reason": rejection_reason,
        "retrieved_at": "NOT_RETRIEVED_IN_STEP2I_AUDIT",
        "sha256": "",
    }


def india_source_attempt_rows(record: AcquisitionRecord, rejection_reason: str) -> list[dict[str, Any]]:
    row = step2i_attempt_template(
        "IND", "*", "Ministry of Statistics and Programme Implementation",
        "IND_MOSPI_NAS2024_STATEMENT_5_1", record.url, "2021-22",
        "PFCE classified by item", "MOSPI_NAS_ITEM", rejection_reason,
    )
    row.update({
        "retrieval_status": record.status,
        "content_type": record.content_type or "",
        "file_signature": "XLSX_ZIP_CONTAINER",
        "current_prices": "CONFIRMED",
        "currency": "INR",
        "unit": "crore",
        "imputed_rent_treatment": "PRESENT_AS_HOUSING_RENT_COMPONENT_BUT_BOUNDARY_NOT_FULLY_CONFIRMED",
        "candidate_class": "UNAVAILABLE",
        "retrieved_at": "SEE_MANIFEST_FOR_RAW_RETRIEVAL_TIME",
        "sha256": record.sha256,
    })
    method = step2i_attempt_template(
        "IND", "*", "Ministry of Statistics and Programme Implementation",
        "IND_MOSPI_METHOD_BOUNDARY_SEARCH", "https://www.mospi.gov.in/",
        "2021-22", "NAS PFCE methodology", "METHODOLOGY_SEARCH", rejection_reason,
    )
    method["retrieval_status"] = "OFFICIAL_METHOD_DOCUMENT_NOT_FOUND_IN_ADAPTER_INPUTS"
    return expand_attempt_categories([row, method])


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


def india_methodology_gate_rows() -> list[dict[str, Any]]:
    source_id = "IND_MOSPI_NAS2024_STATEMENT_5_1"
    return [
        {"criterion": "represents_households_S14", "status": "AMBIGUOUS", "evidence": "Statement uses PFCE/private final consumption expenditure; workbook does not state strict S14-only boundary.", "source_id": source_id},
        {"criterion": "corresponds_to_P31_HFCE", "status": "AMBIGUOUS", "evidence": "PFCE is a national-accounts consumption concept but transaction code P31DC/HFCE is not explicit in the workbook.", "source_id": source_id},
        {"criterion": "excludes_NPISH", "status": "NOT_FOUND", "evidence": "No NPISH exclusion statement found in Statement 5.1 workbook.", "source_id": source_id},
        {"criterion": "excludes_government_consumption", "status": "CONFIRMED", "evidence": "Source title is private final consumption expenditure, not government final consumption expenditure.", "source_id": source_id},
        {"criterion": "includes_imputed_rent", "status": "CONFIRMED", "evidence": "Housing group includes gross rentals for housing.", "source_id": source_id},
        {"criterion": "current_prices", "status": "CONFIRMED", "evidence": "Workbook has explicit current-price block.", "source_id": source_id},
        {"criterion": "reference_period_2021_22_accepted", "status": "CONFIRMED", "evidence": "Workbook exposes fiscal year 2021-22 and adapter preserves it without calendar conversion.", "source_id": source_id},
    ]


def step2h_exception_rows() -> list[dict[str, Any]]:
    return [
        {"economy_code": "BLR", "economy_name": "Belarus", "armilar_category": "CP02", "decision": "UNAVAILABLE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "CP02 cannot be reconstructed without both alcohol and tobacco strict HFCE cells or an official narcotics-excluding aggregate."},
        {"economy_code": "KWT", "economy_name": "Kuwait", "armilar_category": "CP02", "decision": "UNAVAILABLE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "No modelled alcohol/tobacco split is allowed."},
        {"economy_code": "SAU", "economy_name": "Saudi Arabia", "armilar_category": "CP02", "decision": "UNAVAILABLE", "current_status": "MISSING_SOURCE90_ALCOHOL_OR_TOBACCO_NOMINAL_OR_PPP:1102100", "resolution_attempted": "Source 90 public cells audited; no official alcohol+tobacco replacement accepted.", "reason": "No modelled alcohol/tobacco split is allowed."},
        {"economy_code": "BON", "economy_name": "Bonaire", "armilar_category": "*", "decision": "UNAVAILABLE", "current_status": "0/12 categories available", "resolution_attempted": "Participant registry and Source 90 cells audited.", "reason": "No public official twelve-category allocation or proxy-numerator source accepted."},
        {"economy_code": "LBR", "economy_name": "Liberia", "armilar_category": "CP04|CP06|CP09|CP10|CP12", "decision": "UNAVAILABLE", "current_status": "SUPPLEMENTAL_NOMINAL_SOURCE_FAILED_UNIT_RECONCILIATION", "resolution_attempted": "UNData supplemental source compared against direct Source 90 categories.", "reason": "Median supplemental-to-Source90 ratio is incompatible; using it would risk a unit or concept error."},
    ]


def step2i_completion_summary(result: AdapterResult) -> dict[str, Any]:
    rows = result.completion_rows or []
    by_code = {row["economy_code"]: row for row in rows if row["economy_code"] in STEP2I_ECONOMIES}
    return {
        "schema_version": "1.0",
        "pipeline_version": "0.6.0",
        "step": "2I",
        "status": "COMPLETE_DIAGNOSTICALLY",
        "economies_required": list(STEP2I_ECONOMIES),
        "economies_decided": sorted(by_code),
        "accepted_cells_added_to_exact_matrix": 0,
        "experimental_cells": 0,
        "unavailable_cells": len([row for row in (result.cell_status_rows or []) if row.get("cell_class") == "UNAVAILABLE"]),
        "weights_final_remains_empty": True,
        "monetary_release_allowed": False,
        "global_12_category_matrix_complete": False,
        "summary_by_economy": by_code,
        "step2h_exceptions": step2h_exception_rows(),
    }


def write_step2i_report(path: Path, result: AdapterResult) -> None:
    summary = step2i_completion_summary(result)
    lines = [
        "# Step 2I completion report",
        "",
        "Generated: deterministic Step 2I report",
        "",
        "## Version mapping",
        "",
        "| Version | Project step | Meaning |",
        "|---|---|---|",
        "| 0.4.0 | Step 2H | Gap resolver and source probe |",
        "| 0.5.0 | Step 2I start | National adapter architecture and first audits |",
        "| 0.6.0 | Step 2I completion | Diagnostic closure for China, India, Russia, Indonesia and Brazil |",
        "",
        "## Step 2I decisions",
        "",
    ]
    for row in result.completion_rows or []:
        if row["economy_code"] not in STEP2I_ECONOMIES:
            continue
        lines.append(
            f"- {row['economy_code']} {row['economy_name']}: decision `{row['decision']}`, "
            f"accepted `{row['accepted_categories'] or 'none'}`, unavailable `{row['unavailable_categories']}`. "
            f"Blocker: {row['remaining_blockers']}"
        )
    lines.extend([
        "",
        "## Coverage",
        "",
        f"- Exact cells added: `{summary['accepted_cells_added_to_exact_matrix']}`",
        "- Coverage change: `0` complete economies; all gates remain fail-closed.",
        "- `weights_final.csv` remains empty.",
        "",
        "## Step 2H exceptions",
        "",
    ])
    for row in step2h_exception_rows():
        lines.append(f"- {row['economy_code']} {row['armilar_category']}: `{row['decision']}` - {row['reason']}")
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
    return "UNAVAILABLE"


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
