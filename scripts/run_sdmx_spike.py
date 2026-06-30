from __future__ import annotations

import argparse
from pathlib import Path

from armilar_prices.sdmx_spike import SPIKE_STATUS_NETWORK_BLOCKED, run_live_smoke, write_spike_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        run_live_smoke(args.output)
    else:
        write_spike_outputs(args.output, status=SPIKE_STATUS_NETWORK_BLOCKED)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
