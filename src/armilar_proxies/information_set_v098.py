"""CLI and public API for ARMILAR v0.9.8 point-in-time proxy archives."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .archive_builder_v098 import (
    build_archive,
    build_information_set,
    verify_archive_bundle,
    verify_information_set_bundle,
)
from .archive_core_v098 import ProxyInformationSetError, load_policy, policy_hash


def _command_validate_policy(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    print(json.dumps({
        "status": "PROXY_INFORMATION_SET_POLICY_V098_VALID",
        "contract_id": policy["contract_id"],
        "contract_version": policy["contract_version"],
        "policy_sha256": policy_hash(Path(args.policy)),
    }, indent=2, sort_keys=True))
    return 0


def _command_build_archive(args: argparse.Namespace) -> int:
    output = build_archive(
        registry_path=Path(args.registry),
        policy_path=Path(args.policy),
        snapshot_root=Path(args.snapshot_root),
        output_dir=Path(args.output_dir),
        previous_archive_dir=None,
    )
    summary = verify_archive_bundle(output)
    print(json.dumps({"status": summary["status"], "archive_dir": str(output), **summary}, indent=2, sort_keys=True))
    return 0


def _command_extend_archive(args: argparse.Namespace) -> int:
    output = build_archive(
        registry_path=Path(args.registry),
        policy_path=Path(args.policy),
        snapshot_root=Path(args.snapshot_root),
        output_dir=Path(args.output_dir),
        previous_archive_dir=Path(args.previous_archive),
    )
    summary = verify_archive_bundle(output)
    print(json.dumps({"status": summary["status"], "archive_dir": str(output), **summary}, indent=2, sort_keys=True))
    return 0


def _command_build_cutoff(args: argparse.Namespace) -> int:
    output = build_information_set(
        archive_dir=Path(args.archive_dir),
        cutoff=args.cutoff,
        output_dir=Path(args.output_dir),
    )
    summary = verify_information_set_bundle(output)
    print(json.dumps({"status": summary["status"], "information_set_dir": str(output), **summary}, indent=2, sort_keys=True))
    return 0


def _command_verify_archive(args: argparse.Namespace) -> int:
    print(json.dumps(verify_archive_bundle(Path(args.archive_dir)), indent=2, sort_keys=True))
    return 0


def _command_verify_cutoff(args: argparse.Namespace) -> int:
    print(json.dumps(verify_information_set_bundle(Path(args.information_set_dir)), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ARMILAR v0.9.8 first-seen proxy information sets")
    parser.add_argument("--registry", default="config/proxy_source_registry_v097.json")
    parser.add_argument("--policy", default="config/proxy_information_set_v098.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-policy")
    validate.set_defaults(func=_command_validate_policy)

    archive = subparsers.add_parser("build-archive")
    archive.add_argument("--snapshot-root", required=True)
    archive.add_argument("--output-dir", required=True)
    archive.set_defaults(func=_command_build_archive)

    extend = subparsers.add_parser("extend-archive")
    extend.add_argument("--snapshot-root", required=True)
    extend.add_argument("--previous-archive", required=True)
    extend.add_argument("--output-dir", required=True)
    extend.set_defaults(func=_command_extend_archive)

    cutoff = subparsers.add_parser("build-cutoff")
    cutoff.add_argument("--archive-dir", required=True)
    cutoff.add_argument("--cutoff", required=True)
    cutoff.add_argument("--output-dir", required=True)
    cutoff.set_defaults(func=_command_build_cutoff)

    verify_archive = subparsers.add_parser("verify-archive")
    verify_archive.add_argument("archive_dir")
    verify_archive.set_defaults(func=_command_verify_archive)

    verify_cutoff = subparsers.add_parser("verify-cutoff")
    verify_cutoff.add_argument("information_set_dir")
    verify_cutoff.set_defaults(func=_command_verify_cutoff)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ProxyInformationSetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
