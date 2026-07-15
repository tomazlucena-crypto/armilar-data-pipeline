from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

STATUS = "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZATION_RUNNER_V0106_VALID"
PREDECESSOR_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID"
MATERIALIZED_STATUS = "ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZED_ARTIFACT_REPLAY_VALID"


class CheckError(RuntimeError):
    pass


def _load_module(root: Path):
    module_path = root / "src" / "armilar_backtest" / "ecoicop_dual_panel_materialization_v0106.py"
    spec = importlib.util.spec_from_file_location("ecoicop_dual_panel_materialization_v0106", module_path)
    if spec is None or spec.loader is None:
        raise CheckError("cannot import v0.10.6 module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_pyproject(root: Path) -> None:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.10.6"' not in text:
        raise CheckError("pyproject.toml version is not 0.10.6")
    if 'armilar-ecoicop-dual-panel-materialize-v0106 = "armilar_backtest.ecoicop_dual_panel_materialization_v0106:main"' not in text:
        raise CheckError("v0.10.6 console script entry missing")


def _validate_workflow(root: Path) -> None:
    text = (root / ".github" / "workflows" / "fetch-data.yml").read_text(encoding="utf-8")
    if "scripts/check_ecoicop_dual_panel_materialization_v0106.py" not in text:
        raise CheckError("workflow does not run v0.10.6 checker")


def _validate_manifest(root: Path) -> None:
    module = _load_module(root)
    manifest_path = root / "config" / "ecoicop_dual_panel_materialization_v0106_files.sha256"
    expected = {
        "RELEASE_NOTES_V0.10.6.md",
        "config/ecoicop_dual_panel_materialization_v0106.json",
        "docs/DECISION_ECOICOP_DUAL_PANEL_MATERIALIZATION_V0106.md",
        "docs/ECOICOP_DUAL_PANEL_MATERIALIZATION_V0106_CONTRACT.md",
        "schemas/ecoicop_dual_panel_materialization_policy_v0106.schema.json",
        "schemas/ecoicop_dual_panel_materialization_summary_v0106.schema.json",
        "scripts/check_ecoicop_dual_panel_materialization_v0106.py",
        "src/armilar_backtest/ecoicop_dual_panel_materialization_v0106.py",
        "tests/test_ecoicop_dual_panel_materialization_v0106.py",
    }
    if not manifest_path.is_file():
        raise CheckError("v0.10.6 manifest missing")
    actual: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ")
        if len(parts) != 2:
            raise CheckError(f"invalid manifest line {line_number}")
        digest, relative = parts
        actual[relative] = digest
    if set(actual) != expected:
        raise CheckError(f"manifest mismatch: missing={sorted(expected-set(actual))}, extra={sorted(set(actual)-expected)}")
    for relative, digest in actual.items():
        if module.sha256_file(root / relative) != digest:
            raise CheckError(f"manifest hash mismatch: {relative}")


def _validate_no_public_latest_diff(root: Path) -> None:
    result = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "public/latest"], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise CheckError(f"cannot inspect public/latest diff: {result.stderr}")
    if result.stdout.strip():
        raise CheckError("v0.10.6 changes public/latest")


def _write_manifest(staging: Path, module) -> None:
    entries = []
    for candidate in sorted(item for item in staging.rglob("*") if item.is_file()):
        relative = candidate.relative_to(staging).as_posix()
        if relative == "STAGING_MANIFEST.sha256":
            continue
        entries.append(f"{module.sha256_file(candidate)}  {relative}")
    (staging / "STAGING_MANIFEST.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")


