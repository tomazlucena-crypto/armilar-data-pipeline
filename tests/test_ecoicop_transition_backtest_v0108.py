from __future__ import annotations

import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_transition_backtest_v0108 import (
    DEFAULT_POLICY,
    NEXT_MILESTONE,
    READY_STATUS,
    STATUS,
    TransitionBacktestError,
    TransitionBacktestPolicy,
    _build_fixture_attachment,
    _write_manifest,
    create_backtest_readiness_report,
    load_protocol_summary,
    validate_attachment_for_backtest,
    validate_policy_document,
    validate_readiness_report,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / DEFAULT_POLICY


def test_policy_loads_and_gates_closed() -> None:
    policy = TransitionBacktestPolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_transition_backtest_runner"] is True
    assert policy.payload["scope"]["execute_empirical_backtest_in_pr"] is False
    assert policy.payload["next_milestone"] == NEXT_MILESTONE
    assert not any(policy.gates.values())


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["backtest_execution_claim_allowed"] = True
    with pytest.raises(TransitionBacktestError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_empirical_execution_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["execute_empirical_backtest_in_pr"] = True
    with pytest.raises(TransitionBacktestError, match="forbidden"):
        validate_policy_document(payload)


def test_protocol_summary_declares_four_strategies_and_metrics() -> None:
    summary = load_protocol_summary(ROOT / "config/ecoicop_v2_backtest_protocol_v0103.json")
    assert summary["protocol_status"] == "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
    assert summary["strategy_ids"] == ["T0", "T1", "T2", "T3"]
    assert summary["metric_count"] >= 14


def test_attachment_validates_for_backtest(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path)
    summary = validate_attachment_for_backtest(POLICY_PATH, attachment, repo_root=ROOT)
    assert summary["attachment_status"] == "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_ATTACHMENT_V0107_VALID"
    assert summary["transition_backtest_executed"] is False
    assert summary["selected_strategy"] == "NONE"


def test_create_backtest_readiness_report(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path / "fixture")
    output = tmp_path / "readiness"
    report = create_backtest_readiness_report(
        POLICY_PATH,
        attachment,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    assert report["runner_status"] == READY_STATUS
    assert report["transition_backtest_executed"] is False
    assert report["backtest_execution_claim_allowed"] is False
    assert report["selected_strategy"] == "NONE"
    assert (output / "BACKTEST_READINESS_MANIFEST.sha256").is_file()


def test_validate_readiness_report(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path / "fixture")
    output = tmp_path / "readiness"
    create_backtest_readiness_report(
        POLICY_PATH,
        attachment,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    summary = validate_readiness_report(POLICY_PATH, output)
    assert summary["runner_status"] == READY_STATUS
    assert summary["panel_verified_gate_open"] is False


def test_readiness_rejects_backtest_claim(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path / "fixture")
    output = tmp_path / "readiness"
    create_backtest_readiness_report(
        POLICY_PATH,
        attachment,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    report_path = output / "transition_backtest_readiness_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["transition_backtest_executed"] = True
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "BACKTEST_READINESS_MANIFEST.sha256")
    with pytest.raises(TransitionBacktestError, match="empirical backtest"):
        validate_readiness_report(POLICY_PATH, output)


def test_readiness_rejects_strategy_selection(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path / "fixture")
    output = tmp_path / "readiness"
    create_backtest_readiness_report(
        POLICY_PATH,
        attachment,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    report_path = output / "transition_backtest_readiness_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["selected_strategy"] = "T2"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "BACKTEST_READINESS_MANIFEST.sha256")
    with pytest.raises(TransitionBacktestError, match="selected a strategy"):
        validate_readiness_report(POLICY_PATH, output)


def test_readiness_manifest_detects_tampering(tmp_path: Path) -> None:
    attachment = _build_fixture_attachment(ROOT, tmp_path / "fixture")
    output = tmp_path / "readiness"
    create_backtest_readiness_report(
        POLICY_PATH,
        attachment,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0108",
        created_at="2026-07-09T00:00:00Z",
    )
    (output / "transition_backtest_readiness_report.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(TransitionBacktestError, match="manifest hash mismatch"):
        validate_readiness_report(POLICY_PATH, output)
