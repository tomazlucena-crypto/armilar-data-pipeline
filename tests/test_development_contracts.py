from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_development_contracts.py"
SPEC = importlib.util.spec_from_file_location("validate_development_contracts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DevelopmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / "config" / "development_contracts.json"
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))

    def test_committed_contract_registry_is_valid(self) -> None:
        self.assertEqual(MODULE.validate_payload(self.payload), [])

    def test_contract_ids_are_unique(self) -> None:
        ids = [item["contract_id"] for item in self.payload["contracts"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_immediate_milestone_is_split_into_bounded_contracts(self) -> None:
        v086 = [item for item in self.payload["contracts"] if item["milestone"] == "0.8.6"]
        self.assertEqual(
            {item["contract_id"] for item in v086},
            {
                "V086-C01-CONTRACTS-AND-ROADMAP",
                "V086-C02-VERSION-SOURCE-OF-TRUTH",
                "V086-C03-SDMX-CLIENT-SPIKE",
                "V086-C04-PROPERTY-TESTS",
                "V086-C05-DEVELOPMENT-TELEMETRY",
            },
        )
        self.assertTrue(all(item["stop_condition"] for item in v086))
        self.assertTrue(all(item["out_of_scope"] for item in v086))

    def test_release_gates_are_not_weakened(self) -> None:
        first = next(item for item in self.payload["contracts"] if item["contract_id"] == "V086-C01-CONTRACTS-AND-ROADMAP")
        combined = " ".join(first["invariants"])
        self.assertIn("research_release_allowed remains false", combined)
        self.assertIn("monetary_release_allowed remains false", combined)

    def test_validator_rejects_duplicate_ids(self) -> None:
        broken = json.loads(json.dumps(self.payload))
        broken["contracts"].append(json.loads(json.dumps(broken["contracts"][0])))
        errors = MODULE.validate_payload(broken)
        self.assertTrue(any("duplicate contract_id" in error for error in errors))

    def test_validator_rejects_missing_stop_condition(self) -> None:
        broken = json.loads(json.dumps(self.payload))
        del broken["contracts"][0]["stop_condition"]
        errors = MODULE.validate_payload(broken)
        self.assertTrue(any("missing fields" in error and "stop_condition" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
