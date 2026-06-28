from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .source_probe import run_source_probe_only
from .util import json_default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="armilar-source-probe")
    parser.add_argument("--config", default="config/step2_icp2021.json")
    parser.add_argument("--run-dir", default="run-source-probe")
    parser.add_argument("--cache-dir", default=".cache/armilar")
    args = parser.parse_args(argv)
    try:
        summary = run_source_probe_only(
            load_config(args.config),
            run_root=Path(args.run_dir).resolve(),
            cache_root=Path(args.cache_dir).resolve(),
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=json_default))
    return 0
