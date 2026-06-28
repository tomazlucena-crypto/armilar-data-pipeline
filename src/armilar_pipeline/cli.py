from __future__ import annotations

import argparse
import json
import sys

from .pipeline import run_step2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-data")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-step2", help="Acquire ICP 2021 data and build the Armilar weight matrix candidate")
    run.add_argument("--config", default="config/step2_icp2021.json")
    run.add_argument("--run-dir", default="run")
    run.add_argument("--cache-dir", default=".cache/armilar")
    run.add_argument("--output-dir", default="artifacts")
    run.add_argument("--strict-release", action="store_true", help="Exit non-zero when research_release_allowed is false")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-step2":
        try:
            result = run_step2(args.config, args.run_dir, args.cache_dir, args.output_dir)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.strict_release and not result["research_release_allowed"]:
            return 2
        return 0
    return 2
