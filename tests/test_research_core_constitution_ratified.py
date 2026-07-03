from __future__ import annotations

import ast
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.check_research_core_constitution import (
    CONSTITUTION_PATH,
    EXPECTED_APPROVAL_STATEMENT,
    EXPECTED_CONSTITUTION_HASH,
    EXPECTED_DECISIONS,
    EXPECTED_RECORD_HASH,
    MANIFEST_PATH,
    MANIFEST_PATHS,
    RATIFIED_STATUS,
    RECORD_PATH,
    RatifiedConstitutionError,
    canonical_text,
    digest,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


class RatifiedResearchCoreConstitutionTests(unittest.TestCase):
    def copy_fixture(self, destination: Path) -> None:
        for relative in (*MANIFEST_PATHS, MANIFEST_PATH):
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def load_json(self, root: Path, relative: Path) -> dict[str, object]:
        return json.loads((root / relative).read_text(encoding="utf-8"))

    def mutate_json(self, root: Path, relative: Path, mutator) -> None:
        payload = self.load_json(root, relative)
        mutator(payload)
        (root / relative).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def assert_mutation_fails(self, relative: Path, mutator) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            self.mutate_json(root, relative, mutator)
            with self.assertRaises(RatifiedConstitutionError):
                validate(root)

    def test_ratified_contract_passes(self) -> None:
        constitution = validate(ROOT)
        self.assertEqual(constitution["constitution_status"], RATIFIED_STATUS)
        self.assertEqual(constitution["constitution_version"], "1.0.0-research")
        self.assertEqual(constitution["pending_decisions"], [])
        self.assertEqual(tuple(item["id"] for item in constitution["ratified_decisions"]), EXPECTED_DECISIONS)
        self.assertTrue(all(item["status"] == RATIFIED_STATUS for item in constitution["ratified_decisions"]))
        self.assertFalse(any(constitution["release_gates"].values()))
        self.assertEqual(constitution["ratification"]["approval_statement"], EXPECTED_APPROVAL_STATEMENT)
        self.assertEqual(digest(ROOT / CONSTITUTION_PATH), EXPECTED_CONSTITUTION_HASH)
        self.assertEqual(digest(ROOT / RECORD_PATH), EXPECTED_RECORD_HASH)

    def test_gate_activation_fails(self) -> None:
        self.assert_mutation_fails(
            CONSTITUTION_PATH,
            lambda payload: payload["release_gates"].__setitem__("research_release_allowed", True),
        )

    def test_formula_change_fails(self) -> None:
        def mutate(payload):
            decision = next(item for item in payload["ratified_decisions"] if item["id"] == "official_formula")
            decision["executable_contract"]["index_type"] = "OTHER_FORMULA"
        self.assert_mutation_fails(CONSTITUTION_PATH, mutate)

    def test_economy_or_category_change_fails(self) -> None:
        self.assert_mutation_fails(CONSTITUTION_PATH, lambda payload: payload["economies"].append("AUT"))
        self.assert_mutation_fails(CONSTITUTION_PATH, lambda payload: payload["basket_categories"].append("CP13"))

    def test_proxy_limitation_or_ooh_requirement_removal_fails(self) -> None:
        def remove_proxy(payload):
            decision = next(item for item in payload["ratified_decisions"] if item["id"] == "hfce_hicp_conceptual_treatment")
            decision["executable_contract"].pop("weight_implementation_limitation")
        def remove_ooh(payload):
            decision = next(item for item in payload["ratified_decisions"] if item["id"] == "hfce_hicp_conceptual_treatment")
            decision["executable_contract"]["ooh_sensitivity_requirement"].pop("required_before_shadow_production")
        self.assert_mutation_fails(CONSTITUTION_PATH, remove_proxy)
        self.assert_mutation_fails(CONSTITUTION_PATH, remove_ooh)

    def test_arm_l_information_field_removal_fails(self) -> None:
        def mutate(payload):
            decision = next(item for item in payload["ratified_decisions"] if item["id"] == "exact_series_semantics")
            decision["executable_contract"]["ARM-L"]["information_set"].pop("retrieval_cutoff_required")
        self.assert_mutation_fails(CONSTITUTION_PATH, mutate)

    def test_ratification_record_tampering_fails(self) -> None:
        self.assert_mutation_fails(RECORD_PATH, lambda payload: payload.__setitem__("approval_statement", "altered"))

    def test_crlf_is_hash_portable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            path = root / CONSTITUTION_PATH
            text = canonical_text(path.read_bytes()).decode("utf-8")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            validate(root)

    def test_bom_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            path = root / RECORD_PATH
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            with self.assertRaises(RatifiedConstitutionError):
                validate(root)

    def test_checker_has_no_write_or_auto_approval_path(self) -> None:
        source = (ROOT / "scripts/check_research_core_constitution.py").read_text(encoding="utf-8")
        self.assertNotIn("--write-manifest", source)
        tree = ast.parse(source)
        prohibited = {"write_text", "write_bytes", "rename", "unlink", "mkdir", "makedirs"}
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertTrue(calls.isdisjoint(prohibited))


if __name__ == "__main__":
    unittest.main()
