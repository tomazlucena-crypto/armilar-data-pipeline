from __future__ import annotations

import csv
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path

from armilar_backtest.ecoicop_v2_transition_v0102 import (
    EcoicopTransitionError,
    STATUS,
    TransitionPolicy,
    build_transition_audit,
    main,
    verify_transition_audit,
)


LEGACY_CATEGORIES = [f"CP{i:02d}" for i in range(1, 13)]
V2_DIVISIONS = [f"CP{i:02d}" for i in range(1, 14)]


def _load_repository_checker():
    checker_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_ecoicop_v2_transition_v0102.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_ecoicop_v2_transition_v0102", checker_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v0.10.2 repository checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPOSITORY_CHECKER = _load_repository_checker()


def _canonical_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _policy_payload() -> dict[str, object]:
    return {
        "policy_id": "ARMILAR_ECOICOP_V2_TRANSITION_AUDIT_V0102",
        "policy_version": "0.10.2",
        "constitution_path": "constitution/ARMILAR_RESEARCH_CORE_V1.json",
        "legacy_source_policy_path": "config/eurostat_vertical_v087.json",
        "legacy_dataset": "prc_hicp_midx",
        "replacement_dataset": "prc_hicp_minr",
        "legacy_classification": "ECOICOP_V1_PRE_2026",
        "replacement_classification": "ECOICOP_V2_FROM_2026",
        "legacy_end_period": "2025-12",
        "replacement_reference_base": "2025=100",
        "replacement_back_series_start_period": "1996-01",
        "replacement_back_series_end_period": "2025-12",
        "first_live_reference_period": "2026-01",
        "legacy_categories": LEGACY_CATEGORIES,
        "replacement_divisions": V2_DIVISIONS,
        "materially_revised_divisions": ["CP08", "CP09"],
        "split_legacy_division": "CP12",
        "new_division": "CP13",
        "direct_extension_allowed": False,
        "same_code_semantic_equivalence_assumed": False,
        "drop_new_division_allowed": False,
        "silent_category_expansion_allowed": False,
        "back_series_automatic_substitution_allowed": False,
        "required_next_decision": "EXPLICIT_CONSTITUTIONAL_TRANSITION_DECISION_AND_BACKTEST",
        "official_evidence": [
            {
                "evidence_id": "EUROSTAT_HICP_2026_QA",
                "url": "https://ec.europa.eu/eurostat/documents/example.pdf",
                "claim": "Classification transition and back series.",
            },
            {
                "evidence_id": "EUROSTAT_HICP_ESMS",
                "url": "https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm",
                "claim": "Metadata evidence.",
            },
            {
                "evidence_id": "EUROSTAT_HICP_DATABASE_INFORMATION",
                "url": "https://ec.europa.eu/eurostat/web/hicp/information-data",
                "claim": "Database transition evidence.",
            },
        ],
        "gates": {
            "classification_transition_ratified": False,
            "arm_o_2026_extension_allowed": False,
            "backtest_execution_claim_allowed": False,
            "research_release_allowed": False,
            "model_training_allowed": False,
            "arm_l_use_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
        },
    }


