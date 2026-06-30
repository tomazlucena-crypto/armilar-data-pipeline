from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from armilar_pipeline.acquire import AcquisitionRecord
from armilar_pipeline.config import load_config
from armilar_pipeline.country_adapters import (
    BrazilIbgeAuditAdapter,
    EgyptCapmasAuditAdapter,
    IndonesiaBpsAuditAdapter,
    PakistanPbsAuditAdapter,
    NigeriaNbsAuditAdapter,
    BangladeshBbsAuditAdapter,
    VietnamNsoAuditAdapter,
    registered_adapters,
    run_country_adapters_only,
    validate_brazil_methodology_gate_rows,
    validate_egypt_methodology_gate_rows,
    validate_indonesia_methodology_gate_rows,
    validate_pakistan_methodology_gate_rows,
    validate_nigeria_methodology_gate_rows,
    validate_bangladesh_methodology_gate_rows,
    validate_vietnam_methodology_gate_rows,
)
from armilar_pipeline.util import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def make_sources(root: Path, adapter) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    sources: dict[str, Path] = {}
    for spec in adapter.source_specs:
        source_id = str(spec["source_id"])
        suffix = Path(str(spec["filename"])).suffix or ".html"
        path = root / f"{source_id}{suffix}"
        markers = [str(marker) for marker in spec.get("required_markers", ())]
        content = "\n".join(markers + [str(spec.get("concept") or ""), str(spec.get("classification") or "")])
        if suffix == ".csv":
            path.write_text("title,description\n" + content.replace("\n", ",") + "\n", encoding="utf-8")
        else:
            path.write_text(f"<html><body>{content}</body></html>", encoding="utf-8")
        sources[source_id] = path
    return sources


def make_fetch(sources: dict[str, Path], blocked: set[str] | None = None):
    blocked = blocked or set()

    def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
        if source_id in blocked:
            raise OSError(f"blocked fixture source: {source_id}")
        source = sources[source_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        suffix = destination.suffix.lower()
        content_type = "text/csv" if suffix == ".csv" else "text/html"
        return AcquisitionRecord(
            source_id=source_id,
            url=url,
            final_url=url,
            path=destination,
            status="fresh",
            status_code=200,
            content_type=content_type,
            bytes=destination.stat().st_size,
            sha256=sha256_file(destination),
            retrieved_at="2026-06-29T15:00:00Z",
            attempt_errors=(),
        )

    return fake_fetch


def read_one(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle))


