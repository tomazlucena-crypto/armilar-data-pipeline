from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from armilar_prices.acquisition import PriceAcquisitionError, acquire_prices

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_REGISTRY = ROOT / "config" / "price_sources_pilot.json"
FIXTURES = ROOT / "tests" / "fixtures" / "price_replay"


def _copy_fixtures(target: Path) -> Path:
    destination = target / "price_replay"
    shutil.copytree(FIXTURES, destination)
    return destination


def _write_enabled_registry(path: Path) -> None:
    payload = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
    payload["registry_version"] = "test-v0.8.1-provenance"
    for row in payload["series"]:
        row["enabled"] = True
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalized_value(output: Path, series_id: str, period: str) -> float:
    with (output / "normalized_price_observations.csv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        for row in csv.DictReader(handle):
            if row["series_id"] == series_id and row["period"] == period:
                return float(row["price_relative"])
    raise AssertionError(f"missing normalized observation: {series_id}/{period}")


class PriceReplayProvenanceTests(unittest.TestCase):
    def test_hashed_raw_payload_is_the_observation_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            _write_enabled_registry(registry)
            fixtures = _copy_fixtures(root)
            raw_path = fixtures / "raw" / "EUROSTAT_PRT_CP01_HICP.json"
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            payload["observations"][1]["value"] = 102.5
            raw_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            output = root / "out"
            acquire_prices(
                registry,
                output,
                mode="replay",
                fixture_dir=fixtures,
            )

            self.assertAlmostEqual(
                _normalized_value(
                    output,
                    "EUROSTAT_PRT_CP01_HICP",
                    "2021-02",
                ),
                102.5,
            )

    def test_raw_provider_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            _write_enabled_registry(registry)
            fixtures = _copy_fixtures(root)
            raw_path = fixtures / "raw" / "EUROSTAT_PRT_CP01_HICP.json"
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            payload["provider"] = "NOT_EUROSTAT"
            raw_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                PriceAcquisitionError,
                "provider mismatch",
            ):
                acquire_prices(
                    registry,
                    root / "out",
                    mode="replay",
                    fixture_dir=fixtures,
                )

    def test_duplicate_raw_period_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            _write_enabled_registry(registry)
            fixtures = _copy_fixtures(root)
            raw_path = fixtures / "raw" / "OECD_PRT_CPI_HEADLINE.json"
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            payload["observations"].append(
                dict(payload["observations"][0])
            )
            raw_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                PriceAcquisitionError,
                "duplicate raw fixture period",
            ):
                acquire_prices(
                    registry,
                    root / "out",
                    mode="replay",
                    fixture_dir=fixtures,
                )

    def test_live_mode_fails_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            _write_enabled_registry(registry)
            with patch(
                "armilar_prices.acquisition.urllib.request.urlopen"
            ) as urlopen:
                with self.assertRaisesRegex(
                    PriceAcquisitionError,
                    "live acquisition is disabled",
                ):
                    acquire_prices(
                        registry,
                        root / "out",
                        mode="live",
                    )
                urlopen.assert_not_called()

    def test_resolved_registry_version_comes_from_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            _write_enabled_registry(registry)
            output = root / "out"
            acquire_prices(
                registry,
                output,
                mode="replay",
                fixture_dir=FIXTURES,
            )
            resolved = json.loads(
                (output / "resolved_price_series_registry.json").read_text(
                    encoding="utf-8"
                )
            )
            configured = json.loads(
                registry.read_text(encoding="utf-8")
            )
            self.assertEqual(
                resolved["registry_version"],
                configured["registry_version"],
            )


if __name__ == "__main__":
    unittest.main()

