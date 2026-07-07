from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from armilar_backtest.arm_o_materialization_v0101 import (
    AVAILABILITY_SEMANTICS,
    BridgePolicy,
    MaterializationBridgeError,
    build_observation_bridge,
    materialize_arm_o_bridge,
    verify_materialization,
    verify_observation_bridge,
)

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_POLICY = ROOT / "config" / "arm_o_materialization_bridge_v0101.json"
ENGINE_POLICY = ROOT / "config" / "official_engine_v096.json"
TARGET_POLICY = ROOT / "config" / "point_in_time_backtest_protocol_v0100.json"
ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
PERIODS = tuple(f"{year:04d}-{month:02d}" for year in range(2021, 2026) for month in range(1, 13))
RETRIEVED = "2026-06-30T12:00:00Z"


def canonical(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_manifest(root: Path, *, separator: str = " ") -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"):
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}{separator}{path.relative_to(root).as_posix()}\n")
    (root / "MANIFEST.sha256").write_text("".join(rows), encoding="utf-8")


def write_snapshot(root: Path, *, official: bool = True) -> dict[str, object]:
    requests = []
    for category in CATEGORIES:
        data = canonical({"category": category, "provider": "EUROSTAT", "fixture": True})
        digest = hashlib.sha256(data).hexdigest()
        request_id = f"prc_hicp_midx-I15-{category}"
        relative = Path("raw/eurostat/prc_hicp_midx") / f"{request_id}.{digest[:16]}.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        requests.append({
            "request_id": request_id,
            "provider": "EUROSTAT",
            "dataset": "prc_hicp_midx",
            "source_category": category,
            "request_url": f"https://example.invalid/{category}",
            "final_url": f"https://example.invalid/{category}",
            "retrieved_at": RETRIEVED,
            "http_status": 200,
            "content_type": "application/json",
            "etag": None,
            "last_modified": None,
            "raw_file": relative.as_posix(),
            "raw_sha256": digest,
            "raw_bytes": len(data),
        })
    manifest = {
        "snapshot_schema_version": "1.0",
        "parser_id": "armilar-eurostat-vertical",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "policy_version": "0.8.7",
        "policy_sha256": "a" * 64,
        "universe_id": "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7",
        "retrieved_at": RETRIEVED,
        "snapshot_kind": "OFFICIAL_PROVIDER_ACQUISITION" if official else "SYNTHETIC_TEST_FIXTURE",
        "requests": requests,
    }
    (root / "snapshot_manifest.json").write_bytes(canonical(manifest))
    write_manifest(root)
    return manifest


