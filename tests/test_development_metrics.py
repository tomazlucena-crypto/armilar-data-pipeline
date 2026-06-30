from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_development_metrics import generate_metrics, main


ROOT = Path(__file__).resolve().parents[1]


class DevelopmentMetricsTests(unittest.TestCase):
    def test_metrics_are_deterministic_for_same_checkout(self) -> None:
        first = generate_metrics(ROOT)
        second = generate_metrics(ROOT)
        self.assertEqual(first, second)
        self.assertIsNone(first["suite_duration_seconds"]["value"])
        self.assertEqual(
            first["suite_duration_seconds"]["unavailable_reason"],
            "suite duration not measured by telemetry generator",
        )

    def test_metrics_output_is_written_outside_public_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "development_metrics.json"
            self.assertEqual(main(["--repo-root", str(ROOT), "--output", str(output)]), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("production_lines", payload)
            self.assertNotIn("public/latest", str(output).replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
