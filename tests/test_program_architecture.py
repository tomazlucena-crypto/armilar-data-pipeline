from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from armilar_pipeline import __version__
from armilar_proxy_audit.cli import main as proxy_main

ROOT = Path(__file__).resolve().parents[1]


class ProgramArchitectureTests(unittest.TestCase):
    def test_package_and_config_versions_match(self) -> None:
        config = json.loads((ROOT / "config" / "step2_icp2021.json").read_text(encoding="utf-8"))
        self.assertEqual(__version__, "0.8.2")
        self.assertEqual(config["pipeline_version"], __version__)

    def test_program_entry_points_are_declared(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for command in (
            "armilar-source-probe",
            "armilar-proxy-audit",
            "armilar-country",
            "armilar-matrix",
            "armilar-global-weights",
            "armilar-imputation",
            "armilar-global-release",
            "armilar-prices",
        ):
            self.assertIn(command, text)

    def test_empty_proxy_registry_runs_fail_closed_and_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            args = [
                "--comparison-file",
                str(ROOT / "config" / "proxy_ppp_benchmarks.csv"),
                "--policy",
                str(ROOT / "config" / "methodology_policy.json"),
            ]
            self.assertEqual(proxy_main(args + ["--output-dir", str(first)]), 0)
            self.assertEqual(proxy_main(args + ["--output-dir", str(second)]), 0)
            for name in (
                "proxy_ppp_comparison.csv",
                "proxy_error_by_category.csv",
                "proxy_error_by_economy.csv",
                "proxy_validation_summary.json",
            ):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            summary = json.loads((first / "proxy_validation_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["validation_status"], "INSUFFICIENT_DIRECT_EVIDENCE")
            self.assertEqual(summary["direct_hfce_vs_aic_ppp_comparisons"], 0)

    def test_benchmark_registry_starts_empty_but_has_complete_schema(self) -> None:
        path = ROOT / "config" / "proxy_ppp_benchmarks.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(list(reader), [])
            self.assertEqual(
                reader.fieldnames,
                [
                    "economy_code",
                    "economy_name",
                    "armilar_category",
                    "reference_year",
                    "aic_ppp",
                    "strict_hfce_ppp",
                    "source_authority",
                    "source_url",
                    "source_file",
                    "classification",
                    "notes",
                ],
            )

    def test_workflow_publishes_new_audit_outputs_only_on_main(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
        for name in (
            "source_probe_family_coverage.csv",
            "proxy_error_by_category.csv",
            "proxy_error_by_economy.csv",
        ):
            self.assertIn(name, workflow)
        self.assertGreaterEqual(workflow.count("github.event_name != 'pull_request'"), 3)
        self.assertGreaterEqual(workflow.count("github.ref == 'refs/heads/main'"), 3)


if __name__ == "__main__":
    unittest.main()
