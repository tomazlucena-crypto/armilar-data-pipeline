from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.models import CATEGORIES
from armilar_prices.acquisition import PriceAcquisitionError, acquire_prices
from armilar_prices.selector import load_normalized_prices, select_best_prices

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "price_replay"


def write_registry(path: Path, *, eurostat_category: str = "CP01") -> None:
    path.write_text(
        json.dumps(
            {
                "registry_version": "test-v0.8.1",
                "monetary_release_allowed": False,
                "series": [
                    {
                        "series_id": "EUROSTAT_PRT_CP01_HICP",
                        "provider": "Eurostat",
                        "provider_code": "ESTAT",
                        "dataset": "prc_hicp_midx",
                        "economy_code": "PRT",
                        "source_category_code": eurostat_category,
                        "target_categories": "CP01",
                        "evidence_class": "P1_OFFICIAL_CATEGORY",
                        "source_priority": 1,
                        "access_method": "SDMX",
                        "source_url": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/data/prc_hicp_midx",
                        "query_key": "M.INDEX.CP01.PRT",
                        "frequency": "M",
                        "unit": "INDEX",
                        "seasonal_adjustment": "NSA",
                        "fallback_series": "OECD_PRT_CPI_HEADLINE",
                        "enabled": True,
                    },
                    {
                        "series_id": "OECD_PRT_CPI_HEADLINE",
                        "provider": "OECD",
                        "provider_code": "OECD",
                        "dataset": "DSD_PRICES@DF_PRICES_ALL",
                        "economy_code": "PRT",
                        "source_category_code": "_T",
                        "target_categories": "|".join(CATEGORIES),
                        "evidence_class": "P3_OFFICIAL_HEADLINE",
                        "source_priority": 1,
                        "access_method": "SDMX",
                        "source_url": "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/PRT.M.N.CPI.IX._T.N.GY",
                        "query_key": "PRT.M.N.CPI.IX._T.N.GY",
                        "frequency": "M",
                        "unit": "INDEX",
                        "seasonal_adjustment": "NSA",
                        "fallback_series": "",
                        "enabled": True,
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


class PriceAcquisitionTests(unittest.TestCase):
    def test_replay_writes_receipts_hashes_and_normalized_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            output = root / "out"
            write_registry(registry)
            summary = acquire_prices(registry, output, mode="replay", fixture_dir=FIXTURES)

            self.assertEqual(summary["receipt_count"], 2)
            receipts = [
                json.loads(line)
                for line in (output / "price_source_receipts.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            eurostat = next(row for row in receipts if row["series_id"] == "EUROSTAT_PRT_CP01_HICP")
            raw = (FIXTURES / "raw" / "EUROSTAT_PRT_CP01_HICP.json").read_bytes()
            self.assertEqual(eurostat["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(
                eurostat["parser_version"],
                "armilar-prices-acquisition-v0.8.1-provenance-bound",
            )
            self.assertTrue((output / "MANIFEST.sha256").exists())

            with (output / "normalized_price_observations.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn(
                ("EUROSTAT_PRT_CP01_HICP", "CP01", "2021-02", "101.2"),
                {
                    (
                        row["series_id"],
                        row["category_code"],
                        row["period"],
                        row["price_relative"],
                    )
                    for row in rows
                },
            )

    def test_replay_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            write_registry(registry)
            first = root / "first"
            second = root / "second"
            acquire_prices(registry, first, mode="replay", fixture_dir=FIXTURES)
            acquire_prices(registry, second, mode="replay", fixture_dir=FIXTURES)
            for name in (
                "price_source_receipts.jsonl",
                "price_source_health.csv",
                "provider_structure_manifest.json",
                "resolved_price_series_registry.json",
                "normalized_price_observations.csv",
                "MANIFEST.sha256",
            ):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_dsd_snapshot_rejects_unknown_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            write_registry(registry, eurostat_category="CP99")
            with self.assertRaisesRegex(PriceAcquisitionError, "not present in DSD"):
                acquire_prices(registry, root / "out", mode="replay", fixture_dir=FIXTURES)

    def test_eurostat_category_beats_oecd_headline_for_cp01(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry.json"
            output = root / "out"
            write_registry(registry)
            acquire_prices(registry, output, mode="replay", fixture_dir=FIXTURES)
            selected, audit, _ = select_best_prices(
                load_normalized_prices(output / "normalized_price_observations.csv")
            )
            selected_cp01 = [
                row for row in selected if row.economy_code == "PRT" and row.category_code == "CP01"
            ]
            self.assertEqual({row.series_id for row in selected_cp01}, {"EUROSTAT_PRT_CP01_HICP"})
            self.assertTrue(
                any("OECD_PRT_CPI_HEADLINE" in str(row["rejected_series_ids"]) for row in audit)
            )


if __name__ == "__main__":
    unittest.main()