def _build_check_staging(staging: Path, module) -> None:
    raw = staging / "official_response.xml"
    raw.write_bytes(b"<official><series>PT CP01 2025-12</series></official>\n")
    raw_sha = module.sha256_file(raw)
    raw_size = str(raw.stat().st_size)
    module._write_csv(staging / "staged_receipts.csv", [
        "staged_receipt_id", "dataset_role", "provider", "dataset_code", "request_url", "retrieved_at", "http_status",
        "raw_path", "raw_sha256", "byte_count", "content_type", "classification", "time_window", "query_fingerprint",
    ], [{
        "staged_receipt_id": "SR1",
        "dataset_role": "LEGACY_MONTHLY_INDEX",
        "provider": "Eurostat",
        "dataset_code": "prc_hicp_midx",
        "request_url": "https://example.invalid/eurostat/prc_hicp_midx?checker=1",
        "retrieved_at": "2026-07-09T00:00:00Z",
        "http_status": "200",
        "raw_path": "official_response.xml",
        "raw_sha256": raw_sha,
        "byte_count": raw_size,
        "content_type": "application/xml",
        "classification": "ECOICOP_V1_PRE_2026",
        "time_window": "2025-12/2025-12",
        "query_fingerprint": module._sha256_bytes(b"checker-query"),
    }])
    module._write_csv(staging / "staged_observations.csv", [
        "staged_observation_id", "staged_receipt_id", "dataset_role", "economy", "armilar_code", "classification",
        "category_or_division", "period", "unit", "value", "source_period_type", "parser_version", "quality_status",
    ], [{
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
        "parser_version": "checker-parser-v1",
        "quality_status": "OBSERVED_OFFICIAL",
    }])
    module._write_csv(staging / "staged_coverage.csv", [
        "coverage_id", "economy", "armilar_code", "classification", "category_or_division", "period", "dataset_role", "coverage_status", "staged_observation_id",
    ], [{
        "coverage_id": "C1",
        "economy": "PT",
        "armilar_code": "PRT",
        "classification": "ECOICOP_V1_PRE_2026",
        "category_or_division": "CP01",
        "period": "2025-12",
        "dataset_role": "LEGACY_MONTHLY_INDEX",
        "coverage_status": "OBSERVED",
        "staged_observation_id": "SO1",
    }])
    _write_manifest(staging, module)


def validate_repository(root: Path) -> dict[str, str]:
    root = root.resolve()
    _validate_pyproject(root)
    _validate_workflow(root)
    _validate_manifest(root)
    module = _load_module(root)
    policy_path = root / "config" / "ecoicop_dual_panel_materialization_v0106.json"
    policy = module.MaterializationPolicy.load(policy_path)
    if policy.payload["status"] != STATUS:
        raise CheckError("policy status mismatch")
    if any(bool(value) for value in policy.gates.values()):
        raise CheckError("a v0.10.6 gate is open")
    predecessor = module.validate_predecessor(root)
    if predecessor["status"] != PREDECESSOR_STATUS:
        raise CheckError("predecessor status mismatch")
    with tempfile.TemporaryDirectory(prefix="armilar_v0106_check_") as tmp:
        tmp_root = Path(tmp)
        staging = tmp_root / "staging"
        out = tmp_root / "materialized"
        staging.mkdir()
        _build_check_staging(staging, module)
        staging_summary = module.validate_staging_directory(policy_path, staging)
        materialized_summary = module.materialize_external_panel(
            policy_path,
            root / "config" / "ecoicop_dual_panel_replay_v0105.json",
            staging,
            out,
            created_at="2026-07-09T00:00:00Z",
            repo_root=root,
        )
    if staging_summary["staging_receipt_count"] != 1:
        raise CheckError("checker staging fixture did not validate")
    if materialized_summary["status"] != MATERIALIZED_STATUS:
        raise CheckError("materialized artifact did not validate")
    if materialized_summary["panel_verified_gate_open"] is not False:
        raise CheckError("v0.10.6 must not open the panel verification gate")
    if materialized_summary["transition_backtest_executed"] is not False:
        raise CheckError("v0.10.6 must not execute transition backtest")
    _validate_no_public_latest_diff(root)
    return {
        "status": STATUS,
        "policy_sha256": policy.policy_sha256,
        "predecessor_status": predecessor["status"],
        "predecessor_policy_sha256": predecessor["policy_sha256"],
        "materialized_fixture_status": materialized_summary["status"],
        "materialized_fixture_observation_count": str(materialized_summary["materialized_observation_count"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ARMILAR v0.10.6 ECOICOP dual-panel materialization runner")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = validate_repository(args.root)
    except CheckError as exc:
        raise SystemExit(f"ECOICOP_DUAL_PANEL_MATERIALIZATION_V0106_INVALID: {exc}") from exc
    print(STATUS)
    print(f"policy_sha256={result['policy_sha256']}")
    print(f"predecessor_status={result['predecessor_status']}")
    print(f"predecessor_policy_sha256={result['predecessor_policy_sha256']}")
    print(f"materialized_fixture_status={result['materialized_fixture_status']}")
    print(f"materialized_fixture_observation_count={result['materialized_fixture_observation_count']}")
    print("live_2026_observation_count=0")
    print("panel_verified_gate_open=false")
    print("transition_backtest_executed=false")
    print("next_milestone=V0107_RUN_EXTERNAL_DUAL_PANEL_ACQUISITION_AND_ATTACH_VERIFIED_ARTIFACT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
