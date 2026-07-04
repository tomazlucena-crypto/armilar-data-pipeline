"""CLI and public API for ARMILAR v0.9.9 point-in-time proxy features."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .feature_builder_v099 import build_feature_panel, verify_feature_bundle
from .feature_compare_v099 import build_feature_comparison, verify_feature_comparison_bundle
from .feature_core_v099 import ProxyFeatureError, load_policy, policy_hash


def _command_validate_policy(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    print(
        json.dumps(
            {
                "status": "PROXY_FEATURE_MAPPING_POLICY_V099_VALID",
                "contract_id": policy["contract_id"],
                "contract_version": policy["contract_version"],
                "mapping_rule_count": len(policy["category_mappings"]),
                "policy_sha256": policy_hash(Path(args.policy)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _command_build(args: argparse.Namespace) -> int:
    output = build_feature_panel(
        information_set_dir=Path(args.information_set_dir),
        policy_path=Path(args.policy),
        basket_path=Path(args.basket),
        output_dir=Path(args.output_dir),
    )
    summary = verify_feature_bundle(output)
    print(json.dumps({"feature_dir": str(output), **summary}, indent=2, sort_keys=True))
    return 0


def _command_verify(args: argparse.Namespace) -> int:
    print(json.dumps(verify_feature_bundle(Path(args.feature_dir)), indent=2, sort_keys=True))
    return 0


def _command_compare(args: argparse.Namespace) -> int:
    output = build_feature_comparison(
        earlier_feature_dir=Path(args.earlier_feature_dir),
        later_feature_dir=Path(args.later_feature_dir),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps({"comparison_dir": str(output), **verify_feature_comparison_bundle(output)}, indent=2, sort_keys=True))
    return 0


def _command_verify_comparison(args: argparse.Namespace) -> int:
    print(json.dumps(verify_feature_comparison_bundle(Path(args.comparison_dir)), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ARMILAR v0.9.9 mapped point-in-time proxy features")
    parser.add_argument("--policy", default="config/proxy_feature_mapping_v099.json")
    parser.add_argument("--basket", default="basket/ARMILAR_RESEARCH_CORE_V1.csv")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-policy")
    validate.set_defaults(func=_command_validate_policy)

    build = subparsers.add_parser("build")
    build.add_argument("--information-set-dir", required=True)
    build.add_argument("--output-dir", required=True)
    build.set_defaults(func=_command_build)

    verify = subparsers.add_parser("verify")
    verify.add_argument("feature_dir")
    verify.set_defaults(func=_command_verify)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--earlier-feature-dir", required=True)
    compare.add_argument("--later-feature-dir", required=True)
    compare.add_argument("--output-dir", required=True)
    compare.set_defaults(func=_command_compare)

    verify_comparison = subparsers.add_parser("verify-comparison")
    verify_comparison.add_argument("comparison_dir")
    verify_comparison.set_defaults(func=_command_verify_comparison)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ProxyFeatureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
