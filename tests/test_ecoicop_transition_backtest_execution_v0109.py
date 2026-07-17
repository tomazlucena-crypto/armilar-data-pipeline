from __future__ import annotations

import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_transition_backtest_execution_v0109 import (
    DEFAULT_POLICY,
    NEXT_MILESTONE,
    RESULT_STATUS,
    STATUS,
    TransitionBacktestExecutionError,
    TransitionBacktestExecutionPolicy,
    _build_fixture_readiness,
    _write_manifest,
    create_transition_backtest_result,
    load_protocol_summary,
    validate_execution_result,
    validate_policy_document,
    validate_readiness_for_execution,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / DEFAULT_POLICY


def test_policy_loads_and_gates_closed() -> None:
    policy = TransitionBacktestExecutionPolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_transition_backtest_execution_engine"] is True
    assert policy.payload["scope"]["claim_empirical_transition_backtest"] is False
    assert policy.payload["next_milestone"] == NEXT_MILESTONE
    assert not any(policy.gates.values())


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["backtest_execution_claim_allowed"] = True
    with pytest.raises(TransitionBacktestExecutionError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_empirical_claim_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["claim_empirical_transition_backtest"] = True
    with pytest.raises(TransitionBacktestExecutionError, match="forbidden"):
        validate_policy_document(payload)


def test_protocol_summary_declares_four_strategies_and_metrics() -> None:
    summary = load_protocol_summary(ROOT / "config/ecoicop_v2_backtest_protocol_v0103.json")
    assert summary["protocol_status"] == "ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID"
    assert summary["strategy_ids"] == ["T0", "T1", "T2", "T3"]
    assert summary["metric_count"] >= 14


def test_fixture_readiness_validates_for_execution(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path)
    summary = validate_readiness_for_execution(POLICY_PATH, readiness, repo_root=ROOT)
    assert summary["runner_status"] == "ECOICOP_V2_TRANSITION_BACKTEST_READINESS_REPORT_V0108_VALID"
    assert summary["transition_backtest_executed"] is False
    assert summary["selected_strategy"] == "NONE"


def test_create_transition_backtest_result(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    report = create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    assert report["execution_status"] == RESULT_STATUS
    assert report["fixture_execution_completed"] is True
    assert report["empirical_transition_backtest_executed"] is False
    assert report["metric_row_count"] >= 56
    assert (output / "TRANSITION_BACKTEST_RESULT_MANIFEST.sha256").is_file()


def test_validate_execution_result(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    summary = validate_execution_result(POLICY_PATH, output)
    assert summary["execution_status"] == RESULT_STATUS
    assert summary["selected_strategy"] == "NONE"


def test_result_rejects_empirical_execution_claim(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "transition_backtest_result_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["empirical_transition_backtest_executed"] = True
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "TRANSITION_BACKTEST_RESULT_MANIFEST.sha256")
    with pytest.raises(TransitionBacktestExecutionError, match="empirical backtest"):
        validate_execution_result(POLICY_PATH, output)


def test_result_rejects_strategy_selection(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    report_path = output / "transition_backtest_result_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["selected_strategy"] = "T2"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "TRANSITION_BACKTEST_RESULT_MANIFEST.sha256")
    with pytest.raises(TransitionBacktestExecutionError, match="selected a strategy"):
        validate_execution_result(POLICY_PATH, output)


def test_result_manifest_detects_tampering(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    (output / "transition_backtest_metrics.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(TransitionBacktestExecutionError, match="manifest hash mismatch"):
        validate_execution_result(POLICY_PATH, output)


def test_result_rejects_incomplete_metric_matrix(tmp_path: Path) -> None:
    readiness = _build_fixture_readiness(ROOT, tmp_path / "readiness-fixture")
    output = tmp_path / "result"
    create_transition_backtest_result(
        POLICY_PATH,
        readiness,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0109",
        created_at="2026-07-10T00:00:00Z",
    )
    metrics_path = output / "transition_backtest_metrics.csv"
    lines = metrics_path.read_text(encoding="utf-8").splitlines()
    metrics_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    _write_manifest(output, "TRANSITION_BACKTEST_RESULT_MANIFEST.sha256")
    with pytest.raises(TransitionBacktestExecutionError, match="metric matrix"):
        validate_execution_result(POLICY_PATH, output)
