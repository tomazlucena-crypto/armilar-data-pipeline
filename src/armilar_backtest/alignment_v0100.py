"""Align point-in-time v0.9.9 features to future ARM-O targets without look-ahead."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Iterable

from .core_v0100 import (
    BacktestProtocolError, PRECISION, ROUNDING, ZERO, add_months,
    canonical_json_bytes, canonical_utc, csv_bytes, cutoff_month,
    directory_manifest_sha256, fixed_decimal_text, month_distance,
    parse_decimal, parse_utc, read_csv, stable_id, verify_manifest,
    write_manifest, write_transactional,
)
from .protocol_v0100 import ProtocolPolicy
from .target_archive_v0100 import verify_target_archive

CASE_COLUMNS = (
    "forecast_case_id", "cutoff", "origin_period", "horizon_months",
    "target_period", "economy_code", "category_code", "target_metric",
    "target_value", "target_value_unrounded", "target_available_at",
    "target_known_at_cutoff", "feature_bundle_manifest_sha256",
    "target_archive_manifest_sha256", "primary_feature_count",
    "sensitivity_feature_count", "latest_primary_feature_period",
    "latest_sensitivity_feature_period", "case_status",
    "backtest_execution_claim_allowed", "model_training_allowed",
    "arm_l_use_allowed",
)

ALIGNED_FEATURE_COLUMNS = (
    "forecast_case_id", "cutoff", "origin_period", "horizon_months",
    "target_period", "economy_code", "category_code", "target_metric",
    "feature_id", "mapping_id", "source_id", "series_id", "feature_role",
    "mapping_evidence", "transformation", "feature_target_period",
    "feature_lag_months", "feature_value", "feature_unit",
    "feature_latest_available_at", "feature_known_at_cutoff",
    "feature_period_not_after_origin", "period_completeness_status",
    "source_freshness_status", "model_training_allowed",
)

LEAKAGE_COLUMNS = (
    "forecast_case_id", "feature_id", "cutoff", "target_available_at",
    "feature_latest_available_at", "feature_target_period", "origin_period",
    "target_not_known_at_cutoff", "feature_known_at_cutoff",
    "feature_period_not_after_origin", "leakage_status",
)

CANDIDATE_COLUMNS = (
    "cutoff", "origin_period", "horizon_months", "target_period",
    "economy_code", "category_code", "target_metric", "target_present",
    "target_known_at_cutoff", "primary_feature_count",
    "sensitivity_feature_count", "candidate_status",
)

CUTOFF_COLUMNS = (
    "cutoff", "feature_bundle_manifest_sha256", "feature_value_count",
    "case_count", "aligned_feature_count", "target_count_by_cutoff",
    "all_gates_closed",
)


def _read_feature_bundle(path: Path) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    verify_manifest(path)
    try:
        summary = json.loads((path / "feature_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestProtocolError(f"invalid v0.9.9 feature summary: {path}") from exc
    if summary.get("status") != "POINT_IN_TIME_PROXY_FEATURE_PANEL_V099_VALID":
        raise BacktestProtocolError("feature bundle must be a verified v0.9.9 panel")
    if summary.get("contract_version") != "0.9.9":
        raise BacktestProtocolError("feature bundle contract version mismatch")
    forbidden_true = (
        "direct_index_use_allowed", "arm_l_use_allowed", "model_training_allowed",
        "shadow_production_allowed", "monetary_use_allowed",
        "price_coverage_claim_allowed", "model_ready_claim_allowed",
        "backtest_eligibility_claim_allowed", "concordance_approval_claim_allowed",
    )
    if any(bool(summary.get(name)) for name in forbidden_true):
        raise BacktestProtocolError("feature bundle has an opened gate")
    rows = read_csv(path / "feature_values.csv")
    if len(rows) != int(summary.get("feature_value_count", -1)):
        raise BacktestProtocolError("feature row count does not reconcile")
    cutoff = canonical_utc(str(summary["cutoff"]), "feature cutoff")
    for row in rows:
        if canonical_utc(row["cutoff"], "row cutoff") != cutoff:
            raise BacktestProtocolError("feature row cutoff differs from bundle cutoff")
        if row["model_training_allowed"] != "false" or row["arm_l_use_allowed"] != "false":
            raise BacktestProtocolError("feature row contains an opened gate")
    return summary, rows, directory_manifest_sha256(path)


def _latest_features_for_case(
    rows: Iterable[dict[str, str]], *, economy: str, category: str,
    origin_period: str, cutoff: str, policy: ProtocolPolicy,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    cutoff_dt = parse_utc(cutoff, "cutoff")
    for row in rows:
        if row["target_economy_code"] != economy or row["target_category_code"] != category:
            continue
        if row["feature_role"] not in policy.accepted_feature_roles:
            continue
        if row["transformation"] not in policy.accepted_transformations:
            continue
        if month_distance(row["target_period"], origin_period) < 0:
            continue
        if parse_utc(row["latest_available_at"], "latest_available_at") > cutoff_dt:
            continue
        if row["period_completeness_status"] != "COMPLETE_PERIOD":
            continue
        candidates.append(row)

    # Keep one latest point per deterministic stream variant.
    chosen: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for row in candidates:
        key = (
            row["mapping_id"], row["source_id"], row["series_id"],
            row["feature_role"], row["transformation"], row["unit"],
        )
        previous = chosen.get(key)
        if previous is None or (row["target_period"], row["feature_id"]) > (
            previous["target_period"], previous["feature_id"]
        ):
            chosen[key] = row
    return [chosen[key] for key in sorted(chosen)]


def build_alignment(
    *, policy_path: Path, target_archive: Path, feature_bundles: list[Path],
    output_dir: Path, created_at: str,
) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    target_summary = verify_target_archive(target_archive, policy_path=policy_path)
    target_manifest_sha256 = directory_manifest_sha256(target_archive)
    targets = read_csv(target_archive / "cell_targets.csv")
    target_by_key = {
        (row["economy_code"], row["category_code"], row["target_period"], row["target_metric"]): row
        for row in targets
    }
    if len(target_by_key) != len(targets):
        raise BacktestProtocolError("target archive contains duplicate keys")
    if not feature_bundles:
        raise BacktestProtocolError("at least one feature bundle is required")

    bundles: list[tuple[str, dict[str, Any], list[dict[str, str]], str]] = []
    seen_cutoffs: set[str] = set()
    for path in feature_bundles:
        summary, rows, manifest = _read_feature_bundle(path)
        cutoff = canonical_utc(str(summary["cutoff"]), "cutoff")
        if cutoff in seen_cutoffs:
            raise BacktestProtocolError(f"duplicate feature cutoff: {cutoff}")
        seen_cutoffs.add(cutoff)
        bundles.append((cutoff, summary, rows, manifest))
    bundles.sort(key=lambda item: parse_utc(item[0], "cutoff"))

    cases: list[dict[str, str]] = []
    aligned: list[dict[str, str]] = []
    leakage: list[dict[str, str]] = []
    cutoff_inventory: list[dict[str, str]] = []
    candidate_audit: list[dict[str, str]] = []

    for cutoff, feature_summary, feature_rows, feature_manifest in bundles:
        origin = cutoff_month(cutoff)
        cutoff_dt = parse_utc(cutoff, "cutoff")
        case_count_before = len(cases)
        feature_count_before = len(aligned)
        cutoff_target_count = 0
        cells = sorted({(row["economy_code"], row["category_code"]) for row in targets})
        for economy, category in cells:
            for horizon in policy.horizons_months:
                target_period = add_months(origin, horizon)
                for metric in policy.target_metrics:
                    target = target_by_key.get((economy, category, target_period, metric))
                    case_features = _latest_features_for_case(
                        feature_rows, economy=economy, category=category,
                        origin_period=origin, cutoff=cutoff, policy=policy,
                    )
                    primary = [row for row in case_features if row["feature_role"] == "PRIMARY_RESEARCH_DRIVER"]
                    sensitivity = [row for row in case_features if row["feature_role"] == "SENSITIVITY_ONLY"]
                    if target is None:
                        candidate_audit.append({
                            "cutoff": cutoff, "origin_period": origin,
                            "horizon_months": str(horizon), "target_period": target_period,
                            "economy_code": economy, "category_code": category,
                            "target_metric": metric, "target_present": "false",
                            "target_known_at_cutoff": "false",
                            "primary_feature_count": str(len(primary)),
                            "sensitivity_feature_count": str(len(sensitivity)),
                            "candidate_status": "TARGET_NOT_IN_ARCHIVE",
                        })
                        continue
                    cutoff_target_count += 1
                    target_known = parse_utc(target["target_available_at"], "target_available_at") <= cutoff_dt
                    if target_known:
                        candidate_audit.append({
                            "cutoff": cutoff, "origin_period": origin,
                            "horizon_months": str(horizon), "target_period": target_period,
                            "economy_code": economy, "category_code": category,
                            "target_metric": metric, "target_present": "true",
                            "target_known_at_cutoff": "true",
                            "primary_feature_count": str(len(primary)),
                            "sensitivity_feature_count": str(len(sensitivity)),
                            "candidate_status": "TARGET_ALREADY_KNOWN_AT_CUTOFF",
                        })
                        continue
                    candidate_audit.append({
                        "cutoff": cutoff, "origin_period": origin,
                        "horizon_months": str(horizon), "target_period": target_period,
                        "economy_code": economy, "category_code": category,
                        "target_metric": metric, "target_present": "true",
                        "target_known_at_cutoff": "false",
                        "primary_feature_count": str(len(primary)),
                        "sensitivity_feature_count": str(len(sensitivity)),
                        "candidate_status": "ELIGIBLE_FUTURE_TARGET",
                    })
                    case_id = stable_id(
                        "ARMILAR_FORECAST_CASE_V0100", cutoff, economy, category,
                        target_period, metric, str(horizon), target["target_id"],
                    )
                    cases.append({
                        "forecast_case_id": case_id,
                        "cutoff": cutoff,
                        "origin_period": origin,
                        "horizon_months": str(horizon),
                        "target_period": target_period,
                        "economy_code": economy,
                        "category_code": category,
                        "target_metric": metric,
                        "target_value": target["target_value"],
                        "target_value_unrounded": target["target_value_unrounded"],
                        "target_available_at": target["target_available_at"],
                        "target_known_at_cutoff": "false",
                        "feature_bundle_manifest_sha256": feature_manifest,
                        "target_archive_manifest_sha256": target_manifest_sha256,
                        "primary_feature_count": str(len(primary)),
                        "sensitivity_feature_count": str(len(sensitivity)),
                        "latest_primary_feature_period": max((row["target_period"] for row in primary), default=""),
                        "latest_sensitivity_feature_period": max((row["target_period"] for row in sensitivity), default=""),
                        "case_status": "POINT_IN_TIME_DIAGNOSTIC_CASE",
                        "backtest_execution_claim_allowed": "false",
                        "model_training_allowed": "false",
                        "arm_l_use_allowed": "false",
                    })
                    for feature in case_features:
                        known = parse_utc(feature["latest_available_at"], "latest_available_at") <= cutoff_dt
                        period_ok = month_distance(feature["target_period"], origin) >= 0
                        leakage_status = "PASS" if (known and period_ok and not target_known) else "FAIL"
                        aligned.append({
                            "forecast_case_id": case_id,
                            "cutoff": cutoff,
                            "origin_period": origin,
                            "horizon_months": str(horizon),
                            "target_period": target_period,
                            "economy_code": economy,
                            "category_code": category,
                            "target_metric": metric,
                            "feature_id": feature["feature_id"],
                            "mapping_id": feature["mapping_id"],
                            "source_id": feature["source_id"],
                            "series_id": feature["series_id"],
                            "feature_role": feature["feature_role"],
                            "mapping_evidence": feature["mapping_evidence"],
                            "transformation": feature["transformation"],
                            "feature_target_period": feature["target_period"],
                            "feature_lag_months": str(month_distance(feature["target_period"], origin)),
                            "feature_value": feature["value"],
                            "feature_unit": feature["unit"],
                            "feature_latest_available_at": canonical_utc(feature["latest_available_at"], "latest_available_at"),
                            "feature_known_at_cutoff": "true" if known else "false",
                            "feature_period_not_after_origin": "true" if period_ok else "false",
                            "period_completeness_status": feature["period_completeness_status"],
                            "source_freshness_status": feature["source_freshness_status"],
                            "model_training_allowed": "false",
                        })
                        leakage.append({
                            "forecast_case_id": case_id,
                            "feature_id": feature["feature_id"],
                            "cutoff": cutoff,
                            "target_available_at": target["target_available_at"],
                            "feature_latest_available_at": canonical_utc(feature["latest_available_at"], "latest_available_at"),
                            "feature_target_period": feature["target_period"],
                            "origin_period": origin,
                            "target_not_known_at_cutoff": "true" if not target_known else "false",
                            "feature_known_at_cutoff": "true" if known else "false",
                            "feature_period_not_after_origin": "true" if period_ok else "false",
                            "leakage_status": leakage_status,
                        })
        cutoff_inventory.append({
            "cutoff": cutoff,
            "feature_bundle_manifest_sha256": feature_manifest,
            "feature_value_count": str(len(feature_rows)),
            "case_count": str(len(cases) - case_count_before),
            "aligned_feature_count": str(len(aligned) - feature_count_before),
            "target_count_by_cutoff": str(cutoff_target_count),
            "all_gates_closed": "true",
        })

    if any(row["leakage_status"] != "PASS" for row in leakage):
        raise BacktestProtocolError("alignment contains look-ahead leakage")
    missing_target_count = sum(row["candidate_status"] == "TARGET_NOT_IN_ARCHIVE" for row in candidate_audit)
    known_target_count = sum(row["candidate_status"] == "TARGET_ALREADY_KNOWN_AT_CUTOFF" for row in candidate_audit)
    eligible_target_count = sum(row["candidate_status"] == "ELIGIBLE_FUTURE_TARGET" for row in candidate_audit)

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "0.10.0",
        "status": "POINT_IN_TIME_TARGET_ALIGNMENT_V0100_VALID",
        "created_at": canonical_utc(created_at, "created_at"),
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "target_archive_status": target_summary["status"],
        "target_archive_manifest_sha256": target_manifest_sha256,
        "distinct_cutoff_count": len(bundles),
        "candidate_audit_row_count": len(candidate_audit),
        "candidate_missing_target_count": missing_target_count,
        "candidate_target_already_known_count": known_target_count,
        "candidate_eligible_future_target_count": eligible_target_count,
        "alignment_readiness_status": "ELIGIBLE_CASES_AVAILABLE" if cases else "NO_ELIGIBLE_FUTURE_TARGETS",
        "forecast_case_count": len(cases),
        "aligned_feature_count": len(aligned),
        "leakage_audit_row_count": len(leakage),
        "leakage_failure_count": 0,
        "case_with_primary_feature_count": sum(int(row["primary_feature_count"]) > 0 for row in cases),
        "case_with_sensitivity_feature_count": sum(int(row["sensitivity_feature_count"]) > 0 for row in cases),
        "metric_counts": {
            metric: sum(row["target_metric"] == metric for row in cases)
            for metric in policy.target_metrics
        },
        "horizon_counts": {
            str(horizon): sum(int(row["horizon_months"]) == horizon for row in cases)
            for horizon in policy.horizons_months
        },
        "minimum_distinct_cutoffs_for_claim": policy.minimum_distinct_cutoffs_for_claim,
        "backtest_claim_threshold_met": bool(cases) and len(bundles) >= policy.minimum_distinct_cutoffs_for_claim,
        "gates": policy.gates,
    }
    # Threshold satisfaction is informational only; the gate remains closed.

    def writer(staging: Path) -> None:
        (staging / "forecast_cases.csv").write_bytes(csv_bytes(cases, CASE_COLUMNS))
        (staging / "aligned_features.csv").write_bytes(csv_bytes(aligned, ALIGNED_FEATURE_COLUMNS))
        (staging / "leakage_audit.csv").write_bytes(csv_bytes(leakage, LEAKAGE_COLUMNS))
        (staging / "case_candidate_audit.csv").write_bytes(csv_bytes(candidate_audit, CANDIDATE_COLUMNS))
        (staging / "cutoff_inventory.csv").write_bytes(csv_bytes(cutoff_inventory, CUTOFF_COLUMNS))
        (staging / "alignment_summary.json").write_bytes(canonical_json_bytes(summary))
        write_manifest(staging)

    write_transactional(output_dir, writer)
    verify_alignment(output_dir, policy_path=policy_path, target_archive=target_archive)
    return summary


def verify_alignment(path: Path, *, policy_path: Path, target_archive: Path) -> dict[str, Any]:
    policy = ProtocolPolicy.load(policy_path)
    verify_target_archive(target_archive, policy_path=policy_path)
    verify_manifest(path)
    try:
        summary = json.loads((path / "alignment_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestProtocolError("invalid alignment summary") from exc
    if summary.get("status") != "POINT_IN_TIME_TARGET_ALIGNMENT_V0100_VALID":
        raise BacktestProtocolError("unexpected alignment status")
    if summary.get("policy_id") != policy.policy_id or summary.get("gates") != policy.gates:
        raise BacktestProtocolError("alignment policy or gates mismatch")
    if summary.get("target_archive_manifest_sha256") != directory_manifest_sha256(target_archive):
        raise BacktestProtocolError("alignment points to a different target archive")
    cases = read_csv(path / "forecast_cases.csv")
    features = read_csv(path / "aligned_features.csv")
    leakage = read_csv(path / "leakage_audit.csv")
    candidates = read_csv(path / "case_candidate_audit.csv")
    cutoffs = read_csv(path / "cutoff_inventory.csv")
    if len(candidates) != summary.get("candidate_audit_row_count"):
        raise BacktestProtocolError("candidate audit count does not reconcile")
    if len(cases) != summary.get("forecast_case_count") or len(features) != summary.get("aligned_feature_count"):
        raise BacktestProtocolError("alignment counts do not reconcile")
    if len(leakage) != summary.get("leakage_audit_row_count"):
        raise BacktestProtocolError("leakage count does not reconcile")
    case_ids = {row["forecast_case_id"] for row in cases}
    if len(case_ids) != len(cases):
        raise BacktestProtocolError("duplicate forecast_case_id")
    if set(row["forecast_case_id"] for row in features) - case_ids:
        raise BacktestProtocolError("aligned feature references unknown case")
    if set(row["forecast_case_id"] for row in leakage) - case_ids:
        raise BacktestProtocolError("leakage row references unknown case")
    for row in cases:
        if row["target_known_at_cutoff"] != "false":
            raise BacktestProtocolError("case target was known at cutoff")
        if parse_utc(row["target_available_at"], "target_available_at") <= parse_utc(row["cutoff"], "cutoff"):
            raise BacktestProtocolError("case target is not future information")
        if row["backtest_execution_claim_allowed"] != "false" or row["model_training_allowed"] != "false":
            raise BacktestProtocolError("case gate was opened")
    for row in features:
        if row["feature_known_at_cutoff"] != "true" or row["feature_period_not_after_origin"] != "true":
            raise BacktestProtocolError("aligned feature violates point-in-time rules")
        if parse_utc(row["feature_latest_available_at"], "feature_latest_available_at") > parse_utc(row["cutoff"], "cutoff"):
            raise BacktestProtocolError("aligned feature was not known at cutoff")
        if month_distance(row["feature_target_period"], row["origin_period"]) < 0:
            raise BacktestProtocolError("aligned feature period is after origin")
    if any(row["leakage_status"] != "PASS" for row in leakage):
        raise BacktestProtocolError("leakage audit failed")
    candidate_statuses = {"TARGET_NOT_IN_ARCHIVE", "TARGET_ALREADY_KNOWN_AT_CUTOFF", "ELIGIBLE_FUTURE_TARGET"}
    if any(row["candidate_status"] not in candidate_statuses for row in candidates):
        raise BacktestProtocolError("unknown candidate audit status")
    for row in candidates:
        if row["candidate_status"] == "TARGET_NOT_IN_ARCHIVE" and row["target_present"] != "false":
            raise BacktestProtocolError("missing target candidate is marked present")
        if row["candidate_status"] == "TARGET_ALREADY_KNOWN_AT_CUTOFF" and (row["target_present"] != "true" or row["target_known_at_cutoff"] != "true"):
            raise BacktestProtocolError("known target candidate flags are inconsistent")
        if row["candidate_status"] == "ELIGIBLE_FUTURE_TARGET" and (row["target_present"] != "true" or row["target_known_at_cutoff"] != "false"):
            raise BacktestProtocolError("eligible target candidate flags are inconsistent")
    missing_count = sum(row["candidate_status"] == "TARGET_NOT_IN_ARCHIVE" for row in candidates)
    known_count = sum(row["candidate_status"] == "TARGET_ALREADY_KNOWN_AT_CUTOFF" for row in candidates)
    eligible_count = sum(row["candidate_status"] == "ELIGIBLE_FUTURE_TARGET" for row in candidates)
    if missing_count != summary.get("candidate_missing_target_count") or known_count != summary.get("candidate_target_already_known_count") or eligible_count != summary.get("candidate_eligible_future_target_count"):
        raise BacktestProtocolError("candidate status counts do not reconcile")
    if eligible_count != len(cases):
        raise BacktestProtocolError("eligible candidate count differs from case count")
    expected_readiness = "ELIGIBLE_CASES_AVAILABLE" if cases else "NO_ELIGIBLE_FUTURE_TARGETS"
    if summary.get("alignment_readiness_status") != expected_readiness:
        raise BacktestProtocolError("alignment readiness status mismatch")
    if len(cutoffs) != summary.get("distinct_cutoff_count"):
        raise BacktestProtocolError("cutoff inventory count mismatch")
    if summary.get("leakage_failure_count") != 0:
        raise BacktestProtocolError("alignment summary reports leakage failures")
    return summary
