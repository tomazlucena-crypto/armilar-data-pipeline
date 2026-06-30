from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.models import CATEGORIES
from armilar_prices.models import PriceEvidenceClass, PriceSeriesDefinition
from armilar_prices.registry import RegistryError, candidate_series, load_registry, validate_registry


def definition(
    series_id: str,
    evidence: PriceEvidenceClass,
    *,
    economy: str = "AAA",
    targets: tuple[str, ...] = ("CP01",),
    priority: int = 1,
    fallback: tuple[str, ...] = (),
) -> PriceSeriesDefinition:
    return PriceSeriesDefinition(
        series_id=series_id,
        provider="Official provider",
        dataset="dataset",
        economy_code=economy,
        source_category_code="SOURCE",
        target_categories=targets,
        evidence_class=evidence,
        source_priority=priority,
        access_method="FIXTURE",
        source_url="https://example.invalid/source",
        fallback_series=fallback,
    )


class PriceRegistryTests(unittest.TestCase):
    def test_direct_category_precedes_headline(self) -> None:
        headline = definition(
            "HEADLINE",
            PriceEvidenceClass.P3_OFFICIAL_HEADLINE,
            targets=CATEGORIES,
        )
        direct = definition("DIRECT", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, priority=10)
        validate_registry([headline, direct])
        candidates = candidate_series([headline, direct], "AAA", "CP01")
        self.assertEqual([row.series_id for row in candidates], ["DIRECT", "HEADLINE"])

    def test_fallback_cycle_is_rejected(self) -> None:
        first = definition("FIRST", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, fallback=("SECOND",))
        second = definition("SECOND", PriceEvidenceClass.P2_OFFICIAL_AGGREGATE, fallback=("FIRST",))
        with self.assertRaisesRegex(RegistryError, "cycle"):
            validate_registry([first, second])

    def test_cross_economy_fallback_is_rejected(self) -> None:
        first = definition("FIRST", PriceEvidenceClass.P1_OFFICIAL_CATEGORY, fallback=("SECOND",))
        second = definition("SECOND", PriceEvidenceClass.P2_OFFICIAL_AGGREGATE, economy="BBB")
        with self.assertRaisesRegex(RegistryError, "cross-economy"):
            validate_registry([first, second])

    def test_registry_cannot_authorise_monetary_release(self) -> None:
        payload = {
            "monetary_release_allowed": True,
            "series": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "cannot authorise monetary"):
                load_registry(path)

    def test_headline_must_target_all_categories(self) -> None:
        row = definition("HEADLINE", PriceEvidenceClass.P3_OFFICIAL_HEADLINE, targets=("CP01",))
        with self.assertRaisesRegex(ValueError, "all 12"):
            row.validate()
