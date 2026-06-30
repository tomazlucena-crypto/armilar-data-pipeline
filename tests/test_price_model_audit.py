from __future__ import annotations

import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from armilar_prices.audit import (
    PriceModelAuditError,
    audit_global_price_model,
    load_gate_policy,
    verify_manifest,
)
from armilar_prices.completion import build_global_completion_from_files

CATEGORIES = ("ARM01", "ARM02")
ECONOMIES = ("AAA", "AAB", "AAC", "BBB")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare_inputs(root: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    weights = root / "weights.csv"
    rows = []
    values = {
        "AAA": ("0.10", "0.10"),
        "AAB": ("0.10", "0.10"),
        "AAC": ("0.20", "0.10"),
        "BBB": ("0.15", "0.15"),
    }
    for economy in ECONOMIES:
        for index, category in enumerate(CATEGORIES):
            rows.append({
                "economy_code": economy,
                "category_code": category,
                "world_weight": values[economy][index],
            })
    write_csv(weights, ["economy_code", "category_code", "world_weight"], rows)

    profiles = root / "profiles.csv"
    write_csv(
        profiles,
        ["economy_code", "region", "income_group", "characteristics"],
        [
            {"economy_code": "AAA", "region": "R1", "income_group": "HIGH", "characteristics": "URBAN|SERVICE"},
            {"economy_code": "AAB", "region": "R1", "income_group": "HIGH", "characteristics": "URBAN|SERVICE"},
            {"economy_code": "AAC", "region": "R1", "income_group": "UPPER_MIDDLE", "characteristics": "URBAN|INDUSTRY"},
            {"economy_code": "BBB", "region": "R2", "income_group": "HIGH", "characteristics": "URBAN|SERVICE"},
        ],
    )

    observed = root / "observed.csv"
    periods = ("2021-01", "2021-02", "2021-03")
    headline = {
        "AAA": ("100", "102", "104.04"),
        "AAB": ("100", "101", "102.01"),
        "AAC": ("100", "101", "102.01"),
        "BBB": ("100", "103", "106.09"),
    }
    categories = {
        "AAA": {"ARM01": ("100", "107", "114.49"), "ARM02": ("100", "101", "102.01")},
        "AAB": {"ARM01": ("100", "105", "110.25"), "ARM02": ("100", "100", "100")},
        "AAC": {"ARM01": ("100", "103", "106.09"), "ARM02": ("100", "102", "104.04")},
        "BBB": {"ARM01": ("100", "104", "108.16"), "ARM02": ("100", "105", "110.25")},
    }
    obs_rows = []
    for economy in ECONOMIES:
        for period, value in zip(periods, headline[economy]):
            obs_rows.append({
                "economy_code": economy,
                "category_code": "HEADLINE",
                "period": period,
                "price_relative": value,
                "evidence_class": "P3_OFFICIAL_HEADLINE",
                "source_ids": f"SRC_{economy}_HEADLINE",
            })
        for category, levels in categories[economy].items():
            for period, value in zip(periods, levels):
                obs_rows.append({
                    "economy_code": economy,
                    "category_code": category,
                    "period": period,
                    "price_relative": value,
                    "evidence_class": "P1_OFFICIAL_CATEGORY",
                    "source_ids": f"SRC_{economy}_{category}",
                })
    write_csv(
        observed,
        ["economy_code", "category_code", "period", "price_relative", "evidence_class", "source_ids"],
        obs_rows,
    )

    completion_policy = root / "completion_policy.json"
    completion_policy.write_text(json.dumps({
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

    completion_output = root / "completion"
    build_global_completion_from_files(
        weights, observed, profiles, completion_policy, "2021-01", completion_output
    )

    gate_policy = root / "gate_policy.json"
    gate_policy.write_text(json.dumps({
        "policy_version": "test-v0.8.5",
        "status": "DRAFT_UNRATIFIED",
        "ratified": False,
        "required_completion_methodology": "0.8.4",
        "minimum_history_months": 3,
        "minimum_validation_observations": 1,
        "minimum_validation_per_category": 1,
        "minimum_validation_per_region": 1,
        "maximum_mae": "100",
        "maximum_mape_percent": "100",
        "maximum_rmse": "100",
        "maximum_absolute_bias": "100",
        "minimum_interval_coverage": "0",
        "maximum_interval_coverage": "1",
        "minimum_improvement_vs_headline_percent": "-100",
        "maximum_p3_world_weight": "1",
        "maximum_p5_world_weight": "1",
        "minimum_direct_world_weight": "0",
        "maximum_sensitivity_index_shift_bps": "10000",
        "maximum_sensitivity_mae_degradation_percent": "10000",
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }, indent=2) + "\n", encoding="utf-8")

    return weights, observed, profiles, completion_policy, completion_output, gate_policy


class PriceModelAuditTests(unittest.TestCase):
    def run_audit(self, root: Path, **kwargs: object) -> tuple[dict[str, object], Path]:
        weights, observed, profiles, completion_policy, completion_output, gate_policy = prepare_inputs(root)
        output = root / "audit"
        summary = audit_global_price_model(
            weights,
            observed,
            profiles,
            completion_policy,
            completion_output,
            gate_policy,
            "2021-01",
            output,
        )
        return summary, output

    def test_valid_audit_is_deterministic_and_release_stays_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, output = self.run_audit(root)
            first = (output / "MANIFEST.sha256").read_bytes()
            self.assertFalse(summary["research_release_allowed"])
            self.assertFalse(summary["monetary_release_allowed"])
            self.assertFalse(summary["release_gate_passed"])
            self.assertEqual(summary["status"], "EMPIRICAL_GATES_PASSED_POLICY_UNRATIFIED")
            summary2 = audit_global_price_model(
                root / "weights.csv", root / "observed.csv", root / "profiles.csv",
                root / "completion_policy.json", root / "completion", root / "gate_policy.json",
                "2021-01", output,
            )
            self.assertEqual(summary, summary2)
            self.assertEqual(first, (output / "MANIFEST.sha256").read_bytes())

    def test_completion_manifest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_inputs(root)
            path = root / "completion" / "price_evidence_coverage.csv"
            path.write_text(path.read_text(encoding="utf-8") + "x", encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "hash mismatch"):
                audit_global_price_model(
                    root / "weights.csv", root / "observed.csv", root / "profiles.csv",
                    root / "completion_policy.json", root / "completion", root / "gate_policy.json",
                    "2021-01", root / "audit",
                )

    def test_input_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_inputs(root)
            path = root / "profiles.csv"
            path.write_text(path.read_text(encoding="utf-8").replace("SERVICE", "OTHER", 1), encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "input hash mismatch"):
                audit_global_price_model(
                    root / "weights.csv", root / "observed.csv", root / "profiles.csv",
                    root / "completion_policy.json", root / "completion", root / "gate_policy.json",
                    "2021-01", root / "audit",
                )

    def test_policy_cannot_authorise_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            *_, gate = prepare_inputs(root)
            payload = json.loads(gate.read_text(encoding="utf-8"))
            payload["research_release_allowed"] = True
            gate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "cannot authorise"):
                load_gate_policy(gate)

    def test_insufficient_validation_sample_fails_empirical_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            *_, gate = prepare_inputs(root)
            payload = json.loads(gate.read_text(encoding="utf-8"))
            payload["minimum_validation_observations"] = 999999
            gate.write_text(json.dumps(payload), encoding="utf-8")
            summary = audit_global_price_model(
                root / "weights.csv", root / "observed.csv", root / "profiles.csv",
                root / "completion_policy.json", root / "completion", gate,
                "2021-01", root / "audit",
            )
            self.assertFalse(summary["empirical_gate_passed"])
            self.assertEqual(summary["status"], "AUDIT_FAILED")

    def test_outputs_include_baselines_sensitivity_detail_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary, output = self.run_audit(Path(tmp))
            expected = {
                "price_validation_detail.csv",
                "price_baseline_comparison.csv",
                "price_sensitivity_audit.csv",
                "price_model_gate_results.csv",
                "price_model_audit_summary.json",
                "MANIFEST.sha256",
            }
            self.assertTrue(all((output / name).exists() for name in expected))
            with (output / "price_baseline_comparison.csv").open(encoding="utf-8", newline="") as handle:
                baseline_rows = list(csv.DictReader(handle))
            self.assertEqual({row["model_id"] for row in baseline_rows}, {
                "CANDIDATE_SELECTED_PATTERN", "B0_TARGET_HEADLINE_ONLY", "B1_WORLD_PATTERN"
            })
            self.assertGreater(summary["validation_observation_count"], 0)

    def test_sensitivity_audit_contains_predeclared_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, output = self.run_audit(Path(tmp))
            with (output / "price_sensitivity_audit.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            ids = {row["scenario_id"] for row in rows}
            self.assertIn("BASELINE", ids)
            self.assertIn("REGION_DONORS_PLUS_ONE", ids)
            self.assertIn("WORLD_DONORS_PLUS_ONE", ids)

    def test_manifest_verifier_requires_all_completion_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_inputs(root)
            manifest = root / "completion" / "MANIFEST.sha256"
            lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if "price_validation_summary.json" not in line]
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "missing required files"):
                verify_manifest(root / "completion")

    def test_hidden_target_and_future_flags_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary, _ = self.run_audit(Path(tmp))
            self.assertFalse(summary["hidden_target_value_used_for_donor_selection"])
            self.assertFalse(summary["future_period_observations_allowed"])
            self.assertFalse(summary["silent_monthly_renormalisation_allowed"])

    def test_ratified_requires_json_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            *_, gate = prepare_inputs(root)
            payload = json.loads(gate.read_text(encoding="utf-8"))
            payload["ratified"] = "false"
            gate.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "ratified must be a JSON boolean"):
                load_gate_policy(gate)

    def test_mapping_hash_cannot_be_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_inputs(root)
            summary_path = root / "completion" / "price_completion_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["input_hashes"]["classification_mapping_sha256"] = "0" * 64
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            # Rebuild the completion manifest entry for the intentionally modified summary.
            manifest_path = root / "completion" / "MANIFEST.sha256"
            import hashlib
            lines = []
            for line in manifest_path.read_text(encoding="utf-8").splitlines():
                digest, filename = line.split("  ", 1)
                if filename == "price_completion_summary.json":
                    digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                lines.append(f"{digest}  {filename}")
            manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PriceModelAuditError, "no mapping was supplied"):
                audit_global_price_model(
                    root / "weights.csv", root / "observed.csv", root / "profiles.csv",
                    root / "completion_policy.json", root / "completion", root / "gate_policy.json",
                    "2021-01", root / "audit",
                )


if __name__ == "__main__":
    unittest.main()
