from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from armilar_prices.eurostat_vertical import (
    EurostatVerticalError,
    VerticalPolicy,
    acquire_official_snapshot,
    build_request_url,
    build_vertical_series,
    iter_periods,
    verify_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "eurostat_vertical_v087.json"


def canonical(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def make_jsonstat(category: str, periods: list[str], geos: list[str]) -> bytes:
    values: dict[str, float] = {}
    statuses: dict[str, str] = {}
    index = 0
    for _freq in ["M"]:
        for _unit in ["I15"]:
            for _category in [category]:
                for geo_pos, _geo in enumerate(geos):
                    for period_pos, _period in enumerate(periods):
                        category_no = int(category[2:])
                        values[str(index)] = 100.0 + category_no + geo_pos + period_pos * 0.25
                        if period_pos == len(periods) - 1 and geo_pos == 0:
                            statuses[str(index)] = "p"
                        index += 1
    payload = {
        "version": "2.0",
        "class": "dataset",
        "id": ["freq", "unit", "coicop", "geo", "time"],
        "size": [1, 1, 1, len(geos), len(periods)],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "unit": {"category": {"index": {"I15": 0}}},
            "coicop": {"category": {"index": {category: 0}}},
            "geo": {"category": {"index": {geo: i for i, geo in enumerate(geos)}}},
            "time": {"category": {"index": {period: i for i, period in enumerate(periods)}}},
        },
        "value": values,
        "status": statuses,
    }
    return canonical(payload)


def write_snapshot(root: Path, *, omit: tuple[str, str, str] | None = None) -> None:
    policy = VerticalPolicy.load(POLICY)
    periods = list(iter_periods(policy.start_period, policy.end_period))
    geos = [economy.eurostat_code for economy in policy.economies]
    requests = []
    for category in policy.source_categories:
        data = make_jsonstat(category, periods, geos)
        if omit and omit[1] == category:
            payload = json.loads(data)
            target_geo = omit[0]
            target_period = omit[2]
            geo_pos = geos.index(target_geo)
            period_pos = periods.index(target_period)
            linear = geo_pos * len(periods) + period_pos
            payload["value"].pop(str(linear))
            data = canonical(payload)
        digest = hashlib.sha256(data).hexdigest()
        request_id = f"prc_hicp_midx-I15-{category}"
        relative = Path("raw/eurostat/prc_hicp_midx") / f"{request_id}.{digest[:16]}.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        requests.append(
            {
                "request_id": request_id,
                "provider": "EUROSTAT",
                "dataset": "prc_hicp_midx",
                "source_category": category,
                "request_url": build_request_url(policy, category),
                "final_url": build_request_url(policy, category),
                "retrieved_at": "2026-06-30T12:00:00+00:00",
                "http_status": 200,
                "content_type": "application/json",
                "etag": None,
                "last_modified": None,
                "raw_file": relative.as_posix(),
                "raw_sha256": digest,
                "raw_bytes": len(data),
            }
        )
    manifest = {
        "snapshot_schema_version": "1.0",
        "parser_id": "armilar-eurostat-vertical",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "policy_version": "0.8.7",
        "policy_sha256": policy.policy_sha256,
        "universe_id": policy.universe_id,
        "retrieved_at": "2026-06-30T12:00:00+00:00",
        "snapshot_kind": "SYNTHETIC_TEST_FIXTURE",
        "requests": requests,
    }
    (root / "snapshot_manifest.json").write_bytes(canonical(manifest))


