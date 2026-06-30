from __future__ import annotations

import argparse
import json
from pathlib import Path

from .release_gate import ReleaseGateError, evaluate_and_optionally_build


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-global-release")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--validation-summary", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-when-eligible", action="store_true")
    parser.add_argument("--release-id", default="ARM-WEIGHTS-GLOBAL-RESEARCH")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        decision = evaluate_and_optionally_build(
            evidence_path=args.evidence,
            validation_summary_path=args.validation_summary,
            policy_path=args.policy,
            output_dir=args.output,
            build_when_eligible=args.build_when_eligible,
            release_id=args.release_id,
        )
    except (ReleaseGateError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
