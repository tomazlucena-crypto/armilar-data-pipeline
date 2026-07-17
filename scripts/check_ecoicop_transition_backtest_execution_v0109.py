from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "armilar_backtest" / "ecoicop_transition_backtest_execution_v0109.py"
POLICY_PATH = ROOT / "config" / "ecoicop_transition_backtest_execution_v0109.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("ecoicop_transition_backtest_execution_v0109_check", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v0.10.9 transition backtest execution module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load_module()
    try:
        policy = module.TransitionBacktestExecutionPolicy.load(POLICY_PATH)
        predecessor = module.validate_predecessor(ROOT)
        protocol = module.load_protocol_summary(ROOT / module.DEFAULT_PROTOCOL_POLICY)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="armilar-v0109-check-") as temp:
            temp_path = Path(temp)
            readiness = module._build_fixture_readiness(ROOT, temp_path)
            result_dir = temp_path / "result"
            report = module.create_transition_backtest_result(
                POLICY_PATH,
                readiness,
                result_dir,
                repo_root=ROOT,
                repository_commit="fixture-v0109-check",
                created_at="2026-07-10T00:00:00Z",
            )
    except module.TransitionBacktestExecutionError as exc:
        print(f"ECOICOP_TRANSITION_BACKTEST_EXECUTION_V0109_INVALID: {exc}", file=sys.stderr)
        return 1

    print(module.STATUS)
    print(f"policy_sha256={policy.policy_sha256}")
    print(f"predecessor_status={predecessor['status']}")
    print(f"predecessor_policy_sha256={predecessor['policy_sha256']}")
    print(f"protocol_status={protocol['protocol_status']}")
    print(f"strategy_count={len(protocol['strategy_ids'])}")
    print(f"metric_count={protocol['metric_count']}")
    print(f"fixture_result_status={report['execution_status']}")
    print(f"fixture_metric_row_count={report['metric_row_count']}")
    print(f"fixture_execution_completed={report['fixture_execution_completed']}")
    print(f"empirical_transition_backtest_executed={report['empirical_transition_backtest_executed']}")
    print(f"backtest_execution_claim_allowed={report['backtest_execution_claim_allowed']}")
    print(f"selected_strategy={report['selected_strategy']}")
    print(f"result_interpretation_allowed={report['result_interpretation_allowed']}")
    print(f"panel_verified_gate_open={report['panel_verified_gate_open']}")
    print(f"public_latest_modified={report['public_latest_modified']}")
    print(f"official_bytes_committed_to_repository={report['official_bytes_committed_to_repository']}")
    print(f"next_milestone={module.NEXT_MILESTONE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
