from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.models import CATEGORIES as SOURCE_CATEGORIES
from armilar_prices.classification import load_classification_bundle
from armilar_prices.models import NormalizedPriceObservation, PriceEvidenceClass
from armilar_prices.pilot import (
    PricePilotError,
    WorldWeight,
    build_eurostat_category_pilot,
    write_eurostat_pilot_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "config" / "armilar_consumption_classification_v1.json"
MAPPING = (
    ROOT
    / "config"
    / "classification_mappings"
    / "ecoicop_v1_to_armilar_v1.csv"
)


def _bundle():
    return load_classification_bundle(CLASSIFICATION, MAPPING)


def _weights(economies=("DEU", "PRT")):
    share = 0.6 / (len(economies) * len(SOURCE_CATEGORIES))
    return [
        WorldWeight(economy, category, share)
        for economy in economies
        for category in SOURCE_CATEGORIES
    ]


def _prices(
    economies=("DEU", "PRT"),
    periods=("2021-01", "2021-02", "2021-03"),
):
    rows = []
    for economy_index, economy in enumerate(economies):
        for category_index, category in enumerate(SOURCE_CATEGORIES):
            for period_index, period in enumerate(periods):
                value = (
                    100.0
                    if period == "2021-01"
                    else 100.0 + economy_index + category_index / 10 + period_index
                )
                rows.append(
                    NormalizedPriceObservation(
                        series_id=f"EUROSTAT_{economy}_{category}",
                        economy_code=economy,
                        category_code=category,
                        period=period,
                        price_relative=value,
                        evidence_class=PriceEvidenceClass.P1_OFFICIAL_CATEGORY,
                        source_priority=1,
                        provider="EUROSTAT",
                        dataset="prc_hicp_midx",
                        source_category_code=category,
                        reference_period="2021-01",
                    )
                )
    return rows


class EurostatPilotTests(unittest.TestCase):
    def test_fixed_universe_uses_armilar_categories_and_preserves_source_grid(self):
        (
            spec,
            indices,
            contributions,
            source_contributions,
            evidence,
            rejected,
            mapping_audit,
            summary,
        ) = build_eurostat_category_pilot(
            _weights(),
            _prices(),
            "2021-01",
            _bundle(),
            minimum_complete_months=2,
        )
        self.assertEqual(spec.economies, ("DEU", "PRT"))
        self.assertEqual(spec.categories, tuple(f"ARM{i:02d}" for i in range(1, 10)))
        self.assertEqual(spec.source_categories, tuple(SOURCE_CATEGORIES))
        self.assertAlmostEqual(indices[0]["value"], 100.0)
        self.assertAlmostEqual(spec.covered_world_weight_before_normalization, 0.6)
        self.assertAlmostEqual(spec.external_world_weight, 0.4)
        self.assertEqual(len(contributions), 2 * 9 * 3)
        self.assertEqual(len(source_contributions), 2 * 12 * 3)
        self.assertEqual(len(mapping_audit), 12)
        self.assertEqual(summary["category_count"], 9)
        self.assertEqual(summary["source_category_count"], 12)
        self.assertTrue(summary["raw_source_detail_preserved"])
        self.assertFalse(summary["canonical_aggregation_changes_total_index"])
        self.assertFalse(summary["research_release_allowed"])
        self.assertFalse(summary["monetary_release_allowed"])

    def test_canonical_merge_does_not_change_total_index(self):
        result = build_eurostat_category_pilot(
            _weights(), _prices(), "2021-01", _bundle()
        )
        _, indices, contributions, source_contributions, *_ = result
        for index_row in indices:
            period = index_row["period"]
            canonical_total = sum(
                float(row["weighted_index_points"])
                for row in contributions
                if row["period"] == period
            )
            source_total = sum(
                float(row["weighted_index_points"])
                for row in source_contributions
                if row["period"] == period
            )
            self.assertAlmostEqual(float(index_row["value"]), canonical_total)
            self.assertAlmostEqual(float(index_row["value"]), source_total)

    def test_macro_price_relative_uses_fixed_weights_not_simple_average(self):
        weights = []
        for category in SOURCE_CATEGORIES:
            if category == "CP04":
                value = 0.12
            elif category == "CP05":
                value = 0.03
            else:
                value = 0.045
            weights.append(WorldWeight("PRT", category, value))
        prices = []
        for category in SOURCE_CATEGORIES:
            for period in ("2021-01", "2021-02"):
                value = 100.0
                if period == "2021-02" and category == "CP04":
                    value = 110.0
                if period == "2021-02" and category == "CP05":
                    value = 90.0
                prices.append(
                    NormalizedPriceObservation(
                        series_id=f"EUROSTAT_PRT_{category}",
                        economy_code="PRT",
                        category_code=category,
                        period=period,
                        price_relative=value,
                        evidence_class=PriceEvidenceClass.P1_OFFICIAL_CATEGORY,
                        source_priority=1,
                        provider="EUROSTAT",
                        dataset="prc_hicp_midx",
                        source_category_code=category,
                        reference_period="2021-01",
                    )
                )
        _, _, contributions, *_ = build_eurostat_category_pilot(
            weights, prices, "2021-01", _bundle()
        )
        housing = next(
            row
            for row in contributions
            if row["period"] == "2021-02" and row["category_code"] == "ARM04"
        )
        self.assertAlmostEqual(float(housing["price_relative"]), 106.0)
        self.assertNotAlmostEqual(float(housing["price_relative"]), 100.0)
        self.assertEqual(housing["source_category_codes"], "CP04|CP05")

    def test_incomplete_month_is_rejected_without_monthly_renormalisation(self):
        prices = [
            row
            for row in _prices()
            if not (
                row.economy_code == "PRT"
                and row.category_code == "CP12"
                and row.period == "2021-03"
            )
        ]
        spec, indices, contributions, source_contributions, _, rejected, _, _ = (
            build_eurostat_category_pilot(
                _weights(), prices, "2021-01", _bundle(), minimum_complete_months=2
            )
        )
        self.assertEqual(spec.end_period, "2021-02")
        self.assertEqual([row["period"] for row in indices], ["2021-01", "2021-02"])
        row = next(item for item in rejected if item["period"] == "2021-03")
        self.assertEqual(row["reason"], "INCOMPLETE_FIXED_UNIVERSE_MONTH")
        self.assertIn("PRT:CP12", row["missing_cells"])
        self.assertEqual(len(contributions), 2 * 9 * 2)
        self.assertEqual(len(source_contributions), 2 * 12 * 2)

    def test_non_p1_or_non_eurostat_source_is_rejected(self):
        prices = _prices()
        bad = prices[0]
        prices[0] = NormalizedPriceObservation(
            series_id=bad.series_id,
            economy_code=bad.economy_code,
            category_code=bad.category_code,
            period=bad.period,
            price_relative=bad.price_relative,
            evidence_class=PriceEvidenceClass.P3_OFFICIAL_HEADLINE,
            source_priority=bad.source_priority,
            provider="OECD",
            dataset=bad.dataset,
            source_category_code=bad.source_category_code,
            reference_period=bad.reference_period,
        )
        with self.assertRaises(PricePilotError):
            build_eurostat_category_pilot(
                _weights(), prices, "2021-01", _bundle()
            )

    def test_economy_without_minimum_interval_is_excluded_ex_ante(self):
        prices = [
            row
            for row in _prices()
            if not (row.economy_code == "PRT" and row.period != "2021-01")
        ]
        spec, _, _, _, _, rejected, _, _ = build_eurostat_category_pilot(
            _weights(),
            prices,
            "2021-01",
            _bundle(),
            minimum_complete_months=2,
        )
        self.assertEqual(spec.economies, ("DEU",))
        self.assertTrue(
            any(
                row["reason"] == "ECONOMY_FAILED_MINIMUM_COMPLETE_MONTH_GATE"
                and row["missing_cells"] == "PRT"
                for row in rejected
            )
        )

    def test_outputs_and_manifest_are_deterministic(self):
        result = build_eurostat_category_pilot(
            _weights(), _prices(), "2021-01", _bundle(), minimum_complete_months=2
        )
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            write_eurostat_pilot_outputs(*result, Path(left))
            write_eurostat_pilot_outputs(*result, Path(right))
            expected = {
                "price_universe.json",
                "monthly_index.csv",
                "index_contributions.csv",
                "source_category_contributions.csv",
                "classification_mapping_audit.csv",
                "price_evidence_coverage.csv",
                "monthly_index_summary.json",
                "rejected_periods.csv",
                "MANIFEST.sha256",
            }
            self.assertEqual({path.name for path in Path(left).iterdir()}, expected)
            for name in expected:
                self.assertEqual(
                    (Path(left) / name).read_bytes(),
                    (Path(right) / name).read_bytes(),
                )
            manifest = (Path(left) / "MANIFEST.sha256").read_text(encoding="utf-8")
            for line in manifest.splitlines():
                digest, name = line.split(" ", 1)
                self.assertEqual(
                    digest,
                    hashlib.sha256((Path(left) / name).read_bytes()).hexdigest(),
                )

    def test_reference_missing_fails_closed(self):
        prices = [row for row in _prices() if row.period != "2021-01"]
        with self.assertRaises(PricePilotError):
            build_eurostat_category_pilot(
                _weights(), prices, "2021-01", _bundle()
            )

    def test_incomplete_world_weight_grid_excludes_the_economy(self):
        weights = _weights()
        weights.pop()
        spec, _, contributions, source_contributions, *_ = (
            build_eurostat_category_pilot(
                weights, _prices(), "2021-01", _bundle()
            )
        )
        self.assertEqual(spec.economies, ("DEU",))
        self.assertFalse(any(row["economy_code"] == "PRT" for row in contributions))
        self.assertFalse(
            any(row["economy_code"] == "PRT" for row in source_contributions)
        )


if __name__ == "__main__":
    unittest.main()
