"""Run the single local official-data gate for v0.8.7."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from armilar_prices.eurostat_vertical import EurostatVerticalError
from armilar_prices.v087_gate import run_official_gate


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument("--snapshot-dir", type=Path)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--report", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.repo_root.resolve()
    base = root / "artifacts" / "v087"
    snapshot = args.snapshot_dir or base / "eurostat_snapshot"
    output = args.output_dir or base / "eurostat_vertical"
    report = args.report or base / "OFFICIAL_GATE_REPORT.json"
    try:
        payload = run_official_gate(
            policy_path=root / "config" / "eurostat_vertical_v087.json",
            weights_path=root / "public" / "latest" / "weights_observed_universe.csv",
            public_latest_dir=root / "public" / "latest",
            snapshot_dir=snapshot,
            output_dir=output,
            report_path=report,
        )
    except EurostatVerticalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