class EcoicopV2TransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="armilar-v0102-test-"))
        self.root = self.temp / "repo"
        self.root.mkdir()
        self.policy_path = self.root / "config/ecoicop_v2_transition_v0102.json"
        self.constitution_path = self.root / "constitution/ARMILAR_RESEARCH_CORE_V1.json"
        self.legacy_path = self.root / "config/eurostat_vertical_v087.json"
        self.output = self.temp / "audit"
        _canonical_json(self.policy_path, _policy_payload())
        _canonical_json(
            self.constitution_path,
            {
                "basket_categories": LEGACY_CATEGORIES,
                "constitution_status": "RATIFIED_FOR_ENGINE_DEVELOPMENT",
                "prohibitions": [
                    "SILENT_CATEGORY_EXPANSION",
                    "AUTOMATIC_WEIGHT_CHANGES",
                    "AUTOMATIC_GATE_ACTIVATION",
                ],
                "release_gates": {
                    "research_release_allowed": False,
                    "model_promotion_allowed": False,
                    "shadow_production_allowed": False,
                    "monetary_release_allowed": False,
                },
            },
        )
        _canonical_json(
            self.legacy_path,
            {
                "policy_version": "0.8.7",
                "dataset": "prc_hicp_midx",
                "classification_version": "ECOICOP_V1_PRE_2026",
                "end_period": "2025-12",
                "source_categories": LEGACY_CATEGORIES,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            },
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def mutate_policy(self, mutator) -> None:
        payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        mutator(payload)
        _canonical_json(self.policy_path, payload)

    def build(self, output: Path | None = None) -> dict[str, object]:
        return build_transition_audit(
            policy_path=self.policy_path,
            root=self.root,
            output_dir=output or self.output,
            created_at="2026-07-06T00:00:00Z",
        )

    def test_policy_loads_and_freezes_all_gates(self) -> None:
        policy = TransitionPolicy.load(self.policy_path)
        self.assertEqual(policy.policy_version, "0.10.2")
        self.assertTrue(all(value is False for value in policy.gates.values()))
        self.assertFalse(policy.back_series_automatic_substitution_allowed)

    def test_policy_rejects_extra_key(self) -> None:
        self.mutate_policy(lambda payload: payload.__setitem__("extra", True))
        with self.assertRaisesRegex(EcoicopTransitionError, "policy keys mismatch"):
            TransitionPolicy.load(self.policy_path)

    def test_policy_rejects_open_safety_field(self) -> None:
        self.mutate_policy(lambda payload: payload.__setitem__("direct_extension_allowed", True))
        with self.assertRaisesRegex(EcoicopTransitionError, "must remain false"):
            TransitionPolicy.load(self.policy_path)

    def test_policy_rejects_open_gate(self) -> None:
        def mutate(payload: dict[str, object]) -> None:
            gates = payload["gates"]
            assert isinstance(gates, dict)
            gates["research_release_allowed"] = True
        self.mutate_policy(mutate)
        with self.assertRaisesRegex(EcoicopTransitionError, "all v0.10.2 gates"):
            TransitionPolicy.load(self.policy_path)

    def test_policy_rejects_non_eurostat_evidence_url(self) -> None:
        def mutate(payload: dict[str, object]) -> None:
            evidence = payload["official_evidence"]
            assert isinstance(evidence, list)
            evidence[0]["url"] = "https://example.com/source"
        self.mutate_policy(mutate)
        with self.assertRaisesRegex(EcoicopTransitionError, "Eurostat HTTPS"):
            TransitionPolicy.load(self.policy_path)

    def test_policy_rejects_missing_required_evidence(self) -> None:
        def mutate(payload: dict[str, object]) -> None:
            evidence = payload["official_evidence"]
            assert isinstance(evidence, list)
            evidence[0]["evidence_id"] = "OTHER"
        self.mutate_policy(mutate)
        with self.assertRaisesRegex(EcoicopTransitionError, "required official evidence"):
            TransitionPolicy.load(self.policy_path)

    def test_policy_rejects_wrong_replacement_grid(self) -> None:
        self.mutate_policy(lambda payload: payload.__setitem__("replacement_divisions", V2_DIVISIONS[:-1]))
        with self.assertRaisesRegex(EcoicopTransitionError, "CP01-CP13"):
            TransitionPolicy.load(self.policy_path)

    def test_build_and_verify_audit(self) -> None:
        summary = self.build()
        verified = verify_transition_audit(
            self.output, policy_path=self.policy_path, root=self.root
        )
        self.assertEqual(summary, verified)
        self.assertEqual(summary["status"], STATUS)
        self.assertEqual(summary["replacement_division_count"], 13)

    def test_matrix_has_thirteen_rows_and_material_reclassifications(self) -> None:
        self.build()
        with (self.output / "ecoicop_v2_transition_matrix.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 13)
        by_code = {row["replacement_division"]: row for row in rows}
        self.assertEqual(by_code["CP08"]["transition_class"], "MATERIAL_RECLASSIFICATION")
        self.assertEqual(by_code["CP09"]["transition_class"], "MATERIAL_RECLASSIFICATION")
        self.assertTrue(all(row["automatic_use_allowed"] == "false" for row in rows))

    def test_cp12_cp13_relationship_is_explicit(self) -> None:
        self.build()
        with (self.output / "ecoicop_v2_transition_matrix.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = {row["replacement_division"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["CP12"]["transition_class"], "LEGACY_DIVISION_SPLIT")
        self.assertEqual(rows["CP13"]["transition_class"], "LEGACY_DIVISION_SPLIT_NEW_BRANCH")
        self.assertEqual(rows["CP13"]["legacy_division"], "CP12")

    def test_summary_records_back_series_without_authorising_substitution(self) -> None:
        summary = self.build()
        self.assertTrue(summary["replacement_back_series_available"])
        self.assertEqual(summary["replacement_back_series_start_period"], "1996-01")
        self.assertEqual(summary["replacement_back_series_end_period"], "2025-12")
        self.assertEqual(summary["first_live_reference_period"], "2026-01")
        self.assertFalse(summary["back_series_automatic_substitution_allowed"])

    def test_audit_is_byte_deterministic(self) -> None:
        first = self.temp / "first"
        second = self.temp / "second"
        self.build(first)
        self.build(second)
        first_files = {p.name: p.read_bytes() for p in first.iterdir()}
        second_files = {p.name: p.read_bytes() for p in second.iterdir()}
        self.assertEqual(first_files, second_files)

    def test_nonempty_output_is_rejected(self) -> None:
        self.output.mkdir()
        (self.output / "unexpected.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(EcoicopTransitionError, "OUTPUT_DIRECTORY_NOT_EMPTY"):
            self.build()

    def test_invalid_timestamp_is_rejected(self) -> None:
        with self.assertRaisesRegex(EcoicopTransitionError, "explicit UTC"):
            build_transition_audit(
                policy_path=self.policy_path,
                root=self.root,
                output_dir=self.output,
                created_at="2026-07-06",
            )

    def test_tampered_matrix_is_rejected(self) -> None:
        self.build()
        matrix = self.output / "ecoicop_v2_transition_matrix.csv"
        matrix.write_text(matrix.read_text(encoding="utf-8") + "x", encoding="utf-8")
        with self.assertRaisesRegex(EcoicopTransitionError, "manifest mismatch"):
            verify_transition_audit(self.output, policy_path=self.policy_path, root=self.root)

    def test_extra_output_file_is_rejected(self) -> None:
        self.build()
        (self.output / "extra.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(EcoicopTransitionError, "manifest file set mismatch"):
            verify_transition_audit(self.output, policy_path=self.policy_path, root=self.root)

    def test_changed_constitution_categories_are_rejected(self) -> None:
        constitution = json.loads(self.constitution_path.read_text(encoding="utf-8"))
        constitution["basket_categories"] = LEGACY_CATEGORIES + ["CP13"]
        _canonical_json(self.constitution_path, constitution)
        with self.assertRaisesRegex(EcoicopTransitionError, "basket categories changed"):
            self.build()

    def test_missing_constitution_prohibition_is_rejected(self) -> None:
        constitution = json.loads(self.constitution_path.read_text(encoding="utf-8"))
        constitution["prohibitions"].remove("SILENT_CATEGORY_EXPANSION")
        _canonical_json(self.constitution_path, constitution)
        with self.assertRaisesRegex(EcoicopTransitionError, "prohibitions are incomplete"):
            self.build()

    def test_open_constitution_gate_is_rejected(self) -> None:
        constitution = json.loads(self.constitution_path.read_text(encoding="utf-8"))
        constitution["release_gates"]["research_release_allowed"] = True
        _canonical_json(self.constitution_path, constitution)
        with self.assertRaisesRegex(EcoicopTransitionError, "release gates must remain closed"):
            self.build()

    def test_changed_legacy_dataset_is_rejected(self) -> None:
        legacy = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        legacy["dataset"] = "prc_hicp_minr"
        _canonical_json(self.legacy_path, legacy)
        with self.assertRaisesRegex(EcoicopTransitionError, "dataset mismatch"):
            self.build()

    def test_changed_legacy_end_period_is_rejected(self) -> None:
        legacy = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        legacy["end_period"] = "2026-01"
        _canonical_json(self.legacy_path, legacy)
        with self.assertRaisesRegex(EcoicopTransitionError, "end period mismatch"):
            self.build()

    def test_path_escape_is_rejected(self) -> None:
        self.mutate_policy(lambda payload: payload.__setitem__("constitution_path", "../outside.json"))
        policy = TransitionPolicy.load(self.policy_path)
        with self.assertRaisesRegex(EcoicopTransitionError, "path escapes root"):
            build_transition_audit(
                policy_path=self.policy_path,
                root=self.root,
                output_dir=self.output,
                created_at="2026-07-06T00:00:00Z",
            )
        self.assertEqual(policy.constitution_path, "../outside.json")

    def test_repository_checker_accepts_single_v0102_ci_gate(self) -> None:
        workflow = self.root / ".github/workflows/fetch-data.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            "name: test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Run unit tests\n"
            "        run: python -m pytest -q\n"
            "      - name: Validate v0.10.2 ECOICOP v2 transition and predecessor gate\n"
            "        run: python scripts/check_ecoicop_v2_transition_v0102.py --root .\n",
            encoding="utf-8",
            newline="\n",
        )
        REPOSITORY_CHECKER.verify_workflow(self.root)

    def test_repository_checker_rejects_direct_v0101_ci_gate(self) -> None:
        workflow = self.root / ".github/workflows/fetch-data.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            "name: test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Run unit tests\n"
            "        run: python -m pytest -q\n"
            "      - name: Validate v0.10.1 directly\n"
            "        run: python scripts/check_arm_o_materialization_bridge_v0101.py --root .\n"
            "      - name: Validate v0.10.2 ECOICOP v2 transition and predecessor gate\n"
            "        run: python scripts/check_ecoicop_v2_transition_v0102.py --root .\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(
            REPOSITORY_CHECKER.CheckError,
            "must not run the historical v0.10.1 checker directly",
        ):
            REPOSITORY_CHECKER.verify_workflow(self.root)

    def test_cli_validate_policy_returns_zero(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["validate-policy", "--policy", str(self.policy_path)])
        self.assertEqual(result, 0)
        self.assertIn("ECOICOP_V2_TRANSITION_POLICY_V0102_VALID", output.getvalue())

    def test_cli_returns_one_for_invalid_policy(self) -> None:
        self.mutate_policy(lambda payload: payload.__setitem__("direct_extension_allowed", True))
        error = io.StringIO()
        with redirect_stderr(error):
            result = main(["validate-policy", "--policy", str(self.policy_path)])
        self.assertEqual(result, 1)
        self.assertIn("must remain false", error.getvalue())


if __name__ == "__main__":
    unittest.main()
