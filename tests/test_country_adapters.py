from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from armilar_pipeline.acquire import AcquisitionRecord
from armilar_pipeline.config import load_config
from armilar_pipeline.country_adapters import (
    IndiaMospiAdapter,
    RussiaRosstatAuditAdapter,
    ChinaNbsAuditAdapter,
    analyse_china_source,
    china_methodology_gate_rows,
    validate_china_methodology_gate_rows,
    analyse_russia_source,
    russia_methodology_gate_rows,
    validate_russia_methodology_gate_rows,
    classify_cell,
    parse_india_statement_5_1,
    reconcile_india,
    registered_adapters,
    run_country_adapters_only,
    METHODOLOGICAL_STATES,
    completion_row,
    step2i_completion_summary,
    validate_india_methodology_gate_rows,
    india_methodology_gate_rows,
    validate_mixed_provider_cells,
)
from armilar_pipeline.country_cli import main as country_main
from armilar_pipeline.util import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def make_india_workbook(path: Path) -> None:
    strings: list[str] = []

    def s(value: str) -> int:
        strings.append(value)
        return len(strings) - 1

    items = {
        "1": ("Food and non-alcoholic beverages", "100"),
        "2": ("Alcoholic beverages, tobacco and narcotics", "60"),
        "2.1": ("Alcoholic beverages", "20"),
        "2.2": ("Tobacco", "30"),
        "2.3": ("Narcotics", "10"),
        "3": ("Clothing and footwear", "100"),
        "4": ("Housing, water, electricity, gas and other fuels", "100"),
        "5": ("Furnishing, household equipment and routine household maintenance", "100"),
        "6": ("Health", "100"),
        "7": ("Transport", "100"),
        "8": ("Communication", "100"),
        "9": ("Recreation and culture", "100"),
        "10": ("Education", "100"),
        "11": ("Restaurants and hotels", "100"),
        "12": ("Miscellaneous goods and services", "100"),
        "13": ("Total", "1160"),
    }
    cells = [
        '<c r="C7" t="s"><v>{}</v></c>'.format(s("2021-22")),
    ]
    row_number = 9
    for code, (name, value) in items.items():
        cells.append(f'<c r="C{row_number}"><v>{value}</v></c>')
        cells.append('<c r="AA{}" t="s"><v>{}</v></c>'.format(row_number, s(name)))
        cells.append('<c r="AB{}" t="s"><v>{}</v></c>'.format(row_number, s(code)))
        row_number += 1
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="7">{}</row>{}</sheetData></worksheet>'
    ).format(cells[0], "".join(f'<row r="{index}">{"".join(cells[1 + (index - 9) * 3:1 + (index - 8) * 3])}</row>' for index in range(9, row_number)))
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{0}" uniqueCount="{0}">{1}</sst>'
    ).format(len(strings), "".join(f"<si><t>{value}</t></si>" for value in strings))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="5.1" sheetId="1"/></sheets></workbook>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", shared)


def make_official_methodology_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")


def make_india_fetch(workbook: Path, methodology: Path):
    def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = methodology if source_id == IndiaMospiAdapter.methodology_source_id else workbook
        destination.write_bytes(source.read_bytes())
        content_type = (
            "application/pdf" if source_id == IndiaMospiAdapter.methodology_source_id
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return AcquisitionRecord(
            source_id, url, url, destination, "fresh", 200, content_type,
            destination.stat().st_size, sha256_file(destination),
            "2026-06-28T00:00:00Z", (),
        )
    return fake_fetch


def make_russia_fedstat_html(path: Path, *, include_title: bool = True) -> None:
    title = "Расходы на конечное потребление домашних хозяйств" if include_title else "Другой показатель"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><body><h1>{title}</h1><div>Текущие цены</div><div>2021</div>"
        "<div>Территория</div><div>Единица измерения</div></body></html>",
        encoding="utf-8",
    )


