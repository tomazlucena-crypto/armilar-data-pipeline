from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import BuildError, build_release, load_cells


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-global-weights")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build a complete experimental world-weight release")
    build.add_argument("--input", type=Path, required=True, help="CSV containing one row per economy-category cell")
    build.add_argument("--output", type=Path, required=True, help="Output directory")
    build.add_argument("--release-id", default="ARM-WEIGHTS-GLOBAL-RESEARCH")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            summary = build_release(load_cells(args.input), args.output, release_id=args.release_id)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
