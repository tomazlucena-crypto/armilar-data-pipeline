from __future__ import annotations

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from armilar_prices.completion import (
    CompletionPolicy,
    EconomyProfile,
    ObservedPrice,
    PriceCompletionError,
    WeightCell,
    _observation_maps,
    build_global_completion_from_files,
    build_global_indices,
    load_observations,
    load_profiles,
    load_weights,
    complete_price_grid,
    predict_monthly_rate,
    validate_leave_one_out,
)


CATEGORIES = ("ARM01", "ARM02")
ECONOMIES = ("AAA", "AAB", "AAC", "BBB")


def policy(**overrides: object) -> CompletionPolicy:
    payload: dict[str, object] = {
        "policy_version": "test-v0.8.4",
        "required_categories": list(CATEGORIES),
        "minimum_region_donors": 2,
        "minimum_world_donors": 2,
        "maximum_donors": 10,
        "interval_lower_quantile": "0.10",
        "interval_upper_quantile": "0.90",
        "p3_default_half_width": "0.05",
        "validation_horizons": [1, 2],
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    payload.update(overrides)
    return CompletionPolicy.from_mapping(payload)


def weights() -> list[WeightCell]:
    values = {
        "AAA": ("0.10", "0.10"),
        "AAB": ("0.10", "0.10"),
        "AAC": ("0.20", "0.10"),
        "BBB": ("0.15", "0.15"),
    }
    return [
        WeightCell(economy, category, Decimal(values[economy][index]))
        for economy in ECONOMIES
        for index, category in enumerate(CATEGORIES)
    ]


def profiles() -> dict[str, EconomyProfile]:
    return {
        "AAA": EconomyProfile("AAA", "R1", "HIGH", ("URBAN", "SERVICE")),
        "AAB": EconomyProfile("AAB", "R1", "HIGH", ("URBAN", "SERVICE")),
        "AAC": EconomyProfile("AAC", "R1", "UPPER_MIDDLE", ("URBAN", "INDUSTRY")),
        "BBB": EconomyProfile("BBB", "R2", "HIGH", ("URBAN", "SERVICE")),
    }


def row(economy: str, category: str, period: str, value: str, evidence: str | None = None) -> ObservedPrice:
    if evidence is None:
        evidence = "P3_OFFICIAL_HEADLINE" if category == "HEADLINE" else "P1_OFFICIAL_CATEGORY"
    return ObservedPrice(
        economy,
        category,
        period,
        Decimal(value),
        evidence,
        (f"SRC_{economy}_{category}",),
    )


def observations(*, include_target_arm01: bool = False) -> list[ObservedPrice]:
    result: list[ObservedPrice] = []
    headline_levels = {
        "AAA": ("100", "102", "104.04"),
        "AAB": ("100", "101", "102.01"),
        "AAC": ("100", "101", "102.01"),
        "BBB": ("100", "103", "106.09"),
    }
    category_levels = {
        "AAB": {
            "ARM01": ("100", "105", "110.25"),
            "ARM02": ("100", "100", "100"),
        },
        "AAC": {
            "ARM01": ("100", "103", "106.09"),
            "ARM02": ("100", "102", "104.04"),
        },
        "BBB": {
            "ARM01": ("100", "104", "108.16"),
            "ARM02": ("100", "105", "110.25"),
        },
    }
    if include_target_arm01:
        category_levels["AAA"] = {
            "ARM01": ("100", "107", "114.49"),
            "ARM02": ("100", "101", "102.01"),
        }
    else:
        category_levels["AAA"] = {
            "ARM02": ("100", "101", "102.01"),
        }
    periods = ("2021-01", "2021-02", "2021-03")
    for economy in ECONOMIES:
        for period, value in zip(periods, headline_levels[economy]):
            result.append(row(economy, "HEADLINE", period, value))
        for category, levels in category_levels[economy].items():
            for period, value in zip(periods, levels):
                evidence = "P2_OFFICIAL_COMPATIBLE_AGGREGATE" if economy == "AAC" and category == "ARM02" else None
                result.append(row(economy, category, period, value, evidence))
    return sorted(result, key=lambda item: (item.period, item.economy_code, item.category_code))


class CompletionCoreTests(unittest.TestCase):
    def test_p4_preserves_target_headline_and_adds_weighted_median_residual(self) -> None:
        obs = observations()
        by_key, _ = _observation_maps(obs)
        prediction = predict_monthly_rate(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            by_key=by_key,
            profiles=profiles(),
            economy_weights={"AAA": Decimal("0.2"), "AAB": Decimal("0.2"), "AAC": Decimal("0.3"), "BBB": Decimal("0.3")},
            policy=policy(),
        )
        self.assertEqual(prediction.evidence_class, "P4_REGIONAL_PATTERN")
        self.assertEqual(prediction.donor_economies, ("AAB", "AAC"))
        # AAA headline is +2%; AAB residual +4%; AAC residual +2%.
        # AAB has the larger profile-adjusted weight, so the weighted median is +4%.
        self.assertEqual(prediction.central_rate, Decimal("0.06"))

    def test_p5_is_used_when_regional_pool_is_insufficient(self) -> None:
        obs = observations()
        by_key, _ = _observation_maps(obs)
        custom_profiles = profiles()
        custom_profiles["AAA"] = replace(custom_profiles["AAA"], region="ISOLATED")
        prediction = predict_monthly_rate(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            by_key=by_key,
            profiles=custom_profiles,
            economy_weights={economy: Decimal("0.25") for economy in ECONOMIES},
            policy=policy(),
        )
        self.assertEqual(prediction.evidence_class, "P5_WORLD_PATTERN")
        self.assertGreaterEqual(len(prediction.donor_economies), 2)

    def test_p3_is_used_when_no_donor_pool_meets_the_gate(self) -> None:
        obs = observations()
        by_key, _ = _observation_maps(obs)
        prediction = predict_monthly_rate(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            by_key=by_key,
            profiles=profiles(),
            economy_weights={economy: Decimal("0.25") for economy in ECONOMIES},
            policy=policy(minimum_region_donors=4, minimum_world_donors=4),
        )
        self.assertEqual(prediction.evidence_class, "P3_OFFICIAL_HEADLINE")
        self.assertEqual(prediction.central_rate, Decimal("0.02"))

    def test_target_hidden_value_does_not_select_or_change_donors(self) -> None:
        obs = observations(include_target_arm01=True)
        by_key, _ = _observation_maps(obs)
        kwargs = dict(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            profiles=profiles(),
            economy_weights={economy: Decimal("0.25") for economy in ECONOMIES},
            policy=policy(),
        )
        first = predict_monthly_rate(by_key=by_key, **kwargs)
        changed = dict(by_key)
        changed[("AAA", "ARM01", "2021-02")] = replace(
            changed[("AAA", "ARM01", "2021-02")], price_relative=Decimal("999")
        )
        second = predict_monthly_rate(by_key=changed, **kwargs)
        self.assertEqual(first, second)

    def test_future_observation_does_not_change_earlier_prediction(self) -> None:
        obs = observations()
        by_key, _ = _observation_maps(obs)
        kwargs = dict(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            profiles=profiles(),
            economy_weights={economy: Decimal("0.25") for economy in ECONOMIES},
            policy=policy(),
        )
        first = predict_monthly_rate(by_key=by_key, **kwargs)
        changed = dict(by_key)
        changed[("AAB", "ARM01", "2021-03")] = replace(
            changed[("AAB", "ARM01", "2021-03")], price_relative=Decimal("999")
        )
        second = predict_monthly_rate(by_key=changed, **kwargs)
        self.assertEqual(first, second)

    def test_missing_target_headline_fails_closed(self) -> None:
        obs = [item for item in observations() if not (item.economy_code == "AAA" and item.category_code == "HEADLINE" and item.period == "2021-02")]
        by_key, _ = _observation_maps(obs)
        with self.assertRaisesRegex(PriceCompletionError, "target headline missing"):
            predict_monthly_rate(
                target_economy="AAA",
                category="ARM01",
                period="2021-02",
                by_key=by_key,
                profiles=profiles(),
                economy_weights={economy: Decimal("0.25") for economy in ECONOMIES},
                policy=policy(),
            )

    def test_complete_grid_preserves_direct_cells_and_fills_missing_cells(self) -> None:
        completed, audit, summary = complete_price_grid(
            weights(), profiles(), observations(), "2021-01", policy()
        )
        self.assertEqual(len(completed), len(ECONOMIES) * len(CATEGORIES) * 3)
        direct = next(row for row in completed if (row.economy_code, row.category_code, row.period) == ("AAB", "ARM01", "2021-02"))
        imputed = next(row for row in completed if (row.economy_code, row.category_code, row.period) == ("AAA", "ARM01", "2021-02"))
        self.assertTrue(direct.observed)
        self.assertEqual(direct.central_index, Decimal("105"))
        self.assertFalse(imputed.observed)
        self.assertEqual(imputed.evidence_class, "P4_REGIONAL_PATTERN")
        self.assertEqual(imputed.central_index, Decimal("106"))
        self.assertEqual(len(audit), len(completed))
        self.assertFalse(summary["research_release_allowed"])
        self.assertFalse(summary["monetary_release_allowed"])

    def test_global_index_uses_complete_fixed_weights_without_renormalisation(self) -> None:
        completed, _, _ = complete_price_grid(
            weights(), profiles(), observations(), "2021-01", policy()
        )
        indices, uncertainty, coverage = build_global_indices(completed, weights())
        self.assertEqual(indices[0]["index_value"], Decimal("100"))
        feb_coverage = [row for row in coverage if row["period"] == "2021-02"]
        self.assertEqual(sum((row["world_weight"] for row in feb_coverage), Decimal("0")), Decimal("1"))
        self.assertEqual(len(uncertainty), 3)

    def test_leave_one_out_reports_horizon_and_fallback_metrics(self) -> None:
        validation = validate_leave_one_out(
            weights(), profiles(), observations(include_target_arm01=True), "2021-01", policy()
        )
        self.assertTrue(validation)
        self.assertIn(1, {row["horizon_months"] for row in validation})
        self.assertTrue({row["fallback_class"] for row in validation}.issubset({
            "P3_OFFICIAL_HEADLINE", "P4_REGIONAL_PATTERN", "P5_WORLD_PATTERN"
        }))
        self.assertTrue(all("interval_covered" in row for row in validation))


class CompletionFileTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> tuple[Path, Path, Path, Path]:
        weights_path = root / "weights.csv"
        with weights_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["economy_code", "category_code", "world_weight"])
            for item in weights():
                writer.writerow([item.economy_code, item.category_code, item.world_weight])
        profiles_path = root / "profiles.csv"
        with profiles_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["economy_code", "region", "income_group", "characteristics"])
            for item in profiles().values():
                writer.writerow([item.economy_code, item.region, item.income_group, "|".join(item.characteristics)])
        observations_path = root / "observations.csv"
        with observations_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["economy_code", "category_code", "period", "price_relative", "evidence_class", "source_ids"])
            for item in observations(include_target_arm01=True):
                writer.writerow([item.economy_code, item.category_code, item.period, item.price_relative, item.evidence_class, "|".join(item.source_ids)])
        policy_path = root / "policy.json"
        policy_path.write_text(json.dumps({
            "policy_version": "test-v0.8.4",
            "required_categories": list(CATEGORIES),
            "minimum_region_donors": 2,
            "minimum_world_donors": 2,
            "maximum_donors": 10,
            "interval_lower_quantile": "0.10",
            "interval_upper_quantile": "0.90",
            "p3_default_half_width": "0.05",
            "validation_horizons": [1, 2],
            "research_release_allowed": False,
            "monetary_release_allowed": False,
        }, indent=2) + "\n", encoding="utf-8")
        return weights_path, observations_path, profiles_path, policy_path


    def test_cp_weight_release_is_aggregated_through_exact_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weights_path = root / "weights_global.csv"
            weights_path.write_text(
                "economy_code,category_code,weight\n"
                "AAA,CP01,0.20\n"
                "AAA,CP02,0.30\n"
                "BBB,CP01,0.10\n"
                "BBB,CP02,0.40\n",
                encoding="utf-8",
            )
            mapping_path = root / "mapping.csv"
            mapping_path.write_text(
                "source_code,armilar_category,mapping_type,strict_pilot_admissible\n"
                "CP01,ARM01,EXACT_ONE_TO_ONE,true\n"
                "CP02,ARM02,EXACT_ONE_TO_ONE,true\n",
                encoding="utf-8",
            )
            loaded = load_weights(weights_path, CATEGORIES, mapping_path)
            self.assertEqual(len(loaded), 4)
            self.assertEqual(sum((item.world_weight for item in loaded), Decimal("0")), Decimal("1"))

    def test_existing_weight_profile_schema_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.csv"
            path.write_text(
                "economy_code,region_code,income_group,total_real_expenditure,gdp_per_capita,urban_share\n"
                "AAA,R1,HIGH,10,100,0.8\n"
                "AAB,R1,HIGH,20,110,0.9\n",
                encoding="utf-8",
            )
            loaded = load_profiles(path, ["AAA", "AAB"])
            self.assertEqual(loaded["AAA"].region, "R1")
            self.assertEqual(dict(loaded["AAA"].covariates)["gdp_per_capita"], Decimal("100"))

    def test_outputs_and_manifest_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self._write_inputs(root)
            first = root / "first"
            second = root / "second"
            build_global_completion_from_files(*inputs, "2021-01", first)
            build_global_completion_from_files(*inputs, "2021-01", second)
            expected = {
                "monthly_price_cells_complete.csv",
                "monthly_price_uncertainty.csv",
                "price_imputation_audit.csv",
                "price_validation_by_category.csv",
                "price_validation_by_region.csv",
                "price_validation_by_horizon.csv",
                "price_validation_by_fallback.csv",
                "price_validation_summary.json",
                "price_completion_summary.json",
                "monthly_global_experimental_index.csv",
                "monthly_global_index_uncertainty.csv",
                "price_evidence_coverage.csv",
                "MANIFEST.sha256",
            }
            self.assertEqual({path.name for path in first.iterdir()}, expected)
            for filename in expected:
                self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())

    def test_summary_keeps_release_flags_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self._write_inputs(root)
            output = root / "out"
            summary = build_global_completion_from_files(*inputs, "2021-01", output)
            self.assertFalse(summary["research_release_allowed"])
            self.assertFalse(summary["monetary_release_allowed"])
            validation = json.loads((output / "price_validation_summary.json").read_text(encoding="utf-8"))
            self.assertFalse(validation["donor_selection_uses_hidden_target_value"])
            self.assertFalse(validation["future_period_observations_allowed"])


    def test_pilot_output_column_aliases_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "pilot_rows.csv"
            path.write_text(
                "economy_code,category_code,period,price_relative,price_evidence_class,price_series_ids\n"
                "AAA,ARM01,2021-01,100,P1_OFFICIAL_CATEGORY,S1\n"
                "AAA,HEADLINE,2021-01,100,P3_OFFICIAL_HEADLINE,H1\n",
                encoding="utf-8",
            )
            loaded = load_observations(path, CATEGORIES, ["AAA"])
            self.assertEqual(loaded[0].evidence_class, "P1_OFFICIAL_CATEGORY")
            self.assertEqual(loaded[1].evidence_class, "P3_OFFICIAL_HEADLINE")

    def test_summary_hashes_all_input_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self._write_inputs(root)
            output = root / "out"
            summary = build_global_completion_from_files(*inputs, "2021-01", output)
            self.assertTrue(summary["input_provenance_complete"])
            self.assertFalse(summary["methodology_changes_allowed_silently"])
            self.assertEqual(
                set(summary["input_hashes"]),
                {
                    "weights_global_sha256",
                    "observed_prices_sha256",
                    "economy_profiles_sha256",
                    "completion_policy_sha256",
                },
            )
            self.assertTrue(all(len(value) == 64 for value in summary["input_hashes"].values()))

    def test_duplicate_observation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = list(self._write_inputs(root))
            observations_path = inputs[1]
            lines = observations_path.read_text(encoding="utf-8").splitlines()
            observations_path.write_text("\n".join(lines + [lines[1]]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PriceCompletionError, "duplicate observed price cell"):
                build_global_completion_from_files(*inputs, "2021-01", root / "out")


if __name__ == "__main__":
    unittest.main()
