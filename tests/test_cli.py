from __future__ import annotations

import io
import json
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from armilar_pipeline.cli import main


class CliTests(unittest.TestCase):
    def test_success_result_with_decimal_and_path_is_valid_json_and_returns_zero(self) -> None:
        result = {
            "status": "RESEARCH_MATRIX_AVAILABLE_GLOBAL_SCOPE_INCOMPLETE",
            "research_release_allowed": True,
            "monetary_release_allowed": False,
            "run_dir": Path("run"),
            "bundle": Path("artifacts/bundle.zip"),
            "summary": {
                "observed_universe_weight_sum": Decimal("1.000000000000000000000000"),
                "maximum_relative_error": Decimal("0.000000000000004536498750464798581586907940"),
            },
        }
        stdout = io.StringIO()
        with patch("armilar_pipeline.cli.run_step2", return_value=result), patch("sys.stdout", stdout):
            exit_code = main(["run-step2"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["summary"]["observed_universe_weight_sum"], "1.000000000000000000000000")
        self.assertEqual(payload["run_dir"], "run")
        self.assertFalse(payload["monetary_release_allowed"])

    def test_strict_release_returns_two_only_when_research_release_is_false(self) -> None:
        result = {
            "status": "BLOCKED_NO_RESEARCH_MATRIX",
            "research_release_allowed": False,
            "monetary_release_allowed": False,
            "run_dir": "run",
            "bundle": "artifacts/bundle.zip",
            "summary": {"observed_universe_weight_sum": Decimal("0")},
        }
        stdout = io.StringIO()
        with patch("armilar_pipeline.cli.run_step2", return_value=result), patch("sys.stdout", stdout):
            exit_code = main(["run-step2", "--strict-release"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "BLOCKED_NO_RESEARCH_MATRIX")


if __name__ == "__main__":
    unittest.main()
