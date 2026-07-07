"""Deterministic no-training baseline diagnostics for ARMILAR v0.10.0."""
from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from .alignment_v0100 import verify_alignment
from .core_v0100 import (
    BacktestProtocolError, PRECISION, ROUNDING, ZERO, add_months,
    canonical_json_bytes, canonical_utc, csv_bytes, decimal_text,
    directory_manifest_sha256, fixed_decimal_text, parse_decimal, parse_utc,
    read_csv, stable_id, verify_manifest, write_manifest, write_transactional,
)
from .protocol_v0100 import ProtocolPolicy
from .target_archive_v0100 import verify_target_archive

PREDICTION_COLUMNS = (
    "prediction_id", "forecast_case_id", "baseline_id", "cutoff",
    "horizon_months", "target_period", "economy_code", "category_code",
    "target_metric", "prediction_value", "prediction_value_unrounded",
    "target_value", "target_value_unrounded", "error", "absolute_error",
    "squared_error", "baseline_source_target_id", "prediction_available",
    "diagnostic_only", "model_training_allowed", "model_selection_allowed",
    "arm_l_use_allowed",
)

METRIC_COLUMNS = (
    "baseline_id", "target_metric", "horizon_months", "category_code",
    "case_count", "prediction_count", "missing_prediction_count",
    "coverage_rate", "mean_error", "mae", "rmse",
    "diagnostic_only", "model_selection_allowed", "out_of_sample_claim_allowed",
)

READINESS_COLUMNS = (
    "economy_code", "category_code", "target_metric", "horizon_months",
    "distinct_cutoff_count", "case_count", "primary_feature_case_count",
    "complete_baseline_case_count", "minimum_distinct_cutoffs_required",
    "minimum_cases_required", "readiness_status", "backtest_claim_allowed",
    "model_training_allowed",
)


def _target_history(target_archive: Path) -> tuple[list[dict[str, str]], dict[tuple[str, str, str, str], dict[str, str]]]:
    rows = read_csv(target_archive / "cell_targets.csv")
    index = {
        (row["economy_code"], row["category_code"], row["target_period"], row["target_metric"]): row
        for row in rows
    }
    if len(index) != len(rows):
        raise BacktestProtocolError("duplicate target archive key")
    return rows, index


def _known_targets(
    target_rows: list[dict[str, str]], *, economy: str, category: str,
    metric: str, cutoff: str, before_period: str,
) -> list[dict[str, str]]:
    cutoff_dt = parse_utc(cutoff, "cutoff")
    result = [
        row for row in target_rows
        if row["economy_code"] == economy
        and row["category_code"] == category
        and row["target_metric"] == metric
        and row["target_period"] < before_period
        and parse_utc(row["target_available_at"], "target_available_at") <= cutoff_dt
    ]
    return sorted(result, key=lambda row: (row["target_period"], row["target_available_at"], row["target_id"]))


