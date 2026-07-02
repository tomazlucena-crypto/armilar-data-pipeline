from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from scripts.materialize_research_core_basket import main as materialize_main


ROOT = Path(__file__).resolve().parents[1]


class ResearchCoreContractTests(unittest.TestCase):
    def test_materialized_basket_contract(self) -> None:
        basket = ROOT / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv"
        sha = ROOT / "constitution" / "ARMILAR_RESEARCH_CORE_V1.sha256"
        constitution = json.loads((ROOT / "constitution" / "ARMILAR_RESEARCH_CORE_V1.json").read_text(encoding="utf-8"))
        self.assertTrue(basket.is_file())
        self.assertTrue(sha.is_file())
        self.assertEqual(constitution["constitution_status"], "DRAFT")
        self.assertEqual(constitution["constitution_version"], "0.2.0-draft")
        self.assertEqual(constitution["schema_version"], "1.1")
        self.assertEqual(constitution["basket"], "BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS")
        self.assertEqual(constitution["eligibility"], "RESEARCH_ONLY")
        self.assertEqual(len(constitution["pending_decisions"]), 7)
        self.assertTrue(all(item["status"] == "PENDING_RATIFICATION" for item in constitution["pending_decisions"]))
        self.assertFalse(any(constitution["gates"].values()))
        self.assertEqual(
            constitution["evidence_classes"],
            {"EXACT_OFFICIAL": 30, "OFFICIAL_DETERMINISTIC_DERIVATION": 5, "EXPERIMENTAL_RESEARCH": 25},
        )

        with basket.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 60)
        self.assertEqual({row["economy_code"] for row in rows}, {"DEU", "ESP", "FRA", "ITA", "PRT"})
        self.assertEqual({row["armilar_category"] for row in rows}, {f"CP{i:02d}" for i in range(1, 13)})
        self.assertEqual(sum(Decimal(row["raw_world_weight"]) for row in rows), Decimal("0.160150831582167491646292"))
        self.assertEqual(sum(Decimal(row["fixed_universe_weight"]) for row in rows), Decimal("1.000000000000000000000000000"))
        self.assertEqual(
            hashlib.sha256(basket.read_bytes()).hexdigest(),
            sha.read_text(encoding="utf-8").split()[0],
        )

    def test_materializer_check_mode(self) -> None:
        self.assertEqual(materialize_main(["--root", str(ROOT), "--check"]), 0)

    def test_materializer_writes_files_in_temp_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "repo"
            clone.mkdir()
            (clone / "public" / "latest").mkdir(parents=True)
            (clone / "public" / "latest" / "weights_observed_universe.csv").write_bytes(
                (ROOT / "public" / "latest" / "weights_observed_universe.csv").read_bytes()
            )
            (clone / "schemas").mkdir(parents=True)
            (clone / "schemas" / "research_core_constitution.schema.json").write_text(
                (ROOT / "schemas" / "research_core_constitution.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (clone / "schemas" / "research_core_basket.schema.json").write_text(
                (ROOT / "schemas" / "research_core_basket.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.assertEqual(materialize_main(["--root", str(clone)]), 0)
            self.assertTrue((clone / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv").is_file())


if __name__ == "__main__":
    unittest.main()
