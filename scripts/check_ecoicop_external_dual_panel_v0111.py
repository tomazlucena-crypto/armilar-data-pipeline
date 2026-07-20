from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "armilar_backtest" / "ecoicop_external_dual_panel_v0111.py"
POLICY_PATH = ROOT / "config" / "ecoicop_external_dual_panel_v0111.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("ecoicop_external_dual_panel_v0111_check", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v0.11.1 external dual-panel intake module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_fixture_external_panel(module, root: Path, temp: Path) -> tuple[Path, Path]:
    materialization = module._load_module(root, "src/armilar_backtest/ecoicop_dual_panel_materialization_v0106.py", "ecoicop_dual_panel_materialization_v0106_fixture_for_v0111_check")
    attachment = module._load_module(root, "src/armilar_backtest/ecoicop_dual_panel_attachment_v0107.py", "ecoicop_dual_panel_attachment_v0107_fixture_for_v0111_check")
    staging = temp / "staging"
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
    artifact = temp / "artifact"
    materialization.materialize_external_panel(
        root / "config" / "ecoicop_dual_panel_materialization_v0106.json",
        root / "config" / "ecoicop_dual_panel_replay_v0105.json",
        staging,
        artifact,
        created_at="2026-07-10T00:00:00Z",
        repo_root=root,
    )
    attachment_dir = temp / "attachment"
    attachment.create_attachment_descriptor(
        root / "config" / "ecoicop_dual_panel_attachment_v0107.json",
        artifact,
        attachment_dir,
        repo_root=root,
        repository_commit="fixture-v0111-check",
        artifact_uri="external://fixture-v0111-panel",
        created_at="2026-07-10T00:00:00Z",
    )
    return attachment_dir, artifact


def main() -> int:
    module = _load_module()
    try:
        policy = module.ExternalDualPanelIntakePolicy.load(POLICY_PATH)
        predecessor = module.validate_predecessor(ROOT)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="armilar-v0111-check-") as temp_dir:
            temp = Path(temp_dir)
            attachment_dir, artifact_dir = _build_fixture_external_panel(module, ROOT, temp)
            intake = module.create_external_panel_intake_report(
                POLICY_PATH,
                attachment_dir,
                artifact_dir,
                temp / "intake",
                repo_root=ROOT,
                repository_commit="fixture-v0111-check",
                created_at="2026-07-10T00:00:00Z",
            )
    except module.ExternalDualPanelIntakeError as exc:
        print(f"ECOICOP_EXTERNAL_DUAL_PANEL_V0111_INVALID: {exc}", file=sys.stderr)
        return 1

    print(module.STATUS)
    print(f"policy_sha256={policy.policy_sha256}")
    print(f"predecessor_status={predecessor['status']}")
    print(f"predecessor_fixture_status={predecessor['fixture_status']}")
    print(f"strategy_count={len(predecessor['strategy_ids'])}")
    print(f"metric_count={predecessor['metric_count']}")
    print(f"fixture_intake_status={intake['intake_status']}")
    print(f"fixture_attachment_status={intake['attachment_status']}")
    print(f"fixture_artifact_replay_status={intake['artifact_replay_status']}")
    print(f"fixture_observation_count={intake['observation_count']}")
    print(f"external_verified_panel_available={intake['external_verified_panel_available']}")
    print(f"external_result_artifact_available={intake['external_result_artifact_available']}")
    print(f"empirical_transition_backtest_executed={intake['empirical_transition_backtest_executed']}")
    print(f"backtest_execution_claim_allowed={intake['backtest_execution_claim_allowed']}")
    print(f"selected_strategy={intake['selected_strategy']}")
    print(f"panel_verified_gate_open={intake['panel_verified_gate_open']}")
    print(f"public_latest_modified={intake['public_latest_modified']}")
    print(f"official_bytes_committed_to_repository={intake['official_bytes_committed_to_repository']}")
    print(f"blocking_reason={intake['blocking_reason']}")
    print(f"next_milestone={module.NEXT_MILESTONE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