def evaluate_baselines(
    *, policy_path: Path, target_archive: Path, alignment: Path,
    output_dir: Path, created_at: str,
) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    verify_target_archive(target_archive, policy_path=policy_path)
    alignment_summary = verify_alignment(
        alignment, policy_path=policy_path, target_archive=target_archive
    )
    target_rows, target_index = _target_history(target_archive)
    cases = read_csv(alignment / "forecast_cases.csv")

    predictions: list[dict[str, str]] = []
    complete_baseline_by_case: dict[str, int] = defaultdict(int)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUNDING
        for case in cases:
            target_value = parse_decimal(case["target_value_unrounded"], "target_value_unrounded")
            known = _known_targets(
                target_rows,
                economy=case["economy_code"], category=case["category_code"],
                metric=case["target_metric"], cutoff=case["cutoff"],
                before_period=add_months(case["origin_period"], 1),
            )
            prediction_specs: list[tuple[str, Decimal | None, str]] = [
                ("ZERO_CHANGE", ZERO, ""),
            ]
            if known:
                last = known[-1]
                prediction_specs.append((
                    "LAST_OBSERVED_TARGET",
                    parse_decimal(last["target_value_unrounded"], "last target"),
                    last["target_id"],
                ))
            else:
                prediction_specs.append(("LAST_OBSERVED_TARGET", None, ""))
            seasonal_period = add_months(case["target_period"], -12)
            seasonal = target_index.get((
                case["economy_code"], case["category_code"], seasonal_period,
                case["target_metric"],
            ))
            if seasonal is not None and parse_utc(seasonal["target_available_at"], "target_available_at") <= parse_utc(case["cutoff"], "cutoff"):
                prediction_specs.append((
                    "SEASONAL_12M",
                    parse_decimal(seasonal["target_value_unrounded"], "seasonal target"),
                    seasonal["target_id"],
                ))
            else:
                prediction_specs.append(("SEASONAL_12M", None, ""))

            for baseline_id, prediction, source_target_id in prediction_specs:
                available = prediction is not None
                error = (prediction - target_value) if prediction is not None else None
                if available:
                    complete_baseline_by_case[case["forecast_case_id"]] += 1
                predictions.append({
                    "prediction_id": stable_id(
                        "ARMILAR_BASELINE_PREDICTION_V0100",
                        case["forecast_case_id"], baseline_id,
                    ),
                    "forecast_case_id": case["forecast_case_id"],
                    "baseline_id": baseline_id,
                    "cutoff": case["cutoff"],
                    "horizon_months": case["horizon_months"],
                    "target_period": case["target_period"],
                    "economy_code": case["economy_code"],
                    "category_code": case["category_code"],
                    "target_metric": case["target_metric"],
                    "prediction_value": fixed_decimal_text(prediction, policy.output_decimal_places) if prediction is not None else "",
                    "prediction_value_unrounded": decimal_text(prediction) if prediction is not None else "",
                    "target_value": case["target_value"],
                    "target_value_unrounded": case["target_value_unrounded"],
                    "error": decimal_text(error) if error is not None else "",
                    "absolute_error": decimal_text(abs(error)) if error is not None else "",
                    "squared_error": decimal_text(error * error) if error is not None else "",
                    "baseline_source_target_id": source_target_id,
                    "prediction_available": "true" if available else "false",
                    "diagnostic_only": "true",
                    "model_training_allowed": "false",
                    "model_selection_allowed": "false",
                    "arm_l_use_allowed": "false",
                })

    # Aggregate by category as well as an ALL category summary.
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in predictions:
        for category in (row["category_code"], "ALL"):
            groups[(row["baseline_id"], row["target_metric"], row["horizon_months"], category)].append(row)
    metric_rows: list[dict[str, str]] = []
    for key, rows in sorted(groups.items()):
        available = [row for row in rows if row["prediction_available"] == "true"]
        errors = [parse_decimal(row["error"], "error") for row in available]
        count = len(rows)
        prediction_count = len(available)
        if errors:
            with localcontext() as ctx:
                ctx.prec = PRECISION
                ctx.rounding = ROUNDING
                mean_error = sum(errors, ZERO) / Decimal(len(errors))
                mae = sum((abs(value) for value in errors), ZERO) / Decimal(len(errors))
                mse = sum((value * value for value in errors), ZERO) / Decimal(len(errors))
                rmse = mse.sqrt()
        else:
            mean_error = mae = rmse = None
        metric_rows.append({
            "baseline_id": key[0],
            "target_metric": key[1],
            "horizon_months": key[2],
            "category_code": key[3],
            "case_count": str(count),
            "prediction_count": str(prediction_count),
            "missing_prediction_count": str(count - prediction_count),
            "coverage_rate": fixed_decimal_text(Decimal(prediction_count) / Decimal(count) if count else ZERO, 12),
            "mean_error": fixed_decimal_text(mean_error, 12) if mean_error is not None else "",
            "mae": fixed_decimal_text(mae, 12) if mae is not None else "",
            "rmse": fixed_decimal_text(rmse, 12) if rmse is not None else "",
            "diagnostic_only": "true",
            "model_selection_allowed": "false",
            "out_of_sample_claim_allowed": "false",
        })

    readiness_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for case in cases:
        readiness_groups[(
            case["economy_code"], case["category_code"],
            case["target_metric"], case["horizon_months"],
        )].append(case)
    readiness: list[dict[str, str]] = []
    for key, rows in sorted(readiness_groups.items()):
        cutoffs = {row["cutoff"] for row in rows}
        primary_cases = sum(int(row["primary_feature_count"]) > 0 for row in rows)
        complete_baseline_cases = sum(complete_baseline_by_case[row["forecast_case_id"]] == len(policy.baselines) for row in rows)
        if len(cutoffs) < policy.minimum_distinct_cutoffs_for_claim:
            status = "INSUFFICIENT_DISTINCT_CUTOFFS"
        elif len(rows) < policy.minimum_cases_per_cell_metric_horizon_for_claim:
            status = "INSUFFICIENT_CASES"
        elif primary_cases < len(rows):
            status = "INCOMPLETE_PRIMARY_FEATURE_PRESENCE"
        elif complete_baseline_cases < len(rows):
            status = "INCOMPLETE_BASELINE_AVAILABILITY"
        else:
            status = "DIAGNOSTIC_THRESHOLDS_MET_GATE_STILL_CLOSED"
        readiness.append({
            "economy_code": key[0],
            "category_code": key[1],
            "target_metric": key[2],
            "horizon_months": key[3],
            "distinct_cutoff_count": str(len(cutoffs)),
            "case_count": str(len(rows)),
            "primary_feature_case_count": str(primary_cases),
            "complete_baseline_case_count": str(complete_baseline_cases),
            "minimum_distinct_cutoffs_required": str(policy.minimum_distinct_cutoffs_for_claim),
            "minimum_cases_required": str(policy.minimum_cases_per_cell_metric_horizon_for_claim),
            "readiness_status": status,
            "backtest_claim_allowed": "false",
            "model_training_allowed": "false",
        })

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "0.10.0",
        "status": "FROZEN_BASELINE_PROTOCOL_V0100_VALID",
        "created_at": canonical_utc(created_at, "created_at"),
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "alignment_status": alignment_summary["status"],
        "alignment_manifest_sha256": directory_manifest_sha256(alignment),
        "target_archive_manifest_sha256": directory_manifest_sha256(target_archive),
        "forecast_case_count": len(cases),
        "baseline_evaluation_status": "BASELINES_EVALUATED" if cases else "NO_ELIGIBLE_CASES_BASELINES_NOT_EVALUATED",
        "prediction_row_count": len(predictions),
        "available_prediction_count": sum(row["prediction_available"] == "true" for row in predictions),
        "metric_row_count": len(metric_rows),
        "readiness_row_count": len(readiness),
        "readiness_status_counts": {
            status: sum(row["readiness_status"] == status for row in readiness)
            for status in sorted({row["readiness_status"] for row in readiness})
        },
        "baseline_ids": list(policy.baselines),
        "diagnostic_only": True,
        "gates": policy.gates,
    }

    def writer(staging: Path) -> None:
        (staging / "baseline_predictions.csv").write_bytes(csv_bytes(predictions, PREDICTION_COLUMNS))
        (staging / "baseline_metrics.csv").write_bytes(csv_bytes(metric_rows, METRIC_COLUMNS))
        (staging / "cell_protocol_readiness.csv").write_bytes(csv_bytes(readiness, READINESS_COLUMNS))
        (staging / "baseline_summary.json").write_bytes(canonical_json_bytes(summary))
        write_manifest(staging)

    write_transactional(output_dir, writer)
    verify_baseline_evaluation(
        output_dir, policy_path=policy_path, target_archive=target_archive,
        alignment=alignment,
    )
    return summary


