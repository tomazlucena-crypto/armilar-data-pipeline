from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from armilar_pipeline.proxy_audit import build_proxy_error_summaries, normalize_proxy_comparison_rows
from armilar_pipeline.util import write_csv, write_json

COMPARISON_FIELDS = [
    "economy_code", "economy_name", "armilar_category", "aic_ppp", "strict_hfce_ppp",
    "ppp_ratio_hfce_to_aic", "implied_real_expenditure_error_ratio", "status",
    "source_authority", "source_url", "reference_year", "classification", "evidence_note",
]
CATEGORY_FIELDS = [
    "armilar_category", "direct_comparison_count", "economy_count", "category_count",
    "mean_signed_error_ratio", "median_signed_error_ratio", "mean_absolute_error_ratio",
    "median_absolute_error_ratio", "maximum_absolute_error_ratio", "status",
]
ECONOMY_FIELDS = [
    "economy_code", "economy_name", "direct_comparison_count", "economy_count", "category_count",
    "mean_signed_error_ratio", "median_signed_error_ratio", "mean_absolute_error_ratio",
    "median_absolute_error_ratio", "maximum_absolute_error_ratio", "status",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="armilar-proxy-audit")
    parser.add_argument("--comparison-file", required=True)
    parser.add_argument("--output-dir", default="run-proxy-audit/outputs")
    parser.add_argument("--policy", default="config/methodology_policy.json")
    args = parser.parse_args(argv)
    try:
        with Path(args.comparison_file).open("r", encoding="utf-8-sig", newline="") as handle:
            input_rows = list(csv.DictReader(handle))
        policy_payload = json.loads(Path(args.policy).read_text(encoding="utf-8"))
        policy = policy_payload.get("proxy_validation", {})
        normalized = normalize_proxy_comparison_rows(input_rows)
        category_rows, economy_rows, summary = build_proxy_error_summaries(normalized, policy=policy)
        output = Path(args.output_dir).resolve()
        write_csv(output / "proxy_ppp_comparison.csv", COMPARISON_FIELDS, normalized)
        write_csv(output / "proxy_error_by_category.csv", CATEGORY_FIELDS, category_rows)
        write_csv(output / "proxy_error_by_economy.csv", ECONOMY_FIELDS, economy_rows)
        write_json(output / "proxy_validation_summary.json", summary)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
