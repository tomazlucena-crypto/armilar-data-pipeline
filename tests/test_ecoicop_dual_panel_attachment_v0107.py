from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_dual_panel_attachment_v0107 import (
    ATTACHMENT_STATUS,
    NEXT_MILESTONE,
    STATUS,
    AttachmentError,
    AttachmentPolicy,
    create_attachment_descriptor,
    validate_attachment_directory,
    validate_materialized_artifact,
    validate_policy_document,
)
from armilar_backtest.ecoicop_dual_panel_materialization_v0106 import (
    _sha256_bytes,
    _write_csv,
    _write_manifest,
    materialize_external_panel,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_attachment_v0107.json"
MATERIALIZATION_POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_materialization_v0106.json"
REPLAY_POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_replay_v0105.json"


def make_staging(tmp_path: Path) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    raw = staging / "official_response.xml"
    raw.write_bytes(b"<fixture provider='EUROSTAT' dataset='prc_hicp_midx'/>\n")
    raw_sha = sha256_file(raw)
    _write_csv(
        staging / "staged_receipts.csv",
        [
            "staged_receipt_id", "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at",
            "http_status", "raw_path", "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint",
        ],
        [{
            "staged_receipt_id": "SR1",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "provider": "EUROSTAT",
            "dataset_code": "prc_hicp_midx",
            "request_url": "https://example.invalid/eurostat/prc_hicp_midx?fixture=1",
            "retrieved_at": "2026-07-09T00:00:00Z",
            "http_status": "200",
            "raw_path": "official_response.xml",
            "raw_sha256": raw_sha,
            "byte_count": str(raw.stat().st_size),
            "content_type": "application/xml",
            "classification": "ECOICOP_V1_PRE_2026",
            "time_window": "2025-12/2025-12",
            "query_fingerprint": _sha256_bytes(b"v0107-fixture-query"),
        }],
    )
    _write_csv(
        staging / "staged_observations.csv",
        [
            "staged_observation_id", "staged_receipt_id", "dataset_role", "economy", "armilar_code", "classification",
            "category_or_division", "period", "unit", "value", "source_period_type", "parser_version", "quality_status",
        ],
        [{
            "staged_observation_id": "SO1",
            "staged_receipt_id": "SR1",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "economy": "PT",
            "armilar_code": "PRT",
            "classification": "ECOICOP_V1_PRE_2026",
            "category_or_division": "CP01",
            "period": "2025-12",
            "unit": "index_2015_100",
            "value": "121.34",
            "source_period_type": "monthly",
            "parser_version": "fixture-parser-v1",
            "quality_status": "OBSERVED_OFFICIAL",
        }],
    )
    _write_csv(
        staging / "staged_coverage.csv",
        [
            "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status", "staged_observation_id",
        ],
        [{
            "coverage_id": "C1",
            "economy": "PT",
            "armilar_code": "PRT",
            "classification": "ECOICOP_V1_PRE_2026",
            "category_or_division": "CP01",
            "period": "2025-12",
            "dataset_role": "LEGACY_MONTHLY_INDEX",
            "coverage_status": "OBSERVED",
            "staged_observation_id": "SO1",
        }],
    )
    _write_manifest(staging, "STAGING_MANIFEST.sha256")
    return staging


def make_artifact(tmp_path: Path) -> Path:
    staging = make_staging(tmp_path)
    artifact = tmp_path / "artifact"
    materialize_external_panel(
        MATERIALIZATION_POLICY_PATH,
        REPLAY_POLICY_PATH,
        staging,
        artifact,
        created_at="2026-07-09T00:00:00Z",
        repo_root=ROOT,
    )
    return artifact


def test_policy_loads_and_gates_closed() -> None:
    policy = AttachmentPolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_external_attachment_protocol"] is True
    assert policy.payload["scope"]["commit_official_bytes_in_pr"] is False
    assert policy.payload["next_milestone"] == NEXT_MILESTONE
    assert not any(policy.gates.values())


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["ecoicop_v1_v2_dual_panel_verified"] = True
    with pytest.raises(AttachmentError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_live_acquisition_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["acquire_live_provider_bytes_in_pr"] = True
    with pytest.raises(AttachmentError, match="forbidden"):
        validate_policy_document(payload)


def test_materialized_artifact_validates(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    summary = validate_materialized_artifact(POLICY_PATH, artifact, repo_root=ROOT)
    assert summary["artifact_replay_status"] == "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
    assert summary["artifact_manifest_entry_count"] >= 6
    assert summary["observation_count"] == 1


def test_materialized_artifact_rejects_tampered_manifest_entry(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    (artifact / "normalised_observations.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(AttachmentError, match="manifest hash mismatch"):
        validate_materialized_artifact(POLICY_PATH, artifact, repo_root=ROOT)


def test_create_attachment_descriptor(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    attachment = tmp_path / "attachment"
    descriptor = create_attachment_descriptor(
        POLICY_PATH,
        artifact,
        attachment,
        repo_root=ROOT,
        repository_commit="fixture-v0107",
        artifact_uri="external://fixture/ecoicop-dual-panel-v0107",
        created_at="2026-07-09T00:00:00Z",
    )
    assert descriptor["attachment_status"] == ATTACHMENT_STATUS
    assert descriptor["official_bytes_committed_to_repository"] is False
    assert descriptor["public_latest_modified"] is False
    assert descriptor["transition_backtest_executed"] is False
    assert descriptor["selected_strategy"] == "NONE"
    assert (attachment / "ATTACHMENT_MANIFEST.sha256").is_file()


def test_validate_attachment_directory(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    attachment = tmp_path / "attachment"
    create_attachment_descriptor(
        POLICY_PATH,
        artifact,
        attachment,
        repo_root=ROOT,
        repository_commit="fixture-v0107",
        artifact_uri="external://fixture/ecoicop-dual-panel-v0107",
        created_at="2026-07-09T00:00:00Z",
    )
    summary = validate_attachment_directory(POLICY_PATH, attachment)
    assert summary["attachment_status"] == ATTACHMENT_STATUS
    assert summary["artifact_replay_status"] == "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
    assert summary["panel_verified_gate_open"] is False


def test_attachment_rejects_committed_official_bytes_claim(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    attachment = tmp_path / "attachment"
    create_attachment_descriptor(
        POLICY_PATH,
        artifact,
        attachment,
        repo_root=ROOT,
        repository_commit="fixture-v0107",
        artifact_uri="external://fixture/ecoicop-dual-panel-v0107",
        created_at="2026-07-09T00:00:00Z",
    )
    descriptor_path = attachment / "panel_attachment_descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["official_bytes_committed_to_repository"] = True
    descriptor_path.write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(attachment, "ATTACHMENT_MANIFEST.sha256")
    with pytest.raises(AttachmentError, match="official bytes"):
        validate_attachment_directory(POLICY_PATH, attachment)


def test_attachment_rejects_backtest_claim(tmp_path: Path) -> None:
    artifact = make_artifact(tmp_path)
    attachment = tmp_path / "attachment"
    create_attachment_descriptor(
        POLICY_PATH,
        artifact,
        attachment,
        repo_root=ROOT,
        repository_commit="fixture-v0107",
        artifact_uri="external://fixture/ecoicop-dual-panel-v0107",
        created_at="2026-07-09T00:00:00Z",
    )
    descriptor_path = attachment / "panel_attachment_descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["transition_backtest_executed"] = True
    descriptor_path.write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(attachment, "ATTACHMENT_MANIFEST.sha256")
    with pytest.raises(AttachmentError, match="backtest"):
        validate_attachment_directory(POLICY_PATH, attachment)