def make_russia_sut_workbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="5" uniqueCount="5">'
        '<si><t>Таблицы ресурсов и использования 2021</t></si>'
        '<si><t>Продукты и услуги ОКПД2</t></si>'
        '<si><t>Расходы на конечное потребление домашних хозяйств и некоммерческих организаций, обслуживающих домашние хозяйства</t></si>'
        '<si><t>Текущие цены</t></si>'
        '<si><t>Российская Федерация</t></si>'
        '</sst>'
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">'
        + ''.join(f'<c r="{col}1" t="s"><v>{idx}</v></c>' for idx, col in enumerate("ABCDE"))
        + '</row></sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def make_russia_hbs_html(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<html><body>Доходы, расходы и потребление домашних хозяйств в 2021 году. "
        "Обследование бюджетов домашних хозяйств. КИПЦ-ДХ, версия 5.</body></html>",
        encoding="utf-8",
    )


def make_russia_kipc_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>КИПЦ-ДХ Классификатор индивидуального потребления домашних хозяйств по целям</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def make_russia_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")


def make_russia_fetch(files: dict[str, Path], *, blocked: set[str] | None = None):
    blocked = blocked or set()
    def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
        if source_id in blocked:
            raise OSError(f"blocked:{source_id}")
        source = files[source_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        content_type = {
            "RUT_FEDSTAT_HFCE_31414": "text/html",
            "RUT_ROSSTAT_SUT_2021_XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "RUT_ROSSTAT_HBS_2021": "text/html",
            "RUT_ROSSTAT_KIPC_DH_CLASSIFICATION": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022": "application/pdf",
        }[source_id]
        return AcquisitionRecord(
            source_id, url, url, destination, "fresh", 200, content_type,
            destination.stat().st_size, sha256_file(destination),
            "2026-06-29T12:00:00Z", (),
        )
    return fake_fetch


def make_russia_sources(root: Path) -> dict[str, Path]:
    files = {
        "RUT_FEDSTAT_HFCE_31414": root / "fedstat.html",
        "RUT_ROSSTAT_SUT_2021_XLSX": root / "sut.xlsx",
        "RUT_ROSSTAT_HBS_2021": root / "hbs.html",
        "RUT_ROSSTAT_KIPC_DH_CLASSIFICATION": root / "kipc.docx",
        "RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022": root / "accounts.pdf",
    }
    make_russia_fedstat_html(files["RUT_FEDSTAT_HFCE_31414"])
    make_russia_sut_workbook(files["RUT_ROSSTAT_SUT_2021_XLSX"])
    make_russia_hbs_html(files["RUT_ROSSTAT_HBS_2021"])
    make_russia_kipc_docx(files["RUT_ROSSTAT_KIPC_DH_CLASSIFICATION"])
    make_russia_pdf(files["RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022"])
    return files


def make_china_survey_html(path: Path, *, valid: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    title = "Households' Income and Consumption Expenditure in 2021" if valid else "Updated statistical release"
    categories = (
        "Food, tobacco and liquor; Clothing; Residence; Household facilities, articles and services; "
        "Transportation and telecommunication; Education, culture and recreation; "
        "Health care and medical services; Miscellaneous goods and services."
    ) if valid else "Revised category structure pending review."
    survey_note = "The data is based on a sampling survey of more than 100000 survey households." if valid else "Methodology changed."
    path.write_text(
        f"<html><body><h1>{title}</h1><p>2021 per capita consumption expenditure.</p>"
        f"<p>{categories}</p><p>{survey_note}</p></body></html>",
        encoding="utf-8",
    )


def make_china_yearbook_index(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<html><body><h1>China Statistical Yearbook 2022</h1>"
        "<div>3-13 Household Consumption Expenditure</div>"
        "<div>3-21 Intermediate Use Part of 2020 Input-Output Table</div>"
        "<div>3-22 Final Use Part of 2020 Input-Output Table</div></body></html>",
        encoding="utf-8",
    )


def make_china_national_accounts_brief(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<html><body>The 2020 input-output table was compiled from products, goods and services. "
        "It contains competitive input-output and non-competitive input-output tables.</body></html>",
        encoding="utf-8",
    )


def make_china_gdp_verification(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<html><body><h1>Announcement on the Final Verification of GDP in 2021</h1>"
        "<p>Total at current price. GDP by expenditure approach includes final consumption expenditure, "
        "gross capital formation and net exports.</p></body></html>",
        encoding="utf-8",
    )


def make_china_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")


def make_china_sources(root: Path) -> dict[str, Path]:
    files = {
        "CHN_NBS_2021_HOUSEHOLD_CONSUMPTION": root / "survey.html",
        "CHN_NBS_YEARBOOK_2022_INDEX": root / "yearbook.html",
        "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF": root / "brief.html",
        "CHN_NBS_2021_GDP_FINAL_VERIFICATION": root / "gdp.html",
        "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_NOTES": root / "accounts.pdf",
        "CHN_NBS_YEARBOOK_2022_HOUSEHOLD_SURVEY_NOTES": root / "survey_notes.pdf",
    }
    make_china_survey_html(files["CHN_NBS_2021_HOUSEHOLD_CONSUMPTION"])
    make_china_yearbook_index(files["CHN_NBS_YEARBOOK_2022_INDEX"])
    make_china_national_accounts_brief(files["CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF"])
    make_china_gdp_verification(files["CHN_NBS_2021_GDP_FINAL_VERIFICATION"])
    make_china_pdf(files["CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_NOTES"])
    make_china_pdf(files["CHN_NBS_YEARBOOK_2022_HOUSEHOLD_SURVEY_NOTES"])
    return files


def make_china_fetch(files: dict[str, Path], *, blocked: set[str] | None = None):
    blocked = blocked or set()
    def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
        if source_id in blocked:
            raise OSError(f"blocked:{source_id}")
        source = files[source_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        content_type = "application/pdf" if source.suffix == ".pdf" else "text/html"
        return AcquisitionRecord(
            source_id, url, url, destination, "fresh", 200, content_type,
            destination.stat().st_size, sha256_file(destination),
            "2026-06-29T13:30:00Z", (),
        )
    return fake_fetch


class CountryAdapterTests(unittest.TestCase):
    def test_registry_exposes_priority_adapters(self) -> None:
        registry = registered_adapters()
        self.assertIn("IND", registry)
        self.assertIn("RUT", registry)
        self.assertIn("CHN", registry)

    def test_india_statement_5_1_parses_fiscal_year_without_calendar_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "5.1.xlsx"
            make_india_workbook(workbook)
            parsed = parse_india_statement_5_1(workbook)
            self.assertEqual(parsed["1"]["name"], "Food and non-alcoholic beverages")
            self.assertEqual(parsed["2.3"]["name"], "Narcotics")
            self.assertGreater(parsed["13"]["value"], parsed["2.3"]["value"])

    def test_india_reconciliation_excludes_narcotics_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "5.1.xlsx"
            make_india_workbook(workbook)
            parsed = parse_india_statement_5_1(workbook)
            reconciliation = reconcile_india(parsed)
            self.assertEqual(reconciliation["status"], "PASS")
            self.assertEqual(
                reconciliation["source_total"],
                reconciliation["accepted_total"] + reconciliation["excluded_total"],
            )

    def test_cli_acquire_writes_outputs_and_keeps_india_blocked_until_boundary_confirmed(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "5.1.xlsx"
            methodology = root / "chapter22.pdf"
            make_india_workbook(workbook)
            make_official_methodology_pdf(methodology)

            with patch.object(IndiaMospiAdapter, "reviewed_methodology_sha256", sha256_file(methodology)), \
                    patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_india_fetch(workbook, methodology)):
                summary = run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["IND", "CHN"]
                )
            self.assertEqual(summary["adapters_run"], 2)
            self.assertTrue((root / "run" / "outputs" / "country_adapter_status.csv").exists())
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                rows = {row["economy_code"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["IND"]["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
            self.assertEqual(rows["IND"]["status"], "REJECTED_BY_CONFIRMED_METHOD_GATE")
            self.assertTrue((root / "run" / "outputs" / "country_cell_status.csv").exists())
            self.assertTrue((root / "run" / "outputs" / "step2i_completion_summary.json").exists())
            self.assertTrue((root / "run" / "outputs" / "step2i_audit_summary.json").exists())
            self.assertTrue((root / "run" / "outputs" / "country_source_family_coverage.csv").exists())
            self.assertTrue((root / "run" / "outputs" / "STEP_2I_AUDIT_REPORT.md").exists())
            self.assertTrue((root / "run" / "outputs" / "INDIA_METHOD_GATE_REPORT.md").exists())
            with (root / "run" / "outputs" / "india_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
                gates = {row["criterion"]: row for row in csv.DictReader(handle)}
            self.assertEqual(gates["excludes_NPISH"]["status"], "CONTRADICTED")
            self.assertEqual(gates["compatible_with_armilar_calendar_2021"]["status"], "CONTRADICTED")
            self.assertEqual(len(gates["excludes_NPISH"]["source_sha256"]), 64)

    def test_country_cli_rejects_unknown_command_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(country_main(["acquire", "ZZZ", "--run-dir", str(Path(tmp) / "run")]), 0)

    def test_cell_classification_is_per_cell(self) -> None:
        self.assertEqual(classify_cell({"data_class": "EXACT_OFFICIAL", "quality_flags": "NO_ALLOCATION"}), "OFFICIAL_DERIVED_NO_ALLOCATION")
        self.assertEqual(classify_cell({"data_class": "EXPERIMENTAL_ALLOCATION"}), "OFFICIAL_EXPERIMENTAL_ALLOCATION")
        self.assertEqual(classify_cell({"data_class": "CONCEPT_AMBIGUOUS"}), "CONCEPT_AMBIGUOUS")
        self.assertEqual(classify_cell({"data_class": "UNAVAILABLE"}), "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")

    def test_methodological_states_and_final_unavailability_gate(self) -> None:
        self.assertIn("NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE", METHODOLOGICAL_STATES)
        self.assertIn("ACCESS_BLOCKED", METHODOLOGICAL_STATES)
        self.assertIn("UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT", METHODOLOGICAL_STATES)
        with self.assertRaises(ValueError):
            completion_row("AAA", "Alpha", "not exhaustive", 1, "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT")

    def test_india_methodology_audit_distinguishes_unacquired_from_confirmed_rejection(self) -> None:
        rows = {row["criterion"]: row for row in india_methodology_gate_rows()}
        self.assertEqual(rows["reference_period_2021_22_available"]["status"], "CONFIRMED")
        self.assertEqual(rows["compatible_with_armilar_calendar_2021"]["status"], "CONTRADICTED")
        self.assertEqual(rows["excludes_NPISH"]["status"], "NOT_FOUND")

        methodology_record = AcquisitionRecord(
            IndiaMospiAdapter.methodology_source_id, IndiaMospiAdapter.methodology_url,
            IndiaMospiAdapter.methodology_url, Path("chapter22.pdf"), "fresh", 200,
            "application/pdf", 10, "b" * 64, "2026-06-29T00:00:00Z", (),
        )
        confirmed = {
            row["criterion"]: row
            for row in india_methodology_gate_rows(methodology_record=methodology_record)
        }
        self.assertEqual(confirmed["represents_households_S14"]["status"], "CONTRADICTED")
        self.assertEqual(confirmed["excludes_NPISH"]["status"], "CONTRADICTED")
        self.assertEqual(confirmed["excludes_government_consumption"]["status"], "CONFIRMED")
        self.assertEqual(confirmed["includes_imputed_rent"]["status"], "CONFIRMED")
        self.assertEqual(confirmed["excludes_NPISH"]["source_sha256"], "b" * 64)

    def test_india_gate_validator_rejects_invalid_status_and_inconsistent_sector_logic(self) -> None:
        rows = india_methodology_gate_rows()
        rows[0]["status"] = "PROBABLY"
        with self.assertRaisesRegex(ValueError, "invalid statuses"):
            validate_india_methodology_gate_rows(rows)

        rows = india_methodology_gate_rows()
        by_criterion = {row["criterion"]: row for row in rows}
        by_criterion["excludes_NPISH"]["status"] = "CONTRADICTED"
        by_criterion["represents_households_S14"]["status"] = "CONFIRMED"
        with self.assertRaisesRegex(ValueError, "strict S14"):
            validate_india_methodology_gate_rows(rows)

    def test_india_unreviewed_methodology_hash_fails_closed(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "5.1.xlsx"
            methodology = root / "changed.pdf"
            make_india_workbook(workbook)
            make_official_methodology_pdf(methodology)
            with patch.object(IndiaMospiAdapter, "reviewed_methodology_sha256", "0" * 64), \
                    patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_india_fetch(workbook, methodology)):
                run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["IND"]
                )
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "METHODOLOGY_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")
            with (root / "run" / "outputs" / "india_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
                gates = {row["criterion"]: row for row in csv.DictReader(handle)}
            self.assertEqual(gates["excludes_NPISH"]["status"], "NOT_FOUND")
            self.assertEqual(gates["excludes_NPISH"]["review_mode"], "STRUCTURED_WORKBOOK_VALIDATION")
            self.assertEqual(status["accepted_rows"], "0")

    def test_workflow_is_pull_request_safe(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_mixed_provider_cells_are_admissible_when_concepts_match(self) -> None:
        base = {
            "economy_code": "AAA", "economy_name": "Alpha", "reference_period": "2021",
            "value": "1", "currency": "LCU", "unit": "million", "sector": "S14",
            "transaction": "P31DC", "classification": "COICOP", "source_file": "raw.csv",
            "source_url": "https://example.test", "source_hash": "a" * 64,
            "data_class": "OFFICIAL_EXACT_DERIVATION",
            "quality_flags": "CURRENT_PRICES|NPISH_EXCLUDED|GOVERNMENT_EXCLUDED|NO_ALLOCATION",
        }
        rows = [
            {**base, "armilar_category": "CP04", "source_authority": "Authority A"},
            {**base, "armilar_category": "CP06", "source_authority": "Authority B"},
        ]
        self.assertEqual(validate_mixed_provider_cells(rows), (True, "PASS"))

    def test_mixed_provider_cells_reject_incompatible_concepts_years_and_units(self) -> None:
        base = {
            "economy_code": "AAA", "economy_name": "Alpha", "reference_period": "2021",
            "armilar_category": "CP04", "value": "1", "currency": "LCU", "unit": "million",
            "sector": "S14", "transaction": "P31DC", "classification": "COICOP",
            "source_authority": "Authority", "source_file": "raw.csv",
            "source_url": "https://example.test", "source_hash": "a" * 64,
            "data_class": "OFFICIAL_EXACT_DERIVATION",
            "quality_flags": "CURRENT_PRICES|NPISH_EXCLUDED|GOVERNMENT_EXCLUDED|NO_ALLOCATION",
        }
        self.assertEqual(validate_mixed_provider_cells([{**base, "sector": "S14_S15"}])[1], "INCOMPATIBLE_SECTOR")
        self.assertEqual(validate_mixed_provider_cells([base, {**base, "armilar_category": "CP06", "reference_period": "2022"}])[1], "INCOMPATIBLE_REFERENCE_PERIOD")
        self.assertEqual(validate_mixed_provider_cells([base, {**base, "armilar_category": "CP06", "unit": "billion"}])[1], "INCOMPATIBLE_UNIT")

    def test_step2i_summary_is_deterministic_and_fail_closed(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "5.1.xlsx"
            methodology = root / "chapter22.pdf"
            make_india_workbook(workbook)
            make_official_methodology_pdf(methodology)

            with patch.object(IndiaMospiAdapter, "reviewed_methodology_sha256", sha256_file(methodology)), \
                    patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_india_fetch(workbook, methodology)):
                run_country_adapters_only(config, run_root=root / "run1", cache_root=root / "cache", economy_codes=["IND", "CHN", "RUT", "IDN", "BRA"])
                run_country_adapters_only(config, run_root=root / "run2", cache_root=root / "cache", economy_codes=["IND", "CHN", "RUT", "IDN", "BRA"])
            one = (root / "run1" / "outputs" / "step2i_completion_summary.json").read_text(encoding="utf-8")
            two = (root / "run2" / "outputs" / "step2i_completion_summary.json").read_text(encoding="utf-8")
            self.assertEqual(one, two)
            self.assertIn('"accepted_cells_added_to_exact_matrix": 0', one)
            self.assertIn('"weights_final_remains_empty": true', one)


    def test_russia_sources_keep_aggregate_sut_and_survey_concepts_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = make_russia_sources(Path(tmp))
            fedstat = analyse_russia_source("RUT_FEDSTAT_HFCE_31414", files["RUT_FEDSTAT_HFCE_31414"], "text/html")
            sut = analyse_russia_source("RUT_ROSSTAT_SUT_2021_XLSX", files["RUT_ROSSTAT_SUT_2021_XLSX"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            hbs = analyse_russia_source("RUT_ROSSTAT_HBS_2021", files["RUT_ROSSTAT_HBS_2021"], "text/html")
            self.assertTrue(fedstat["aggregate_hfce"])
            self.assertFalse(fedstat["purpose_dimension"])
            self.assertEqual(fedstat["decision"], "REJECT_AGGREGATE_ONLY")
            self.assertTrue(sut["product_classification"])
            self.assertFalse(sut["purpose_classification"])
            self.assertTrue(sut["households_npish_combined_marker"])
            self.assertEqual(sut["decision"], "REJECT_ALLOCATION_REQUIRED")
            self.assertTrue(hbs["purpose_classification"])
            self.assertEqual(hbs["decision"], "REJECT_CLASS_C_SURVEY")

    def test_russia_full_source_chain_is_rejected_without_exact_cells(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_russia_sources(root)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_russia_fetch(files)):
                summary = run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["RUT"]
                )
            self.assertEqual(summary["accepted_rows"], 0)
            self.assertEqual(summary["failures"], 0)
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
            self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
            with (root / "run" / "outputs" / "russia_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
                gates = {row["criterion"]: row for row in csv.DictReader(handle)}
            self.assertEqual(gates["aggregate_household_hfce_available"]["status"], "CONFIRMED")
            self.assertEqual(gates["twelve_purpose_categories_in_national_accounts"]["status"], "CONTRADICTED")
            self.assertEqual(gates["sut_is_exact_purpose_classification"]["status"], "CONTRADICTED")
            self.assertEqual(gates["household_survey_is_national_accounts_p31dc"]["status"], "CONTRADICTED")
            self.assertEqual(gates["exact_armilar_source_available"]["status"], "CONTRADICTED")
            self.assertTrue((root / "run" / "outputs" / "RUSSIA_METHOD_GATE_REPORT.md").exists())
            self.assertEqual(len(list((root / "run" / "raw" / "country_adapters" / "RUT").rglob("*.*"))), 5)

    def test_russia_blocked_critical_source_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_russia_sources(root)
            with patch(
                "armilar_pipeline.country_adapters.fetch_url",
                side_effect=make_russia_fetch(files, blocked={"RUT_ROSSTAT_SUT_2021_XLSX"}),
            ):
                run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["RUT"]
                )
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            self.assertEqual(status["data_class"], "ACCESS_BLOCKED")
            with (root / "run" / "outputs" / "country_source_attempts.csv").open(encoding="utf-8", newline="") as handle:
                attempts = list(csv.DictReader(handle))
            blocked = [row for row in attempts if row["dataset"] == "RUT_ROSSTAT_SUT_2021_XLSX"]
            self.assertTrue(blocked)
            self.assertTrue(all(row["retrieval_status"] == "ACCESS_BLOCKED" for row in blocked))
            self.assertTrue(all(not row["sha256"] for row in blocked))

    def test_russia_changed_critical_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_russia_sources(root)
            make_russia_fedstat_html(files["RUT_FEDSTAT_HFCE_31414"], include_title=False)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_russia_fetch(files)):
                run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["RUT"]
                )
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_russia_gate_validator_rejects_inconsistent_exact_source_conclusion(self) -> None:
        rows = russia_methodology_gate_rows()
        rows[0]["status"] = "PROBABLY"
        with self.assertRaisesRegex(ValueError, "invalid statuses"):
            validate_russia_methodology_gate_rows(rows)


    def test_china_sources_keep_survey_io_and_national_accounts_concepts_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = make_china_sources(Path(tmp))
            survey = analyse_china_source("CHN_NBS_2021_HOUSEHOLD_CONSUMPTION", files["CHN_NBS_2021_HOUSEHOLD_CONSUMPTION"], "text/html")
            index = analyse_china_source("CHN_NBS_YEARBOOK_2022_INDEX", files["CHN_NBS_YEARBOOK_2022_INDEX"], "text/html")
            io_source = analyse_china_source("CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF", files["CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF"], "text/html")
            gdp = analyse_china_source("CHN_NBS_2021_GDP_FINAL_VERIFICATION", files["CHN_NBS_2021_GDP_FINAL_VERIFICATION"], "text/html")
            self.assertTrue(survey["household_survey"])
            self.assertTrue(survey["eight_group_classification"])
            self.assertEqual(survey["decision"], "REJECT_CLASS_C_EIGHT_GROUP_SURVEY")
            self.assertTrue(index["input_output_reference_2020"])
            self.assertEqual(index["decision"], "DISCOVERY_INVENTORY_ONLY")
            self.assertTrue(io_source["product_classification"])
            self.assertFalse(io_source["purpose_classification"])
            self.assertEqual(io_source["decision"], "REJECT_WRONG_YEAR_PRODUCT_IO")
            self.assertFalse(gdp["purpose_dimension"])
            self.assertEqual(gdp["decision"], "REJECT_AGGREGATE_ONLY")

    def test_china_full_source_chain_is_rejected_without_exact_cells(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_china_sources(root)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_china_fetch(files)):
                summary = run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["CHN"]
                )
            self.assertEqual(summary["accepted_rows"], 0)
            self.assertEqual(summary["failures"], 0)
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
            self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
            with (root / "run" / "outputs" / "china_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
                gates = {row["criterion"]: row for row in csv.DictReader(handle)}
            self.assertEqual(gates["official_2021_household_survey_available"]["status"], "CONFIRMED")
            self.assertEqual(gates["survey_has_twelve_armilar_categories"]["status"], "CONTRADICTED")
            self.assertEqual(gates["survey_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
            self.assertEqual(gates["input_output_reference_year_matches_2021"]["status"], "CONTRADICTED")
            self.assertEqual(gates["exact_armilar_source_available"]["status"], "CONTRADICTED")
            self.assertTrue((root / "run" / "outputs" / "CHINA_METHOD_GATE_REPORT.md").exists())
            self.assertEqual(len(list((root / "run" / "raw" / "country_adapters" / "CHN").rglob("*.*"))), 6)

    def test_china_blocked_critical_source_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_china_sources(root)
            with patch(
                "armilar_pipeline.country_adapters.fetch_url",
                side_effect=make_china_fetch(files, blocked={"CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF"}),
            ):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["CHN"])
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            self.assertEqual(status["data_class"], "ACCESS_BLOCKED")
            with (root / "run" / "outputs" / "country_source_attempts.csv").open(encoding="utf-8", newline="") as handle:
                attempts = list(csv.DictReader(handle))
            blocked = [row for row in attempts if row["dataset"] == "CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF"]
            self.assertTrue(blocked)
            self.assertTrue(all(row["retrieval_status"] == "ACCESS_BLOCKED" for row in blocked))
            self.assertTrue(all(not row["sha256"] for row in blocked))

    def test_china_changed_critical_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = make_china_sources(root)
            make_china_survey_html(files["CHN_NBS_2021_HOUSEHOLD_CONSUMPTION"], valid=False)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_china_fetch(files)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["CHN"])
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                status = next(csv.DictReader(handle))
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_china_gate_validator_rejects_inconsistent_exact_source_conclusion(self) -> None:
        rows = china_methodology_gate_rows()
        rows[0]["status"] = "PROBABLY"
        with self.assertRaisesRegex(ValueError, "invalid statuses"):
            validate_china_methodology_gate_rows(rows)

    def test_workflow_publishes_china_audit_outputs_only_under_existing_guards(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("china_methodology_gate_audit.csv", workflow)
        self.assertIn("CHINA_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_workflow_publishes_russia_audit_outputs_only_under_existing_guards(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("russia_methodology_gate_audit.csv", workflow)
        self.assertIn("RUSSIA_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)


if __name__ == "__main__":
    unittest.main()
