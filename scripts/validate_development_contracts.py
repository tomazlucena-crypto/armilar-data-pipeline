from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "development_contracts.json"
CONTRACT_ID = re.compile(r"^V\d{3}-C\d{2}-[A-Z0-9-]+$")
MILESTONE = re.compile(r"^\d+\.\d+\.\d+$")
BASE_FIELDS = {
    "contract_id",
    "milestone",
    "status",
    "objective",
    "inputs",
    "outputs",
    "invariants",
    "failure_states",
    "success_condition",
    "stop_condition",
    "fallback_condition",
    "acceptance_tests",
    "out_of_scope",
}
LIST_FIELDS = {"inputs", "outputs", "invariants", "failure_states", "acceptance_tests", "out_of_scope"}
TEXT_FIELDS = {"objective", "success_condition", "stop_condition", "fallback_condition"}


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_payload(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["root must be an object"]

    if payload.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")

    reviewed_on = payload.get("reviewed_on")
    try:
        date.fromisoformat(reviewed_on)
    except (TypeError, ValueError):
        errors.append("reviewed_on must be an ISO date")

    statuses = payload.get("allowed_statuses")
    if not isinstance(statuses, list) or not statuses or not all(_non_empty_string(item) for item in statuses):
        errors.append("allowed_statuses must be a non-empty list of strings")
        statuses = []

    required_fields = payload.get("required_fields")
    expected_contract_fields = BASE_FIELDS - {"contract_id", "milestone", "status"}
    if not isinstance(required_fields, list) or set(required_fields) != expected_contract_fields:
        errors.append("required_fields must exactly match the ten contract-content fields")

    contracts = payload.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        errors.append("contracts must be a non-empty list")
        return errors

    seen: set[str] = set()
    for index, contract in enumerate(contracts):
        prefix = f"contracts[{index}]"
        if not isinstance(contract, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = BASE_FIELDS - set(contract)
        extra = set(contract) - BASE_FIELDS
        if missing:
            errors.append(f"{prefix} missing fields: {sorted(missing)}")
        if extra:
            errors.append(f"{prefix} has unexpected fields: {sorted(extra)}")

        contract_id = contract.get("contract_id")
        if not _non_empty_string(contract_id) or not CONTRACT_ID.fullmatch(contract_id):
            errors.append(f"{prefix}.contract_id has invalid format")
        elif contract_id in seen:
            errors.append(f"duplicate contract_id: {contract_id}")
        else:
            seen.add(contract_id)

        milestone = contract.get("milestone")
        if not _non_empty_string(milestone) or not MILESTONE.fullmatch(milestone):
            errors.append(f"{prefix}.milestone has invalid format")

        if contract.get("status") not in statuses:
            errors.append(f"{prefix}.status is not allowed")

        for field in TEXT_FIELDS:
            if not _non_empty_string(contract.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string")

        for field in LIST_FIELDS:
            value = contract.get(field)
            if not isinstance(value, list) or not value or not all(_non_empty_string(item) for item in value):
                errors.append(f"{prefix}.{field} must be a non-empty list of non-empty strings")

    return errors


def validate_file(path: Path = DEFAULT_PATH) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"contract file not found: {path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
    return validate_payload(payload)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]).resolve() if args else DEFAULT_PATH
    errors = validate_file(path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"Validated {len(payload['contracts'])} development contracts from {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
