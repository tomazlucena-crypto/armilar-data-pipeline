from __future__ import annotations

import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_external_dual_panel_v0111 import (
    DEFAULT_POLICY,
    INTAKE_STATUS,
    NEXT_MILESTONE,
    STATUS,
    ExternalDualPanelIntakeError,
    ExternalDualPanelIntakePolicy,
    _load_module,
    _write_manifest,
    create_external_panel_intake_report,
    validate_external_panel_intake_report,
    validate_policy_document,
    validate_predecessor,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / DEFAULT_POLICY


def _build_fixture_external_panel(tmp_path: Path) -> tuple[Path, Path]:
    materialization = _load_module(ROOT, "src/armilar_backtest/ecoicop_dual_panel_materialization_v0106.py", "ecoicop_dual_panel_materialization_v0106_fixture_for_v0111_tests")
    attachment = _load_module(ROOT, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_fixture_for_v0111_tests")
    staging = tmp_path / "staging"
    staging.mkdir()
    raw = b'{"fixture":"v0111","provider":"EUROSTAT"}\n'
    raw_path = staging / "raw" / "eurostat_fixture.json"
    raw_path.parent.mkdir()
    raw_path.write_bytes(raw)
    raw_sha = materialization._sha256_bytes(raw)
    (staging / "staged_receipts.csv").write_text(
        "staged_receipt_id,dataset_role,provider,dataset_code,request_url,retrieved_at,http_status,raw_path,raw_sha256,byte_count,content_type,classification,time_window,query_fingerprint\n"
        f"SR1,LEGACY_MONTHLY_INDEX,EUROSTAT,prc_hicp_midx,https://example.invalid/eurostat,2026-07-10T00:00:00Z,200,raw/eurostat_fixture.json,{raw_sha},{len(raw)},application/json,ECOICOP_V1_PRE_2026,2021-01:2025-12,fixture-query\n",
        encoding="utf-8",
    )
    (staging / "staged_observations.csv").write_text(
        "staged_observation_id,staged_receipt_id,dataset_role,economy,armilar_code,classification,category_or_division,period,unit,value,source_period_type,parser_version,quality_status\n"
        "SO1,SR1,LEGACY_MONTHLY_INDEX,PRT,CP01,ECOICOP_V1_PRE_2026,CP01,2021-01,I15,100.0,monthly,fixture-v0111,OBSERVED_OFFICIAL\n",
        encoding="utf-8",
    )
    (staging / "staged_coverage.csv").write_text(
        "coverage_id,economy,armilar_code,classification,category_or_division,period,dataset_role,coverage_status,staged_observation_id\n"
        "C1,PRT,CP01,ECOICOP_V1_PRE_2026,CP01,2021-01,LEGACY_MONTHLY_INDEX,OBSERVED,SO1\n",
        encoding="utf-8",
    )
    materialization._write_manifest(staging, "STAGING_MANIFEST.sha256")
    artifact = tmp_path / "artifact"
    materialization.materialize_external_panel(
        ROOT / "config" / "ecoicop_dual_panel_materialization_v0106.json",
        ROOT / "config" / "ecoicop_dual_panel_replay_v0105.json",
        staging,
        artifact,
        created_at="2026-07-10T00:00:00Z",
        repo_root=ROOT,
    )
    attachment_dir = tmp_path / "attachment"
    attachment.create_attachment_descriptor(
        ROOT / "config" / "ecoicop_dual_panel_attachment_v0107.json",
        artifact,
        attachment_dir,
        repo_root=ROOT,
        repository_commit="fixture-v0111-test",
        artifact_uri="external://fixture-v0111-panel",
        created_at="2026-07-10T00:00:00Z",
    )
    return attachment_dir, artifact


def test_policy_loads_and_keeps_gates_closed() -> None:
    policy = ExternalDualPanelIntakePolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_external_panel_intake_runner"] is True
    assert policy.payload["scope"]["run_real_empirical_backtest"] is False
    assert policy.payload["next_milestone"] == NEXT_MILESTONE
    assert not any(policy.gates.values())


def test_policy_rejects_live_acquisition_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["acquire_live_provider_bytes_in_pr"] = True
    with pytest.raises(ExternalDualPanelIntakeError, match="forbidden"):
        validate_policy_document(payload)


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["backtest_execution_claim_allowed"] = True
    with pytest.raises(ExternalDualPanelIntakeError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_predecessor_validates_v0110_chain() -> None:
    predecessor = validate_predecessor(ROOT)
    assert predecessor["status"] == "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_GATE_V0110_VALID"
    assert predecessor["fixture_status"] == "ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_PREFLIGHT_REPORT_V0110_VALID"
    assert predecessor["metric_count"] >= 14
    assert predecessor["metric_row_count"] >= 56


def test_create_external_panel_intake_report(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    report = create_external_panel_intake_report(
        POLICY_PATH,
        attachment_dir,
        artifact_dir,
        output,
        repo_root=ROOT,
        repository_commit="fixture-v0111",
        created_at="2026-07-10T00:00:00Z",
    )
    assert report["intake_status"] == INTAKE_STATUS
    assert report["external_verified_panel_available"] is True
    assert report["empirical_transition_backtest_executed"] is False
    assert report["selected_strategy"] == "NONE"
    assert (output / "EXTERNAL_DUAL_PANEL_INTAKE_MANIFEST.sha256").is_file()


def test_validate_external_panel_intake_report(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, output, repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")
    report = validate_external_panel_intake_report(POLICY_PATH, output)
    assert report["blocking_reason"] == "EXTERNAL_PANEL_ATTACHED_READY_FOR_SEPARATE_EMPIRICAL_RUN"


def test_intake_rejects_backtest_claim(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, output, repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")
    report_path = output / "external_dual_panel_intake_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["empirical_transition_backtest_executed"] = True
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EXTERNAL_DUAL_PANEL_INTAKE_MANIFEST.sha256")
    with pytest.raises(ExternalDualPanelIntakeError, match="must be False"):
        validate_external_panel_intake_report(POLICY_PATH, output)


def test_intake_rejects_strategy_selection(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, output, repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")
    report_path = output / "external_dual_panel_intake_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["selected_strategy"] = "T1"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(output, "EXTERNAL_DUAL_PANEL_INTAKE_MANIFEST.sha256")
    with pytest.raises(ExternalDualPanelIntakeError, match="selected a strategy"):
        validate_external_panel_intake_report(POLICY_PATH, output)


def test_intake_manifest_detects_tampering(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, output, repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")
    (output / "external_dual_panel_intake_report.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ExternalDualPanelIntakeError, match="manifest hash mismatch"):
        validate_external_panel_intake_report(POLICY_PATH, output)


def test_rejects_invalid_attachment(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    descriptor_path = attachment_dir / "panel_attachment_descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["selected_strategy"] = "T2"
    descriptor_path.write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ExternalDualPanelIntakeError, match="manifest hash mismatch|selected a strategy"):
        create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, tmp_path / "intake", repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")


def test_output_directory_must_be_empty(tmp_path: Path) -> None:
    attachment_dir, artifact_dir = _build_fixture_external_panel(tmp_path)
    output = tmp_path / "intake"
    output.mkdir()
    (output / "existing.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExternalDualPanelIntakeError, match="output directory is not empty"):
        create_external_panel_intake_report(POLICY_PATH, attachment_dir, artifact_dir, output, repo_root=ROOT, repository_commit="fixture-v0111", created_at="2026-07-10T00:00:00Z")
