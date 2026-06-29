from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from armilar_pipeline.acquire import AcquisitionError, AcquisitionRecord
from armilar_pipeline.config import load_config
from armilar_pipeline.source_probe import load_source_candidates, run_source_probe_only, run_source_probes
from armilar_pipeline.util import sha256_file

ROOT = Path(__file__).resolve().parents[1]


class SourceProbeTests(unittest.TestCase):
    def _registry(self, path: Path) -> None:
        fields = [
            "economy_code", "economy_name", "source_id", "source_authority", "source_url",
            "access_method", "reference_period", "national_accounts_or_survey", "institutional_sector",
            "transaction_code", "classification", "category_coverage", "current_prices_available",
            "currency", "unit", "npish_excluded", "government_excluded", "imputed_rent_included",
            "machine_readable", "methodological_candidate_class", "confidence", "integration_cost",
            "blocking_reason", "expected_content_types", "required_markers", "notes",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "economy_code": "AAA", "economy_name": "Alpha", "source_id": "AAA_OFFICIAL",
                "source_authority": "Alpha Statistics", "source_url": "https://example.test/alpha.html",
                "access_method": "HTML", "reference_period": "2021", "national_accounts_or_survey": "SURVEY",
                "institutional_sector": "HOUSEHOLDS", "transaction_code": "", "classification": "CUSTOM",
                "category_coverage": "8_GROUPS", "current_prices_available": "YES", "currency": "LCU",
                "unit": "LCU", "npish_excluded": "UNKNOWN", "government_excluded": "YES",
                "imputed_rent_included": "UNKNOWN", "machine_readable": "YES",
                "methodological_candidate_class": "C_ONLY", "confidence": "HIGH", "integration_cost": "LOW",
                "blocking_reason": "SURVEY_NOT_S14_P31", "expected_content_types": "text/html",
                "required_markers": "official consumption|2021", "notes": "fixture",
            })

    def test_probe_preserves_source_and_classifies_accessible_candidate(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)

            def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("<html>Official consumption results for 2021</html>", encoding="utf-8")
                return AcquisitionRecord(
                    source_id=source_id, url=url, final_url=url, path=destination, status="fresh",
                    status_code=200, content_type="text/html; charset=utf-8", bytes=destination.stat().st_size,
                    sha256=sha256_file(destination), retrieved_at="2026-06-28T00:00:00Z", attempt_errors=(),
                )

            with patch("armilar_pipeline.source_probe.fetch_url", side_effect=fake_fetch):
                result = run_source_probes(
                    config, candidates_path=registry, run_root=root / "run", cache_root=root / "cache"
                )

            self.assertEqual(result.summary["economies_probed"], 1)
            self.assertEqual(result.summary["c_only_economies"], 1)
            self.assertEqual(result.economy_rows[0]["best_runtime_candidate_class"], "C_ONLY")
            self.assertEqual(result.economy_rows[0]["best_methodological_candidate_class"], "C_ONLY")
            self.assertEqual(result.candidate_rows[0]["signature_status"], "PASS")
            self.assertEqual(result.candidate_rows[0]["marker_status"], "PASS")

    def test_economy_filter_rejects_unknown_code_before_network_access(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)
            with self.assertRaisesRegex(ValueError, "Unknown source-probe economy codes"):
                run_source_probes(
                    config, candidates_path=registry, run_root=root / "run",
                    cache_root=root / "cache", economy_codes=["ZZZ"],
                )

    def test_duplicate_source_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.csv"
            self._registry(path)
            rows = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(rows + [rows[-1]]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate source probe source_id"):
                load_source_candidates(path)

    def test_corrupted_xlsx_download_is_rejected(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)
            with registry.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["source_url"] = "https://example.test/bad.xlsx"
            rows[0]["expected_content_types"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"PK corrupted")
                return AcquisitionRecord(
                    source_id, url, url, destination, "fresh", 200,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    destination.stat().st_size, sha256_file(destination),
                    "2026-06-28T00:00:00Z", (),
                )

            with patch("armilar_pipeline.source_probe.fetch_url", side_effect=fake_fetch):
                result = run_source_probes(
                    config, candidates_path=registry, run_root=root / "run", cache_root=root / "cache"
                )
            self.assertEqual(result.candidate_rows[0]["retrieval_status"], "CONTENT_VALIDATION_FAILED")
            self.assertEqual(result.candidate_rows[0]["signature_status"], "FAIL")

    def test_standalone_probe_program_writes_auditable_outputs(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Use a patched config registry path by calling the lower-level probe through a temporary copy.
            registry = root / "candidates.csv"
            self._registry(registry)
            with patch.object(type(config), "source_probe_candidates_path", new_callable=lambda: property(lambda _: registry)):
                def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text("<html>Official consumption results for 2021</html>", encoding="utf-8")
                    return AcquisitionRecord(source_id, url, url, destination, "fresh", 200, "text/html", destination.stat().st_size, sha256_file(destination), "2026-06-28T00:00:00Z", ())
                with patch("armilar_pipeline.source_probe.fetch_url", side_effect=fake_fetch):
                    summary = run_source_probe_only(config, run_root=root / "run", cache_root=root / "cache")
            self.assertEqual(summary["economies_probed"], 1)
            self.assertTrue((root / "run" / "outputs" / "source_probe_summary.json").exists())
            self.assertTrue((root / "run" / "SHA256SUMS").exists())


    def test_landing_page_is_rejected_as_dataset_even_when_accessible(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)
            with registry.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            fields = list(rows[0]) + ["source_family", "family_order", "resource_type", "evidence_role", "methodological_state"]
            rows[0].update({
                "source_family": "official_statistical_database",
                "family_order": "3",
                "resource_type": "LANDING_PAGE",
                "evidence_role": "DISCOVERY",
                "methodological_state": "EXACT_OFFICIAL",
                "methodological_candidate_class": "A_CANDIDATE",
            })
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("<html>Official consumption results for 2021</html>", encoding="utf-8")
                return AcquisitionRecord(source_id, url, url, destination, "fresh", 200, "text/html", destination.stat().st_size, sha256_file(destination), "2026-06-28T00:00:00Z", ())

            with patch("armilar_pipeline.source_probe.fetch_url", side_effect=fake_fetch):
                result = run_source_probes(config, candidates_path=registry, run_root=root / "run", cache_root=root / "cache")
            row = result.candidate_rows[0]
            self.assertEqual(row["retrieval_status"], "ACQUIRED_DISCOVERY_EVIDENCE")
            self.assertTrue(row["homepage_rejected_as_dataset"])
            self.assertEqual(row["runtime_candidate_class"], "D_UNAVAILABLE")
            self.assertEqual(result.economy_rows[0]["audit_state"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")

    def test_network_failure_preserves_receipt_and_is_access_blocked(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)
            error = AcquisitionError(
                source_id="source_probe_AAA_OFFICIAL",
                url="https://example.test/alpha.html",
                attempt_errors=("URLError:DNS failure", "URLError:DNS failure"),
                retrieved_at="2026-06-29T10:00:00Z",
            )
            with patch("armilar_pipeline.source_probe.fetch_url", side_effect=error):
                result = run_source_probes(config, candidates_path=registry, run_root=root / "run", cache_root=root / "cache")
            row = result.candidate_rows[0]
            self.assertEqual(row["runtime_methodological_state"], "ACCESS_BLOCKED")
            self.assertEqual(result.economy_rows[0]["audit_state"], "ACCESS_BLOCKED")
            receipt = root / "run" / row["failure_receipt"]
            self.assertTrue(receipt.exists())
            self.assertIn("DNS failure", receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["source_hash"], "")

    def test_uninvestigated_families_prevent_exhaustive_unavailability(self) -> None:
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "candidates.csv"
            self._registry(registry)
            with registry.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            fields = list(rows[0]) + ["source_family", "family_order", "resource_type", "evidence_role", "methodological_state"]
            rows[0].update({
                "source_family": "official_structured_publications",
                "family_order": "5",
                "resource_type": "LANDING_PAGE",
                "evidence_role": "DISCOVERY",
                "methodological_state": "UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT",
                "methodological_candidate_class": "D_UNAVAILABLE",
            })
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            def fake_fetch(config, *, source_id, url, destination, cache_path=None, accept="*/*"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("<html>Official consumption results for 2021</html>", encoding="utf-8")
                return AcquisitionRecord(source_id, url, url, destination, "fresh", 200, "text/html", destination.stat().st_size, sha256_file(destination), "2026-06-28T00:00:00Z", ())

            with patch("armilar_pipeline.source_probe.fetch_url", side_effect=fake_fetch):
                result = run_source_probes(config, candidates_path=registry, run_root=root / "run", cache_root=root / "cache")
            economy = result.economy_rows[0]
            self.assertFalse(economy["core_family_probe_complete"])
            self.assertFalse(economy["definitive_unavailability_allowed"])
            self.assertEqual(economy["audit_state"], "NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE")
            uninvestigated = [row for row in result.family_rows if row["core_family"] and row["audit_status"] == "NOT_INVESTIGATED"]
            self.assertGreaterEqual(len(uninvestigated), 1)


if __name__ == "__main__":
    unittest.main()