def write_weights(path: Path) -> None:
    policy = VerticalPolicy.load(POLICY)
    fields = [
        "economy_code",
        "economy_name",
        "armilar_category",
        "weight",
        "quality_flags",
        "numerator_source_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for economy in policy.economies:
            for category in policy.source_categories:
                writer.writerow(
                    {
                        "economy_code": economy.armilar_code,
                        "economy_name": economy.name,
                        "armilar_category": category,
                        "weight": "0.01",
                        "quality_flags": "TEST_OBSERVED",
                        "numerator_source_id": "TEST_WEIGHT_SOURCE",
                    }
                )
        writer.writerow(
            {
                "economy_code": "ROW",
                "economy_name": "Rest of world",
                "armilar_category": "CP01",
                "weight": "0.40",
                "quality_flags": "OUTSIDE_DECLARED_UNIVERSE",
                "numerator_source_id": "TEST_WEIGHT_SOURCE",
            }
        )


class FakeHeaders(dict):
    def get(self, key: str, default=None):
        return super().get(key, default)


class FakeResponse:
    def __init__(self, data: bytes):
        self._data = data
        self.status = 200
        self.url = "https://example.invalid/final"
        self.headers = FakeHeaders({"Content-Type": "application/json", "ETag": '"x"'})

    def read(self, amount: int = -1) -> bytes:
        return self._data if amount < 0 else self._data[:amount]

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class EurostatVerticalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.snapshot = self.temp / "snapshot"
        self.output = self.temp / "output"
        self.weights = self.temp / "weights.csv"
        write_snapshot(self.snapshot)
        write_weights(self.weights)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def test_policy_is_fixed_and_release_blocked(self) -> None:
        policy = VerticalPolicy.load(POLICY)
        self.assertEqual(len(policy.economies), 5)
        self.assertEqual(len(policy.source_categories), 12)
        self.assertFalse(policy.research_release_allowed)
        self.assertFalse(policy.monetary_release_allowed)
        self.assertEqual(policy.reference_year, 2021)

    def test_request_url_is_bounded_and_category_specific(self) -> None:
        policy = VerticalPolicy.load(POLICY)
        url = build_request_url(policy, "CP04")
        self.assertIn("coicop=CP04", url)
        self.assertIn("sinceTimePeriod=2021-01", url)
        self.assertIn("untilTimePeriod=2025-12", url)
        for geo in ("DE", "ES", "FR", "IT", "PT"):
            self.assertIn(f"geo={geo}", url)
        with self.assertRaisesRegex(EurostatVerticalError, "UNDECLARED_FALLBACK"):
            build_request_url(policy, "CP00")

    def test_complete_replay_builds_expected_outputs(self) -> None:
        summary = build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        self.assertEqual(summary["status"], "TEST_FIXTURE_VERTICAL_SERIES_BUILT")
        self.assertEqual(summary["month_count"], 60)
        self.assertEqual(summary["observation_count"], 5 * 12 * 60)
        self.assertEqual(summary["declared_universe_world_weight"], "0.600000000000000000")
        for name in (
            "normalized_price_observations.csv",
            "monthly_index.csv",
            "contributions_by_economy.csv",
            "contributions_by_source_category.csv",
            "contributions_by_armilar_category.csv",
            "fixed_universe_weights.csv",
            "uncertainty_summary.json",
            "run_summary.json",
            "ECONOMIC_REPORT.md",
            "MANIFEST.sha256",
        ):
            self.assertTrue((self.output / name).is_file(), name)
        verify_manifest(self.output)

    def test_reference_year_average_is_exactly_100(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        with (self.output / "monthly_index.csv").open(newline="", encoding="utf-8") as handle:
            rows = [row for row in csv.DictReader(handle) if row["period"].startswith("2021-")]
        self.assertEqual(len(rows), 12)
        average = sum((Decimal(row["index_value"]) for row in rows), Decimal("0")) / Decimal("12")
        self.assertLess(abs(average - Decimal("100")), Decimal("1e-12"))

    def test_contributions_sum_to_monthly_index(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        with (self.output / "monthly_index.csv").open(newline="", encoding="utf-8") as handle:
            indices = {row["period"]: Decimal(row["index_value"]) for row in csv.DictReader(handle)}
        with (self.output / "contributions_by_armilar_category.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            totals: dict[str, Decimal] = {}
            for row in csv.DictReader(handle):
                totals[row["period"]] = totals.get(row["period"], Decimal(0)) + Decimal(
                    row["index_level_contribution"]
                )
        for period, index in indices.items():
            self.assertLess(abs(totals[period] - index), Decimal("1e-10"))

    def test_incomplete_grid_fails_without_renormalising(self) -> None:
        shutil.rmtree(self.snapshot)
        write_snapshot(self.snapshot, omit=("PT", "CP12", "2024-06"))
        with self.assertRaisesRegex(EurostatVerticalError, "INCOMPLETE_COMMON_INTERVAL"):
            build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        self.assertFalse((self.output / "monthly_index.csv").exists())

    def test_changed_raw_bytes_fail_hash_verification(self) -> None:
        manifest = json.loads((self.snapshot / "snapshot_manifest.json").read_text())
        raw = self.snapshot / manifest["requests"][0]["raw_file"]
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaisesRegex(EurostatVerticalError, "REPLAY_HASH_MISMATCH"):
            build_vertical_series(POLICY, self.snapshot, self.weights, self.output)

    def test_replay_is_deterministic(self) -> None:
        output_two = self.temp / "output_two"
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        build_vertical_series(POLICY, self.snapshot, self.weights, output_two)
        files_one = {
            p.relative_to(self.output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.output.rglob("*")
            if p.is_file()
        }
        files_two = {
            p.relative_to(output_two).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output_two.rglob("*")
            if p.is_file()
        }
        self.assertEqual(files_one, files_two)

    def test_uncertainty_is_not_fabricated(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        payload = json.loads((self.output / "uncertainty_summary.json").read_text())
        self.assertFalse(payload["numeric_interval_available"])
        self.assertIsNone(payload["lower_bound"])
        self.assertIsNone(payload["upper_bound"])
        self.assertFalse(payload["research_release_allowed"])
        self.assertFalse(payload["monetary_release_allowed"])

    def test_manifest_detects_output_tampering(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        target = self.output / "monthly_index.csv"
        target.write_text(target.read_text() + "tampered\n")
        with self.assertRaisesRegex(EurostatVerticalError, "MANIFEST_HASH_MISMATCH"):
            verify_manifest(self.output)

    def test_acquisition_preserves_exact_bytes_and_receipts(self) -> None:
        policy = VerticalPolicy.load(POLICY)
        periods = list(iter_periods(policy.start_period, policy.end_period))
        geos = [economy.eurostat_code for economy in policy.economies]
        by_category = {category: make_jsonstat(category, periods, geos) for category in policy.source_categories}

        def opener(request, timeout):
            query = request.full_url.split("coicop=", 1)[1].split("&", 1)[0]
            self.assertEqual(timeout, 30)
            return FakeResponse(by_category[query])

        acquired = self.temp / "acquired"
        manifest = acquire_official_snapshot(
            POLICY,
            acquired,
            retrieved_at="2026-06-30T12:00:00+00:00",
            opener=opener,
        )
        self.assertEqual(len(manifest["requests"]), 12)
        self.assertEqual(manifest["snapshot_kind"], "OFFICIAL_PROVIDER_ACQUISITION")
        for request in manifest["requests"]:
            data = (acquired / request["raw_file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), request["raw_sha256"])
        verify_manifest(acquired)

    def test_synthetic_fixture_is_never_presented_as_official_evidence(self) -> None:
        summary = build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        self.assertEqual(summary["snapshot_kind"], "SYNTHETIC_TEST_FIXTURE")
        self.assertEqual(summary["status"], "TEST_FIXTURE_VERTICAL_SERIES_BUILT")
        report = (self.output / "ECONOMIC_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("synthetic test fixture", report)
        self.assertIn("no official price evidence", report)
        with (self.output / "normalized_price_observations.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            first = next(csv.DictReader(handle))
        self.assertEqual(first["price_evidence_class"], "TEST_FIXTURE_NOT_EVIDENCE")

    def test_output_does_not_touch_public_latest(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        self.assertNotIn("public/latest", self.output.as_posix())
        self.assertFalse((ROOT / "public" / "latest" / "monthly_index.csv").exists())

    def test_nonempty_output_directory_fails_closed(self) -> None:
        self.output.mkdir(parents=True)
        (self.output / "stale.txt").write_text("stale")
        with self.assertRaisesRegex(EurostatVerticalError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            build_vertical_series(POLICY, self.snapshot, self.weights, self.output)

    def test_snapshot_raw_path_cannot_escape_snapshot_root(self) -> None:
        manifest_path = self.snapshot / "snapshot_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["requests"][0]["raw_file"] = "../../outside.json"
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(EurostatVerticalError, "RAW_PATH_INVALID"):
            build_vertical_series(POLICY, self.snapshot, self.weights, self.output)

    def test_manifest_path_cannot_escape_output_root(self) -> None:
        build_vertical_series(POLICY, self.snapshot, self.weights, self.output)
        (self.output / "MANIFEST.sha256").write_text(
            "0" * 64 + "  ../../outside.txt\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(EurostatVerticalError, "MANIFEST_PATH_INVALID"):
            verify_manifest(self.output)

    def test_2026_data_are_blocked_without_ecoiocop_v2_mapping(self) -> None:
        payload = json.loads(POLICY.read_text(encoding="utf-8"))
        payload["end_period"] = "2026-01"
        path = self.temp / "future_policy.json"
        path.write_bytes(canonical(payload))
        with self.assertRaisesRegex(EurostatVerticalError, "CLASSIFICATION_BREAK_UNRESOLVED"):
            VerticalPolicy.load(path)

    def test_real_repository_weight_schema_when_available(self) -> None:
        real_weights = ROOT / "public" / "latest" / "weights_observed_universe.csv"
        if not real_weights.is_file():
            self.skipTest("repository weight artefact is not present in the overlay-only package")
        output = self.temp / "real_weight_output"
        summary = build_vertical_series(POLICY, self.snapshot, real_weights, output)
        self.assertEqual(summary["economy_count"], 5)
        self.assertEqual(summary["source_category_count"], 12)
        self.assertEqual(summary["observation_count"], 3600)
        self.assertEqual(
            summary["declared_universe_world_weight"],
            "0.160150831582167492",
        )
        verify_manifest(output)


class EurostatOfficialGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.repo = self.temp / "repo"
        (self.repo / "config").mkdir(parents=True)
        (self.repo / "public" / "latest").mkdir(parents=True)
        shutil.copy2(POLICY, self.repo / "config" / "eurostat_vertical_v087.json")
        self.weights = self.repo / "public" / "latest" / "weights_observed_universe.csv"
        write_weights(self.weights)
        (self.repo / "public" / "latest" / "sentinel.txt").write_text(
            "unchanged\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def _opener(self, request, timeout):
        policy = VerticalPolicy.load(POLICY)
        periods = list(iter_periods(policy.start_period, policy.end_period))
        geos = [economy.eurostat_code for economy in policy.economies]
        category = request.full_url.split("coicop=", 1)[1].split("&", 1)[0]
        return FakeResponse(make_jsonstat(category, periods, geos))

    def test_single_gate_simulation_preserves_public_latest(self) -> None:
        from armilar_prices.v087_gate import hash_tree, run_official_gate

        before = hash_tree(self.repo / "public" / "latest")
        report = self.repo / "artifacts" / "v087" / "OFFICIAL_GATE_REPORT.json"
        payload = run_official_gate(
            policy_path=self.repo / "config" / "eurostat_vertical_v087.json",
            weights_path=self.weights,
            public_latest_dir=self.repo / "public" / "latest",
            snapshot_dir=self.repo / "artifacts" / "v087" / "snapshot",
            output_dir=self.repo / "artifacts" / "v087" / "output",
            report_path=report,
            retrieved_at="2026-06-30T12:00:00+00:00",
            opener=self._opener,
            test_mode=True,
        )
        self.assertEqual(payload["gate_status"], "TEST_GATE_SIMULATION_PASSED")
        self.assertTrue(payload["test_mode"])
        self.assertEqual(payload["reference_year_average"], "100.000000000000")
        self.assertEqual(before, hash_tree(self.repo / "public" / "latest"))
        self.assertTrue(report.is_file())

    def test_single_gate_rejects_nonempty_snapshot(self) -> None:
        from armilar_prices.v087_gate import run_official_gate

        snapshot = self.repo / "artifacts" / "snapshot"
        snapshot.mkdir(parents=True)
        (snapshot / "stale.txt").write_text("stale", encoding="utf-8")
        with self.assertRaisesRegex(EurostatVerticalError, "EMPIRICAL_GATE_PATH_NOT_EMPTY"):
            run_official_gate(
                policy_path=self.repo / "config" / "eurostat_vertical_v087.json",
                weights_path=self.weights,
                public_latest_dir=self.repo / "public" / "latest",
                snapshot_dir=snapshot,
                output_dir=self.repo / "artifacts" / "output",
                report_path=self.repo / "artifacts" / "report.json",
                opener=self._opener,
                test_mode=True,
            )


if __name__ == "__main__":
    unittest.main()
