from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import BuildError, build_release, load_cells
from .staging import load_strict_matrix, write_evidence_cells


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-global-weights")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a complete experimental world-weight release")
    build.add_argument("--input", type=Path, required=True, help="CSV containing one row per economy-category cell")
    build.add_argument("--output", type=Path, required=True, help="Output directory")
    build.add_argument("--release-id", default="ARM-WEIGHTS-GLOBAL-RESEARCH")

    stage = subparsers.add_parser("stage-strict", help="Convert strict Step 2 matrix rows into canonical evidence cells")
    stage.add_argument("--matrix", type=Path, required=True, help="economy_category_matrix_weight_eligible.csv")
    stage.add_argument("--output", type=Path, required=True, help="Output directory")
    stage.add_argument("--model-version", default="strict-staging-v0.7.1")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            summary = build_release(load_cells(args.input), args.output, release_id=args.release_id)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.command == "stage-strict":
            rows = write_evidence_cells(
                load_strict_matrix(args.matrix, model_version=args.model_version),
                args.output,
            )
            print(
                json.dumps(
                    {
                        "evidence_cell_count": len(rows),
                        "output_dir": str(args.output),
                        "monetary_release_allowed": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
