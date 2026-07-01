#!/usr/bin/env python3
"""Run the bounded local v0.8.8 backtest gate without network access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from armilar_prices.backtest_v088 import build_backtest, verify_manifest


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def hash_tree(root: Path) -> Mapping[str, Any]:
    files = []
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": sha256(path.read_bytes()),
                    }
                )
    return {
        "root_exists": root.exists(),
        "file_count": len(files),
        "tree_sha256": sha256(canonical(files)),
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("config/backtest_v088.json"))
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("artifacts/v087/eurostat_vertical"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/v088/minimum_backtest"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/v088/BACKTEST_GATE_REPORT.json"),
    )
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    policy = (repo / args.policy).resolve() if not args.policy.is_absolute() else args.policy
    input_dir = (repo / args.input_dir).resolve() if not args.input_dir.is_absolute() else args.input_dir
    output_dir = (repo / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    report = (repo / args.report).resolve() if not args.report.is_absolute() else args.report
    latest = repo / "public" / "latest"

    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"BACKTEST_OUTPUT_NOT_EMPTY: {output_dir}")
    if report.exists():
        raise SystemExit(f"BACKTEST_GATE_REPORT_EXISTS: {report}")

    before = hash_tree(latest)
    summary = build_backtest(policy, input_dir, output_dir)
    verify_manifest(output_dir)
    after = hash_tree(latest)
    if before != after:
        raise SystemExit("PUBLIC_LATEST_MUTATED")
    if summary.get("status") != "MINIMUM_BACKTEST_COMPLETED_WITH_VINTAGE_LIMITATION":
        raise SystemExit(f"BACKTEST_STATUS_INVALID: {summary.get('status')}")
    if summary.get("publication_aware") is not False:
        raise SystemExit("VINTAGE_CLAIM_UNSUPPORTED")
    if summary.get("research_release_allowed") is not False:
        raise SystemExit("RESEARCH_RELEASE_GATE_WEAKENED")
    if summary.get("monetary_release_allowed") is not False:
        raise SystemExit("MONETARY_RELEASE_GATE_WEAKENED")

    top_path = output_dir / "top_three_error_sources.json"
    top = json.loads(top_path.read_text(encoding="utf-8"))
    if len(top.get("top_three", [])) != 3:
        raise SystemExit("TOP_THREE_NOT_IDENTIFIABLE")

    payload = {
        "gate_schema_version": "1.0",
        "gate_status": "MINIMUM_BACKTEST_GATE_PASSED_WITH_VINTAGE_LIMITATION",
        "policy_version": summary["policy_version"],
        "universe_id": summary["universe_id"],
        "vintage_mode": summary["vintage_mode"],
        "publication_aware": False,
        "common_case_count_per_model": summary["common_case_count_per_model"],
        "total_case_rows": summary["total_case_rows"],
        "input_dir": input_dir.as_posix(),
        "input_manifest_sha256": summary["input_manifest_sha256"],
        "output_dir": output_dir.as_posix(),
        "output_manifest_sha256": sha256((output_dir / "MANIFEST.sha256").read_bytes()),
        "top_three_error_sources": top["top_three"],
        "public_latest_before": before,
        "public_latest_after": after,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
        "limitations": [
            summary["vintage_limitation"],
            summary["official_headline_comparison_reason"],
            "FX sensitivity is unavailable because the primary index excludes current FX and no vintage-aligned FX panel is supplied.",
            "Imputed-economy sensitivity is unavailable because the declared input universe has no imputed economies.",
        ],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_bytes(canonical(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
