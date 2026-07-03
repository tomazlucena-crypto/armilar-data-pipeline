from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from armilar_prices.official_engine_v096 import (
    BuildRequest,
    EnginePolicy,
    OfficialEngineError,
    SeriesKind,
    append_ledger,
    build_run,
    export_parquet,
    reconcile_runs,
    replay_run,
    run_ooh_sensitivity,
    load_weights,
    verify_ledger,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_POLICY = ROOT / "config" / "official_engine_v096.json"
BASE_OOH = ROOT / "config" / "ooh_scenarios_v096.json"
CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
PERIODS = tuple([f"2021-{m:02d}" for m in range(1, 13)] + [f"2022-{m:02d}" for m in range(1, 13)])


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def next_month_publication(period: str) -> str:
    year, month = map(int, period.split("-"))
    month += 1
    if month == 13:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}-15T10:00:00Z"


def write_policy(path: Path, **changes: object) -> None:
    payload = json.loads(BASE_POLICY.read_text(encoding="utf-8"))
    payload["end_period"] = "2022-12"
    payload.update(changes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_weights(path: Path, *, missing: tuple[str, str] | None = None) -> None:
    fields = [
        "economy_code",
        "category_code",
        "fixed_universe_weight",
        "weight_evidence_class",
        "source_id",
    ]
    rows = []
    for economy in ("AAA", "BBB"):
        for category in CATEGORIES:
            if missing == (economy, category):
                continue
            weight = "0.04"
            if economy == "BBB" and category == "CP12":
                weight = "0.08"
            rows.append(
                {
                    "economy_code": economy,
                    "category_code": category,
                    "fixed_universe_weight": weight,
                    "weight_evidence_class": "EXACT_OFFICIAL",
                    "source_id": "TEST_WEIGHT_SOURCE",
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_observations(
    path: Path,
    *,
    headline: bool = False,
    omit: tuple[str, str, str] | None = None,
    add_revision: bool = True,
) -> None:
    fields = [
        "series_id",
        "economy_code",
        "category_code",
        "period",
        "value",
        "published_at",
        "retrieved_at",
        "vintage_id",
        "revision_sequence",
        "raw_snapshot_id",
        "source_sha256",
        "evidence_class",
    ]
    rows = []
    categories = ("CP00",) if headline else CATEGORIES
    for economy_pos, economy in enumerate(("AAA", "BBB")):
        for category_pos, category in enumerate(categories, start=1):
            for period in PERIODS:
                if omit == (economy, category, period):
                    continue
                if period.startswith("2021-"):
                    value = Decimal("100")
                else:
                    month = Decimal(period[-2:]) / Decimal("10")
                    value = Decimal("105") + Decimal(economy_pos) + Decimal(category_pos) / Decimal("10") + month
                rows.append(
                    {
                        "series_id": f"{economy}_{category}",
                        "economy_code": economy,
                        "category_code": category,
                        "period": period,
                        "value": format(value, "f"),
                        "published_at": next_month_publication(period),
                        "retrieved_at": next_month_publication(period),
                        "vintage_id": "INITIAL",
                        "revision_sequence": "0",
                        "raw_snapshot_id": f"snapshot-{economy}-{category}-{period}-initial",
                        "source_sha256": digest(f"{economy}|{category}|{period}|initial"),
                        "evidence_class": "OFFICIAL_CATEGORY" if not headline else "OFFICIAL_HEADLINE",
                    }
                )
            if add_revision:
                period = "2022-12"
                original = Decimal("105") + Decimal(economy_pos) + Decimal(category_pos) / Decimal("10") + Decimal("1.2")
                revised = original + Decimal("2.5")
                rows.append(
                    {
                        "series_id": f"{economy}_{category}",
                        "economy_code": economy,
                        "category_code": category,
                        "period": period,
                        "value": format(revised, "f"),
                        "published_at": "2023-02-15T10:00:00Z",
                        "retrieved_at": "2023-02-15T10:05:00Z",
                        "vintage_id": "REVISION_1",
                        "revision_sequence": "1",
                        "raw_snapshot_id": f"snapshot-{economy}-{category}-{period}-revision1",
                        "source_sha256": digest(f"{economy}|{category}|{period}|revision1"),
                        "evidence_class": "OFFICIAL_CATEGORY" if not headline else "OFFICIAL_HEADLINE",
                    }
                )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class OfficialEngineV096Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="armilar-v096-test-"))
        self.policy = self.temp / "policy.json"
        self.weights = self.temp / "weights.csv"
        self.categories = self.temp / "category_observations.csv"
        self.headline = self.temp / "headline_observations.csv"
        self.ledger = self.temp / "ledger.jsonl"
        write_policy(self.policy)
        write_weights(self.weights)
        write_observations(self.categories)
        write_observations(self.headline, headline=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def request(
        self,
        run_id: str,
        kind: SeriesKind,
        *,
        cutoff: str = "2023-01-31T23:59:59Z",
        vintage: str = "VINTAGE_2023_01",
    ) -> BuildRequest:
        return BuildRequest(
            run_id=run_id,
            series_kind=kind,
            vintage_id=vintage,
            cutoff_at=cutoff,
            created_at="2023-03-01T00:00:00Z",
        )

    def build(
        self,
        run_id: str,
        kind: SeriesKind = SeriesKind.ARM_O,
        *,
        cutoff: str = "2023-01-31T23:59:59Z",
        vintage: str = "VINTAGE_2023_01",
        output: Path | None = None,
    ) -> Path:
        output = output or self.temp / run_id
        build_run(
            policy_path=self.policy,
            weights_path=self.weights,
            category_observations_path=self.categories,
            headline_observations_path=self.headline,
            output_dir=output,
            ledger_path=self.ledger,
            request=self.request(run_id, kind, cutoff=cutoff, vintage=vintage),
        )
        return output


    def test_real_research_core_basket_schema_when_available(self) -> None:
        real_basket = ROOT / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv"
        if not real_basket.is_file():
            self.skipTest("repository basket is not present in overlay-only validation")
        rows = load_weights(real_basket, EnginePolicy.load(self.policy))
        self.assertEqual(len(rows), 60)
        self.assertEqual(len({row.economy_code for row in rows}), 5)
        self.assertEqual(len({row.category_code for row in rows}), 12)
        self.assertEqual(sum((row.weight for row in rows), Decimal("0")), Decimal("1.000000000000000000000000000"))

    def test_policy_requires_ratified_contract_and_closed_gates(self) -> None:
        policy = EnginePolicy.load(self.policy)
        self.assertEqual(policy.constitution_version, "1.0.0-research")
        self.assertEqual(policy.reference_average, Decimal("100"))
        self.assertFalse(policy.research_release_allowed)
        self.assertFalse(policy.monetary_release_allowed)
        self.assertTrue(policy.ooh_sensitivity_required)

    def test_open_gate_is_rejected(self) -> None:
        payload = json.loads(self.policy.read_text())
        payload["release_gates"]["research_release_allowed"] = True
        self.policy.write_text(json.dumps(payload))
        with self.assertRaisesRegex(OfficialEngineError, "release gates must remain false"):
            EnginePolicy.load(self.policy)

    def test_arm_o_builds_complete_immutable_bundle(self) -> None:
        run = self.build("arm-o-2023-01")
        verify_manifest(run)
        summary = json.loads((run / "outputs" / "run_summary.json").read_text())
        self.assertEqual(summary["series_kind"], "ARM-O")
        self.assertEqual(summary["period_count"], 24)
        self.assertEqual(summary["weight_cell_count"], 24)
        self.assertEqual(summary["research_core_weight_cell_count"], 24)
        self.assertEqual(summary["experimental_proxy_cell_count"], 0)
        self.assertEqual(summary["experimental_proxy_weight_total"], "0")
        self.assertTrue(summary["experimental_proxy_disclosure_required"])
        self.assertEqual(summary["normalised_observation_count"], 24 * 24)
        self.assertEqual(summary["reference_average"], "100")
        self.assertFalse(any(summary["release_gates"].values()))
        index = read_csv(run / "outputs" / "index_series.csv")
        base = [Decimal(row["index_value"]) for row in index if row["period"].startswith("2021-")]
        self.assertEqual(sum(base) / Decimal(12), Decimal("100"))
        self.assertTrue(all(row["status"] == "COMPLETE" for row in index))

    def test_canonical_scales_and_rounding_residuals_reconcile(self) -> None:
        run = self.build("arm-o-contributions")
        index_rows = read_csv(run / "outputs" / "index_series.csv")
        cells = read_csv(run / "outputs" / "cell_contributions.csv")
        economies = read_csv(run / "outputs" / "economy_contributions.csv")
        categories = read_csv(run / "outputs" / "category_contributions.csv")

        index_by_period = {row["period"]: row for row in index_rows}
        canonical_cells: dict[str, Decimal] = {}
        unrounded_cells: dict[str, Decimal] = {}
        canonical_economies: dict[str, Decimal] = {}
        canonical_categories: dict[str, Decimal] = {}

        for row in cells:
            self.assertRegex(row["price_relative"], r"^-?\d+\.\d{12}$")
            self.assertRegex(row["index_level_contribution"], r"^-?\d+\.\d{12}$")
            canonical_cells[row["period"]] = canonical_cells.get(row["period"], Decimal("0")) + Decimal(
                row["index_level_contribution"]
            )
            unrounded_cells[row["period"]] = unrounded_cells.get(row["period"], Decimal("0")) + Decimal(
                row["index_level_contribution_unrounded"]
            )
        for row in economies:
            self.assertRegex(row["index_level_contribution"], r"^-?\d+\.\d{12}$")
            canonical_economies[row["period"]] = canonical_economies.get(row["period"], Decimal("0")) + Decimal(
                row["index_level_contribution"]
            )
        for row in categories:
            self.assertRegex(row["index_level_contribution"], r"^-?\d+\.\d{12}$")
            canonical_categories[row["period"]] = canonical_categories.get(row["period"], Decimal("0")) + Decimal(
                row["index_level_contribution"]
            )

        for period, row in index_by_period.items():
            self.assertRegex(row["index_value"], r"^-?\d+\.\d{12}$")
            canonical_index = Decimal(row["index_value"])
            unrounded_index = Decimal(row["index_value_unrounded"])
            self.assertEqual(unrounded_cells[period], unrounded_index)
            self.assertEqual(
                canonical_cells[period] + Decimal(row["cell_contribution_rounding_residual"]),
                canonical_index,
            )
            self.assertEqual(
                canonical_economies[period] + Decimal(row["economy_contribution_rounding_residual"]),
                canonical_index,
            )
            self.assertEqual(
                canonical_categories[period] + Decimal(row["category_contribution_rounding_residual"]),
                canonical_index,
            )

    def test_rounding_residual_is_nonzero_for_adversarial_weights(self) -> None:
        rows = read_csv(self.weights)
        for pos, row in enumerate(rows):
            row["fixed_universe_weight"] = "0.041666666666666666666666667"
        rows[-1]["fixed_universe_weight"] = "0.041666666666666666666666659"
        with self.weights.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        run = self.build("rounding-residual")
        index_rows = read_csv(run / "outputs" / "index_series.csv")
        self.assertTrue(
            any(Decimal(row["cell_contribution_rounding_residual"]) != 0 for row in index_rows)
        )

    def test_cutoff_excludes_later_revision(self) -> None:
        old = self.build("arm-o-old")
        new = self.build(
            "arm-r-new",
            SeriesKind.ARM_R,
            cutoff="2023-03-01T00:00:00Z",
            vintage="VINTAGE_2023_03",
        )
        old_index = {row["period"]: Decimal(row["index_value"]) for row in read_csv(old / "outputs" / "index_series.csv")}
        new_index = {row["period"]: Decimal(row["index_value"]) for row in read_csv(new / "outputs" / "index_series.csv")}
        self.assertEqual(old_index["2022-11"], new_index["2022-11"])
        self.assertGreater(new_index["2022-12"], old_index["2022-12"])


    def test_arm_o_remains_first_published_even_after_revision_is_available(self) -> None:
        early = self.build("arm-o-first-early")
        late = self.build(
            "arm-o-first-late",
            SeriesKind.ARM_O,
            cutoff="2023-03-01T00:00:00Z",
            vintage="FIRST_PUBLISHED_AS_OF_LATE_CUTOFF",
        )
        early_index = {row["period"]: row["index_value"] for row in read_csv(early / "outputs" / "index_series.csv")}
        late_index = {row["period"]: row["index_value"] for row in read_csv(late / "outputs" / "index_series.csv")}
        self.assertEqual(early_index, late_index)
        selected = [
            row for row in read_csv(late / "outputs" / "normalised_price_observations.csv")
            if row["period"] == "2022-12"
        ]
        self.assertTrue(all(row["revision_sequence"] == "0" for row in selected))


    def test_revision_retrieved_after_cutoff_is_not_available_to_arm_r(self) -> None:
        rows = read_csv(self.categories)
        for row in rows:
            if row["revision_sequence"] == "1":
                row["retrieved_at"] = "2023-04-01T00:00:00Z"
        with self.categories.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        arm_o = self.build("retrieval-cutoff-arm-o")
        arm_r = self.build(
            "retrieval-cutoff-arm-r",
            SeriesKind.ARM_R,
            cutoff="2023-03-01T00:00:00Z",
            vintage="REVISION_NOT_YET_RETRIEVED",
        )
        left = {row["period"]: row["index_value"] for row in read_csv(arm_o / "outputs" / "index_series.csv")}
        right = {row["period"]: row["index_value"] for row in read_csv(arm_r / "outputs" / "index_series.csv")}
        self.assertEqual(left, right)

    def test_proxy_or_model_price_evidence_is_rejected(self) -> None:
        rows = read_csv(self.categories)
        rows[0]["evidence_class"] = "REGIONAL_PROXY_MODEL"
        with self.categories.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(OfficialEngineError, "cannot use proxy or model evidence"):
            self.build("proxy-price-rejected")

    def test_reconciliation_decomposes_revision(self) -> None:
        old = self.build("arm-o-reconcile-old")
        new = self.build(
            "arm-r-reconcile-new",
            SeriesKind.ARM_R,
            cutoff="2023-03-01T00:00:00Z",
            vintage="VINTAGE_2023_03",
        )
        output = self.temp / "reconciliation"
        summary = reconcile_runs(old, new, output)
        self.assertEqual(summary["status"], "RECONCILED")
        self.assertEqual(summary["revised_period_count"], 1)
        self.assertEqual(summary["cell_revision_count"], 24)
        self.assertEqual(summary["cell_row_count"], 24 * 24)
        self.assertFalse(any(summary["release_gates"].values()))
        verify_manifest(output)
        rows = read_csv(output / "index_reconciliation.csv")
        revision = next(row for row in rows if row["period"] == "2022-12")
        self.assertGreater(Decimal(revision["revision_index_points"]), Decimal("0"))
        self.assertRegex(revision["old_index_value"], r"^-?\d+\.\d{12}$")
        self.assertRegex(revision["new_index_value"], r"^-?\d+\.\d{12}$")
        self.assertRegex(revision["revision_index_points"], r"^-?\d+\.\d{12}$")
        self.assertRegex(revision["revision_percent"], r"^-?\d+\.\d{8}$")

    def test_append_only_ledger_chains_runs(self) -> None:
        self.build("arm-o-ledger-1")
        self.build(
            "arm-r-ledger-2",
            SeriesKind.ARM_R,
            cutoff="2023-03-01T00:00:00Z",
            vintage="VINTAGE_2023_03",
        )
        entries = verify_ledger(self.ledger)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["previous_hash"], "0" * 64)
        self.assertEqual(entries[1]["previous_hash"], entries[0]["entry_hash"])

    def test_same_run_id_with_different_content_is_rejected_and_removed(self) -> None:
        self.build("immutable-run")
        second = self.temp / "immutable-run-conflict"
        with self.assertRaisesRegex(OfficialEngineError, "immutable run_id already exists"):
            build_run(
                policy_path=self.policy,
                weights_path=self.weights,
                category_observations_path=self.categories,
                headline_observations_path=self.headline,
                output_dir=second,
                ledger_path=self.ledger,
                request=self.request(
                    "immutable-run",
                    SeriesKind.ARM_R,
                    cutoff="2023-03-01T00:00:00Z",
                    vintage="DIFFERENT",
                ),
            )
        self.assertFalse(second.exists())
        self.assertEqual(len(verify_ledger(self.ledger)), 1)

    def test_replay_is_deterministic(self) -> None:
        run = self.build("arm-o-replay")
        receipt = replay_run(run)
        self.assertEqual(receipt["status"], "REPLAY_VERIFIED")
        self.assertEqual(len(receipt["verified_files"]), 5)

    def test_manifest_detects_tampering(self) -> None:
        run = self.build("arm-o-tamper")
        target = run / "outputs" / "index_series.csv"
        target.write_text(target.read_text() + "tampered\n")
        with self.assertRaisesRegex(OfficialEngineError, "MANIFEST_HASH_MISMATCH"):
            verify_manifest(run)

    def test_ledger_detects_tampering(self) -> None:
        self.build("arm-o-ledger-tamper")
        payload = self.ledger.read_text()
        self.ledger.write_text(payload.replace("ARM-O", "ARM-R", 1))
        with self.assertRaisesRegex(OfficialEngineError, "ledger hash mismatch"):
            verify_ledger(self.ledger)

    def test_incomplete_price_grid_fails_closed_without_output(self) -> None:
        write_observations(self.categories, omit=("BBB", "CP12", "2022-08"))
        output = self.temp / "incomplete-run"
        with self.assertRaisesRegex(OfficialEngineError, "incomplete selected panel"):
            self.build("incomplete-run", output=output)
        self.assertFalse(output.exists())
        self.assertFalse(self.ledger.exists())

    def test_incomplete_weight_grid_is_rejected(self) -> None:
        write_weights(self.weights, missing=("BBB", "CP12"))
        with self.assertRaisesRegex(OfficialEngineError, "weight grid incomplete"):
            self.build("bad-weights")

    def test_nonempty_output_directory_is_rejected(self) -> None:
        output = self.temp / "nonempty"
        output.mkdir()
        (output / "stale.txt").write_text("stale")
        with self.assertRaisesRegex(OfficialEngineError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            self.build("nonempty-run", output=output)

    def test_arm_h_uses_headline_and_derived_economy_weights(self) -> None:
        run = self.build("arm-h-2023-01", SeriesKind.ARM_H)
        summary = json.loads((run / "outputs" / "run_summary.json").read_text())
        self.assertEqual(summary["series_kind"], "ARM-H")
        self.assertEqual(summary["category_count"], 1)
        self.assertEqual(summary["formula"], "ARITHMETIC_HEADLINE_CP00_WITH_DERIVED_ECONOMY_WEIGHTS")
        self.assertEqual(summary["weight_cell_count"], 2)
        categories = {row["category_code"] for row in read_csv(run / "outputs" / "cell_contributions.csv")}
        self.assertEqual(categories, {"CP00"})

    def test_ooh_sensitivity_is_explicitly_non_evidential(self) -> None:
        run = self.build("arm-o-ooh")
        output = self.temp / "ooh"
        summary = run_ooh_sensitivity(run, BASE_OOH, output)
        self.assertEqual(summary["status"], "OOH_SCENARIO_HARNESS_COMPLETED")
        self.assertEqual(summary["evidence_status"], "SCENARIO_NOT_EVIDENCE")
        self.assertFalse(summary["uses_official_oohpi"])
        self.assertFalse(summary["constitutional_ooh_requirement_satisfied"])
        self.assertFalse(summary["shadow_production_authorised"])
        self.assertFalse(any(summary["release_gates"].values()))
        rows = read_csv(output / "ooh_sensitivity.csv")
        neutral = [row for row in rows if row["scenario_id"] == "OOH_CP04_NEUTRAL_100"]
        self.assertTrue(all(Decimal(row["impact_index_points"]) == 0 for row in neutral))

    def test_optional_parquet_contract_with_or_without_duckdb(self) -> None:
        run = self.build("arm-o-parquet")
        try:
            import duckdb  # noqa: F401
        except ModuleNotFoundError:
            with self.assertRaisesRegex(OfficialEngineError, "OPTIONAL_STORAGE_DEPENDENCY_MISSING"):
                export_parquet(run, self.temp / "parquet")
        else:
            output = self.temp / "parquet"
            summary = export_parquet(run, output)
            self.assertEqual(summary["status"], "PARQUET_DERIVED_VIEW_EXPORTED")
            self.assertEqual(summary["file_count"], 5)
            self.assertFalse(summary["canonical_storage"])
            self.assertFalse(any(summary["release_gates"].values()))
            verify_manifest(output)
            parquet_files = sorted(output.glob("*.parquet"))
            self.assertEqual(len(parquet_files), 5)
            self.assertTrue(all(path.stat().st_size > 0 for path in parquet_files))

    def test_manifest_rejects_path_escape(self) -> None:
        run = self.build("arm-o-path-escape")
        (run / "MANIFEST.sha256").write_text("0" * 64 + " ../../outside.txt\n")
        with self.assertRaisesRegex(OfficialEngineError, "path escapes root"):
            verify_manifest(run)

    def test_manifest_rejects_duplicate_target(self) -> None:
        run = self.build("arm-o-duplicate-manifest")
        manifest = run / "MANIFEST.sha256"
        first = manifest.read_text(encoding="utf-8").splitlines()[0]
        manifest.write_text(manifest.read_text(encoding="utf-8") + first + "\n", encoding="utf-8")
        with self.assertRaisesRegex(OfficialEngineError, "duplicate manifest target"):
            verify_manifest(run)


    def test_input_row_order_does_not_change_economic_outputs(self) -> None:
        first = self.build("order-a")
        rows = read_csv(self.categories)
        fields = list(rows[0])
        rows.reverse()
        reordered = self.temp / "category_observations_reordered.csv"
        with reordered.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        second = build_run(
            policy_path=self.policy,
            weights_path=self.weights,
            category_observations_path=reordered,
            headline_observations_path=self.headline,
            output_dir=self.temp / "order-b",
            ledger_path=self.ledger,
            request=self.request("order-b", SeriesKind.ARM_O),
        )
        second_dir = self.temp / second["run_id"]
        for name in (
            "index_series.csv",
            "normalised_price_observations.csv",
            "cell_contributions.csv",
            "economy_contributions.csv",
            "category_contributions.csv",
        ):
            left = read_csv(first / "outputs" / name)
            right = read_csv(second_dir / "outputs" / name)
            for rows in (left, right):
                for row in rows:
                    row.pop("run_id", None)
            self.assertEqual(left, right)

    def test_duplicate_weight_cell_is_rejected(self) -> None:
        rows = read_csv(self.weights)
        with self.weights.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows + [rows[0]])
        with self.assertRaises(OfficialEngineError):
            load_weights(self.weights, EnginePolicy.load(self.policy))

    def test_json_float_is_rejected_where_exact_decimal_is_required(self) -> None:
        payload = json.loads(self.policy.read_text(encoding="utf-8"))
        payload["reference_average"] = 100.0
        self.policy.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaises(OfficialEngineError):
            EnginePolicy.load(self.policy)

    def test_nonuniform_base_months_are_normalised_to_exact_annual_average_100(self) -> None:
        rows = read_csv(self.categories)
        for row in rows:
            if row["economy_code"] == "AAA" and row["category_code"] == "CP01" and row["period"].startswith("2021-"):
                row["value"] = str(89 + int(row["period"][-2:]))
        with self.categories.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        run = self.build("nonuniform-base")
        normalised = [
            Decimal(row["price_relative"])
            for row in read_csv(run / "outputs" / "normalised_price_observations.csv")
            if row["economy_code"] == "AAA"
            and row["category_code"] == "CP01"
            and row["period"].startswith("2021-")
        ]
        self.assertEqual(len(normalised), 12)
        self.assertEqual(sum(normalised) / Decimal(12), Decimal("100"))

    def test_ledger_append_is_idempotent_for_identical_run(self) -> None:
        run = self.build("arm-o-idempotent")
        before = self.ledger.read_bytes()
        entry = append_ledger(self.ledger, run)
        self.assertEqual(entry["sequence"], 1)
        self.assertEqual(before, self.ledger.read_bytes())


if __name__ == "__main__":
    unittest.main()
