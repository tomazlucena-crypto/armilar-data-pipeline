from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from armilar_backtest.ecoicop_dual_panel_replay_v0105 import (
    EXTERNAL_REPLAY_STATUS,
    STATUS,
    ReplayPolicy,
    ReplayVerifierError,
    build_replay_contract_scaffold,
    validate_external_panel_artifact,
    validate_policy_document,
    validate_predecessor,
    verify_replay_contract_scaffold,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "ecoicop_dual_panel_replay_v0105.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_manifest(directory: Path) -> None:
    entries = []
    for path in sorted(directory.iterdir()):
        if path.name == "PANEL_MANIFEST.sha256" or not path.is_file():
            continue
        entries.append(f"{_sha256(path)}  {path.name}\n")
    (directory / "PANEL_MANIFEST.sha256").write_text("".join(entries), encoding="utf-8")


def _make_valid_external_panel(tmp_path: Path) -> Path:
    artifact = tmp_path / "panel"
    artifact.mkdir()
    raw = artifact / "raw_response.xml"
    raw.write_bytes(b"<generic:DataSet>official fixture bytes</generic:DataSet>\n")
    raw_digest = _sha256(raw)
    raw_size = str(raw.stat().st_size)
    policy = ReplayPolicy.load(POLICY_PATH)
    _write_csv(
        artifact / "raw_receipts.csv",
        list(policy.raw_fields),
        [
            {
                "receipt_id": "R1",
                "dataset_role": "LEGACY_MONTHLY_INDEX",
                "provider": "EUROSTAT",
                "dataset_code": "prc_hicp_midx",
                "request_url": "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx",
                "retrieved_at": "2026-07-09T00:00:00Z",
                "http_status": "200",
                "raw_path": raw.name,
                "raw_sha256": raw_digest,
                "byte_count": raw_size,
                "content_type": "application/xml",
                "classification": "ECOICOP_V1_PRE_2026",
                "time_window": "2021-01/2025-12",
                "query_fingerprint": "fixture-query-fingerprint",
            }
        ],
    )
    _write_csv(
        artifact / "normalised_observations.csv",
        list(policy.observation_fields),
        [
            {
                "observation_id": "O1",
                "receipt_id": "R1",
                "dataset_role": "LEGACY_MONTHLY_INDEX",
                "economy": "PT",
                "armilar_code": "PRT",
                "classification": "ECOICOP_V1_PRE_2026",
                "category_or_division": "CP01",
                "period": "2025-12",
                "unit": "I15",
                "value": "123.45",
                "source_period_type": "MONTH",
                "parser_version": "fixture-parser-v1",
                "quality_status": "OBSERVED_OFFICIAL",
            }
        ],
    )
    _write_csv(
        artifact / "dual_panel_coverage.csv",
        list(policy.coverage_fields),
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
                "observation_id": "O1",
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
                "observation_id": "",
            },
        ],
    )
    _write_csv(
        artifact / "dual_panel_lineage.csv",
        list(policy.lineage_fields),
        [
            {
                "lineage_id": "L1",
                "observation_id": "O1",
                "receipt_id": "R1",
                "transformation_step": "parse_official_response",
                "input_sha256": raw_digest,
                "output_sha256": hashlib.sha256(b"O1").hexdigest(),
                "may_rewrite_history": "false",
            }
        ],
    )
    summary = {
        "status": EXTERNAL_REPLAY_STATUS,
        "policy_version": "0.10.5",
        "created_at": "2026-07-09T00:00:00Z",
        "policy_sha256": policy.policy_sha256,
        "predecessor_status": "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID",
        "external_artifact": True,
        "receipt_count": 1,
        "observation_count": 1,
        "coverage_row_count": 2,
        "lineage_row_count": 1,
        "live_2026_observation_count": 0,
        "panel_verified_gate_open": False,
        "transition_backtest_executed": False,
        "selected_strategy": "NONE",
    }
    (artifact / "panel_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(artifact)
    return artifact


def test_policy_loads_and_gates_closed() -> None:
    policy = ReplayPolicy.load(POLICY_PATH)
    assert policy.payload["status"] == STATUS
    assert policy.payload["scope"]["define_external_panel_replay_verifier"] is True
    assert not any(policy.gates.values())
    assert policy.payload["artifact_boundary"]["official_bytes_committed_in_code_pr"] is False


def test_policy_rejects_open_gate() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["gates"]["ecoicop_v1_v2_dual_panel_verified"] = True
    with pytest.raises(ReplayVerifierError, match="gates must remain closed"):
        validate_policy_document(payload)


def test_policy_rejects_backtest_scope() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["scope"]["execute_transition_backtest"] = True
    with pytest.raises(ReplayVerifierError, match="forbidden"):
        validate_policy_document(payload)


def test_contract_scaffold_is_reproducible(tmp_path: Path) -> None:
    out = tmp_path / "contract"
    summary = build_replay_contract_scaffold(POLICY_PATH, out, created_at="2026-07-09T00:00:00Z")
    replay = verify_replay_contract_scaffold(POLICY_PATH, out)
    assert summary == replay
    assert summary["receipt_count"] == 0
    assert summary["observation_count"] == 0
    assert summary["panel_verified_gate_open"] is False
    assert (out / "CONTRACT_MANIFEST.sha256").is_file()


def test_scaffold_refuses_non_empty_directory(tmp_path: Path) -> None:
    out = tmp_path / "contract"
    out.mkdir()
    (out / "stale.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(ReplayVerifierError, match="not empty"):
        build_replay_contract_scaffold(POLICY_PATH, out, created_at="2026-07-09T00:00:00Z")


def test_external_panel_fixture_validates(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    summary = validate_external_panel_artifact(POLICY_PATH, artifact)
    assert summary["status"] == EXTERNAL_REPLAY_STATUS
    assert summary["receipt_count"] == 1
    assert summary["observation_count"] == 1
    assert summary["panel_verified_gate_open"] is False


def test_external_panel_rejects_raw_hash_mismatch(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    (artifact / "raw_response.xml").write_bytes(b"tampered\n")
    with pytest.raises(ReplayVerifierError, match="manifest hash mismatch"):
        validate_external_panel_artifact(POLICY_PATH, artifact)


def test_external_panel_rejects_unknown_receipt(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    rows = list(csv.DictReader((artifact / "normalised_observations.csv").open(encoding="utf-8", newline="")))
    rows[0]["receipt_id"] = "UNKNOWN"
    _write_csv(artifact / "normalised_observations.csv", list(rows[0]), rows)
    _write_manifest(artifact)
    with pytest.raises(ReplayVerifierError, match="unknown receipt"):
        validate_external_panel_artifact(POLICY_PATH, artifact)


def test_external_panel_rejects_live_2026_observation(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    rows = list(csv.DictReader((artifact / "normalised_observations.csv").open(encoding="utf-8", newline="")))
    rows[0]["period"] = "2026-01"
    _write_csv(artifact / "normalised_observations.csv", list(rows[0]), rows)
    _write_manifest(artifact)
    with pytest.raises(ReplayVerifierError, match="live 2026"):
        validate_external_panel_artifact(POLICY_PATH, artifact)


def test_external_panel_rejects_strategy_selection(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    summary = json.loads((artifact / "panel_summary.json").read_text(encoding="utf-8"))
    summary["selected_strategy"] = "T2"
    (artifact / "panel_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(artifact)
    with pytest.raises(ReplayVerifierError, match="select a transition strategy"):
        validate_external_panel_artifact(POLICY_PATH, artifact)


def test_external_panel_rejects_history_rewrite_lineage(tmp_path: Path) -> None:
    artifact = _make_valid_external_panel(tmp_path)
    rows = list(csv.DictReader((artifact / "dual_panel_lineage.csv").open(encoding="utf-8", newline="")))
    rows[0]["may_rewrite_history"] = "true"
    _write_csv(artifact / "dual_panel_lineage.csv", list(rows[0]), rows)
    _write_manifest(artifact)
    with pytest.raises(ReplayVerifierError, match="may_rewrite_history"):
        validate_external_panel_artifact(POLICY_PATH, artifact)


def test_predecessor_v0104_replays() -> None:
    result = validate_predecessor(ROOT)
    assert result["status"] == "ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID"
    assert len(result["policy_sha256"]) == 64
