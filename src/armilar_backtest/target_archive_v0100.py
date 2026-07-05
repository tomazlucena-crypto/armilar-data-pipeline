"""Build a deterministic cell-level target archive from a verified ARM-O run."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from .core_v0100 import (
    BacktestProtocolError, HUNDRED, PRECISION, ROUNDING, add_months,
    canonical_json_bytes, canonical_utc, csv_bytes, decimal_text,
    directory_manifest_sha256, parse_decimal, parse_utc, read_csv,
    stable_id, verify_manifest, write_manifest, write_transactional,
)
from .protocol_v0100 import ProtocolPolicy

TARGET_COLUMNS = (
    "target_id", "economy_code", "category_code", "target_period",
    "target_metric", "target_value", "target_value_unrounded",
    "target_available_at", "current_source_published_at",
    "lag_source_published_at", "current_source_vintage_id",
    "lag_source_vintage_id", "arm_o_run_id", "arm_o_vintage_id",
    "arm_o_cutoff_at", "arm_o_manifest_sha256", "evaluation_only",
    "target_archive_claim_allowed", "model_training_allowed",
    "arm_l_use_allowed",
)


def _later_utc(first: str, second: str) -> str:
    return canonical_utc(first if parse_utc(first, "timestamp") >= parse_utc(second, "timestamp") else second, "timestamp")


def _load_arm_o_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    verify_manifest(run_dir)
    summary_path = run_dir / "outputs" / "run_summary.json"
    observations_path = run_dir / "outputs" / "normalised_price_observations.csv"
    if not summary_path.is_file() or not observations_path.is_file():
        raise BacktestProtocolError("ARM-O run lacks canonical outputs")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BacktestProtocolError("invalid ARM-O run summary") from exc
    if summary.get("engine_version") != "0.9.6" or summary.get("series_kind") != "ARM-O":
        raise BacktestProtocolError("target archive requires an ARM-O v0.9.6 run")
    if summary.get("status") != "COMPLETE":
        raise BacktestProtocolError("ARM-O run must be COMPLETE")
    gates = summary.get("release_gates")
    if not isinstance(gates, dict) or any(bool(value) for value in gates.values()):
        raise BacktestProtocolError("ARM-O release gates must remain closed")
    rows = read_csv(observations_path)
    if len(rows) != int(summary.get("normalised_observation_count", -1)):
        raise BacktestProtocolError("ARM-O observation count does not reconcile")
    return summary, rows, directory_manifest_sha256(run_dir)


def build_target_archive(
    *, policy_path: Path, arm_o_run: Path, output_dir: Path, created_at: str,
) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    created_at = canonical_utc(created_at, "created_at")
    summary, observations, run_manifest_sha256 = _load_arm_o_run(arm_o_run)

    by_cell_period: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in observations:
        key = (row["economy_code"], row["category_code"], row["period"])
        if key in by_cell_period:
            raise BacktestProtocolError(f"duplicate ARM-O observation: {key}")
        if row.get("evidence_class", "").upper().find("PROXY") >= 0:
            raise BacktestProtocolError("ARM-O target archive cannot contain proxy price evidence")
        by_cell_period[key] = row

    targets: list[dict[str, str]] = []
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUNDING
        for (economy, category, period), current in sorted(by_cell_period.items()):
            current_value = parse_decimal(current["price_relative_unrounded"], "price_relative_unrounded")
            for metric, lag in (("MONTHLY_CHANGE_PCT", -1), ("YEAR_OVER_YEAR_CHANGE_PCT", -12)):
                lag_period = add_months(period, lag)
                previous = by_cell_period.get((economy, category, lag_period))
                if previous is None:
                    continue
                previous_value = parse_decimal(previous["price_relative_unrounded"], "lag price_relative_unrounded")
                if previous_value <= 0:
                    raise BacktestProtocolError("lagged ARM-O relative must be positive")
                target_value = (current_value / previous_value - Decimal(1)) * HUNDRED
                available_at = _later_utc(current["published_at"], previous["published_at"])
                target_id = stable_id(
                    "ARMILAR_TARGET_V0100", economy, category, period, metric,
                    summary["run_id"], available_at,
                )
                targets.append({
                    "target_id": target_id,
                    "economy_code": economy,
                    "category_code": category,
                    "target_period": period,
                    "target_metric": metric,
                    "target_value": f"{target_value.quantize(Decimal('0.000000000001')):.12f}",
                    "target_value_unrounded": decimal_text(target_value),
                    "target_available_at": available_at,
                    "current_source_published_at": canonical_utc(current["published_at"], "published_at"),
                    "lag_source_published_at": canonical_utc(previous["published_at"], "published_at"),
                    "current_source_vintage_id": current["source_vintage_id"],
                    "lag_source_vintage_id": previous["source_vintage_id"],
                    "arm_o_run_id": summary["run_id"],
                    "arm_o_vintage_id": summary["vintage_id"],
                    "arm_o_cutoff_at": canonical_utc(summary["cutoff_at"], "arm_o_cutoff_at"),
                    "arm_o_manifest_sha256": run_manifest_sha256,
                    "evaluation_only": "true",
                    "target_archive_claim_allowed": "false",
                    "model_training_allowed": "false",
                    "arm_l_use_allowed": "false",
                })

    if not targets:
        raise BacktestProtocolError("target archive would be empty")

    cell_counts: dict[str, int] = defaultdict(int)
    metric_counts: dict[str, int] = defaultdict(int)
    for row in targets:
        cell_counts[f"{row['economy_code']}:{row['category_code']}"] += 1
        metric_counts[row["target_metric"]] += 1

    archive_summary: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "0.10.0",
        "status": "ARM_O_TARGET_ARCHIVE_V0100_VALID",
        "created_at": created_at,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "arm_o_run_id": summary["run_id"],
        "arm_o_vintage_id": summary["vintage_id"],
        "arm_o_cutoff_at": canonical_utc(summary["cutoff_at"], "arm_o_cutoff_at"),
        "arm_o_manifest_sha256": run_manifest_sha256,
        "target_count": len(targets),
        "cell_count": len(cell_counts),
        "metric_counts": dict(sorted(metric_counts.items())),
        "earliest_target_period": min(row["target_period"] for row in targets),
        "latest_target_period": max(row["target_period"] for row in targets),
        "evaluation_only": True,
        "gates": policy.gates,
    }

    def writer(staging: Path) -> None:
        (staging / "cell_targets.csv").write_bytes(csv_bytes(targets, TARGET_COLUMNS))
        (staging / "target_archive_summary.json").write_bytes(canonical_json_bytes(archive_summary))
        write_manifest(staging)

    write_transactional(output_dir, writer)
    verify_target_archive(output_dir, policy_path=policy_path)
    return archive_summary


def verify_target_archive(path: Path, *, policy_path: Path) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    verify_manifest(path)
    try:
        summary = json.loads((path / "target_archive_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestProtocolError("invalid target archive summary") from exc
    if summary.get("status") != "ARM_O_TARGET_ARCHIVE_V0100_VALID":
        raise BacktestProtocolError("unexpected target archive status")
    if summary.get("policy_id") != policy.policy_id or summary.get("policy_version") != policy.policy_version:
        raise BacktestProtocolError("target archive policy mismatch")
    if summary.get("gates") != policy.gates or summary.get("evaluation_only") is not True:
        raise BacktestProtocolError("target archive gates or role mismatch")
    rows = read_csv(path / "cell_targets.csv")
    if len(rows) != summary.get("target_count"):
        raise BacktestProtocolError("target archive row count mismatch")
    seen: set[str] = set()
    by_key: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if set(row) != set(TARGET_COLUMNS):
            raise BacktestProtocolError("target archive columns mismatch")
        if row["target_id"] in seen:
            raise BacktestProtocolError("duplicate target_id")
        seen.add(row["target_id"])
        key = (row["economy_code"], row["category_code"], row["target_period"], row["target_metric"])
        if key in by_key:
            raise BacktestProtocolError("duplicate target key")
        by_key.add(key)
        if row["target_metric"] not in policy.target_metrics:
            raise BacktestProtocolError("unexpected target metric")
        if row["evaluation_only"] != "true" or row["target_archive_claim_allowed"] != "false":
            raise BacktestProtocolError("target archive role was promoted")
        if row["model_training_allowed"] != "false" or row["arm_l_use_allowed"] != "false":
            raise BacktestProtocolError("target archive forbidden gate opened")
        parse_utc(row["target_available_at"], "target_available_at")
        parse_decimal(row["target_value_unrounded"], "target_value_unrounded")
    if len({(row["economy_code"], row["category_code"]) for row in rows}) != summary.get("cell_count"):
        raise BacktestProtocolError("target archive cell count mismatch")
    return summary
