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
    parse_india_statement_5_1,
    reconcile_india,
    registered_adapters,
    run_country_adapters_only,
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
            make_india_workbook(workbook)

            def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(workbook.read_bytes())
                return AcquisitionRecord(
                    source_id, url, url, destination, "fresh", 200,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    destination.stat().st_size, sha256_file(destination),
                    "2026-06-28T00:00:00Z", (),
                )

            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=fake_fetch):
                summary = run_country_adapters_only(
                    config, run_root=root / "run", cache_root=root / "cache", economy_codes=["IND", "CHN"]
                )
            self.assertEqual(summary["adapters_run"], 2)
            self.assertTrue((root / "run" / "outputs" / "country_adapter_status.csv").exists())
            with (root / "run" / "outputs" / "country_adapter_status.csv").open(encoding="utf-8", newline="") as handle:
                rows = {row["economy_code"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["IND"]["data_class"], "UNAVAILABLE")
            self.assertEqual(rows["IND"]["status"], "BLOCKED_BY_METHOD_GATE")

    def test_country_cli_rejects_unknown_command_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(country_main(["acquire", "ZZZ", "--run-dir", str(Path(tmp) / "run")]), 0)


if __name__ == "__main__":
    unittest.main()
