from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from armilar_prices.sdmx_spike import (
    SELECTED_CLIENT,
    declared_targets,
    preserve_raw_response,
    write_spike_outputs,
)


class SDMXSpikeTests(unittest.TestCase):
    def test_declared_targets_build_data_and_metadata_specs(self) -> None:
        targets = declared_targets()
        self.assertEqual({target.provider for target in targets}, {"ESTAT", "OECD"})
        for target in targets:
            target.data_spec.validate()
            target.metadata_spec.validate()
            self.assertIn("startPeriod", target.data_spec.params | {"startPeriod": target.start_period})

    def test_raw_bytes_are_preserved_with_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = preserve_raw_response(
                Path(tmp),
                provider="ESTAT",
                resource_id="dataset",
                key="A.B.C",
                content=b"official bytes",
                content_type="text/csv",
                final_url="https://example.invalid/data",
                mode="replay",
            )
            self.assertEqual(receipt["byte_count"], 14)
            self.assertEqual(len(receipt["sha256"]), 64)
            self.assertTrue((Path(tmp) / str(receipt["raw_path"])).exists())

    def test_network_blocked_report_selects_sdmx1_without_pysdmx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = write_spike_outputs(Path(tmp), status="NETWORK_BLOCKED")
            self.assertEqual(summary["selected_client"], SELECTED_CLIENT)
            self.assertEqual(summary["pysdmx_decision"], "NOT_EVALUATED_NO_DOCUMENTED_SDMX1_GAP")
            self.assertFalse(summary["live_network_allowed_in_pull_request"])
            self.assertTrue((Path(tmp) / "MANIFEST.sha256").exists())
            decision = json.loads((Path(tmp) / "sdmx_client_decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["status"], "NETWORK_BLOCKED")


if __name__ == "__main__":
    unittest.main()
