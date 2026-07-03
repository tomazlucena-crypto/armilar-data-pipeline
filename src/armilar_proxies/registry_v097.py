"""Public API and CLI for the ARMILAR v0.9.7 proxy registry and acquisition layer."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .acquisition_v097 import acquire_source, replay_snapshot, verify_ledger, verify_manifest
from .core_v097 import (
    ProxyRegistryError,
    UrlLibFetcher,
    canonical_json_bytes,
    canonical_text_bytes,
    decimal_text,
    load_registry,
    parse_month,
    parse_quarter,
    parse_week,
    registry_hash,
    sha256_bytes,
    sha256_file,
    source_by_id,
    utc_timestamp,
    validate_raw_magic,
    validate_registry,
)
from .parsers_v097 import (
    OBSERVATION_COLUMNS,
    csv_bytes,
    parse_ec_oil_bulletin_xlsx,
    parse_eurostat_jsonstat,
    parse_fao_ffpi_csv,
    parse_world_bank_pink_sheet_xlsx,
    sort_observations,
)

def _command_validate(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.registry))
    print(json.dumps({
        "status": "PROXY_SOURCE_REGISTRY_V097_VALID",
        "registry_id": registry["registry_id"],
        "registry_version": registry["registry_version"],
        "source_count": len(registry["sources"]),
        "registry_sha256": registry_hash(Path(args.registry)),
    }, indent=2, sort_keys=True))
    return 0


def _command_list(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.registry))
    print(json.dumps(registry["sources"], indent=2, sort_keys=True))
    return 0


def _command_acquire(args: argparse.Namespace) -> int:
    result = acquire_source(
        registry_path=Path(args.registry),
        source_id=args.source_id,
        output_root=Path(args.output_root),
        retrieved_at=args.retrieved_at,
        published_at=args.published_at,
    )
    print(json.dumps({"status": "PROXY_SNAPSHOT_ACQUIRED", "snapshot_dir": str(result)}, indent=2, sort_keys=True))
    return 0


def _command_replay(args: argparse.Namespace) -> int:
    print(json.dumps(replay_snapshot(registry_path=Path(args.registry), snapshot_dir=Path(args.snapshot_dir)), indent=2, sort_keys=True))
    return 0


def _command_verify_ledger(args: argparse.Namespace) -> int:
    entries = verify_ledger(Path(args.ledger))
    print(json.dumps({
        "status": "PROXY_SNAPSHOT_LEDGER_VALID",
        "entry_count": len(entries),
        "last_entry_hash": entries[-1]["entry_hash"] if entries else None,
    }, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ARMILAR v0.9.7 research proxy registry and acquisition")
    parser.add_argument("--registry", default="config/proxy_source_registry_v097.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-registry")
    validate.set_defaults(func=_command_validate)
    list_sources = subparsers.add_parser("list-sources")
    list_sources.set_defaults(func=_command_list)
    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("source_id")
    acquire.add_argument("--output-root", required=True)
    acquire.add_argument("--retrieved-at", required=True)
    acquire.add_argument("--published-at")
    acquire.set_defaults(func=_command_acquire)
    replay = subparsers.add_parser("replay")
    replay.add_argument("snapshot_dir")
    replay.set_defaults(func=_command_replay)
    ledger = subparsers.add_parser("verify-ledger")
    ledger.add_argument("ledger")
    ledger.set_defaults(func=_command_verify_ledger)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ProxyRegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
