from __future__ import annotations

import csv
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Protocol

from .acquire import AcquisitionRecord, fetch_url
from .config import Step2Config
from .util import sha256_file, utc_now, write_csv, write_json, write_sha256sums


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


@dataclass(frozen=True)
class AdapterResult:
    status_rows: list[dict[str, Any]]
    evidence_rows: list[dict[str, Any]]
    normalized_rows: list[dict[str, Any]]
    mapping_rows: list[dict[str, Any]]
    reconciliation_rows: list[dict[str, Any]]
    failure_rows: list[dict[str, Any]]
    acquisition_records: list[AcquisitionRecord]


class CountryAdapter(Protocol):
    economy_code: str
    economy_name: str
    adapter_id: str

    def acquire_and_parse(self, config: Step2Config, run_root: Path, cache_root: Path) -> AdapterResult:
        ...


def registered_adapters() -> dict[str, CountryAdapter]:
    adapters: list[CountryAdapter] = [
        IndiaMospiAdapter(),
        AuditOnlyAdapter(
            "RUT", "Russian Federation", "RUT_ROSSTAT_OFFICIAL_SOURCE_AUDIT",
            "Federal State Statistics Service",
            "https://eng.rosstat.gov.ru/storage/mediabank/BRICS_Joint_Statistical_Publication_2025.pdf",
            "2021", "HFCE_BY_PURPOSE_OR_COICOP_HH", "structured source not located",
            "UNAVAILABLE",
            "No deterministic official XLS/XLSX/CSV/SDMX/HTML Rosstat table with 2021 strict household COICOP-HH values has passed the gates.",
        ),
        AuditOnlyAdapter(
            "CHN", "China", "CHN_NBS_OFFICIAL_SOURCE_AUDIT",
            "National Bureau of Statistics of China",
            "https://www.stats.gov.cn/english/PressRelease/202201/t20220118_1826649.html",
            "2021", "HOUSEHOLD_SURVEY_EIGHT_GROUPS", "8 groups",
            "UNAVAILABLE",
            "Official NBS table is a household survey with eight combined groups, not national-accounts S14/P31 with twelve Armilar categories.",
        ),
        AuditOnlyAdapter("IDN", "Indonesia", "IDN_BPS_OFFICIAL_SOURCE_AUDIT", "Badan Pusat Statistik", "https://www.bps.go.id/en/publication/2025/05/28/2a1c585ebbd574dd91afed67/gross-domestic-product-of-indonesia-by-expenditure--2020-2024.html", "2021", "HFCE_REGROUPED", "7 groups", "UNAVAILABLE", "Official source identified in probe regroups COICOP and cannot be bridged exactly to twelve Armilar categories."),
        AuditOnlyAdapter("BRA", "Brazil", "BRA_IBGE_OFFICIAL_SOURCE_AUDIT", "Instituto Brasileiro de Geografia e Estatistica", "https://www.ibge.gov.br/estatisticas/economicas/comercio/9052-sistema-de-contas-nacionais-brasil.html", "2021", "SNA_PRODUCT_TABLES", "product tables", "UNAVAILABLE", "Official product tables would require many-to-many product-to-COICOP allocation."),
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
        )


class AuditOnlyAdapter:
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
        )


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
    return AdapterResult([], [], [], [], [], [], [])


def _extend(target: AdapterResult, source: AdapterResult) -> None:
    target.status_rows.extend(source.status_rows)
    target.evidence_rows.extend(source.evidence_rows)
    target.normalized_rows.extend(source.normalized_rows)
    target.mapping_rows.extend(source.mapping_rows)
    target.reconciliation_rows.extend(source.reconciliation_rows)
    target.failure_rows.extend(source.failure_rows)
    target.acquisition_records.extend(source.acquisition_records)
