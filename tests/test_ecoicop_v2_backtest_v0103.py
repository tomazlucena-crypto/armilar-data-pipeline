from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from armilar_backtest.ecoicop_v2_backtest_v0103 import (  # noqa: E402
    ALLOWED_MAPPING_STATES,
    EXPECTED_AUDIT_FILES,
    EXPECTED_METRICS,
    EXPECTED_REPLACEMENT_CODES,
    NEXT_MILESTONE,
    STATUS,
    ProtocolBundle,
    ProtocolError,
    build_protocol_audit,
    main,
    validate_mapping_document,
    validate_protocol_document,
    verify_protocol_audit,
)

POLICY = ROOT / "config" / "ecoicop_v2_backtest_protocol_v0103.json"
MAPPING = ROOT / "config" / "ecoicop_v1_v2_mapping_candidates_v0103.json"
CREATED_AT = "2026-07-07T00:00:00Z"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def valid_documents() -> tuple[dict, dict]:
    return read_json(POLICY), read_json(MAPPING)


def test_valid_bundle_loads() -> None:
    bundle = ProtocolBundle.load(POLICY, MAPPING)
    assert bundle.policy["status"] == STATUS
    assert len(bundle.mapping_rows) == 13


def test_mapping_state_machine_is_complete() -> None:
    mapping = read_json(MAPPING)
    assert set(mapping["allowed_states"]) == set(ALLOWED_MAPPING_STATES)
    assert set(mapping["state_semantics"]) == set(ALLOWED_MAPPING_STATES)


def test_mapping_covers_every_replacement_division_once() -> None:
    bundle = ProtocolBundle.load(POLICY, MAPPING)
    assert tuple(row.replacement_code for row in bundle.mapping_rows) == EXPECTED_REPLACEMENT_CODES


def test_no_mapping_is_automatic() -> None:
    bundle = ProtocolBundle.load(POLICY, MAPPING)
    assert not any(row.automatic_use_allowed for row in bundle.mapping_rows)


def test_material_reclassifications_are_explicit() -> None:
    bundle = ProtocolBundle.load(POLICY, MAPPING)
    by_code = {row.replacement_code: row for row in bundle.mapping_rows}
    assert {by_code[code].state for code in ("CP07", "CP08", "CP09")} == {
        "MATERIAL_RECLASSIFICATION"
    }


def test_cp12_and_cp13_remain_evidence_dependent_split() -> None:
    bundle = ProtocolBundle.load(POLICY, MAPPING)
    by_code = {row.replacement_code: row for row in bundle.mapping_rows}
    for code in ("CP12", "CP13"):
        assert by_code[code].state == "SPLIT_REQUIRES_EVIDENCE"
        assert by_code[code].legacy_codes == ("CP12",)


def test_strategy_register_is_exact_and_has_no_automatic_winner() -> None:
    policy = read_json(POLICY)
    assert [row["strategy_id"] for row in policy["strategies"]] == ["T0", "T1", "T2", "T3"]
    assert not any(row["automatic_selection_allowed"] for row in policy["strategies"])
    assert policy["decision_output_contract"]["automatic_winner_allowed"] is False


def test_metric_register_is_predeclared_and_complete() -> None:
    policy = read_json(POLICY)
    assert {row["metric_id"] for row in policy["metrics"]} == set(EXPECTED_METRICS)
    assert all(row["required_for_completion"] for row in policy["metrics"])


def test_all_release_training_and_monetary_gates_are_closed() -> None:
    policy = read_json(POLICY)
    assert not any(policy["gates"].values())
    constraints = policy["constitutional_constraints"]
    assert not any(value for key, value in constraints.items() if key != "constitution_path")


def test_v0103_scope_is_protocol_only() -> None:
    scope = read_json(POLICY)["scope"]
    assert scope["define_protocol_only"] is True
    assert sum(bool(value) for key, value in scope.items() if key != "define_protocol_only") == 0


def test_rejects_open_gate(tmp_path: Path) -> None:
    policy, mapping = valid_documents()
    policy["gates"]["classification_transition_ratified"] = True
    with pytest.raises(ProtocolError, match="must remain closed"):
        validate_protocol_document(policy, mapping)


def test_rejects_empirical_scope(tmp_path: Path) -> None:
    policy, mapping = valid_documents()
    policy["scope"]["execute_empirical_backtest"] = True
    with pytest.raises(ProtocolError, match="forbidden empirical"):
        validate_protocol_document(policy, mapping)