def verify_baseline_evaluation(
    path: Path, *, policy_path: Path, target_archive: Path, alignment: Path,
) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    verify_target_archive(target_archive, policy_path=policy_path)
    verify_alignment(alignment, policy_path=policy_path, target_archive=target_archive)
    verify_manifest(path)
    try:
        summary = json.loads((path / "baseline_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestProtocolError("invalid baseline summary") from exc
    if summary.get("status") != "FROZEN_BASELINE_PROTOCOL_V0100_VALID":
        raise BacktestProtocolError("unexpected baseline status")
    if summary.get("policy_id") != policy.policy_id or summary.get("gates") != policy.gates:
        raise BacktestProtocolError("baseline policy or gates mismatch")
    if summary.get("diagnostic_only") is not True:
        raise BacktestProtocolError("baseline evaluation was promoted beyond diagnostics")
    expected_evaluation_status = "BASELINES_EVALUATED" if summary.get("forecast_case_count") else "NO_ELIGIBLE_CASES_BASELINES_NOT_EVALUATED"
    if summary.get("baseline_evaluation_status") != expected_evaluation_status:
        raise BacktestProtocolError("baseline evaluation status mismatch")
    predictions = read_csv(path / "baseline_predictions.csv")
    metrics = read_csv(path / "baseline_metrics.csv")
    readiness = read_csv(path / "cell_protocol_readiness.csv")
    if len(predictions) != summary.get("prediction_row_count"):
        raise BacktestProtocolError("prediction count mismatch")
    if len(metrics) != summary.get("metric_row_count") or len(readiness) != summary.get("readiness_row_count"):
        raise BacktestProtocolError("baseline output count mismatch")
    case_ids = {row["forecast_case_id"] for row in read_csv(alignment / "forecast_cases.csv")}
    for row in predictions:
        if row["forecast_case_id"] not in case_ids:
            raise BacktestProtocolError("prediction references unknown case")
        if row["baseline_id"] not in policy.baselines:
            raise BacktestProtocolError("unexpected baseline_id")
        if row["diagnostic_only"] != "true" or row["model_selection_allowed"] != "false":
            raise BacktestProtocolError("baseline prediction gate opened")
        if row["prediction_available"] == "true":
            error = parse_decimal(row["error"], "error")
            prediction = parse_decimal(row["prediction_value_unrounded"], "prediction")
            target = parse_decimal(row["target_value_unrounded"], "target")
            if error != prediction - target:
                raise BacktestProtocolError("baseline error does not reconcile")
        elif any(row[field] for field in ("prediction_value", "prediction_value_unrounded", "error", "absolute_error", "squared_error")):
            raise BacktestProtocolError("missing prediction contains numeric outputs")
    if any(row["model_selection_allowed"] != "false" or row["out_of_sample_claim_allowed"] != "false" for row in metrics):
        raise BacktestProtocolError("metric output opened a forbidden claim")
    if any(row["backtest_claim_allowed"] != "false" or row["model_training_allowed"] != "false" for row in readiness):
        raise BacktestProtocolError("readiness output opened a forbidden gate")
    return summary
