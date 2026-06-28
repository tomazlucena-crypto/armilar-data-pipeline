from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .country_adapters import run_country_adapters_only
from .pipeline import run_step2
from .source_probe import run_source_probe_only
from .util import json_default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-data")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-step2", help="Acquire ICP 2021 data and build the Armilar weight matrix candidate")
    run.add_argument("--config", default="config/step2_icp2021.json")
    run.add_argument("--run-dir", default="run")
    run.add_argument("--cache-dir", default=".cache/armilar")
    run.add_argument("--output-dir", default="artifacts")
    run.add_argument("--strict-release", action="store_true", help="Exit non-zero when research_release_allowed is false")
    probe = sub.add_parser("probe-sources", help="Run only the Step 2H0 official-source feasibility probes")
    probe.add_argument("--config", default="config/step2_icp2021.json")
    probe.add_argument("--run-dir", default="run-source-probe")
    probe.add_argument("--cache-dir", default=".cache/armilar")
    country = sub.add_parser("country", help="Run national-source adapters with isolated per-economy failures")
    country.add_argument("economy_codes", nargs="*", help="Optional economy codes such as IND RUT CHN")
    country.add_argument("--config", default="config/step2_icp2021.json")
    country.add_argument("--run-dir", default="run-country")
    country.add_argument("--cache-dir", default=".cache/armilar")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-step2":
        try:
            result = run_step2(args.config, args.run_dir, args.cache_dir, args.output_dir)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=json_default))
        if args.strict_release and not result["research_release_allowed"]:
            return 2
        return 0
    if args.command == "probe-sources":
        try:
            result = run_source_probe_only(
                load_config(args.config),
                run_root=Path(args.run_dir).resolve(),
                cache_root=Path(args.cache_dir).resolve(),
            )
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=json_default))
        return 0
    if args.command == "country":
        try:
            result = run_country_adapters_only(
                load_config(args.config),
                run_root=Path(args.run_dir).resolve(),
                cache_root=Path(args.cache_dir).resolve(),
                economy_codes=args.economy_codes or None,
            )
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=json_default))
        return 0
    return 2
