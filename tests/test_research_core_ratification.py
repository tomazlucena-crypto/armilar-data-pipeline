from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.check_research_core_ratification import (
    BASKET_RELATIVE_PATH,
    CONSTITUTION_RELATIVE_PATH,
    EXPECTED_CONSTITUTION_HASH,
    EXPECTED_DECISIONS,
    EXPECTED_PROXY_CATEGORIES,
    EXPECTED_PROXY_TOTAL,
    MANIFEST_PATHS,
    PROPOSAL_MANIFEST_RELATIVE_PATH,
    PROPOSAL_RELATIVE_PATH,
    PROPOSAL_SCHEMA_RELATIVE_PATH,
    PROXY_ANNEX_RELATIVE_PATH,
    PROXY_ANNEX_SCHEMA_RELATIVE_PATH,
    RatificationProposalError,
    canonical_text,
    check_manifest,
    derive_proxy_annex,
    digest,
    main as checker_main,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


class RatificationProposalTests(unittest.TestCase):
    def load_json(self, root: Path, relative: Path) -> dict[str, object]:
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def copy_fixture(self, destination: Path) -> None:
        required = set(MANIFEST_PATHS) | {
            PROPOSAL_MANIFEST_RELATIVE_PATH,
            CONSTITUTION_RELATIVE_PATH,
        }
        for relative in required:
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def mutate(self, root: Path, relative: Path, mutator) -> None:
        payload = self.load_json(root, relative)
        mutator(payload)
        (root / relative).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def decision(self, proposal: dict[str, object], decision_id: str) -> dict[str, object]:
        return next(item for item in proposal["decisions"] if item["id"] == decision_id)

    def test_proposal_is_complete_but_not_approved(self) -> None:
        proposal = validate(ROOT)
        self.assertEqual(proposal["proposal_version"], "0.2.0")
        self.assertEqual(proposal["proposal_status"], "PROPOSED")
        self.assertEqual(proposal["approval_status"], "NOT_APPROVED")
        self.assertTrue(proposal["required_human_approval"])
        self.assertEqual(tuple(item["id"] for item in proposal["decisions"]), EXPECTED_DECISIONS)
        self.assertTrue(all(item["status"] == "PROPOSED" for item in proposal["decisions"]))
        self.assertTrue(all(not value for value in proposal["ratification_effect"]["release_gates_unchanged"].values()))

    def test_target_constitution_is_unchanged_draft(self) -> None:
        path = ROOT / CONSTITUTION_RELATIVE_PATH
        self.assertEqual(digest(path), EXPECTED_CONSTITUTION_HASH)
        constitution = self.load_json(ROOT, CONSTITUTION_RELATIVE_PATH)
        self.assertEqual(constitution["constitution_status"], "DRAFT")
        self.assertEqual(len(constitution["pending_decisions"]), 7)
        self.assertTrue(all(item["status"] == "PENDING_RATIFICATION" for item in constitution["pending_decisions"]))
        self.assertFalse(any(constitution["release_gates"].values()))

    def test_proxy_annex_is_derived_from_real_basket(self) -> None:
        annex = self.load_json(ROOT, PROXY_ANNEX_RELATIVE_PATH)
        self.assertEqual(annex, derive_proxy_annex(ROOT))
        self.assertEqual(annex["cell_count"], 25)
        self.assertEqual(tuple(annex["categories"]), EXPECTED_PROXY_CATEGORIES)
        self.assertEqual(annex["fixed_universe_weight_total"], EXPECTED_PROXY_TOTAL)
        self.assertEqual(len(annex["cells"]), 25)

    def test_ppp_weight_and_fixed_scope_contract(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        formula = self.decision(proposal, "official_formula")["executable_contract"]
        self.assertEqual(formula["index_type"], "PPP_ADJUSTED_FIXED_WEIGHT_ARITHMETIC_LASPEYRES_TYPE")
        self.assertEqual(formula["weight_definition"]["target_concept"], "HFCE_2021_REAL_EXPENDITURE_PPP_ADJUSTED")
        self.assertEqual(formula["weight_definition"]["proxy_exception"], "AIC_PPP_PROXY_IDENTIFIED_PER_CELL")
        self.assertTrue(formula["basket_scope"]["economies_and_categories_fixed_within_basket_version"])
        self.assertTrue(formula["basket_scope"]["new_economy_or_category_requires_new_basket_version"])
        self.assertEqual(formula["proxy_exposure"]["fixed_universe_weight_total"], EXPECTED_PROXY_TOTAL)

    def test_arm_l_information_set_is_reproducible(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        arm_l = self.decision(proposal, "exact_series_semantics")["executable_contract"]["ARM-L"]
        info = arm_l["information_set"]
        self.assertEqual(info["eligibility_rule"], "PUBLISHED_AT_LTE_INFORMATION_CUTOFF_AND_RETRIEVED_AT_LTE_RETRIEVAL_CUTOFF")
        self.assertEqual(info["late_arrival_policy"], "NEXT_RELEASE_ONLY")
        self.assertEqual(info["source_precedence"], "CELL_SPECIFIC_VERSIONED_SOURCE_REGISTRY")
        self.assertTrue(info["same_information_set_same_model_same_basket_same_output"])
        self.assertTrue(info["uncertainty_bounds_required"])
        self.assertFalse(arm_l["retroactive_revision_to_match_arm_o_allowed"])
        self.assertTrue(arm_l["schedule_policy"]["versioned_release_schedule_contract_required"])
        self.assertFalse(arm_l["schedule_policy"]["constitutional_clock_time_fixed"])

    def test_ooh_sensitivity_is_required_and_bounded(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        treatment = self.decision(proposal, "hfce_hicp_conceptual_treatment")["executable_contract"]
        ooh = treatment["ooh_sensitivity_requirement"]
        self.assertTrue(ooh["required_before_external_research_release"])
        self.assertTrue(ooh["required_before_shadow_production"])
        self.assertTrue(ooh["does_not_measure_complete_hfce_hicp_gap"])
        self.assertTrue(ooh["may_not_be_presented_as_imputed_rent_equivalence"])
        hfce = self.decision(proposal, "hfce_hicp_conceptual_treatment")["executable_contract"]
        self.assertTrue(hfce["oohpi_vs_hfce_distinction_required"])
        self.assertTrue(hfce["hfce_income_imputed_rent_distinction_required"])
        self.assertEqual(treatment["proxy_exposure_weight_total"], EXPECTED_PROXY_TOTAL)

    def test_patch_classes_cover_proxy_to_exact_transition(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        amendment = self.decision(proposal, "constitutional_amendment_process")["executable_contract"]
        self.assertEqual(
            set(amendment["change_classes"]),
            {
                "EDITORIAL_PATCH",
                "EVIDENCE_METADATA_PATCH",
                "NUMERICAL_WEIGHT_PATCH",
                "BASKET_SCOPE_CHANGE",
                "CONSTITUTIONAL_METHOD_CHANGE",
            },
        )
        transition = amendment["proxy_to_exact_transition"]
        self.assertEqual(transition["same_numeric_weight"], "EVIDENCE_METADATA_PATCH")
        self.assertEqual(transition["changed_numeric_weight_same_scope"], "NUMERICAL_WEIGHT_PATCH")
        self.assertEqual(transition["new_economy_or_category"], "BASKET_SCOPE_CHANGE")
        self.assertFalse(transition["silent_upgrade_allowed"])
        self.assertFalse(transition["silent_proxy_to_exact_promotion_allowed"])
        self.assertTrue(amendment["change_classes"]["BASKET_SCOPE_CHANGE"]["economies_and_categories_fixed_within_basket_version"])

    def test_schemas_are_closed_over_exact_payloads(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        proposal_schema = self.load_json(ROOT, PROPOSAL_SCHEMA_RELATIVE_PATH)
        annex = self.load_json(ROOT, PROXY_ANNEX_RELATIVE_PATH)
        annex_schema = self.load_json(ROOT, PROXY_ANNEX_SCHEMA_RELATIVE_PATH)
        self.assertEqual(proposal_schema["const"], proposal)
        self.assertEqual(annex_schema["const"], annex)

    def test_manifest_and_checker(self) -> None:
        check_manifest(ROOT)
        self.assertEqual(checker_main(["--root", str(ROOT)]), 0)

    def test_line_endings_are_canonical_for_manifest(self) -> None:
        self.assertEqual(canonical_text(b"alpha\nbeta\n"), canonical_text(b"alpha\r\nbeta\r\n"))
        self.assertEqual(canonical_text(b"alpha\nbeta\n"), canonical_text(b"alpha\rbeta\r"))
        with self.assertRaises(RatificationProposalError):
            canonical_text(b"\xef\xbb\xbfalpha\n")

    def test_fail_closed_mutations(self) -> None:
        mutations = {
            "self_approved": (PROPOSAL_RELATIVE_PATH, lambda p: p.__setitem__("approval_status", "APPROVED")),
            "decision_removed": (PROPOSAL_RELATIVE_PATH, lambda p: p["decisions"].pop()),
            "ppp_concept_changed": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "official_formula")["executable_contract"]["weight_definition"].__setitem__("target_concept", "NOMINAL_CURRENT_EXPENDITURE"),
            ),
            "scope_expansion_allowed": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "official_formula")["executable_contract"]["basket_scope"].__setitem__("new_economy_or_category_requires_new_basket_version", False),
            ),
            "arm_l_cutoff_removed": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "exact_series_semantics")["executable_contract"]["ARM-L"]["information_set"].__setitem__("information_cutoff_required", False),
            ),
            "arm_l_rewrite_allowed": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "exact_series_semantics")["executable_contract"]["ARM-L"].__setitem__("retroactive_revision_to_match_arm_o_allowed", True),
            ),
            "ooh_shadow_gate_removed": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "hfce_hicp_conceptual_treatment")["executable_contract"]["ooh_sensitivity_requirement"].__setitem__("required_before_shadow_production", False),
            ),
            "silent_proxy_upgrade": (
                PROPOSAL_RELATIVE_PATH,
                lambda p: self.decision(p, "constitutional_amendment_process")["executable_contract"]["proxy_to_exact_transition"].__setitem__("silent_upgrade_allowed", True),
            ),
            "annex_total_changed": (
                PROXY_ANNEX_RELATIVE_PATH,
                lambda p: p.__setitem__("fixed_universe_weight_total", "0.5"),
            ),
            "canonical_gate_enabled": (
                CONSTITUTION_RELATIVE_PATH,
                lambda p: p["release_gates"].__setitem__("research_release_allowed", True),
            ),
        }
        for name, (relative, mutator) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.copy_fixture(root)
                self.mutate(root, relative, mutator)
                with self.assertRaises(RatificationProposalError):
                    validate(root)


    def test_proxy_annex_missing_or_modified_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_fixture(root)
            (root / PROXY_ANNEX_RELATIVE_PATH).unlink()
            with self.assertRaises(RatificationProposalError):
                validate(root)

    def test_manifest_must_include_proxy_annex(self) -> None:
        lines = (ROOT / PROPOSAL_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8").splitlines()
        self.assertIn(PROXY_ANNEX_RELATIVE_PATH.as_posix(), {line.split(" ", 1)[1] for line in lines})

    def test_manifest_detects_visible_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_fixture(root)
            target = root / MANIFEST_PATHS[0]
            target.write_text(target.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8", newline="\n")
            with self.assertRaises(RatificationProposalError):
                check_manifest(root)


if __name__ == "__main__":
    unittest.main()
