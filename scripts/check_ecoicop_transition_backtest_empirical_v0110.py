from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "armilar_backtest" / "ecoicop_transition_backtest_empirical_v0110.py"
POLICY_PATH = ROOT / "config" / "ecoicop_transition_backtest_empirical_v0110.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("ecoicop_transition_backtest_empirical_v0110_check", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v0.11.0 empirical transition backtest gate module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load_module()
    try:
        policy = module.EmpiricalBacktestGatePolicy.load(POLICY_PATH)
        predecessor = module.validate_predecessor(ROOT)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="armilar-v0110-check-") as temp:
            preflight = module.create_empirical_preflight_report(
                POLICY_PATH,
                Path(temp) / "preflight",
                repo_root=ROOT,
                repository_commit="fixture-v0110-check",
                created_at="2026-07-10T00:00:00Z",
            )
    except module.EmpiricalBacktestGateError as exc:
        print(f"ECOICOP_TRANSITION_BACKTEST_EMPIRICAL_V0110_INVALID: {exc}", file=sys.stderr)
        return 1

    print(module.STATUS)
    print(f"policy_sha256={policy.policy_sha256}")
    print(f"predecessor_status={predecessor['status']}")
    print(f"predecessor_fixture_status={predecessor['fixture_status']}")
    print(f"predecessor_policy_sha256={predecessor['policy_sha256']}")
    print(f"strategy_count={len(predecessor['strategy_ids'])}")
    print(f"metric_count={predecessor['metric_count']}")
    print(f"fixture_preflight_status={preflight['preflight_status']}")
    print(f"fixture_metric_row_count={preflight['metric_row_count']}")
    print(f"external_verified_panel_available={preflight['external_verified_panel_available']}")
    print(f"external_result_artifact_available={preflight['external_result_artifact_available']}")
    print(f"empirical_transition_backtest_executed={preflight['empirical_transition_backtest_executed']}")
    print(f"backtest_execution_claim_allowed={preflight['backtest_execution_claim_allowed']}")
    print(f"selected_strategy={preflight['selected_strategy']}")
    print(f"result_interpretation_allowed={preflight['result_interpretation_allowed']}")
    print(f"panel_verified_gate_open={preflight['panel_verified_gate_open']}")
    print(f"public_latest_modified={preflight['public_latest_modified']}")
    print(f"official_bytes_committed_to_repository={preflight['official_bytes_committed_to_repository']}")
    print(f"blocking_reason={preflight['blocking_reason']}")
    print(f"next_milestone={module.NEXT_MILESTONE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
