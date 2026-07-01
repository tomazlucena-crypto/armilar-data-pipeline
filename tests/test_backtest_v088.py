from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from decimal import Decimal, getcontext
from pathlib import Path

from armilar_prices.backtest_v088 import (
    BacktestError,
    BacktestPolicy,
    MODELS,
    add_months,
    build_backtest,
    load_panel,
    rolling_origin_pairs,
    run_cases,
    verify_manifest,
)

getcontext().prec = 42
ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "backtest_v088.json"
ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
CATEGORIES = tuple(f"CP{i:02d}" for i in range(1, 13))
ARMILAR_MAP = {
    "CP01": "ARM01", "CP02": "ARM02", "CP03": "ARM03",
    "CP04": "ARM04", "CP05": "ARM04", "CP06": "ARM05",
    "CP07": "ARM06", "CP08": "ARM06", "CP09": "ARM07",
    "CP10": "ARM07", "CP11": "ARM08", "CP12": "ARM09",
}


def periods(start: str, end: str) -> list[str]:
    result = []
    current = start
    while current <= end:
        result.append(current)
        current = add_months(current, 1)
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root: Path) -> None:
    files = sorted(path for path in root.iterdir() if path.is_file() and path.name != "MANIFEST.sha256")
    text = "\n".join(f"{sha256(path)}  {path.name}" for path in files) + "\n"
    (root / "MANIFEST.sha256").write_text(text, encoding="utf-8", newline="")


