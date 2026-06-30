from __future__ import annotations

import argparse
import json
from pathlib import Path

from .imputation import (
    ImputationError,
    complete_research_grid,
    load_constraints,
    load_evidence_cells,
    load_policy,
    load_profiles,
    validate_baselines,
    validation_metrics_by_class_category,
    write_imputation_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-imputation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Build research-only C/D/E imputation candidates")
    run.add_argument("--evidence", type=Path, required=True)
    run.add_argument("--profiles", type=Path, required=True)
    run.add_argument("--constraints", type=Path)
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--validate", action="store_true", help="Also run leave-one-out validation")

    validate = subparsers.add_parser("validate", help="Run leave-one-out validation only")
    validate.add_argument("--evidence", type=Path, required=True)
    validate.add_argument("--profiles", type=Path, required=True)
    validate.add_argument("--policy", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evidence = load_evidence_cells(args.evidence)
        profiles = load_profiles(args.profiles)
        policy = load_policy(args.policy)
        if args.command == "validate":
            predictions, summary = validate_baselines(evidence, profiles, policy)
            write_imputation_outputs([], {"validation_only": True, "monetary_release_allowed": False}, args.output, predictions, summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        constraints = load_constraints(args.constraints)
        predictions = None
        validation_summary = None
        metrics = None
        if args.validate:
            predictions, validation_summary = validate_baselines(evidence, profiles, policy)
            metrics = validation_metrics_by_class_category(predictions)
        completed, run_summary = complete_research_grid(
            evidence, profiles, constraints, policy, validation_metrics=metrics
        )
        write_imputation_outputs(completed, run_summary, args.output, predictions, validation_summary)
        print(json.dumps(run_summary, indent=2, sort_keys=True))
        return 0
    except (ImputationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