class RemainingCountryAuditTests(unittest.TestCase):
    def test_registry_uses_dedicated_indonesia_brazil_and_egypt_adapters(self) -> None:
        registry = registered_adapters()
        self.assertIsInstance(registry["IDN"], IndonesiaBpsAuditAdapter)
        self.assertIsInstance(registry["BRA"], BrazilIbgeAuditAdapter)
        self.assertIsInstance(registry["EGY"], EgyptCapmasAuditAdapter)
        self.assertIsInstance(registry["PAK"], PakistanPbsAuditAdapter)
        self.assertIsInstance(registry["NGA"], NigeriaNbsAuditAdapter)
        self.assertIsInstance(registry["BGD"], BangladeshBbsAuditAdapter)
        self.assertIsInstance(registry["VNM"], VietnamNsoAuditAdapter)

    def _run_full(self, adapter, code: str):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        sources = make_sources(root / "sources", adapter)
        with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
            summary = run_country_adapters_only(
                config, run_root=root / "run", cache_root=root / "cache", economy_codes=[code]
            )
        return temp, root, summary, sources

    def test_indonesia_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(IndonesiaBpsAuditAdapter(), "IDN")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
        with (root / "run" / "outputs" / "indonesia_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_indonesia_methodology_gate_rows(gates)
        exact = {row["criterion"]: row for row in gates}["exact_armilar_source_available"]
        self.assertEqual(exact["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "INDONESIA_METHOD_GATE_REPORT.md").exists())

    def test_indonesia_blocked_core_source_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = IndonesiaBpsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            blocked = {"IDN_BPS_SUPPLY_USE_TABLES"}
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources, blocked)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["IDN"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            self.assertEqual(status["data_class"], "ACCESS_BLOCKED")

    def test_indonesia_changed_core_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = IndonesiaBpsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            sources["IDN_BPS_GDP_EXPENDITURE_2020_2024"].write_text("changed page", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["IDN"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_brazil_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(BrazilIbgeAuditAdapter(), "BRA")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        with (root / "run" / "outputs" / "brazil_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_brazil_methodology_gate_rows(gates)
        self.assertEqual({r["criterion"]: r for r in gates}["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "BRAZIL_METHOD_GATE_REPORT.md").exists())

    def test_brazil_registry_row_has_complete_schema(self) -> None:
        with (ROOT / "config" / "source_probe_candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        row = next(row for row in rows if row["source_id"] == "BRA_IBGE_CLASSIFICACOES_METODOLOGIA")
        self.assertTrue(all(value is not None for value in row.values()))
        self.assertEqual(row["transaction_code"], "MULTIPLE")
        self.assertEqual(row["methodological_candidate_class"], "D_UNAVAILABLE")
        self.assertEqual(row["methodological_state"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")

    def test_egypt_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(EgyptCapmasAuditAdapter(), "EGY")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
        with (root / "run" / "outputs" / "egypt_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_egypt_methodology_gate_rows(gates)
        by_criterion = {row["criterion"]: row for row in gates}
        self.assertEqual(by_criterion["sut_reference_period_matches_2021"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["hiecs_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "EGYPT_METHOD_GATE_REPORT.md").exists())
        with (root / "run" / "outputs" / "country_cell_status.csv").open(encoding="utf-8", newline="") as handle:
            cells = list(csv.DictReader(handle))
        self.assertEqual(len(cells), 12)
        self.assertTrue(all(row["admissible_to_exact_matrix"] == "false" for row in cells))

    def test_egypt_blocked_catalogue_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = EgyptCapmasAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            with patch(
                "armilar_pipeline.country_adapters.fetch_url",
                side_effect=make_fetch(sources, {"EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV"}),
            ):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["EGY"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            self.assertEqual(status["data_class"], "ACCESS_BLOCKED")

    def test_egypt_changed_hiecs_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = EgyptCapmasAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            sources["EGY_CAPMAS_HIECS_2021"].write_text("changed catalogue entry", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["EGY"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_egypt_fixture_outputs_are_deterministic(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = EgyptCapmasAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run1", cache_root=root / "cache1", economy_codes=["EGY"])
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run2", cache_root=root / "cache2", economy_codes=["EGY"])
            outputs1 = root / "run1" / "outputs"
            outputs2 = root / "run2" / "outputs"
            names1 = sorted(path.name for path in outputs1.iterdir())
            names2 = sorted(path.name for path in outputs2.iterdir())
            self.assertEqual(names1, names2)
            for name in names1:
                self.assertEqual((outputs1 / name).read_bytes(), (outputs2 / name).read_bytes(), name)


    def test_pakistan_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(PakistanPbsAuditAdapter(), "PAK")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
        with (root / "run" / "outputs" / "pakistan_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_pakistan_methodology_gate_rows(gates)
        by_criterion = {row["criterion"]: row for row in gates}
        self.assertEqual(by_criterion["reference_period_matches_calendar_2021"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["twelve_armilar_purposes_available_in_national_accounts"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["hies_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "PAKISTAN_METHOD_GATE_REPORT.md").exists())
        with (root / "run" / "outputs" / "country_cell_status.csv").open(encoding="utf-8", newline="") as handle:
            cells = list(csv.DictReader(handle))
        self.assertEqual(len(cells), 12)
        self.assertTrue(all(row["admissible_to_exact_matrix"] == "false" for row in cells))

    def test_pakistan_blocked_workbook_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = PakistanPbsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            with patch(
                "armilar_pipeline.country_adapters.fetch_url",
                side_effect=make_fetch(sources, {"PAK_PBS_NATIONAL_ACCOUNTS_XLSX"}),
            ):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["PAK"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            self.assertEqual(status["data_class"], "ACCESS_BLOCKED")

    def test_pakistan_changed_hies_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = PakistanPbsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            sources["PAK_PBS_HIES_2018_19"].write_text("changed survey page", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["PAK"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_pakistan_fixture_outputs_are_deterministic(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = PakistanPbsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run1", cache_root=root / "cache1", economy_codes=["PAK"])
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run2", cache_root=root / "cache2", economy_codes=["PAK"])
            outputs1 = root / "run1" / "outputs"
            outputs2 = root / "run2" / "outputs"
            names1 = sorted(path.name for path in outputs1.iterdir())
            names2 = sorted(path.name for path in outputs2.iterdir())
            self.assertEqual(names1, names2)
            for name in names1:
                self.assertEqual((outputs1 / name).read_bytes(), (outputs2 / name).read_bytes(), name)


    def test_nigeria_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(NigeriaNbsAuditAdapter(), "NGA")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        with (root / "run" / "outputs" / "nigeria_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_nigeria_methodology_gate_rows(gates)
        by_criterion = {row["criterion"]: row for row in gates}
        self.assertEqual(by_criterion["household_consumption_is_purpose_classified"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["download_is_machine_readable_twelve_purpose_data"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["consumption_pattern_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "NIGERIA_METHOD_GATE_REPORT.md").exists())

    def test_nigeria_blocked_report_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = NigeriaNbsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources, {"NGA_NBS_ELIBRARY_REPORT_PAGE"})):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["NGA"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")

    def test_nigeria_changed_survey_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = NigeriaNbsAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            sources["NGA_NBS_CONSUMPTION_PATTERN_2019"].write_text("changed survey page", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["NGA"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")


    def test_bangladesh_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(BangladeshBbsAuditAdapter(), "BGD")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        with (root / "run" / "outputs" / "bangladesh_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_bangladesh_methodology_gate_rows(gates)
        by_criterion = {row["criterion"]: row for row in gates}
        self.assertEqual(by_criterion["twelve_armilar_purposes_available_in_national_accounts"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["hies_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["hies_reference_period_matches_2021"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "BANGLADESH_METHOD_GATE_REPORT.md").exists())

    def test_bangladesh_blocked_portal_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); adapter = BangladeshBbsAuditAdapter(); sources = make_sources(root / "sources", adapter)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources, {"BGD_BBS_NSDS_PORTAL"})):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["BGD"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")

    def test_bangladesh_changed_hies_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); adapter = BangladeshBbsAuditAdapter(); sources = make_sources(root / "sources", adapter)
            sources["BGD_BBS_HIES_DOCUMENTATION"].write_text("changed survey page", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["BGD"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")


    def test_vietnam_full_source_chain_rejects_without_exact_rows(self) -> None:
        temp, root, summary, _ = self._run_full(VietnamNsoAuditAdapter(), "VNM")
        self.addCleanup(temp.cleanup)
        self.assertEqual(summary["accepted_rows"], 0)
        self.assertEqual(summary["failures"], 0)
        status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
        self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
        with (root / "run" / "outputs" / "vietnam_methodology_gate_audit.csv").open(encoding="utf-8", newline="") as handle:
            gates = list(csv.DictReader(handle))
        validate_vietnam_methodology_gate_rows(gates)
        by_criterion = {row["criterion"]: row for row in gates}
        self.assertEqual(by_criterion["2021_release_is_household_level_by_purpose"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["vhlss_is_national_accounts_s14_p31"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["vhlss_reference_period_matches_2021"]["status"], "CONTRADICTED")
        self.assertEqual(by_criterion["exact_armilar_source_available"]["status"], "CONTRADICTED")
        self.assertTrue((root / "run" / "outputs" / "VIETNAM_METHOD_GATE_REPORT.md").exists())

    def test_vietnam_blocked_release_prevents_closed_rejection(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); adapter = VietnamNsoAuditAdapter(); sources = make_sources(root / "sources", adapter)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources, {"VNM_NSO_SOCIO_ECONOMIC_2021"})):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["VNM"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")

    def test_vietnam_changed_vhlss_content_requires_review(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); adapter = VietnamNsoAuditAdapter(); sources = make_sources(root / "sources", adapter)
            sources["VNM_NSO_VHLSS_2022"].write_text("changed survey page", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["VNM"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")

    def test_workflow_publishes_vietnam_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("vietnam_methodology_gate_audit.csv", workflow)
        self.assertIn("VIETNAM_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_workflow_publishes_bangladesh_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("bangladesh_methodology_gate_audit.csv", workflow)
        self.assertIn("BANGLADESH_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_workflow_publishes_nigeria_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("nigeria_methodology_gate_audit.csv", workflow)
        self.assertIn("NIGERIA_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_workflow_publishes_pakistan_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("pakistan_methodology_gate_audit.csv", workflow)
        self.assertIn("PAKISTAN_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_workflow_publishes_egypt_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        self.assertIn("egypt_methodology_gate_audit.csv", workflow)
        self.assertIn("EGYPT_METHOD_GATE_REPORT.md", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)


if __name__ == "__main__":
    unittest.main()

class Step2HExceptionAuditTests(unittest.TestCase):
    def _run_full(self, adapter, code: str):
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        sources = make_sources(root / "sources", adapter)
        with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
            summary = run_country_adapters_only(
                config, run_root=root / "run", cache_root=root / "cache", economy_codes=[code]
            )
        return temp, root, summary, sources

    def test_exception_adapters_are_registered(self) -> None:
        from armilar_pipeline.country_adapters import (
            BelarusBelstatExceptionAuditAdapter,
            KuwaitCsbExceptionAuditAdapter,
            SaudiGastatExceptionAuditAdapter,
            BonaireCbsExceptionAuditAdapter,
            LiberiaLisgisExceptionAuditAdapter,
        )
        registry = registered_adapters()
        self.assertIsInstance(registry["BLR"], BelarusBelstatExceptionAuditAdapter)
        self.assertIsInstance(registry["KWT"], KuwaitCsbExceptionAuditAdapter)
        self.assertIsInstance(registry["SAU"], SaudiGastatExceptionAuditAdapter)
        self.assertIsInstance(registry["BON"], BonaireCbsExceptionAuditAdapter)
        self.assertIsInstance(registry["LBR"], LiberiaLisgisExceptionAuditAdapter)

    def test_each_exception_source_chain_rejects_without_exact_rows(self) -> None:
        from armilar_pipeline.country_adapters import (
            BelarusBelstatExceptionAuditAdapter,
            KuwaitCsbExceptionAuditAdapter,
            SaudiGastatExceptionAuditAdapter,
            BonaireCbsExceptionAuditAdapter,
            LiberiaLisgisExceptionAuditAdapter,
        )
        for code, adapter in [
            ("BLR", BelarusBelstatExceptionAuditAdapter()),
            ("KWT", KuwaitCsbExceptionAuditAdapter()),
            ("SAU", SaudiGastatExceptionAuditAdapter()),
            ("BON", BonaireCbsExceptionAuditAdapter()),
            ("LBR", LiberiaLisgisExceptionAuditAdapter()),
        ]:
            with self.subTest(code=code):
                temp, root, summary, _ = self._run_full(adapter, code)
                try:
                    self.assertEqual(summary["accepted_rows"], 0)
                    status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
                    self.assertEqual(status["status"], "REJECTED_BY_CONFIRMED_SOURCE_GATES")
                    self.assertEqual(status["data_class"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
                    exception = read_one(root / "run" / "outputs" / "step2h_exception_audit.csv")
                    self.assertEqual(exception["economy_code"], code)
                    self.assertEqual(exception["decision"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
                    with (root / "run" / "outputs" / "country_normalized_rows.csv").open(encoding="utf-8") as handle:
                        self.assertEqual(len(handle.read().splitlines()), 1)
                finally:
                    temp.cleanup()

    def test_blocked_exception_source_prevents_closed_rejection(self) -> None:
        from armilar_pipeline.country_adapters import KuwaitCsbExceptionAuditAdapter
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = KuwaitCsbExceptionAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            blocked = {"KWT_CSB_HIES_2019_2021"}
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources, blocked)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["KWT"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "ACCESS_BLOCKED")
            exception = read_one(root / "run" / "outputs" / "step2h_exception_audit.csv")
            self.assertEqual(exception["decision"], "ACCESS_BLOCKED")

    def test_changed_exception_source_requires_review(self) -> None:
        from armilar_pipeline.country_adapters import BonaireCbsExceptionAuditAdapter
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = BonaireCbsExceptionAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            sources["BON_CBS_CPI_WEIGHTS"].write_text("changed source", encoding="utf-8")
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=make_fetch(sources)):
                run_country_adapters_only(config, run_root=root / "run", cache_root=root / "cache", economy_codes=["BON"])
            status = read_one(root / "run" / "outputs" / "country_adapter_status.csv")
            self.assertEqual(status["status"], "SOURCE_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(status["data_class"], "CONCEPT_AMBIGUOUS")

    def test_exception_fixture_outputs_are_deterministic(self) -> None:
        from armilar_pipeline.country_adapters import SaudiGastatExceptionAuditAdapter
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = SaudiGastatExceptionAuditAdapter()
            sources = make_sources(root / "sources", adapter)
            fetch = make_fetch(sources)
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=fetch):
                run_country_adapters_only(config, run_root=root / "run1", cache_root=root / "cache1", economy_codes=["SAU"])
            with patch("armilar_pipeline.country_adapters.fetch_url", side_effect=fetch):
                run_country_adapters_only(config, run_root=root / "run2", cache_root=root / "cache2", economy_codes=["SAU"])
            files1 = sorted(p.relative_to(root / "run1") for p in (root / "run1").rglob("*") if p.is_file() and p.name != "SHA256SUMS")
            files2 = sorted(p.relative_to(root / "run2") for p in (root / "run2").rglob("*") if p.is_file() and p.name != "SHA256SUMS")
            self.assertEqual(files1, files2)
            for rel in files1:
                self.assertEqual((root / "run1" / rel).read_bytes(), (root / "run2" / rel).read_bytes())
