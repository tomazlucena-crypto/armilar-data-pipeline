#!/usr/bin/env python3
"""Check ARMILAR v0.10.7 ECOICOP dual-panel external attachment protocol."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


def _import_module(root: Path):
    import importlib.util
    import sys

    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_attachment_v0107.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_attachment_v0107_check", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v0.10.7 attachment module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _import_materializer(root: Path):
    import importlib.util
    import sys

    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_materialization_v0106.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_materialization_v0106_for_v0107_check", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v0.10.6 materialization module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_minimal_staging(materializer, staging: Path) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    raw = staging / "official_response.xml"
    raw.write_bytes(b"<fixture provider='EUROSTAT' dataset='prc_hicp_midx'/>\n")
    raw_sha = materializer.sha256_file(raw)
    materializer._write_csv(
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
            "query_fingerprint": materializer._sha256_bytes(b"v0107-fixture-query"),
        }],
    )
    materializer._write_csv(
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
    materializer._write_csv(
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
    materializer._write_manifest(staging, "STAGING_MANIFEST.sha256")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    module = _import_module(root)
    materializer = _import_materializer(root)
    policy_path = root / "config" / "ecoicop_dual_panel_attachment_v0107.json"
    policy = module.AttachmentPolicy.load(policy_path)
    predecessor = module.validate_predecessor(root)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        staging = tmp_path / "staging"
        artifact = tmp_path / "artifact"
        attachment = tmp_path / "attachment"
        _make_minimal_staging(materializer, staging)
        materializer.materialize_external_panel(
            root / "config" / "ecoicop_dual_panel_materialization_v0106.json",
            root / "config" / "ecoicop_dual_panel_replay_v0105.json",
            staging,
            artifact,
            created_at="2026-07-09T00:00:00Z",
            repo_root=root,
        )
        artifact_summary = module.validate_materialized_artifact(policy_path, artifact, repo_root=root)
        descriptor = module.create_attachment_descriptor(
            policy_path,
            artifact,
            attachment,
            repo_root=root,
            repository_commit="fixture-v0107",
            artifact_uri="external://fixture/ecoicop-dual-panel-v0107",
            created_at="2026-07-09T00:00:00Z",
        )
        attachment_summary = module.validate_attachment_directory(policy_path, attachment)
    print(module.STATUS)
    print(f"policy_sha256={policy.policy_sha256}")
    print(f"predecessor_status={predecessor['status']}")
    print(f"predecessor_policy_sha256={predecessor['policy_sha256']}")
    print(f"fixture_artifact_replay_status={artifact_summary['artifact_replay_status']}")
    print(f"fixture_artifact_manifest_entry_count={artifact_summary['artifact_manifest_entry_count']}")
    print(f"fixture_attachment_status={descriptor['attachment_status']}")
    print(f"fixture_attachment_manifest_sha256={attachment_summary['attachment_manifest_sha256']}")
    print(f"official_bytes_committed_to_repository={descriptor['official_bytes_committed_to_repository']}")
    print(f"public_latest_modified={descriptor['public_latest_modified']}")
    print(f"panel_verified_gate_open={descriptor['panel_verified_gate_open']}")
    print(f"transition_backtest_executed={descriptor['transition_backtest_executed']}")
    print(f"next_milestone={module.NEXT_MILESTONE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
