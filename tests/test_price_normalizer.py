from __future__ import annotations

import unittest

from armilar_global_weights.models import CATEGORIES
from armilar_prices.models import PriceEvidenceClass, PriceObservation, PriceSeriesDefinition
from armilar_prices.normalizer import PriceNormalizationError, normalize_observations
from armilar_prices.selector import select_best_prices


def series(
    series_id: str,
    evidence: PriceEvidenceClass,
    targets: tuple[str, ...],
    priority: int = 1,
) -> PriceSeriesDefinition:
    return PriceSeriesDefinition(
        series_id=series_id,
        provider="Provider",
        dataset="Dataset",
        economy_code="AAA",
        source_category_code="SRC",
        target_categories=targets,
        evidence_class=evidence,
        source_priority=priority,
        access_method="FIXTURE",
        source_url="https://example.invalid",
    )


class PriceNormalizerTests(unittest.TestCase):
    def test_rebases_and_expands_headline(self) -> None:
        definition = series("HEADLINE", PriceEvidenceClass.P3_OFFICIAL_HEADLINE, CATEGORIES)
        raw = [
            PriceObservation("HEADLINE", "2021-01", 80.0),
            PriceObservation("HEADLINE", "2021-02", 88.0),
        ]
        rows, summary = normalize_observations([definition], raw, "2021-01")
        self.assertEqual(len(rows), 24)
        february = [row for row in rows if row.period == "2021-02"]
        self.assertTrue(all(abs(row.price_relative - 110.0) < 1e-12 for row in february))
        self.assertEqual(summary["normalised_series_count"], 1)

    def test_series_without_reference_period_is_reported_and_skipped(self) -> None:
        definition = series("DIRECT", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, ("CP01",))
        rows, summary = normalize_observations(
            [definition], [PriceObservation("DIRECT", "2021-02", 100.0)], "2021-01"
        )
        self.assertEqual(rows, [])
        self.assertEqual(summary["series_missing_reference_period"], ["DIRECT"])

    def test_duplicate_series_period_is_rejected(self) -> None:
        definition = series("DIRECT", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, ("CP01",))
        raw = [
            PriceObservation("DIRECT", "2021-01", 100.0),
            PriceObservation("DIRECT", "2021-01", 101.0),
        ]
        with self.assertRaisesRegex(PriceNormalizationError, "duplicate"):
            normalize_observations([definition], raw, "2021-01")

    def test_selection_prefers_direct_over_headline(self) -> None:
        definitions = [
            series("DIRECT", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, ("CP01",), priority=50),
            series("HEADLINE", PriceEvidenceClass.P3_OFFICIAL_HEADLINE, CATEGORIES, priority=1),
        ]
        raw = [
            PriceObservation("DIRECT", "2021-01", 100.0),
            PriceObservation("DIRECT", "2021-02", 120.0),
            PriceObservation("HEADLINE", "2021-01", 100.0),
            PriceObservation("HEADLINE", "2021-02", 110.0),
        ]
        rows, _ = normalize_observations(definitions, raw, "2021-01")
        selected, audit, _ = select_best_prices(rows)
        cp01_feb = next(row for row in selected if row.category_code == "CP01" and row.period == "2021-02")
        self.assertEqual(cp01_feb.series_id, "DIRECT")
        self.assertTrue(any(row["candidate_count"] == 2 for row in audit))