def write_panel(root: Path, *, omit=None, duplicate=False, official=True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fields = [
        "universe_id", "economy_code", "economy_name", "source_category",
        "armilar_category", "period", "price_relative", "fixed_universe_weight",
        "price_evidence_class",
    ]
    all_periods = periods("2021-01", "2025-12")
    rows = []
    cell_index = 0
    for economy_index, economy in enumerate(ECONOMIES):
        for category_index, category in enumerate(CATEGORIES):
            cell_index += 1
            weight = Decimal("0.016") if cell_index < 60 else Decimal("0.056")
            for month_index, period in enumerate(all_periods):
                if omit == (economy, category, period):
                    continue
                # Correlated trend plus bounded economy/category variation. Donor methods
                # have signal, while no model is guaranteed to dominate every cell.
                common = Decimal("1") + Decimal(month_index) * Decimal("0.0022")
                economy_effect = Decimal(economy_index) * Decimal(month_index) * Decimal("0.00008")
                category_effect = Decimal(category_index) * Decimal(month_index) * Decimal("0.000025")
                cycle = Decimal(((month_index + category_index) % 12) - 6) * Decimal("0.00035")
                value = common + economy_effect + category_effect + cycle
                rows.append(
                    {
                        "universe_id": "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7",
                        "economy_code": economy,
                        "economy_name": economy,
                        "source_category": category,
                        "armilar_category": ARMILAR_MAP[category],
                        "period": period,
                        "price_relative": format(value, "f"),
                        "fixed_universe_weight": format(weight, "f"),
                        "price_evidence_class": "P1_OFFICIAL_CATEGORY",
                    }
                )
    if duplicate:
        rows.append(dict(rows[0]))
    with (root / "normalized_price_observations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    by_period = {}
    for row in rows:
        by_period.setdefault(row["period"], Decimal("0"))
        by_period[row["period"]] += (
            Decimal("100")
            * Decimal(row["fixed_universe_weight"])
            * Decimal(row["price_relative"])
        )
    with (root / "monthly_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["period", "index_value"], lineterminator="\n")
        writer.writeheader()
        for period in sorted(by_period):
            writer.writerow({"period": period, "index_value": format(by_period[period], "f")})
    summary = {
        "universe_id": "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7",
        "snapshot_kind": "OFFICIAL_PROVIDER_ACQUISITION" if official else "SYNTHETIC_TEST_FIXTURE",
    }
    (root / "run_summary.json").write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="",
    )
    write_manifest(root)


class BacktestV088Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.input = self.temp / "input"
        self.output = self.temp / "output"
        write_panel(self.input)
        payload = json.loads(POLICY.read_text())
        payload["evaluation_end"] = "2022-06"
        payload["horizons"] = [1, 3]
        payload["top_source_minimum_cases"] = 2
        self.fast_policy = self.temp / "fast_policy.json"
        self.fast_policy.write_text(json.dumps(payload), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def test_policy_declares_vintage_limitation_and_closed_release_gates(self) -> None:
        policy = BacktestPolicy.load(POLICY)
        self.assertEqual(policy.models, MODELS)
        self.assertFalse(policy.publication_aware)
        self.assertEqual(policy.vintage_mode, "FINAL_VINTAGE_PSEUDO_REAL_TIME")
        self.assertFalse(policy.research_release_allowed)
        self.assertFalse(policy.monetary_release_allowed)

    def test_publication_aware_claim_is_rejected(self) -> None:
        payload = json.loads(POLICY.read_text())
        payload["publication_aware"] = True
        altered = self.temp / "policy.json"
        altered.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(BacktestError, "VINTAGE_CLAIM_UNSUPPORTED"):
            BacktestPolicy.load(altered)

    def test_panel_is_complete_and_weights_sum_to_one(self) -> None:
        panel = load_panel(self.input, BacktestPolicy.load(POLICY))
        self.assertEqual(len(panel.cells), 60)
        self.assertEqual(len(panel.periods), 60)
        self.assertEqual(sum((cell.weight for cell in panel.cells), Decimal("0")), Decimal("1"))

    def test_nonofficial_input_is_rejected(self) -> None:
        shutil.rmtree(self.input)
        write_panel(self.input, official=False)
        with self.assertRaisesRegex(BacktestError, "OFFICIAL_INPUT_REQUIRED"):
            load_panel(self.input, BacktestPolicy.load(POLICY))

    def test_incomplete_grid_is_rejected(self) -> None:
        shutil.rmtree(self.input)
        write_panel(self.input, omit=("PRT", "CP12", "2024-06"))
        with self.assertRaisesRegex(BacktestError, "INCOMPLETE_PANEL_GRID"):
            load_panel(self.input, BacktestPolicy.load(POLICY))

    def test_duplicate_cell_is_rejected(self) -> None:
        shutil.rmtree(self.input)
        write_panel(self.input, duplicate=True)
        with self.assertRaisesRegex(BacktestError, "DUPLICATE_PANEL_CELL"):
            load_panel(self.input, BacktestPolicy.load(POLICY))

    def test_temporal_pairs_never_use_target_or_future_as_origin(self) -> None:
        policy = BacktestPolicy.load(self.fast_policy)
        panel = load_panel(self.input, policy)
        pairs = rolling_origin_pairs(panel, policy)
        self.assertTrue(pairs)
        for origin, target, horizon in pairs:
            self.assertLess(origin, target)
            self.assertEqual(add_months(origin, horizon), target)
            self.assertGreaterEqual(target, policy.evaluation_start)
            self.assertLessEqual(target, policy.evaluation_end)

    def test_all_models_use_identical_case_sample(self) -> None:
        policy = BacktestPolicy.load(self.fast_policy)
        panel = load_panel(self.input, policy)
        cases = run_cases(panel, policy)
        samples = {
            model: {case.case_id for case in cases if case.model == model}
            for model in policy.models
        }
        first = samples[policy.models[0]]
        self.assertGreater(len(first), 100)
        for model in policy.models[1:]:
            self.assertEqual(samples[model], first)

    def test_build_writes_required_outputs_and_quantitative_top_three(self) -> None:
        summary = build_backtest(self.fast_policy, self.input, self.output)
        self.assertEqual(summary["status"], "MINIMUM_BACKTEST_COMPLETED_WITH_VINTAGE_LIMITATION")
        self.assertFalse(summary["publication_aware"])
        required = (
            "backtest_cases.csv", "model_metrics.csv", "error_by_scenario.csv",
            "error_by_horizon.csv", "error_by_economy.csv", "error_by_category.csv",
            "error_by_evidence_class.csv", "construction_sensitivity.csv",
            "sensitivity_summary.json", "top_three_error_sources.json",
            "backtest_summary.json", "BACKTEST_REPORT.md", "MANIFEST.sha256",
        )
        for name in required:
            self.assertTrue((self.output / name).is_file(), name)
        top = json.loads((self.output / "top_three_error_sources.json").read_text())
        self.assertEqual(len(top["top_three"]), 3)
        for row in top["top_three"]:
            self.assertGreater(int(row["case_count"]), 0)
            self.assertGreaterEqual(Decimal(row["mean_absolute_bps"]), Decimal("0"))

    def test_model_metrics_reproduce_case_rows(self) -> None:
        build_backtest(self.fast_policy, self.input, self.output)
        with (self.output / "backtest_cases.csv").open(newline="", encoding="utf-8") as handle:
            cases = list(csv.DictReader(handle))
        with (self.output / "model_metrics.csv").open(newline="", encoding="utf-8") as handle:
            metrics = {row["model"]: row for row in csv.DictReader(handle)}
        for model in MODELS:
            rows = [row for row in cases if row["model"] == model]
            reproduced = sum((Decimal(row["absolute_error_bps"]) for row in rows), Decimal("0")) / Decimal(len(rows))
            self.assertLess(abs(reproduced - Decimal(metrics[model]["mean_absolute_bps"])), Decimal("1e-7"))

    def test_backtest_is_deterministic(self) -> None:
        output_two = self.temp / "output_two"
        build_backtest(self.fast_policy, self.input, self.output)
        build_backtest(self.fast_policy, self.input, output_two)
        hashes_one = {
            path.relative_to(self.output).as_posix(): sha256(path)
            for path in self.output.rglob("*") if path.is_file()
        }
        hashes_two = {
            path.relative_to(output_two).as_posix(): sha256(path)
            for path in output_two.rglob("*") if path.is_file()
        }
        self.assertEqual(hashes_one, hashes_two)

    def test_manifest_detects_tampering(self) -> None:
        build_backtest(self.fast_policy, self.input, self.output)
        verify_manifest(self.output)
        report = self.output / "BACKTEST_REPORT.md"
        report.write_text(report.read_text() + "tampered\n")
        with self.assertRaisesRegex(BacktestError, "MANIFEST_HASH_MISMATCH"):
            verify_manifest(self.output)

    def test_sensitivity_does_not_fabricate_unavailable_results(self) -> None:
        build_backtest(self.fast_policy, self.input, self.output)
        sensitivity = json.loads((self.output / "sensitivity_summary.json").read_text())
        self.assertFalse(sensitivity["official_headline_improvement_identifiable"])
        self.assertFalse(sensitivity["fx_methodology_sensitivity_available"])
        self.assertFalse(sensitivity["imputed_economy_effect_available"])
        summary = json.loads((self.output / "backtest_summary.json").read_text())
        self.assertFalse(summary["research_release_allowed"])
        self.assertFalse(summary["monetary_release_allowed"])

    def test_input_index_identity_is_verified(self) -> None:
        index_path = self.input / "monthly_index.csv"
        rows = index_path.read_text(encoding="utf-8").splitlines()
        period, value = rows[1].split(",", 1)
        rows[1] = f"{period},{Decimal(value) + Decimal('0.01')}"
        index_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        write_manifest(self.input)
        with self.assertRaisesRegex(BacktestError, "INPUT_INDEX_IDENTITY_FAILED"):
            load_panel(self.input, BacktestPolicy.load(POLICY))

    def test_output_directory_must_be_empty(self) -> None:
        self.output.mkdir()
        (self.output / "stale.txt").write_text("stale")
        with self.assertRaisesRegex(BacktestError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            build_backtest(self.fast_policy, self.input, self.output)


if __name__ == "__main__":
    unittest.main()
