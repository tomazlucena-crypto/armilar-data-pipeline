from __future__ import annotations

import unittest

from armilar_prices.index_engine import (
    AggregationMode,
    IndexBuildError,
    WeightRecord,
    calculate_monthly_indices,
)
from armilar_prices.models import NormalizedPriceObservation, PriceEvidenceClass


def price(economy: str, category: str, period: str, relative: float, evidence: PriceEvidenceClass) -> NormalizedPriceObservation:
    return NormalizedPriceObservation(
        series_id=f"{economy}_{category}_{evidence.value}",
        economy_code=economy,
        category_code=category,
        period=period,
        price_relative=relative,
        evidence_class=evidence,
        source_priority=1,
        provider="Provider",
        dataset="Dataset",
        source_category_code=category,
        reference_period="2021-01",
    )


class PriceIndexEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weights = [
            WeightRecord("AAA", "CP01", 0.4),
            WeightRecord("BBB", "CP01", 0.6),
        ]
        self.prices = [
            price("AAA", "CP01", "2021-01", 100.0, PriceEvidenceClass.P1_OFFICIAL_CATEGORY),
            price("BBB", "CP01", "2021-01", 100.0, PriceEvidenceClass.P3_OFFICIAL_HEADLINE),
            price("AAA", "CP01", "2021-02", 110.0, PriceEvidenceClass.P1_OFFICIAL_CATEGORY),
            price("BBB", "CP01", "2021-02", 120.0, PriceEvidenceClass.P3_OFFICIAL_HEADLINE),
        ]

    def test_complete_index_is_deterministic_and_reference_is_100(self) -> None:
        rows, contributions, coverage, summary = calculate_monthly_indices(
            self.weights, self.weights, self.prices, "2021-01"
        )
        global_rows = [row for row in rows if row["index_id"] == "ARM-M-GLOBAL-RESEARCH"]
        self.assertEqual(global_rows[0]["value"], 100.0)
        self.assertAlmostEqual(global_rows[1]["value"], 116.0)
        self.assertEqual(global_rows[1]["direct_or_official_aggregate_price_weight"], 0.4)
        self.assertEqual(global_rows[1]["headline_or_proxy_price_weight"], 0.6)
        self.assertEqual(summary["incomplete_index_row_count"], 0)
        self.assertTrue(contributions)
        self.assertTrue(coverage)

    def test_missing_price_does_not_trigger_silent_renormalisation(self) -> None:
        rows, contributions, _, summary = calculate_monthly_indices(
            self.weights, self.weights, self.prices[:-1], "2021-01"
        )
        february = [row for row in rows if row["period"] == "2021-02"]
        self.assertTrue(all(row["status"] == "INCOMPLETE" for row in february))
        self.assertTrue(all(row["value"] is None for row in february))
        self.assertFalse(any(row["period"] == "2021-02" for row in contributions))
        self.assertFalse(summary["silent_renormalisation_allowed"])

    def test_fx_adjusted_mode_is_blocked_pending_ratification(self) -> None:
        with self.assertRaisesRegex(IndexBuildError, "not constitutionally ratified"):
            calculate_monthly_indices(
                self.weights,
                self.weights,
                self.prices,
                "2021-01",
                aggregation_mode=AggregationMode.COMMON_CURRENCY_FX_ADJUSTED,
            )
