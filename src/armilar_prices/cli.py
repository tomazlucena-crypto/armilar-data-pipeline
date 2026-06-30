from __future__ import annotations

import argparse
import json
from pathlib import Path

from .index_engine import (
    AggregationMode,
    IndexBuildError,
    calculate_monthly_indices,
    load_core_weights,
    load_global_weights,
    write_index_outputs,
)
from .acquisition import PriceAcquisitionError, acquire_prices
from .normalizer import (
    PriceNormalizationError,
    load_observations,
    normalize_observations,
    write_normalized_outputs,
)
from .registry import RegistryError, load_registry, registry_summary
from .selector import (
    PriceSelectionError,
    load_normalized_prices,
    select_best_prices,
    write_selection_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-prices")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry")
    validate.add_argument("--registry", type=Path, required=True)

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("--registry", type=Path, required=True)
    acquire.add_argument("--output", type=Path, required=True)
    acquire.add_argument("--mode", choices=["replay", "live"], default="replay")
    acquire.add_argument("--fixture-dir", type=Path)
    acquire.add_argument("--reference-period", default="2021-01")

    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("--registry", type=Path, required=True)
    normalize.add_argument("--observations", type=Path, required=True)
    normalize.add_argument("--reference-period", required=True)
    normalize.add_argument("--output", type=Path, required=True)

    select = subparsers.add_parser("select")
    select.add_argument("--normalized", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    calculate = subparsers.add_parser("calculate")
    calculate.add_argument("--weights-global", type=Path, required=True)
    calculate.add_argument("--weights-core", type=Path, required=True)
    calculate.add_argument("--selected-prices", type=Path, required=True)
    calculate.add_argument("--reference-period", required=True)
    calculate.add_argument("--output", type=Path, required=True)
    calculate.add_argument(
        "--aggregation-mode",
        choices=[mode.value for mode in AggregationMode],
        default=AggregationMode.PPP_WEIGHTED_LOCAL_PRICE_RELATIVES.value,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-registry":
            definitions = load_registry(args.registry)
            print(json.dumps(registry_summary(definitions), indent=2, sort_keys=True))
            return 0
        if args.command == "acquire":
            summary = acquire_prices(
                args.registry,
                args.output,
                mode=args.mode,
                fixture_dir=args.fixture_dir,
                reference_period=args.reference_period,
            )
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.command == "normalize":
            definitions = load_registry(args.registry)
            rows, summary = normalize_observations(
                definitions,
                load_observations(args.observations),
                args.reference_period,
            )
            write_normalized_outputs(rows, summary, args.output)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.command == "select":
            rows, audit, summary = select_best_prices(load_normalized_prices(args.normalized))
            write_selection_outputs(rows, audit, summary, args.output)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.command == "calculate":
            index_rows, contributions, evidence, summary = calculate_monthly_indices(
                load_global_weights(args.weights_global),
                load_core_weights(args.weights_core),
                load_normalized_prices(args.selected_prices),
                args.reference_period,
                aggregation_mode=AggregationMode(args.aggregation_mode),
            )
            write_index_outputs(index_rows, contributions, evidence, summary, args.output)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
    except (RegistryError, PriceAcquisitionError, PriceNormalizationError, PriceSelectionError, IndexBuildError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
