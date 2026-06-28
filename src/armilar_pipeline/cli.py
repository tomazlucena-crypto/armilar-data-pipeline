from __future__ import annotations

import argparse
from pathlib import Path

from .bundle import create_bundle
from .config import ConfigError, load_config
from .diagnostics import diagnose
from .download import fetch
from .util import write_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-data")
    subcommands = parser.add_subparsers(dest="command", required=True)

    diagnose_cmd = subcommands.add_parser("diagnose", help="Test DNS, TLS and HTTP access")
    diagnose_cmd.add_argument("--config", default="config/sources.json")
    diagnose_cmd.add_argument("--output", default="run/diagnostics.json")

    fetch_cmd = subcommands.add_parser("fetch", help="Download configured data sources")
    fetch_cmd.add_argument("--config", default="config/sources.json")
    fetch_cmd.add_argument("--run-dir", default="run")
    fetch_cmd.add_argument("--cache-dir", default=".cache/armilar")

    bundle_cmd = subcommands.add_parser("bundle", help="Create an immutable ZIP bundle")
    bundle_cmd.add_argument("--run-dir", default="run")
    bundle_cmd.add_argument("--output-dir", default="artifacts")

    run_cmd = subcommands.add_parser("run-all", help="Diagnose, fetch and bundle")
    run_cmd.add_argument("--config", default="config/sources.json")
    run_cmd.add_argument("--run-dir", default="run")
    run_cmd.add_argument("--cache-dir", default=".cache/armilar")
    run_cmd.add_argument("--output-dir", default="artifacts")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "diagnose":
            config = load_config(args.config)
            report = diagnose(config)
            write_json(args.output, report)
            print(f"Diagnostics written to {args.output}")
            return 0

        if args.command == "fetch":
            config = load_config(args.config)
            manifest = fetch(config, args.run_dir, args.cache_dir)
            manifest_path = Path(args.run_dir) / "manifest.json"
            write_json(manifest_path, manifest)
            print(f"Manifest written to {manifest_path}")
            print(f"Operational status: {manifest['operational_status']}")
            return 0

        if args.command == "bundle":
            bundle_path = create_bundle(args.run_dir, args.output_dir)
            print(f"Bundle written to {bundle_path}")
            return 0

        if args.command == "run-all":
            config = load_config(args.config)
            run_dir = Path(args.run_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "diagnostics.json", diagnose(config))
            manifest = fetch(config, run_dir, args.cache_dir)
            write_json(run_dir / "manifest.json", manifest)
            bundle_path = create_bundle(run_dir, args.output_dir)
            print(f"Operational status: {manifest['operational_status']}")
            print(f"Bundle written to {bundle_path}")
            return 0
    except (ConfigError, OSError, RuntimeError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2

    return 2
