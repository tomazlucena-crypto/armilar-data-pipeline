from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from scripts.materialize_research_core_basket import (
    BASKET_COLUMNS,
    BASKET_RELATIVE_PATH,
    BASKET_SCHEMA_RELATIVE_PATH,
    CONFIG_RELATIVE_PATH,
    CONSTITUTION_MD_RELATIVE_PATH,
    CONSTITUTION_RELATIVE_PATH,
    CONSTITUTION_SCHEMA_RELATIVE_PATH,
    ContractError,
    DECISION_RELATIVE_PATH,
    DECISION_V1_RELATIVE_PATH,
    EXPECTED_EVIDENCE_COUNTS,
    MANIFEST_PATHS,
    MANIFEST_RELATIVE_PATH,
    NORMALIZATION_RULE,
    REPAIR_DECISION_RELATIVE_PATH,
    SCRIPT_RELATIVE_PATH,
    SCOPE_RELATIVE_PATH,
    SOURCE_GLOBAL_SUM,
    SOURCE_RELATIVE_PATH,
    SOURCE_ROW_COUNT,
    SNAPSHOT_CANONICAL_SHA256,
    SOURCE_SNAPSHOT_HASH_POLICY,
    UPSTREAM_RAW_SHA256,
    TARGET_CATEGORIES,
    TARGET_ECONOMIES,
    TARGET_NORMALIZED_SUM,
    TARGET_RAW_SUM,
    build_basket_rows,
    canonicalize_utf8_text,
    classify_evidence,
    main as materialize_main,
    manifest_digest,
    read_source,
    render_basket_csv,
    select_source_rows,
    validate_static_contracts,
)

ROOT = Path(__file__).resolve().parents[1]


class ResearchCoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_path = ROOT / SOURCE_RELATIVE_PATH
        self.legacy_source_path = ROOT / Path("public/latest/weights_observed_universe.csv")
        self.basket_path = ROOT / BASKET_RELATIVE_PATH
        self.manifest_path = ROOT / MANIFEST_RELATIVE_PATH
        self.constitution_path = ROOT / CONSTITUTION_RELATIVE_PATH
        self.constitution_schema_path = ROOT / CONSTITUTION_SCHEMA_RELATIVE_PATH
        self.basket_schema_path = ROOT / BASKET_SCHEMA_RELATIVE_PATH

    def load_constitution(self, root: Path = ROOT) -> dict[str, object]:
        return json.loads((root / CONSTITUTION_RELATIVE_PATH).read_text(encoding="utf-8"))

    def load_basket(self, root: Path = ROOT) -> list[dict[str, str]]:
        with (root / BASKET_RELATIVE_PATH).open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def copy_contract_repo(self, destination: Path) -> None:
        for relative_path in MANIFEST_PATHS:
            if relative_path in {BASKET_RELATIVE_PATH}:
                continue
            source = ROOT / relative_path
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for relative_path in (CONSTITUTION_RELATIVE_PATH, CONSTITUTION_SCHEMA_RELATIVE_PATH, BASKET_SCHEMA_RELATIVE_PATH, CONFIG_RELATIVE_PATH):
            source = ROOT / relative_path
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)

    def mutate_constitution(self, root: Path, mutator) -> None:
        payload = self.load_constitution(root)
        mutator(payload)
        (root / CONSTITUTION_RELATIVE_PATH).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_source_contract(self) -> None:
        self.assertEqual(manifest_digest(self.source_path, SOURCE_RELATIVE_PATH), SNAPSHOT_CANONICAL_SHA256)
        rows = read_source(self.source_path)
        self.assertEqual(len(rows), SOURCE_ROW_COUNT)
        self.assertEqual(sum((Decimal(row["weight"]) for row in rows), Decimal("0")), SOURCE_GLOBAL_SUM)

    def test_selected_grid_and_sums(self) -> None:
        selected = select_source_rows(read_source(self.source_path))
        self.assertEqual(len(selected), 60)
        self.assertEqual({row["economy_code"] for row in selected}, set(TARGET_ECONOMIES))
        self.assertEqual({row["armilar_category"] for row in selected}, set(TARGET_CATEGORIES))
        self.assertEqual(sum((Decimal(row["weight"]) for row in selected), Decimal("0")), TARGET_RAW_SUM)
        built = build_basket_rows(selected)
        self.assertEqual(sum((Decimal(row.fixed_universe_weight) for row in built), Decimal("0")), TARGET_NORMALIZED_SUM)
        self.assertEqual(Counter(row.evidence_class for row in built), Counter(EXPECTED_EVIDENCE_COUNTS))

    def test_basket_contract_and_provenance(self) -> None:
        rows = self.load_basket()
        self.assertEqual(len(rows), 60)
        self.assertEqual(tuple(rows[0].keys()), BASKET_COLUMNS)
        self.assertEqual(
            [(row["economy_code"], row["category_code"]) for row in rows],
            [(economy, category) for economy in TARGET_ECONOMIES for category in TARGET_CATEGORIES],
        )
        self.assertNotIn("CP00", {row["category_code"] for row in rows})
        self.assertEqual(len({(row["economy_code"], row["category_code"]) for row in rows}), 60)
        self.assertEqual(sum((Decimal(row["raw_world_weight"]) for row in rows), Decimal("0")), TARGET_RAW_SUM)
        self.assertEqual(
            sum((Decimal(row["fixed_universe_weight"]) for row in rows), Decimal("0")),
            TARGET_NORMALIZED_SUM,
        )
        self.assertEqual(Counter(row["evidence_class"] for row in rows), Counter(EXPECTED_EVIDENCE_COUNTS))
        for row in rows:
            with self.subTest(cell=f"{row['economy_code']}/{row['category_code']}"):
                self.assertEqual(row["research_core_id"], "ARMILAR_RESEARCH_CORE_V1")
                self.assertEqual(row["basket_version"], "0.3.0-draft")
                self.assertEqual(row["normalization_rule"], NORMALIZATION_RULE)
                self.assertEqual(row["status"], "RESEARCH_ONLY")
                self.assertTrue(row["numerator_source_id"])
                self.assertTrue(row["numerator_source_file"])
                self.assertTrue(row["numerator_source_hash"])
                self.assertTrue(row["ppp_source_heading"])
                self.assertTrue(row["ppp_scope"])
                self.assertTrue(row["derivation"])
                self.assertTrue(row["quality_flags"])
                self.assertEqual(row["rounding_residual_applied"], "0")
                self.assertEqual(
                    row["evidence_class"],
                    classify_evidence(
                        {
                            "ppp_scope": row["ppp_scope"],
                            "derivation": row["derivation"],
                            "economy_code": row["economy_code"],
                            "armilar_category": row["category_code"],
                        }
                    ),
                )

    def test_constitution_contract(self) -> None:
        validate_static_contracts(ROOT)
        constitution = self.load_constitution()
        self.assertEqual(constitution["constitution_status"], "RATIFIED_FOR_ENGINE_DEVELOPMENT")
        self.assertEqual(constitution["constitution_version"], "1.0.0-research")
        self.assertEqual(constitution["schema_version"], "1.3")
        self.assertEqual(constitution["economies"], list(TARGET_ECONOMIES))
        self.assertEqual(constitution["basket_categories"], list(TARGET_CATEGORIES))
        self.assertEqual(constitution["benchmark_categories"], ["CP00"])
        self.assertEqual(set(constitution["series"]), {"ARM-O", "ARM-L", "ARM-R", "ARM-H"})
        self.assertTrue(all(not series["may_replace_other_series"] for series in constitution["series"].values()))
        self.assertFalse(any(constitution["release_gates"].values()))
        self.assertEqual(constitution["pending_decisions"], [])
        self.assertEqual(len(constitution["ratified_decisions"]), 7)
        self.assertTrue(all(item["status"] == "RATIFIED_FOR_ENGINE_DEVELOPMENT" for item in constitution["ratified_decisions"]))
        self.assertTrue(all(item["status"] == "RATIFIED_FOR_ENGINE_DEVELOPMENT" for item in constitution["series"].values()))
        self.assertTrue(all("provisional_semantics" not in item for item in constitution["series"].values()))
        semantics = next(item["executable_contract"] for item in constitution["ratified_decisions"] if item["id"] == "exact_series_semantics")
        self.assertTrue(all(constitution["series"][series_id]["semantics"] == semantics[series_id] for series_id in constitution["series"]))
        self.assertFalse(constitution["currency_policy"]["current_fx_in_ARM_O"])
        self.assertFalse(constitution["currency_policy"]["current_fx_in_ARM_L"])
        materialization = constitution["basket_materialization"]
        self.assertEqual(materialization["evidence_class_counts"], EXPECTED_EVIDENCE_COUNTS)
        self.assertEqual(materialization["upstream_raw_sha256"], UPSTREAM_RAW_SHA256)
        self.assertEqual(materialization["constitutional_snapshot_sha256"], SNAPSHOT_CANONICAL_SHA256)
        self.assertEqual(materialization["constitutional_snapshot_hash_policy"], SOURCE_SNAPSHOT_HASH_POLICY)
        self.assertTrue(materialization["upstream_raw_hash_is_provenance_metadata"])
        self.assertTrue(materialization["constitutional_snapshot_hash_is_enforced"])
        for relative_path in constitution["source_documents"]:
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_schema_coherence(self) -> None:
        constitution = self.load_constitution()
        constitution_schema = json.loads(self.constitution_schema_path.read_text(encoding="utf-8"))
        basket_schema = json.loads(self.basket_schema_path.read_text(encoding="utf-8"))
        self.assertEqual(constitution_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(constitution_schema["additionalProperties"])
        self.assertEqual(set(constitution_schema["required"]), set(constitution))
        for key, value in constitution.items():
            self.assertEqual(constitution_schema["properties"][key]["const"], value)
        self.assertEqual(basket_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(basket_schema["additionalProperties"])
        self.assertEqual(tuple(basket_schema["required"]), BASKET_COLUMNS)
        self.assertEqual(set(basket_schema["properties"]), set(BASKET_COLUMNS))
        self.assertNotIn("CP00", basket_schema["properties"]["category_code"]["enum"])

    def test_manifest_contract(self) -> None:
        lines = self.manifest_path.read_text(encoding="utf-8").splitlines()
        expected_paths = [path.as_posix() for path in MANIFEST_PATHS]
        self.assertEqual([line.split("  ", 1)[1] for line in lines], expected_paths)
        self.assertIn(SOURCE_RELATIVE_PATH.as_posix(), expected_paths)
        self.assertNotIn("public/latest/weights_observed_universe.csv", expected_paths)
        self.assertNotIn(MANIFEST_RELATIVE_PATH.as_posix(), expected_paths)
        self.assertEqual(manifest_digest(self.source_path, SOURCE_RELATIVE_PATH), SNAPSHOT_CANONICAL_SHA256)
        for line in lines:
            digest, relative_path = line.split("  ", 1)
            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, manifest_digest(ROOT / relative_path, Path(relative_path)))

    def test_manifest_text_hash_is_line_ending_independent(self) -> None:
        lf = b"alpha\nbeta\n"
        crlf = b"alpha\r\nbeta\r\n"
        cr = b"alpha\rbeta\r"
        self.assertEqual(canonicalize_utf8_text(lf), b"alpha\nbeta\n")
        self.assertEqual(canonicalize_utf8_text(lf), canonicalize_utf8_text(crlf))
        self.assertEqual(canonicalize_utf8_text(lf), canonicalize_utf8_text(cr))
        self.assertEqual(
            hashlib.sha256(canonicalize_utf8_text(lf)).hexdigest(),
            hashlib.sha256(canonicalize_utf8_text(crlf)).hexdigest(),
        )

    def test_manifest_text_hash_rejects_bom_and_detects_visible_changes(self) -> None:
        with self.assertRaises(ContractError):
            canonicalize_utf8_text(b"\xef\xbb\xbfalpha\n")
        original = hashlib.sha256(canonicalize_utf8_text(b"alpha\nbeta\n")).hexdigest()
        changed = hashlib.sha256(canonicalize_utf8_text(b"alpha\ngamma\n")).hexdigest()
        self.assertNotEqual(original, changed)

    def test_source_snapshot_is_immutable_and_canonical(self) -> None:
        self.assertTrue(self.source_path.is_file())
        self.assertEqual(manifest_digest(self.source_path, SOURCE_RELATIVE_PATH), SNAPSHOT_CANONICAL_SHA256)
        with self.source_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), SOURCE_ROW_COUNT)
        self.assertEqual(sum((Decimal(row["weight"]) for row in rows), Decimal("0")), SOURCE_GLOBAL_SUM)

    def test_materializer_check_mode(self) -> None:
        self.assertEqual(materialize_main(["--root", str(ROOT), "--check"]), 0)

    def test_source_order_does_not_change_basket(self) -> None:
        rows = read_source(self.source_path)
        forward = render_basket_csv(build_basket_rows(select_source_rows(rows)))
        reverse = render_basket_csv(build_basket_rows(select_source_rows(reversed(rows))))
        self.assertEqual(forward, reverse)
        self.assertEqual(canonicalize_utf8_text(forward), canonicalize_utf8_text(self.basket_path.read_bytes()))

    def test_public_latest_mutation_does_not_change_basket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_contract_repo(root)
            public_latest = root / "public/latest/weights_observed_universe.csv"
            public_latest.parent.mkdir(parents=True, exist_ok=True)
            public_latest.write_text("tampered\n", encoding="utf-8", newline="\n")
            self.assertEqual(materialize_main(["--root", str(root)]), 0)
            self.assertEqual((root / BASKET_RELATIVE_PATH).read_bytes(), self.basket_path.read_bytes())

    def test_snapshot_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_contract_repo(root)
            snapshot = root / SOURCE_RELATIVE_PATH
            snapshot.write_text(snapshot.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8", newline="\n")
            with self.assertRaises(ContractError):
                materialize_main(["--root", str(root)])

    def test_snapshot_removal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_contract_repo(root)
            (root / SOURCE_RELATIVE_PATH).unlink()
            with self.assertRaises(ContractError):
                materialize_main(["--root", str(root)])

    def test_selected_source_mutations_fail(self) -> None:
        selected = select_source_rows(read_source(self.source_path))
        cases = {}
        cases["missing"] = selected[:-1]
        cases["duplicate"] = selected + [deepcopy(selected[0])]
        altered = deepcopy(selected)
        altered[0]["weight"] = str(Decimal(altered[0]["weight"]) + Decimal("0.000000000000000000000001"))
        cases["altered_weight"] = altered
        unsupported = deepcopy(selected)
        unsupported[0]["ppp_scope"] = "UNKNOWN_SCOPE"
        cases["unsupported_evidence"] = unsupported
        for name, rows in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ContractError):
                    if name in {"missing", "duplicate", "altered_weight"}:
                        chosen = select_source_rows(rows)
                    else:
                        chosen = rows
                    build_basket_rows(chosen)

    def test_fail_closed_constitution_mutations(self) -> None:
        mutations = {
            "gate_true": lambda payload: payload["release_gates"].__setitem__("research_release_allowed", True),
            "sixth_economy": lambda payload: payload["economies"].append("AUT"),
            "cp13": lambda payload: payload["basket_categories"].append("CP13"),
            "cp00_weighted": lambda payload: payload["basket_categories"].append("CP00"),
            "ratified_decision_removed": lambda payload: payload["ratified_decisions"].pop(),
            "ratified_decision_status_changed": lambda payload: payload["ratified_decisions"][0].__setitem__("status", "PROPOSED"),
            "cell_count": lambda payload: payload["basket_materialization"].__setitem__("expected_cell_count", 59),
            "basket_state": lambda payload: payload["basket_materialization"].__setitem__("status", "RATIFIED"),
            "synthetic_allowed": lambda payload: payload["basket_materialization"].__setitem__("synthetic_test_weights_allowed", True),
            "renormalization_allowed": lambda payload: payload["basket_materialization"].__setitem__("silent_renormalization_allowed", True),
            "upstream_hash_changed": lambda payload: payload["basket_materialization"].__setitem__("upstream_raw_sha256", "0" * 64),
            "snapshot_hash_changed": lambda payload: payload["basket_materialization"].__setitem__("constitutional_snapshot_sha256", "0" * 64),
            "snapshot_policy_changed": lambda payload: payload["basket_materialization"].__setitem__("constitutional_snapshot_hash_policy", "UTF8_WITHOUT_BOM_CRLF"),
            "snapshot_enforcement_disabled": lambda payload: payload["basket_materialization"].__setitem__("constitutional_snapshot_hash_is_enforced", False),
            "constitution_reverted_to_draft": lambda payload: payload.__setitem__("constitution_status", "DRAFT"),
        }
        for name, mutator in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                self.copy_contract_repo(root)
                self.mutate_constitution(root, mutator)
                with self.assertRaises(ContractError):
                    validate_static_contracts(root)

    def test_materializer_writes_atomically_in_clean_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_contract_repo(root)
            self.assertEqual(materialize_main(["--root", str(root)]), 0)
            self.assertEqual(materialize_main(["--root", str(root), "--check"]), 0)
            self.assertEqual(
                canonicalize_utf8_text((root / BASKET_RELATIVE_PATH).read_bytes()),
                canonicalize_utf8_text(self.basket_path.read_bytes()),
            )
            temporary_files = list(root.rglob("*.tmp"))
            self.assertEqual(temporary_files, [])

    def test_check_detects_basket_and_manifest_tampering(self) -> None:
        for relative_path in (BASKET_RELATIVE_PATH, MANIFEST_RELATIVE_PATH):
            with self.subTest(path=relative_path.as_posix()), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                self.copy_contract_repo(root)
                materialize_main(["--root", str(root)])
                path = root / relative_path
                path.write_bytes(path.read_bytes() + b"tamper\n")
                with self.assertRaises(ContractError):
                    materialize_main(["--root", str(root), "--check"])


if __name__ == "__main__":
    unittest.main()
