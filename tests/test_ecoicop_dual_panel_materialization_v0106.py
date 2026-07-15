from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_dual_panel_materialization_v0106 import (
    COVERAGE_STATUSES,
    MATERIALIZED_STATUS,
    QUALITY_STATUSES,
    STATUS,
    MaterializationError,
    MaterializationPolicy,
    materialize_external_panel,
    validate_policy_document,
    validate_staging_directory,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_materialization_v0106.json"
REPLAY_POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_replay_v0105.json"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(path: Path) -> None:
    entries = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix()
        if relative == "STAGING_MANIFEST.sha256":
            continue
        entries.append(f"{_sha(candidate)}  {relative}")
    (path / "STAGING_MANIFEST.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")


def make_staging(tmp_path: Path) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    raw = staging / "official_response.xml"
    raw.write_bytes(b"<official><series>PT CP01 2025-12</series></official>\n")
    raw_digest = _sha(raw)
    raw_size = str(raw.stat().st_size)
    _write_csv(
        staging / "staged_receipts.csv",
        [
            "staged_receipt_id", "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at",
            "http_status", "raw_path", "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint",
        ],
        [
            {
                "staged_receipt_id": "SR1",
                "dataset_role": "LEGACY_MONTHLY_INDEX",
                "provider": "Eurostat",
                "dataset_code": "prc_hicp_midx",
                "request_url": "https://example.invalid/eurostat/prc_hicp_midx?fixture=1",
                "retrieved_at": "2026-07-09T00:00:00Z",
                "http_status": "200",
                "raw_path": "official_response.xml",
                "raw_sha256": raw_digest,
                "byte_count": raw_size,
                "content_type": "application/xml",
                "classification": "ECOICOP_V1_PRE_2026",
                "time_window": "2025-12/2025-12",
                "query_fingerprint": hashlib.sha256(b"fixture-query").hexdigest(),
            }
        ],
    )
    _write_csv(
        staging / "staged_observations.csv",
        [
            "staged_observation_id", "staged_receipt_id", "dataset_role", "economy", "armilar_code", "classification",
            "category_or_division", "period", "unit", "value", "source_period_type", "parser_version", "quality_status",
        ],
        [
            {
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
            }
        ],
    )
    _write_csv(
        staging / "staged_coverage.csv",
        [
            "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status", "staged_observation_id",
        ],
        [
            {
                "coverage_id": "C1",
                "economy": "PT",
                "armilar_code": "PRT",
                "classification": "ECOICOP_V1_PRE_2026",
                "category_or_division": "CP01",
                "period": "2025-12",
                "dataset_role": "LEGACY_MONTHLY_INDEX",
                "coverage_status": "OBSERVED",
                "staged_observation_id": "SO1",
            },
            {
                "coverage_id": "C2",
                "economy": "PT",
                "armilar_code": "PRT",
                "classification": "ECOICOP_V2_FROM_2026",
                "category_or_division": "CP13",
                "period": "2025-12",
                "dataset_role": "REPLACEMENT_MONTHLY_INDEX_AND_RATES",
                "coverage_status": "MISSING",
                "staged_observation_id": "",
            },
        ],
    )
    _write_manifest(staging)
    return staging


def test_policy_loads_and_gates_closed() -> None:
    policy = MaterializationPolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_offline_materialization_runner"] is True
    assert policy.payload["scope"]["acquire_live_provider_bytes_in_pr"] is False
    assert not any(policy.gates.values())
    assert tuple(policy.staging_contract["allowed_quality_statuses"]) == QUALITY_STATUSES
    assert tuple(policy.staging_contract["allowed_coverage_statuses"]) == COVERAGE_STATUSES


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["ecoicop_v1_v2_dual_panel_verified"] = True
    with pytest.raises(MaterializationError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_live_acquisition_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["acquire_live_provider_bytes_in_pr"] = True
    with pytest.raises(MaterializationError, match="forbidden"):
        validate_policy_document(payload)


def test_staging_fixture_validates(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    summary = validate_staging_directory(POLICY_PATH, staging)
    assert summary["staging_receipt_count"] == 1
    assert summary["staging_observation_count"] == 1
    assert summary["live_2026_observation_count"] == 0


def test_staging_rejects_manifest_hash_mismatch(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    (staging / "official_response.xml").write_bytes(b"tampered\n")
    with pytest.raises(MaterializationError, match="manifest hash mismatch"):
        validate_staging_directory(POLICY_PATH, staging)


def test_staging_rejects_unknown_receipt(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    rows = list(csv.DictReader((staging / "staged_observations.csv").open(encoding="utf-8", newline="")))
    rows[0]["staged_receipt_id"] = "UNKNOWN"
    _write_csv(staging / "staged_observations.csv", list(rows[0]), rows)
    _write_manifest(staging)
    with pytest.raises(MaterializationError, match="unknown staged receipt"):
        validate_staging_directory(POLICY_PATH, staging)


def test_staging_rejects_live_2026_rows(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    rows = list(csv.DictReader((staging / "staged_observations.csv").open(encoding="utf-8", newline="")))
    rows[0]["period"] = "2026-01"
    _write_csv(staging / "staged_observations.csv", list(rows[0]), rows)
    _write_manifest(staging)
    with pytest.raises(MaterializationError, match="refuses live 2026"):
        validate_staging_directory(POLICY_PATH, staging)


def test_materializer_builds_v0105_replay_valid_artifact(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    out = tmp_path / "materialized"
    summary = materialize_external_panel(
        POLICY_PATH,
        REPLAY_POLICY_PATH,
        staging,
        out,
        created_at="2026-07-09T00:00:00Z",
        repo_root=ROOT,
    )
    assert summary["status"] == MATERIALIZED_STATUS
    assert summary["materialized_artifact_status"] == "ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID"
    assert summary["materialized_receipt_count"] == 1
    assert summary["materialized_observation_count"] == 1
    assert summary["panel_verified_gate_open"] is False
    assert (out / "PANEL_MANIFEST.sha256").is_file()
    rows = list(csv.DictReader((out / "raw_receipts.csv").open(encoding="utf-8", newline="")))
    assert rows[0]["receipt_id"] == "R000001"


def test_materializer_refuses_non_empty_output(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    out = tmp_path / "materialized"
    out.mkdir()
    (out / "stale.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(MaterializationError, match="not empty"):
        materialize_external_panel(POLICY_PATH, REPLAY_POLICY_PATH, staging, out, created_at="2026-07-09T00:00:00Z", repo_root=ROOT)


def test_materializer_output_does_not_select_strategy(tmp_path: Path) -> None:
    staging = make_staging(tmp_path)
    out = tmp_path / "materialized"
    summary = materialize_external_panel(POLICY_PATH, REPLAY_POLICY_PATH, staging, out, created_at="2026-07-09T00:00:00Z", repo_root=ROOT)
    panel_summary = json.loads((out / "panel_summary.json").read_text(encoding="utf-8"))
    assert panel_summary["selected_strategy"] == "NONE"
    assert panel_summary["transition_backtest_executed"] is False
    assert panel_summary["panel_verified_gate_open"] is False
    assert summary["selected_strategy"] == "NONE"
