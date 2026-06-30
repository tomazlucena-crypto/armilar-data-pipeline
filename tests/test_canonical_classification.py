from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from armilar_global_weights.models import CATEGORIES as SOURCE_CATEGORIES
from armilar_prices.classification import (
    ARMILAR_CATEGORY_CODES,
    ClassificationError,
    load_armilar_classification,
    load_category_mappings,
    load_classification_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "config" / "armilar_consumption_classification_v1.json"
MAPPING_V1 = (
    ROOT
    / "config"
    / "classification_mappings"
    / "ecoicop_v1_to_armilar_v1.csv"
)
MAPPING_V2 = (
    ROOT
    / "config"
    / "classification_mappings"
    / "ecoicop_v2_to_armilar_v1_provisional.csv"
)


class CanonicalClassificationTests(unittest.TestCase):
    def test_classification_has_nine_stable_categories_and_explicit_exclusions(self):
        classification = load_armilar_classification(CLASSIFICATION)
        self.assertEqual(classification.category_codes, ARMILAR_CATEGORY_CODES)
        self.assertEqual(len(classification.categories), 9)
        self.assertIn("NARCOTICS", classification.global_exclusions)
        self.assertTrue(classification.raw_source_detail_preserved)
        self.assertFalse(classification.monetary_release_allowed)

    def test_ecoicop_v1_maps_every_source_division_exactly_once(self):
        bundle = load_classification_bundle(CLASSIFICATION, MAPPING_V1)
        bundle.validate_strict_source_grid(SOURCE_CATEGORIES)
        self.assertEqual(
            tuple(sorted(row.source_code for row in bundle.mappings)),
            tuple(SOURCE_CATEGORIES),
        )
        self.assertEqual(len({row.source_code for row in bundle.mappings}), 12)
        self.assertEqual(
            {row.armilar_category for row in bundle.mappings},
            set(ARMILAR_CATEGORY_CODES),
        )

    def test_mapping_merges_are_explicit(self):
        bundle = load_classification_bundle(CLASSIFICATION, MAPPING_V1)
        by_source = bundle.mapping_by_source()
        self.assertEqual(by_source["CP04"].armilar_category, "ARM04")
        self.assertEqual(by_source["CP05"].armilar_category, "ARM04")
        self.assertEqual(by_source["CP07"].armilar_category, "ARM06")
        self.assertEqual(by_source["CP08"].armilar_category, "ARM06")
        self.assertEqual(by_source["CP09"].armilar_category, "ARM07")
        self.assertEqual(by_source["CP10"].armilar_category, "ARM07")
        for code in ("CP04", "CP05", "CP07", "CP08", "CP09", "CP10"):
            self.assertEqual(by_source[code].mapping_type, "EXACT_MERGE")

    def test_provisional_ecoicop_v2_bridge_is_loadable_but_fails_strict_gate(self):
        source_codes = tuple(f"CP{i:02d}" for i in range(1, 14))
        bundle = load_classification_bundle(
            CLASSIFICATION,
            MAPPING_V2,
            expected_source_codes=source_codes,
            require_strict=False,
        )
        self.assertEqual(bundle.source_classification_version, "V2")
        with self.assertRaisesRegex(
            ClassificationError,
            "not admissible for strict pilot",
        ):
            bundle.validate_strict_source_grid(source_codes)

    def test_duplicate_source_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mapping.csv"
            rows = MAPPING_V1.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(rows + [rows[1]]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ClassificationError, "source grid mismatch|exactly once"):
                load_classification_bundle(CLASSIFICATION, path)

    def test_mapping_hash_changes_when_mapping_changes(self):
        original = load_classification_bundle(CLASSIFICATION, MAPPING_V1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mapping.csv"
            text = MAPPING_V1.read_text(encoding="utf-8")
            path.write_text(text.replace("Exact source division", "Audited source division", 1), encoding="utf-8")
            changed = load_classification_bundle(CLASSIFICATION, path)
            self.assertNotEqual(original.mapping_sha256, changed.mapping_sha256)


if __name__ == "__main__":
    unittest.main()
