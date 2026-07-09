from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from armilar_backtest.ecoicop_dual_panel_v0104 import (  # noqa: E402
    EXPECTED_DATASET_ROLES,
    EXPECTED_ECONOMIES,
    EXPECTED_LEGACY_CATEGORIES,
    EXPECTED_REPLACEMENT_DIVISIONS,
    NEXT_MILESTONE,
    STATUS,
    VERSION,
    DualPanelError,
    DualPanelPolicy,
    acquisition_requests,
    build_dual_panel_scaffold,
    main,
    validate_policy_document,
    verify_dual_panel_scaffold,
)

POLICY = ROOT / "config" / "ecoicop_dual_panel_v0104.json"
CREATED_AT = "2026-07-09T00:00:00Z"


def read_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_policy_loads_and_has_expected_status() -> None:
    policy = DualPanelPolicy.load(POLICY)
    assert policy.payload["policy_version"] == VERSION
    assert policy.payload["status"] == STATUS
    assert policy.payload["next_milestone"] == NEXT_MILESTONE


def test_policy_reuses_the_v087_five_economy_universe() -> None:
    policy = DualPanelPolicy.load(POLICY)
    assert tuple(item["eurostat_code"] for item in policy.universe["economies"]) == EXPECTED_ECONOMIES
    assert tuple(policy.universe["legacy_categories"]) == EXPECTED_LEGACY_CATEGORIES
    assert tuple(policy.universe["replacement_divisions"]) == EXPECTED_REPLACEMENT_DIVISIONS


def test_dataset_contracts_are_complete_and_ordered() -> None:
    policy = DualPanelPolicy.load(POLICY)
    assert tuple(contract.role for contract in policy.dataset_contracts) == EXPECTED_DATASET_ROLES
    assert all(contract.required_for_v0104_replay for contract in policy.dataset_contracts)


def test_gates_remain_closed() -> None:
    policy = DualPanelPolicy.load(POLICY)
    assert not any(policy.gates.values())


def test_scope_does_not_execute_backtest_or_ratification() -> None:
    scope = read_policy()["scope"]
    assert scope["define_acquisition_and_replay_contract"] is True
    assert not any(value for key, value in scope.items() if key != "define_acquisition_and_replay_contract")


def test_period_policy_does_not_allow_committed_live_2026_observations() -> None:
    period_policy = read_policy()["period_policy"]
    assert period_policy["legacy_period_end"] == "2025-12"
    assert period_policy["committed_live_2026_observations_allowed"] is False


def test_raw_receipt_contract_requires_hashes_and_timestamps() -> None:
    fields = set(read_policy()["raw_receipt_contract"]["required_fields"])
    assert {"receipt_id", "retrieved_at", "raw_path", "raw_sha256", "query_fingerprint"}.issubset(fields)


def test_normalised_contract_forbids_transition_and_monetary_fields() -> None:
    forbidden = set(read_policy()["normalized_observation_contract"]["forbidden_fields"])
    assert {"transition_strategy", "arm_o_2026_value", "monetary_value"}.issubset(forbidden)


def test_acquisition_register_contains_legacy_and_replacement_requests() -> None:
    policy = DualPanelPolicy.load(POLICY)
    requests = acquisition_requests(policy)
    roles = {row["dataset_role"] for row in requests}
    assert roles == set(EXPECTED_DATASET_ROLES)
    assert any(row["category_or_division"] == "CP13" for row in requests)
    assert any(row["category_or_division"] == "CP12" for row in requests)
    assert not any(row["live_fetch_allowed_in_pr"] == "true" for row in requests)


def test_acquisition_register_has_unique_request_ids() -> None:
    policy = DualPanelPolicy.load(POLICY)
    requests = acquisition_requests(policy)
    request_ids = [row["request_id"] for row in requests]
    assert len(request_ids) == len(set(request_ids))


