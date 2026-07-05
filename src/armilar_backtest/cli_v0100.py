"""CLI for ARMILAR v0.10.0 research target alignment and baseline protocol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .alignment_v0100 import build_alignment, verify_alignment
from .baseline_v0100 import evaluate_baselines, verify_baseline_evaluation
from .protocol_v0100 import ProtocolPolicy
from .target_archive_v0100 import build_target_archive, verify_target_archive


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="armilar-backtest-v0100")
    result.add_argument(
        "--policy", type=Path,
        default=Path("config/point_in_time_backtest_protocol_v0100.json"),
    )
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-policy")

    target = sub.add_parser("build-target-archive")
    target.add_argument("--arm-o-run", type=Path, required=True)
    target.add_argument("--output", type=Path, required=True)
    target.add_argument("--created-at", required=True)

    target_verify = sub.add_parser("verify-target-archive")
    target_verify.add_argument("--archive", type=Path, required=True)

    align = sub.add_parser("align")
    align.add_argument("--target-archive", type=Path, required=True)
    align.add_argument("--feature-bundle", type=Path, action="append", required=True)
    align.add_argument("--output", type=Path, required=True)
    align.add_argument("--created-at", required=True)

    align_verify = sub.add_parser("verify-alignment")
    align_verify.add_argument("--target-archive", type=Path, required=True)
    align_verify.add_argument("--alignment", type=Path, required=True)

    baseline = sub.add_parser("evaluate-baselines")
    baseline.add_argument("--target-archive", type=Path, required=True)
    baseline.add_argument("--alignment", type=Path, required=True)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.add_argument("--created-at", required=True)

    baseline_verify = sub.add_parser("verify-baselines")
    baseline_verify.add_argument("--target-archive", type=Path, required=True)
    baseline_verify.add_argument("--alignment", type=Path, required=True)
    baseline_verify.add_argument("--evaluation", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "validate-policy":
        policy = ProtocolPolicy.load(args.policy)
        _print({
            "status": "POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID",
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "gates": policy.gates,
        })
    elif args.command == "build-target-archive":
        _print(build_target_archive(
            policy_path=args.policy, arm_o_run=args.arm_o_run,
            output_dir=args.output, created_at=args.created_at,
        ))
    elif args.command == "verify-target-archive":
        _print(verify_target_archive(args.archive, policy_path=args.policy))
    elif args.command == "align":
        _print(build_alignment(
            policy_path=args.policy, target_archive=args.target_archive,
            feature_bundles=args.feature_bundle, output_dir=args.output,
            created_at=args.created_at,
        ))
    elif args.command == "verify-alignment":
        _print(verify_alignment(
            args.alignment, policy_path=args.policy,
            target_archive=args.target_archive,
        ))
    elif args.command == "evaluate-baselines":
        _print(evaluate_baselines(
            policy_path=args.policy, target_archive=args.target_archive,
            alignment=args.alignment, output_dir=args.output,
            created_at=args.created_at,
        ))
    elif args.command == "verify-baselines":
        _print(verify_baseline_evaluation(
            args.evaluation, policy_path=args.policy,
            target_archive=args.target_archive, alignment=args.alignment,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
