from __future__ import annotations

import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_transition_backtest_empirical_v0110 import (
    DEFAULT_POLICY,
    NEXT_MILESTONE,
    PREFLIGHT_STATUS,
    STATUS,
    EmpiricalBacktestGateError,
    EmpiricalBacktestGatePolicy,
    _write_manifest,
    create_empirical_preflight_report,
    validate_empirical_preflight_report,
    validate_policy_document,
    validate_predecessor,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / DEFAULT_POLICY


def test_policy_loads_and_gates_are_closed() -> None:
    policy = EmpiricalBacktestGatePolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_empirical_backtest_gatekeeper"] is True
    assert policy.payload["scope"]["claim_empirical_transition_backtest"] is False
    assert policy.payload["next_milestone"] == NEXT_MILESTONE
    assert not any(policy.gates.values())


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["backtest_execution_claim_allowed"] = True
    with pytest.raises(EmpiricalBacktestGateError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_empirical_claim_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["claim_empirical_transition_backtest"] = True
    with pytest.raises(EmpiricalBacktestGateError, match="forbidden"):
        validate_policy_document(payload)


def test_predecessor_validates_v0109_chain() -> None:
    predecessor = validate_predecessor(ROOT)
    assert predecessor["status"] == "ECOICOP_V2_TRANSITION_BACKTEST_EXECUTION_ENGINE_V0109_VALID"
    assert predecessor["fixture_status"] == "ECOICOP_V2_TRANSITION_BACKTEST_RESULT_FIXTURE_V0109_VALID"
    assert predecessor["strategy_ids"] == ["T0", "T1", "T2", "T3"]
    assert predecessor["metric_count"] >= 14
    assert predecessor["metric_row_count"] >= 56


def test_create_empirical_preflight_report(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    report = create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    assert report["preflight_status"] == PREFLIGHT_STATUS
    assert report["empirical_transition_backtest_executed"] is False
    assert report["backtest_execution_claim_allowed"] is False
    assert report["selected_strategy"] == "NONE"
    assert (output / "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256").is_file()


def test_validate_empirical_preflight_report(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    report = validate_empirical_preflight_report(POLICY_PATH, output)
    assert report["external_verified_panel_available"] is False
    assert report["blocking_reason"] == "EXTERNAL_VERIFIED_PANEL_AND_EMPIRICAL_RESULT_NOT_ATTACHED"


def test_preflight_rejects_empirical_execution_claim(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "empirical_transition_backtest_preflight_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["empirical_transition_backtest_executed"] = True
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256")
    with pytest.raises(EmpiricalBacktestGateError, match="must remain false"):
        validate_empirical_preflight_report(POLICY_PATH, output)


def test_preflight_rejects_strategy_selection(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "empirical_transition_backtest_preflight_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["selected_strategy"] = "T1"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256")
    with pytest.raises(EmpiricalBacktestGateError, match="selected a strategy"):
        validate_empirical_preflight_report(POLICY_PATH, output)


def test_preflight_manifest_detects_tampering(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    (output / "empirical_transition_backtest_preflight_report.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(EmpiricalBacktestGateError, match="manifest hash mismatch"):
        validate_empirical_preflight_report(POLICY_PATH, output)


def test_preflight_rejects_wrong_blocking_reason(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "empirical_transition_backtest_preflight_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["blocking_reason"] = "READY"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256")
    with pytest.raises(EmpiricalBacktestGateError, match="blocking reason"):
        validate_empirical_preflight_report(POLICY_PATH, output)


def test_preflight_rejects_open_panel_gate(tmp_path: Path) -> None:
    output = tmp_path / "preflight"
    create_empirical_preflight_report(
        POLICY_PATH,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0110",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "empirical_transition_backtest_preflight_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["panel_verified_gate_open"] = True
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256")
    with pytest.raises(EmpiricalBacktestGateError, match="must remain false"):
        validate_empirical_preflight_report(POLICY_PATH, output)