def test_rejects_automatic_mapping() -> None:
    _, mapping = valid_documents()
    mapping["rows"][0]["automatic_use_allowed"] = True
    with pytest.raises(ProtocolError, match="automatic mapping is forbidden"):
        validate_mapping_document(mapping)


def test_rejects_duplicate_replacement_code() -> None:
    _, mapping = valid_documents()
    mapping["rows"][1]["replacement_code"] = mapping["rows"][0]["replacement_code"]
    with pytest.raises(ProtocolError, match="duplicates"):
        validate_mapping_document(mapping)


def test_rejects_wrong_cp13_source() -> None:
    _, mapping = valid_documents()
    cp13 = next(row for row in mapping["rows"] if row["replacement_code"] == "CP13")
    cp13["legacy_codes"] = ["CP11"]
    with pytest.raises(ProtocolError, match="CP13 must be"):
        validate_mapping_document(mapping)


def test_rejects_missing_metric() -> None:
    policy, mapping = valid_documents()
    policy["metrics"].pop()
    with pytest.raises(ProtocolError, match="metric register differs"):
        validate_protocol_document(policy, mapping)


def test_rejects_wrong_official_dataset_code() -> None:
    policy, mapping = valid_documents()
    target = next(row for row in policy["dataset_contracts"] if row["role"] == "REPLACEMENT_ITEM_WEIGHTS")
    target["dataset_code"] = "invented_dataset"
    with pytest.raises(ProtocolError, match="dataset codes changed"):
        validate_protocol_document(policy, mapping)


def test_build_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_summary = build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=first,
        created_at=CREATED_AT,
    )
    second_summary = build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=second,
        created_at=CREATED_AT,
    )
    assert first_summary == second_summary
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_audit_file_set_and_row_counts(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=audit,
        created_at=CREATED_AT,
    )
    assert {path.name for path in audit.iterdir()} == set(EXPECTED_AUDIT_FILES) | {"MANIFEST.sha256"}
    with (audit / "mapping_matrix.csv").open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 13
    with (audit / "strategy_register.csv").open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 4


def test_summary_claims_zero_empirical_and_live_observations(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    summary = build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=audit,
        created_at=CREATED_AT,
    )
    assert summary["empirical_observation_count"] == 0
    assert summary["live_2026_observation_count"] == 0
    assert summary["backtest_execution_claim_allowed"] is False
    assert summary["arm_o_2026_extension_allowed"] is False
    assert summary["next_milestone"] == NEXT_MILESTONE


def test_verify_round_trip(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    built = build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=audit,
        created_at=CREATED_AT,
    )
    verified = verify_protocol_audit(audit, policy_path=POLICY, mapping_path=MAPPING)
    assert verified == built


def test_verify_rejects_tampered_output(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=audit,
        created_at=CREATED_AT,
    )
    with (audit / "metric_register.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    with pytest.raises(ProtocolError, match="hash mismatch"):
        verify_protocol_audit(audit, policy_path=POLICY, mapping_path=MAPPING)


def test_verify_rejects_extra_file(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    build_protocol_audit(
        policy_path=POLICY,
        mapping_path=MAPPING,
        output_dir=audit,
        created_at=CREATED_AT,
    )
    (audit / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ProtocolError, match="file set mismatch"):
        verify_protocol_audit(audit, policy_path=POLICY, mapping_path=MAPPING)


def test_build_rejects_implicit_or_non_utc_timestamp(tmp_path: Path) -> None:
    with pytest.raises(ProtocolError, match="explicit UTC"):
        build_protocol_audit(
            policy_path=POLICY,
            mapping_path=MAPPING,
            output_dir=tmp_path / "audit",
            created_at="2026-07-07",
        )


def test_cli_validate_policy(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "validate-policy",
            "--policy",
            str(POLICY),
            "--mapping",
            str(MAPPING),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert STATUS in captured.out
    assert '"empirical_observation_count": 0' in captured.out


def test_cli_rejects_bad_mapping(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mapping = read_json(MAPPING)
    mapping["global_rules"]["cp13_drop_allowed"] = True
    bad = tmp_path / "bad.json"
    write_json(bad, mapping)
    result = main(
        [
            "validate-policy",
            "--policy",
            str(POLICY),
            "--mapping",
            str(bad),
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "INVALID" in captured.out


def test_documents_remain_json_serialisable() -> None:
    policy, mapping = valid_documents()
    assert json.loads(json.dumps(copy.deepcopy(policy))) == policy
    assert json.loads(json.dumps(copy.deepcopy(mapping))) == mapping