def write_vertical_output(root: Path, snapshot: Path, *, official: bool = True) -> None:
    snapshot_manifest = json.loads((snapshot / "snapshot_manifest.json").read_text())
    by_category = {item["source_category"]: item for item in snapshot_manifest["requests"]}
    fields = [
        "universe_id", "economy_code", "economy_name", "eurostat_geo",
        "source_category", "armilar_category", "period", "price_value",
        "reference_period", "reference_price_value", "price_relative",
        "raw_world_weight", "fixed_universe_weight", "index_level_contribution",
        "price_evidence_class", "provider", "dataset", "unit", "status",
        "request_id", "raw_file", "raw_sha256", "weight_numerator_source_id",
        "weight_numerator_source_file", "weight_numerator_source_hash",
        "weight_ppp_source_heading", "weight_ppp_scope", "weight_derivation",
        "weight_quality_flags",
    ]
    root.mkdir(parents=True, exist_ok=True)
    with (root / "normalized_price_observations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for economy_pos, economy in enumerate(ECONOMIES):
            for category_pos, category in enumerate(CATEGORIES, start=1):
                request = by_category[category]
                for period_pos, period in enumerate(PERIODS):
                    value = Decimal("95") + Decimal(economy_pos) + Decimal(category_pos) / 10 + Decimal(period_pos) / 20
                    writer.writerow({
                        "universe_id": "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7",
                        "economy_code": economy,
                        "economy_name": economy,
                        "eurostat_geo": economy[:2],
                        "source_category": category,
                        "armilar_category": category,
                        "period": period,
                        "price_value": format(value, "f"),
                        "reference_period": "2021_ANNUAL_AVERAGE",
                        "reference_price_value": "100",
                        "price_relative": "1",
                        "raw_world_weight": "0.01",
                        "fixed_universe_weight": "0.016666666666666667",
                        "index_level_contribution": "1",
                        "price_evidence_class": "P1_OFFICIAL_CATEGORY" if official else "TEST_FIXTURE_NOT_EVIDENCE",
                        "provider": "EUROSTAT",
                        "dataset": "prc_hicp_midx",
                        "unit": "I15",
                        "status": "",
                        "request_id": request["request_id"],
                        "raw_file": request["raw_file"],
                        "raw_sha256": request["raw_sha256"],
                        "weight_numerator_source_id": "TEST",
                        "weight_numerator_source_file": "",
                        "weight_numerator_source_hash": "",
                        "weight_ppp_source_heading": "",
                        "weight_ppp_scope": "",
                        "weight_derivation": "",
                        "weight_quality_flags": "",
                    })
    summary = {
        "schema_version": "1.0",
        "pipeline_version": "0.8.7",
        "parser_id": "armilar-eurostat-vertical",
        "status": "RESEARCH_VERTICAL_SERIES_BUILT" if official else "TEST_FIXTURE_VERTICAL_SERIES_BUILT",
        "universe_id": "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "classification_version": "ECOICOP_V1_PRE_2026",
        "policy_sha256": "a" * 64,
        "weights_input_file": "weights.csv",
        "weights_input_sha256": "b" * 64,
        "reference_period": "2021_ANNUAL_AVERAGE",
        "start_period": "2021-01",
        "end_period": "2025-12",
        "month_count": 60,
        "economy_count": 5,
        "source_category_count": 12,
        "armilar_category_count": 12,
        "observation_count": 3600,
        "declared_universe_world_weight": "0.160150831582167492",
        "direct_price_weight_within_declared_universe": "1.000000000000000000",
        "normalization_rule": "FIXED_UNIVERSE_NORMALISE_ONCE",
        "aggregation_mode": "PPP_WEIGHTED_LOCAL_PRICE_RELATIVES",
        "fx_treatment": "SEPARATE_NOT_USED_IN_PRIMARY_INDEX",
        "price_concept": "HICP_HOUSEHOLD_FINAL_MONETARY_CONSUMPTION",
        "weight_concept": "ARMILAR_HFCE_PPP_2021",
        "concept_alignment_status": "PARTIAL_HFMCE_HFCE_SCOPE_MISMATCH",
        "uncertainty_numeric_interval_available": False,
        "snapshot_manifest_sha256": hashlib.sha256((snapshot / "snapshot_manifest.json").read_bytes()).hexdigest(),
        "source_snapshot_retrieved_at": RETRIEVED,
        "snapshot_kind": "OFFICIAL_PROVIDER_ACQUISITION" if official else "SYNTHETIC_TEST_FIXTURE",
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    (root / "run_summary.json").write_bytes(canonical(summary))
    write_manifest(root)


def write_weights(path: Path) -> None:
    fields = ["economy_code", "category_code", "fixed_universe_weight", "weight_evidence_class", "source_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for economy in ECONOMIES:
            for category in CATEGORIES:
                writer.writerow({
                    "economy_code": economy,
                    "category_code": category,
                    "fixed_universe_weight": "0.0166666666666666666666666667",
                    "weight_evidence_class": "EXACT_OFFICIAL",
                    "source_id": "TEST_RESEARCH_CORE",
                })


class MaterializationBridgeV0101Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="armilar-v0101-test-"))
        self.snapshot = self.temp / "snapshot"
        self.vertical = self.temp / "vertical"
        self.bridge = self.temp / "bridge"
        self.materialization = self.temp / "materialization"
        self.weights = self.temp / "weights.csv"
        write_snapshot(self.snapshot)
        write_vertical_output(self.vertical, self.snapshot)
        write_weights(self.weights)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def test_policy_is_closed_and_conservative(self) -> None:
        policy = BridgePolicy.load(BRIDGE_POLICY)
        self.assertEqual(policy.policy_version, "0.10.1")
        self.assertEqual(policy.availability_semantics, AVAILABILITY_SEMANTICS)
        self.assertFalse(any(policy.gates.values()))

    def test_valid_official_vertical_converts_exact_grid(self) -> None:
        summary = build_observation_bridge(
            policy_path=BRIDGE_POLICY,
            snapshot_dir=self.snapshot,
            vertical_output_dir=self.vertical,
            output_dir=self.bridge,
            created_at="2026-07-01T00:00:00Z",
        )
        self.assertEqual(summary["observation_count"], 3600)
        self.assertEqual(summary["availability_semantics"], AVAILABILITY_SEMANTICS)
        verified = verify_observation_bridge(self.bridge, policy_path=BRIDGE_POLICY)
        self.assertEqual(verified["status"], "VERIFIED_V087_TO_V096_OBSERVATION_BRIDGE")
        rows = list(csv.DictReader((self.bridge / "category_observations_v096.csv").open()))
        self.assertEqual(len(rows), 3600)
        self.assertTrue(all(row["published_at"] == RETRIEVED for row in rows))
        self.assertTrue(all(row["retrieved_at"] == RETRIEVED for row in rows))
        self.assertTrue(all("OFFICIAL_CATEGORY" in row["evidence_class"] for row in rows))


    def test_double_space_v087_manifests_are_accepted(self) -> None:
        write_manifest(self.snapshot, separator="  ")
        write_manifest(self.vertical, separator="  ")
        summary = build_observation_bridge(
            policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
            vertical_output_dir=self.vertical, output_dir=self.bridge,
            created_at="2026-07-01T00:00:00Z",
        )
        self.assertEqual(summary["observation_count"], 3600)
        self.assertEqual(
            verify_observation_bridge(self.bridge, policy_path=BRIDGE_POLICY)["status"],
            "VERIFIED_V087_TO_V096_OBSERVATION_BRIDGE",
        )

    def test_invalid_manifest_separators_are_rejected(self) -> None:
        manifest = self.snapshot / "MANIFEST.sha256"
        original = manifest.read_text(encoding="utf-8").splitlines()
        for separator in ("   ", "\t"):
            digest, relative = original[0].split(" ", 1)
            manifest.write_text(
                "\n".join([f"{digest}{separator}{relative}", *original[1:]]) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MaterializationBridgeError, "invalid manifest line 1"):
                build_observation_bridge(
                    policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                    vertical_output_dir=self.vertical, output_dir=self.bridge,
                    created_at="2026-07-01T00:00:00Z",
                )
            if self.bridge.exists():
                shutil.rmtree(self.bridge)
        write_manifest(self.snapshot)

    def test_synthetic_snapshot_is_rejected(self) -> None:
        shutil.rmtree(self.snapshot)
        shutil.rmtree(self.vertical)
        write_snapshot(self.snapshot, official=False)
        write_vertical_output(self.vertical, self.snapshot, official=False)
        with self.assertRaisesRegex(MaterializationBridgeError, "official provider acquisition"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_tampered_raw_bytes_are_rejected(self) -> None:
        manifest = json.loads((self.snapshot / "snapshot_manifest.json").read_text())
        raw = self.snapshot / manifest["requests"][0]["raw_file"]
        raw.write_bytes(raw.read_bytes() + b"tamper")
        with self.assertRaisesRegex(MaterializationBridgeError, "manifest mismatch"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_missing_observation_is_rejected(self) -> None:
        rows = list(csv.DictReader((self.vertical / "normalized_price_observations.csv").open()))
        fields = list(rows[0])
        with (self.vertical / "normalized_price_observations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows[:-1])
        write_manifest(self.vertical)
        with self.assertRaisesRegex(MaterializationBridgeError, "row count mismatch"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_mismatched_raw_provenance_is_rejected(self) -> None:
        rows = list(csv.DictReader((self.vertical / "normalized_price_observations.csv").open()))
        fields = list(rows[0])
        rows[0]["raw_sha256"] = "0" * 64
        with (self.vertical / "normalized_price_observations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        write_manifest(self.vertical)
        with self.assertRaisesRegex(MaterializationBridgeError, "raw provenance mismatch"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def build_bridge(self) -> None:
        build_observation_bridge(
            policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
            vertical_output_dir=self.vertical, output_dir=self.bridge,
            created_at="2026-07-01T00:00:00Z",
        )

    def test_materializes_real_contract_run_and_targets(self) -> None:
        self.build_bridge()
        summary = materialize_arm_o_bridge(
            bridge_policy_path=BRIDGE_POLICY,
            engine_policy_path=ENGINE_POLICY,
            target_policy_path=TARGET_POLICY,
            weights_path=self.weights,
            observation_bridge=self.bridge,
            output_dir=self.materialization,
            run_id="ARM-O-EUROSTAT-V087-FIRST-SEEN",
            vintage_id="EUROSTAT-V087-FIRST-SEEN",
            created_at="2026-07-01T01:00:00Z",
        )
        self.assertEqual(summary["status"], "ARM_O_MATERIALIZATION_AND_TARGET_BRIDGE_VALID")
        self.assertEqual(summary["arm_o_period_count"], 60)
        self.assertEqual(summary["arm_o_observation_count"], 3600)
        self.assertEqual(summary["target_count"], 6420)
        self.assertEqual(summary["ledger_entry_count"], 1)
        self.assertEqual(
            summary["backtest_overlap_status"],
            "NO_FUTURE_TARGETS_AFTER_2025_UNTIL_OFFICIAL_ENGINE_PERIOD_IS_EXTENDED",
        )
        checked = verify_materialization(
            self.materialization,
            bridge_policy_path=BRIDGE_POLICY,
            target_policy_path=TARGET_POLICY,
        )
        self.assertEqual(checked["target_count"], 6420)

    def test_target_availability_is_first_verified_retrieval(self) -> None:
        self.build_bridge()
        materialize_arm_o_bridge(
            bridge_policy_path=BRIDGE_POLICY, engine_policy_path=ENGINE_POLICY,
            target_policy_path=TARGET_POLICY, weights_path=self.weights,
            observation_bridge=self.bridge, output_dir=self.materialization,
            run_id="ARM-O-1", vintage_id="V1", created_at="2026-07-01T01:00:00Z",
        )
        rows = list(csv.DictReader((self.materialization / "target_archive" / "cell_targets.csv").open()))
        self.assertTrue(rows)
        self.assertTrue(all(row["target_available_at"] == RETRIEVED for row in rows))

    def test_materialization_detects_nested_tampering(self) -> None:
        self.build_bridge()
        materialize_arm_o_bridge(
            bridge_policy_path=BRIDGE_POLICY, engine_policy_path=ENGINE_POLICY,
            target_policy_path=TARGET_POLICY, weights_path=self.weights,
            observation_bridge=self.bridge, output_dir=self.materialization,
            run_id="ARM-O-2", vintage_id="V2", created_at="2026-07-01T01:00:00Z",
        )
        target = self.materialization / "arm_o_run" / "outputs" / "index_series.csv"
        target.write_text(target.read_text() + "tampered\n")
        with self.assertRaises(Exception):
            verify_materialization(
                self.materialization,
                bridge_policy_path=BRIDGE_POLICY,
                target_policy_path=TARGET_POLICY,
            )

    def test_nonempty_outputs_fail_closed(self) -> None:
        self.bridge.mkdir()
        (self.bridge / "stale.txt").write_text("stale")
        with self.assertRaisesRegex(MaterializationBridgeError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_policy_gate_opening_is_rejected(self) -> None:
        payload = json.loads(BRIDGE_POLICY.read_text())
        payload["gates"]["model_training_allowed"] = True
        changed = self.temp / "policy.json"
        changed.write_bytes(canonical(payload))
        with self.assertRaisesRegex(MaterializationBridgeError, "gates must remain false"):
            BridgePolicy.load(changed)

    def test_snapshot_and_output_timestamp_must_match(self) -> None:
        summary = json.loads((self.vertical / "run_summary.json").read_text())
        summary["source_snapshot_retrieved_at"] = "2026-07-01T12:00:00Z"
        (self.vertical / "run_summary.json").write_bytes(canonical(summary))
        write_manifest(self.vertical)
        with self.assertRaisesRegex(MaterializationBridgeError, "retrieval timestamp mismatch"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_vertical_output_manifest_tampering_is_rejected(self) -> None:
        target = self.vertical / "normalized_price_observations.csv"
        target.write_text(target.read_text() + "tampered\n")
        with self.assertRaisesRegex(MaterializationBridgeError, "manifest mismatch"):
            build_observation_bridge(
                policy_path=BRIDGE_POLICY, snapshot_dir=self.snapshot,
                vertical_output_dir=self.vertical, output_dir=self.bridge,
                created_at="2026-07-01T00:00:00Z",
            )

    def test_bridge_manifest_tampering_is_rejected(self) -> None:
        self.build_bridge()
        target = self.bridge / "category_observations_v096.csv"
        target.write_text(target.read_text() + "tampered\n")
        with self.assertRaises(Exception):
            verify_observation_bridge(self.bridge, policy_path=BRIDGE_POLICY)

    def test_compatibility_view_preserves_payload_bytes(self) -> None:
        self.build_bridge()
        materialize_arm_o_bridge(
            bridge_policy_path=BRIDGE_POLICY, engine_policy_path=ENGINE_POLICY,
            target_policy_path=TARGET_POLICY, weights_path=self.weights,
            observation_bridge=self.bridge, output_dir=self.materialization,
            run_id="ARM-O-3", vintage_id="V3", created_at="2026-07-01T01:00:00Z",
        )
        original = self.materialization / "arm_o_run"
        view = self.materialization / "arm_o_target_input_view"
        original_hashes = {
            path.relative_to(original).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in original.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
        }
        view_hashes = {
            path.relative_to(view).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in view.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
        }
        self.assertEqual(original_hashes, view_hashes)
        self.assertTrue(all("  " in line for line in (view / "MANIFEST.sha256").read_text().splitlines()))
        self.assertTrue(all("  " not in line for line in (original / "MANIFEST.sha256").read_text().splitlines()))

    def test_target_archive_contains_both_metrics(self) -> None:
        self.build_bridge()
        materialize_arm_o_bridge(
            bridge_policy_path=BRIDGE_POLICY, engine_policy_path=ENGINE_POLICY,
            target_policy_path=TARGET_POLICY, weights_path=self.weights,
            observation_bridge=self.bridge, output_dir=self.materialization,
            run_id="ARM-O-4", vintage_id="V4", created_at="2026-07-01T01:00:00Z",
        )
        rows = list(csv.DictReader((self.materialization / "target_archive" / "cell_targets.csv").open()))
        counts = {}
        for row in rows:
            counts[row["target_metric"]] = counts.get(row["target_metric"], 0) + 1
        self.assertEqual(counts["MONTHLY_CHANGE_PCT"], 3540)
        self.assertEqual(counts["YEAR_OVER_YEAR_CHANGE_PCT"], 2880)

    def test_nonempty_materialization_output_fails_closed(self) -> None:
        self.build_bridge()
        self.materialization.mkdir()
        (self.materialization / "stale.txt").write_text("stale")
        with self.assertRaisesRegex(MaterializationBridgeError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            materialize_arm_o_bridge(
                bridge_policy_path=BRIDGE_POLICY, engine_policy_path=ENGINE_POLICY,
                target_policy_path=TARGET_POLICY, weights_path=self.weights,
                observation_bridge=self.bridge, output_dir=self.materialization,
                run_id="ARM-O-5", vintage_id="V5", created_at="2026-07-01T01:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
