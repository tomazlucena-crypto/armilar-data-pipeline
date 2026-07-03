from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.check_research_core_ratification import (
    CONSTITUTION_RELATIVE_PATH,
    EXPECTED_CONSTITUTION_HASH,
    EXPECTED_DECISIONS,
    MANIFEST_PATHS,
    PROPOSAL_MANIFEST_RELATIVE_PATH,
    PROPOSAL_RELATIVE_PATH,
    PROPOSAL_SCHEMA_RELATIVE_PATH,
    RatificationProposalError,
    canonical_text,
    check_manifest,
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

    def test_proposal_is_complete_but_not_approved(self) -> None:
        proposal = validate(ROOT)
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

    def test_schema_is_closed_over_exact_proposal(self) -> None:
        proposal = self.load_json(ROOT, PROPOSAL_RELATIVE_PATH)
        schema = self.load_json(ROOT, PROPOSAL_SCHEMA_RELATIVE_PATH)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["const"], proposal)

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
            "ratified_status": (PROPOSAL_RELATIVE_PATH, lambda p: p.__setitem__("proposal_status", "RATIFIED")),
            "decision_removed": (PROPOSAL_RELATIVE_PATH, lambda p: p["decisions"].pop()),
            "decision_ratified": (PROPOSAL_RELATIVE_PATH, lambda p: p["decisions"][0].__setitem__("status", "RATIFIED")),
            "gate_enabled": (PROPOSAL_RELATIVE_PATH, lambda p: p["ratification_effect"]["release_gates_unchanged"].__setitem__("research_release_allowed", True)),
            "canonical_gate_enabled": (CONSTITUTION_RELATIVE_PATH, lambda p: p["release_gates"].__setitem__("research_release_allowed", True)),
            "canonical_ratified": (CONSTITUTION_RELATIVE_PATH, lambda p: p.__setitem__("constitution_status", "RATIFIED_FOR_ENGINE_DEVELOPMENT")),
            "pending_removed": (CONSTITUTION_RELATIVE_PATH, lambda p: p["pending_decisions"].pop()),
        }
        for name, (relative, mutator) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.copy_fixture(root)
                self.mutate(root, relative, mutator)
                with self.assertRaises(RatificationProposalError):
                    validate(root)

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
