from __future__ import annotations

import argparse
import json
import sys

from armilar_pipeline.pipeline import run_step2
from armilar_pipeline.util import json_default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="armilar-matrix")
    parser.add_argument("--config", default="config/step2_icp2021.json")
    parser.add_argument("--run-dir", default="run")
    parser.add_argument("--cache-dir", default=".cache/armilar")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--strict-release", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_step2(args.config, args.run_dir, args.cache_dir, args.output_dir)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=json_default))
    return 2 if args.strict_release and not result["research_release_allowed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