def test_build_and_verify_scaffold(tmp_path: Path) -> None:
    out = tmp_path / "audit"
    summary = build_dual_panel_scaffold(POLICY, out, created_at=CREATED_AT)
    replay = verify_dual_panel_scaffold(POLICY, out)
    assert summary == replay
    assert summary["status"] == STATUS
    assert summary["committed_observation_count"] == 0
    assert summary["live_2026_observation_count"] == 0


def test_scaffold_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_dual_panel_scaffold(POLICY, first, created_at=CREATED_AT)
    build_dual_panel_scaffold(POLICY, second, created_at=CREATED_AT)
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_scaffold_file_set_and_request_rows(tmp_path: Path) -> None:
    out = tmp_path / "audit"
    build_dual_panel_scaffold(POLICY, out, created_at=CREATED_AT)
    assert {path.name for path in out.iterdir()} == set(read_policy()["output_files"])
    with (out / "acquisition_request_register.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) > 100
    assert {row["live_fetch_allowed_in_pr"] for row in rows} == {"false"}


def test_rejects_open_gate() -> None:
    payload = read_policy()
    payload["gates"]["research_release_allowed"] = True
    with pytest.raises(DualPanelError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_rejects_backtest_scope() -> None:
    payload = read_policy()
    payload["scope"]["execute_transition_backtest"] = True
    with pytest.raises(DualPanelError, match="forbidden v0.10.4 scope"):
        validate_policy_document(payload)


def test_rejects_wrong_economy_universe() -> None:
    payload = read_policy()
    payload["universe"]["economies"][0]["eurostat_code"] = "NL"
    with pytest.raises(DualPanelError, match="economy universe"):
        validate_policy_document(payload)


def test_rejects_missing_replacement_division() -> None:
    payload = read_policy()
    payload["universe"]["replacement_divisions"].remove("CP13")
    with pytest.raises(DualPanelError, match="replacement division"):
        validate_policy_document(payload)


def test_rejects_wrong_dataset_code() -> None:
    payload = read_policy()
    payload["dataset_contracts"][0]["dataset_code"] = "invented"
    with pytest.raises(DualPanelError, match="dataset code mismatch"):
        validate_policy_document(payload)


def test_verify_rejects_manifest_hash_mismatch(tmp_path: Path) -> None:
    out = tmp_path / "audit"
    build_dual_panel_scaffold(POLICY, out, created_at=CREATED_AT)
    target = out / "dual_panel_lineage_contract.csv"
    target.write_text(target.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
    with pytest.raises(DualPanelError, match="manifest hash mismatch"):
        verify_dual_panel_scaffold(POLICY, out)


def test_verify_rejects_committed_observations(tmp_path: Path) -> None:
    out = tmp_path / "audit"
    build_dual_panel_scaffold(POLICY, out, created_at=CREATED_AT)
    summary_path = out / "dual_panel_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["committed_observation_count"] = 1
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(DualPanelError, match="manifest hash mismatch|commit observations"):
        verify_dual_panel_scaffold(POLICY, out)


def test_cli_validate_policy(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(ROOT), "validate-policy"]) == 0
    captured = capsys.readouterr().out
    assert STATUS in captured
    assert "dataset_contract_count=6" in captured


def test_cli_build_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "audit"
    assert main(["--root", str(ROOT), "build-scaffold", "--output-dir", str(out), "--created-at", CREATED_AT]) == 0
    assert main(["--root", str(ROOT), "verify-scaffold", "--output-dir", str(out)]) == 0
    captured = capsys.readouterr().out
    assert captured.count(STATUS) == 2


def test_output_files_are_declared_in_policy() -> None:
    output_files = set(read_policy()["output_files"])
    assert {
        "acquisition_request_register.csv",
        "dataset_receipt_contract.csv",
        "dual_panel_coverage_contract.csv",
        "dual_panel_lineage_contract.csv",
        "normalised_observation_contract.csv",
        "dual_panel_summary.json",
        "MANIFEST.sha256",
    } == output_files
