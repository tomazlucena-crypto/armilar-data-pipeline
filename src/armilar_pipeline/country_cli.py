from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .country_adapters import run_country_adapters_only
from .util import json_default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="armilar-country")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire", help="Acquire and parse isolated national adapters")
    acquire.add_argument("economy_codes", nargs="*", help="Optional economy codes such as IND RUT CHN")
    acquire.add_argument("--config", default="config/step2_icp2021.json")
    acquire.add_argument("--run-dir", default="run-country")
    acquire.add_argument("--cache-dir", default=".cache/armilar")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "acquire":
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


if __name__ == "__main__":
    raise SystemExit(main())
