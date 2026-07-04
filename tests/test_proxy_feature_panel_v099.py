from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from armilar_proxies.archive_core_v098 import (
    PANEL_COLUMNS,
    SOURCE_CUTOFF_STATUS_COLUMNS,
    bundle_manifest_bytes,
    csv_bytes,
)
from armilar_proxies.core_v097 import canonical_json_bytes, sha256_file
from armilar_proxies.feature_builder_v099 import _pearson, build_feature_panel, verify_feature_bundle
from armilar_proxies.feature_compare_v099 import build_feature_comparison, verify_feature_comparison_bundle
from armilar_proxies.feature_panel_v099 import build_parser
from armilar_proxies.feature_core_v099 import (
    FEATURE_PANEL_STATUS,
    ProxyFeatureError,
    decimal_text,
    decimal_value,
    load_policy,
    mapping_for_row,
    month_key,
    percent_change,
    resolve_geography,
    shift_month,
    target_period_metadata,
    validate_policy,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "proxy_feature_mapping_v099.json"
BASKET = ROOT / "basket" / "ARMILAR_RESEARCH_CORE_V1.csv"
if not BASKET.exists():
    BASKET = ROOT / "ARMILAR_RESEARCH_CORE_V1.csv"


def _observation(source, series, domain, geography, period, frequency, value, unit, cutoff, available_at="2025-03-01T00:00:00Z"):
    identity = "|".join([source, series, domain, geography, period, frequency, unit])
    return {
        "observation_key": hashlib.sha256(identity.encode()).hexdigest(),
        "version_sequence": 1,
        "source_id": source,
        "series_id": series,
        "proxy_domain": domain,
        "geography": geography,
        "period": period,
        "frequency": frequency,
        "unit": unit,
        "value": str(value),
        "available_at": available_at,
        "availability_basis": "FIRST_VERIFIED_RETRIEVAL",
        "first_snapshot_id": "snap-" + source[:6],
        "first_source_sha256": "a" * 64,
        "cutoff": cutoff,
        "historical_first_published_claim_allowed": "false",
        "direct_index_use_allowed": "false",
        "arm_l_use_allowed": "false",
        "model_training_allowed": "false",
    }


def _information_set(tmp_path: Path, *, cutoff="2025-03-15T00:00:00Z", stale_world_bank=False) -> Path:
    target = tmp_path / "information_set"
    target.mkdir()
    rows = []
    for period, value in [("2024-01", 100), ("2024-02", 101), ("2025-01", 110), ("2025-02", 121)]:
        rows.append(_observation("WORLD_BANK_PINK_SHEET_MONTHLY", "WB_FOOD_INDEX", "FOOD", "WORLD", period, "MONTHLY", value, "INDEX", cutoff))
    rows.append(_observation("WORLD_BANK_PINK_SHEET_MONTHLY", "WB_ENERGY_INDEX", "ENERGY", "WORLD", "2025-02", "MONTHLY", 150, "INDEX", cutoff))
    for period, value in [("2025-01", 100), ("2025-02", 102)]:
        rows.append(_observation("FAO_FOOD_PRICE_INDEX_MONTHLY", "FAO_FFPI", "FOOD", "WORLD", period, "MONTHLY", value, "INDEX", cutoff))
    for period, value in [("2025-01-06", 100), ("2025-01-20", 120), ("2025-02-03", 130)]:
        rows.append(_observation("EC_WEEKLY_OIL_BULLETIN_HISTORY", "EC_OIL_DIESEL", "TRANSPORT", "GERMANY", period, "WEEKLY", value, "EUR", cutoff))
    rows.append(_observation("EC_WEEKLY_OIL_BULLETIN_HISTORY", "EC_OIL_DIESEL", "TRANSPORT", "BELGIUM", "2025-02-03", "WEEKLY", 140, "EUR", cutoff))
    for period, value in [("2024-Q1", 100), ("2025-Q1", 105)]:
        rows.append(_observation("EUROSTAT_OOHPI_QUARTERLY", "EUROSTAT_OOHPI_OOH_TOTAL_I15_Q", "HOUSING_OOH_SENSITIVITY", "DE", period, "QUARTERLY", value, "INDEX", cutoff))
    rows.append(_observation("FAO_FOOD_PRICE_INDEX_MONTHLY", "UNKNOWN", "FOOD", "WORLD", "2025-02", "MONTHLY", 1, "INDEX", cutoff))
    (target / "panel.csv").write_bytes(csv_bytes(rows, PANEL_COLUMNS))
    statuses = []
    source_rows = [
        ("WORLD_BANK_PINK_SHEET_MONTHLY", "STALE_BEYOND_EXPECTED_WINDOW" if stale_world_bank else "CURRENT_WITHIN_EXPECTED_WINDOW", 5 if not stale_world_bank else 50, 21, 5),
        ("FAO_FOOD_PRICE_INDEX_MONTHLY", "CURRENT_WITHIN_EXPECTED_WINDOW", 5, 21, 3),
        ("EC_WEEKLY_OIL_BULLETIN_HISTORY", "CURRENT_WITHIN_EXPECTED_WINDOW", 3, 12, 4),
        ("EUROSTAT_OOHPI_QUARTERLY", "STALE_BEYOND_EXPECTED_WINDOW", 134, 100, 2),
    ]
    for source, freshness, age, allowed, count in source_rows:
        statuses.append({
            "source_id": source,
            "cutoff": cutoff,
            "selected_observation_count": count,
            "latest_snapshot_id": "snap",
            "latest_snapshot_at": "2025-03-10T00:00:00Z",
            "age_days": age,
            "allowed_age_days": allowed,
            "freshness_status": freshness,
        })
    (target / "source_cutoff_status.csv").write_bytes(csv_bytes(statuses, SOURCE_CUTOFF_STATUS_COLUMNS))
    summary = {
        "schema_version": "1.0",
        "contract_version": "0.9.8",
        "status": "POINT_IN_TIME_RESEARCH_INPUT_ONLY",
        "cutoff": cutoff,
        "archive_manifest_sha256": "b" * 64,
        "selected_observation_count": len(rows),
        "source_count": 4,
        "archive_source_count": 4,
        "current_source_count": 2 if stale_world_bank else 3,
        "stale_source_count": 2 if stale_world_bank else 1,
        "no_snapshot_source_count": 0,
        "first_available_at": "2025-03-01T00:00:00Z",
        "last_available_at": "2025-03-01T00:00:00Z",
        "historical_first_published_claim_allowed": False,
        "direct_index_use_allowed": False,
        "arm_l_use_allowed": False,
        "model_training_allowed": False,
        "shadow_production_allowed": False,
        "monetary_use_allowed": False,
    }
    (target / "information_set_summary.json").write_bytes(canonical_json_bytes(summary))
    entries = {name: sha256_file(target / name) for name in ["panel.csv", "source_cutoff_status.csv", "information_set_summary.json"]}
    (target / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
    return target


def _build(tmp_path: Path, **kwargs) -> Path:
    info = _information_set(tmp_path, **kwargs)
    out = tmp_path / "features"
    build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=out)
    return out


def _rewrite_csv(path: Path, mutate):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    mutate(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _rehash(bundle: Path):
    names = [
        "feature_values.csv",
        "cell_coverage.csv",
        "mapping_audit.csv",
        "unmapped_observations.csv",
        "feature_stream_history.csv",
        "cell_period_coverage.csv",
        "feature_concordance.csv",
        "cell_research_diagnostics.csv",
        "feature_availability_profile.csv",
        "cell_provenance_concentration.csv",
        "cell_research_risk_flags.csv",
        "feature_summary.json",
    ]
    (bundle / "MANIFEST.sha256").write_text("".join(f"{sha256_file(bundle/name)}  {name}\n" for name in sorted(names)), encoding="utf-8")


def _later_information_set(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = _information_set(tmp_path, cutoff="2025-04-15T00:00:00Z")
    rows = list(csv.DictReader((target / "panel.csv").open()))
    for row in rows:
        if row["source_id"] == "WORLD_BANK_PINK_SHEET_MONTHLY" and row["series_id"] == "WB_FOOD_INDEX" and row["period"] == "2025-02":
            row["value"] = "122"
    rows.append(_observation(
        "FAO_FOOD_PRICE_INDEX_MONTHLY",
        "FAO_FFPI",
        "FOOD",
        "WORLD",
        "2025-03",
        "MONTHLY",
        103,
        "INDEX",
        "2025-04-15T00:00:00Z",
        available_at="2025-04-01T00:00:00Z",
    ))
    (target / "panel.csv").write_bytes(csv_bytes(rows, PANEL_COLUMNS))
    statuses = list(csv.DictReader((target / "source_cutoff_status.csv").open()))
    for row in statuses:
        if row["source_id"] == "FAO_FOOD_PRICE_INDEX_MONTHLY":
            row["selected_observation_count"] = str(int(row["selected_observation_count"]) + 1)
            row["latest_snapshot_at"] = "2025-04-10T00:00:00Z"
            row["age_days"] = "5"
    (target / "source_cutoff_status.csv").write_bytes(csv_bytes(statuses, SOURCE_CUTOFF_STATUS_COLUMNS))
    summary = json.loads((target / "information_set_summary.json").read_text())
    summary["selected_observation_count"] = len(rows)
    summary["last_available_at"] = "2025-04-01T00:00:00Z"
    (target / "information_set_summary.json").write_bytes(canonical_json_bytes(summary))
    entries = {name: sha256_file(target / name) for name in ["panel.csv", "source_cutoff_status.csv", "information_set_summary.json"]}
    (target / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
    return target


def _build_comparison(tmp_path: Path):
    first_root = tmp_path / "first-input"; first_root.mkdir()
    later_root = tmp_path / "later-input"
    earlier_info = _information_set(first_root)
    later_info = _later_information_set(later_root)
    earlier = tmp_path / "earlier-features"
    later = tmp_path / "later-features"
    build_feature_panel(information_set_dir=earlier_info, policy_path=POLICY, basket_path=BASKET, output_dir=earlier)
    build_feature_panel(information_set_dir=later_info, policy_path=POLICY, basket_path=BASKET, output_dir=later)
    comparison = tmp_path / "comparison"
    build_feature_comparison(earlier_feature_dir=earlier, later_feature_dir=later, output_dir=comparison)
    return earlier, later, comparison


def test_cli_exposes_comparison_commands():
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert {"validate-policy", "build", "verify", "compare", "verify-comparison"}.issubset(subparsers.choices)


def test_policy_validates():
    load_policy(POLICY)


def test_build_and_verify(tmp_path):
    out = _build(tmp_path)
    summary = verify_feature_bundle(out)
    assert summary["status"] == FEATURE_PANEL_STATUS
    assert summary["research_core_cell_count"] == 60
    assert summary["feature_value_count"] == 66


def test_outputs_are_deterministic(tmp_path):
    info = _information_set(tmp_path)
    first = tmp_path / "first"; second = tmp_path / "second"
    build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=first)
    build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=second)
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}


def test_output_directory_must_not_exist(tmp_path):
    info = _information_set(tmp_path); out = tmp_path / "features"; out.mkdir()
    with pytest.raises(ProxyFeatureError):
        build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=out)


def test_weekly_values_are_monthly_mean(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    row = next(r for r in rows if r["series_id"] == "EC_OIL_DIESEL" and r["target_period"] == "2025-01" and r["transformation"] == "LEVEL")
    assert row["value"] == "110.000000000000"
    assert row["component_count"] == "2"


def test_quarterly_maps_to_quarter_end_month(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    assert any(r["series_id"].startswith("EUROSTAT_OOHPI_") and r["target_period"] == "2025-03" for r in rows)


def test_global_feature_broadcasts_to_five_economies(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    economies = {r["target_economy_code"] for r in rows if r["mapping_id"] == "WB_FOOD_INDEX_TO_CP01" and r["target_period"] == "2025-02" and r["transformation"] == "LEVEL"}
    assert economies == {"DEU", "ESP", "FRA", "ITA", "PRT"}


def test_source_geography_maps_only_matching_economy(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    economies = {r["target_economy_code"] for r in rows if r["series_id"] == "EC_OIL_DIESEL" and r["transformation"] == "LEVEL"}
    assert economies == {"DEU"}


def test_unresolved_and_unknown_are_audited(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "unmapped_observations.csv").open()))
    assert {r["reason"] for r in rows} == {"UNRESOLVED_GEOGRAPHY", "UNMAPPED_SERIES"}


def test_period_change_and_yoy_are_exact(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    period = next(r for r in rows if r["mapping_id"] == "WB_FOOD_INDEX_TO_CP01" and r["target_economy_code"] == "DEU" and r["target_period"] == "2025-02" and r["transformation"] == "PERIOD_CHANGE_PCT")
    yoy = next(r for r in rows if r["mapping_id"] == "WB_FOOD_INDEX_TO_CP01" and r["target_economy_code"] == "DEU" and r["target_period"] == "2025-02" and r["transformation"] == "YEAR_OVER_YEAR_PCT")
    assert period["value"] == "10.000000000000"
    assert yoy["value"] == "19.801980198020"


def test_feature_age_and_completeness(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_values.csv").open()))
    current = next(r for r in rows if r["target_period"] == "2025-03")
    complete = next(r for r in rows if r["target_period"] == "2025-02")
    assert current["period_completeness_status"] == "PARTIAL_PERIOD_AS_OF_CUTOFF"
    assert current["feature_age_days"] == "0"
    assert complete["target_period_end"] == "2025-02-28"
    assert complete["feature_age_days"] == "15"


def test_coverage_counts_streams_not_historical_rows(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "cell_coverage.csv").open()))
    deu_food = next(r for r in rows if r["economy_code"] == "DEU" and r["category_code"] == "CP01")
    assert deu_food["primary_feature_count"] == "2"
    assert deu_food["latest_primary_target_period"] == "2025-02"


def test_weights_sum_exactly_one(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "cell_coverage.csv").open()))
    assert sum(decimal_value(r["fixed_universe_weight"]) for r in rows) == decimal_value("1")


def test_all_gates_closed(tmp_path):
    out = _build(tmp_path)
    summary = json.loads((out / "feature_summary.json").read_text())
    assert all(summary[key] is False for key in [
        "direct_index_use_allowed",
        "arm_l_use_allowed",
        "model_training_allowed",
        "shadow_production_allowed",
        "monetary_use_allowed",
        "price_coverage_claim_allowed",
        "model_ready_claim_allowed",
        "backtest_eligibility_claim_allowed",
        "concordance_approval_claim_allowed",
    ])


def test_extended_diagnostic_outputs_exist_and_reconcile(tmp_path):
    out = _build(tmp_path)
    summary = verify_feature_bundle(out)
    assert summary["feature_stream_count"] == 17
    assert summary["cell_period_coverage_row_count"] == 900
    assert summary["concordance_pair_count"] == 5
    assert summary["cell_research_diagnostic_count"] == 60
    assert summary["feature_stream_with_long_history_count"] == 0
    assert summary["concordance_pair_with_sufficient_overlap_count"] == 0


def test_stream_history_is_frequency_aware(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_stream_history.csv").open()))
    quarterly = next(row for row in rows if row["series_id"].startswith("EUROSTAT_OOHPI_"))
    monthly = next(row for row in rows if row["series_id"] == "FAO_FFPI" and row["target_economy_code"] == "DEU")
    assert quarterly["expected_period_step_months"] == "3"
    assert quarterly["missing_expected_period_count"] == "3"
    assert quarterly["research_diagnostic_status"] == "SENSITIVITY_HISTORY"
    assert monthly["missing_expected_period_count"] == "0"
    assert monthly["research_diagnostic_status"] == "SHORT_HISTORY"
    assert monthly["backtest_eligibility_claim_allowed"] == "false"


def test_cell_period_coverage_exposes_missing_months(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "cell_period_coverage.csv").open()))
    deu_food = [row for row in rows if row["economy_code"] == "DEU" and row["category_code"] == "CP01"]
    assert len(deu_food) == 15
    assert next(row for row in deu_food if row["target_period"] == "2025-02")["complete_primary_stream_count"] == "2"
    assert next(row for row in deu_food if row["target_period"] == "2024-03")["period_status"] == "NO_FEATURE"


def test_concordance_is_descriptive_and_never_approved(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "feature_concordance.csv").open()))
    row = next(item for item in rows if item["target_economy_code"] == "DEU" and item["target_category_code"] == "CP01")
    assert row["overlap_period_count"] == "1"
    assert row["direction_agreement_ratio"] == "1.000000000000"
    assert row["concordance_status"] == "INSUFFICIENT_OVERLAP"
    assert row["concordance_approval_claim_allowed"] == "false"
    assert row["model_ready_claim_allowed"] == "false"


def test_cell_research_diagnostics_are_not_eligibility_claims(tmp_path):
    out = _build(tmp_path)
    rows = list(csv.DictReader((out / "cell_research_diagnostics.csv").open()))
    food = next(row for row in rows if row["economy_code"] == "DEU" and row["category_code"] == "CP01")
    empty = next(row for row in rows if row["economy_code"] == "DEU" and row["category_code"] == "CP02")
    assert food["diagnostic_class"] == "PRIMARY_SHORT_HISTORY"
    assert food["distinct_primary_source_count"] == "2"
    assert food["complete_multi_source_period_count"] == "2"
    assert empty["diagnostic_class"] == "NO_PRIMARY_FEATURE"
    assert food["backtest_eligibility_claim_allowed"] == "false"


def test_decimal_pearson_is_deterministic():
    assert _pearson(
        [(decimal_value("1"), decimal_value("2")), (decimal_value("2"), decimal_value("4")), (decimal_value("3"), decimal_value("6"))],
        12,
    ) == "1.000000000000"
    assert _pearson([(decimal_value("1"), decimal_value("2")), (decimal_value("1"), decimal_value("3"))], 12) == ""


def test_policy_rejects_diagnostic_promotion():
    policy = json.loads(POLICY.read_text())
    policy["diagnostic_policy"]["no_automatic_eligibility_promotion"] = False
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)


def test_availability_provenance_and_risk_outputs_are_descriptive(tmp_path):
    out = _build(tmp_path)
    availability = list(csv.DictReader((out / "feature_availability_profile.csv").open()))
    provenance = list(csv.DictReader((out / "cell_provenance_concentration.csv").open()))
    risk = list(csv.DictReader((out / "cell_research_risk_flags.csv").open()))
    assert availability
    assert len(provenance) == 60
    assert len(risk) == 60
    food_stream = next(row for row in availability if row["source_id"] == "WORLD_BANK_PINK_SHEET_MONTHLY" and row["target_economy_code"] == "DEU" and row["target_category_code"] == "CP01")
    assert int(food_stream["beyond_diagnostic_window_count"]) > 0
    assert food_stream["availability_profile_status"] == "SOME_FIRST_SEEN_LAGS_BEYOND_DIAGNOSTIC_WINDOW"
    food_cell = next(row for row in provenance if row["economy_code"] == "DEU" and row["category_code"] == "CP01")
    assert food_cell["distinct_primary_source_count"] == "2"
    assert food_cell["quality_weighting_allowed"] == "false"
    empty_risk = next(row for row in risk if row["economy_code"] == "DEU" and row["category_code"] == "CP02")
    assert empty_risk["no_primary_feature"] == "true"
    assert empty_risk["risk_profile_status"] == "NO_PRIMARY_FEATURE"
    assert empty_risk["model_ready_claim_allowed"] == "false"


def test_negative_first_seen_lag_is_flagged_without_promotion(tmp_path):
    info = _information_set(tmp_path)
    rows = list(csv.DictReader((info / "panel.csv").open()))
    for row in rows:
        if row["source_id"] == "FAO_FOOD_PRICE_INDEX_MONTHLY" and row["period"] == "2025-02":
            row["available_at"] = "2025-02-15T00:00:00Z"
    (info / "panel.csv").write_bytes(csv_bytes(rows, PANEL_COLUMNS))
    entries = {name: sha256_file(info / name) for name in ["panel.csv", "source_cutoff_status.csv", "information_set_summary.json"]}
    (info / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
    out = tmp_path / "negative-lag-features"
    build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=out)
    availability = list(csv.DictReader((out / "feature_availability_profile.csv").open()))
    row = next(item for item in availability if item["source_id"] == "FAO_FOOD_PRICE_INDEX_MONTHLY" and item["target_economy_code"] == "DEU")
    assert int(row["negative_first_seen_lag_count"]) == 1
    assert row["availability_profile_status"] == "NEGATIVE_FIRST_SEEN_LAG_PRESENT"
    risk = list(csv.DictReader((out / "cell_research_risk_flags.csv").open()))
    cell = next(item for item in risk if item["economy_code"] == "DEU" and item["category_code"] == "CP01")
    assert cell["negative_first_seen_lag_present"] == "true"
    assert cell["backtest_eligibility_claim_allowed"] == "false"


def test_policy_rejects_risk_score_or_changed_diagnostic_threshold():
    policy = json.loads(POLICY.read_text())
    policy["diagnostic_policy"]["no_aggregate_risk_score"] = False
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)
    policy = json.loads(POLICY.read_text())
    policy["diagnostic_policy"]["provenance_concentration_diagnostic_percent"] = 49
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)


def test_feature_panel_comparison_revision_stability_outputs(tmp_path):
    _, _, comparison = _build_comparison(tmp_path)
    streams = list(csv.DictReader((comparison / "stream_revision_stability.csv").open()))
    cells = list(csv.DictReader((comparison / "cell_revision_stability.csv").open()))
    assert streams
    assert len(cells) == 60
    changed = next(row for row in streams if row["source_id"] == "WORLD_BANK_PINK_SHEET_MONTHLY" and row["target_economy_code"] == "DEU" and row["target_category_code"] == "CP01" and row["transformation"] == "LEVEL")
    assert int(changed["value_changed_feature_count"]) == 1
    assert changed["stability_status"] == "VALUE_REVISIONS_OBSERVED"
    assert changed["comparison_decision_use_allowed"] == "false"
    cell = next(row for row in cells if row["economy_code"] == "DEU" and row["category_code"] == "CP01")
    assert int(cell["streams_with_value_revisions"]) >= 1
    assert cell["model_ready_claim_allowed"] == "false"


def test_feature_panel_comparison_rejects_stability_tampering(tmp_path):
    _, _, comparison = _build_comparison(tmp_path)
    _rewrite_csv(comparison / "stream_revision_stability.csv", lambda rows: rows[0].__setitem__("unchanged_feature_count", "999"))
    names = [
        "feature_deltas.csv",
        "cell_coverage_deltas.csv",
        "stream_revision_stability.csv",
        "cell_revision_stability.csv",
        "comparison_summary.json",
    ]
    (comparison / "MANIFEST.sha256").write_text("".join(f"{sha256_file(comparison/name)}  {name}\n" for name in sorted(names)), encoding="utf-8")
    with pytest.raises(ProxyFeatureError):
        verify_feature_comparison_bundle(comparison)


def test_feature_panel_comparison_detects_additions_and_revisions(tmp_path):
    _, _, comparison = _build_comparison(tmp_path)
    summary = verify_feature_comparison_bundle(comparison)
    assert summary["status"] == "POINT_IN_TIME_PROXY_FEATURE_COMPARISON_V099_VALID"
    assert summary["added_feature_count"] > 0
    assert summary["value_changed_feature_count"] > 0
    assert summary["removed_feature_count"] == 0
    rows = list(csv.DictReader((comparison / "feature_deltas.csv").open()))
    changed = next(row for row in rows if row["series_id"] == "WB_FOOD_INDEX" and row["target_period"] == "2025-02" and row["transformation"] == "LEVEL")
    assert changed["delta_status"] == "VALUE_CHANGED"
    assert changed["value_delta"] == "1.000000000000"


def test_feature_panel_comparison_is_deterministic(tmp_path):
    earlier, later, first = _build_comparison(tmp_path)
    second = tmp_path / "comparison-2"
    build_feature_comparison(earlier_feature_dir=earlier, later_feature_dir=later, output_dir=second)
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {path.name: path.read_bytes() for path in second.iterdir()}


def test_feature_panel_comparison_rejects_reverse_cutoffs(tmp_path):
    earlier, later, _ = _build_comparison(tmp_path)
    with pytest.raises(ProxyFeatureError):
        build_feature_comparison(earlier_feature_dir=later, later_feature_dir=earlier, output_dir=tmp_path / "reverse")


def test_feature_panel_comparison_rejects_semantic_tampering(tmp_path):
    _, _, comparison = _build_comparison(tmp_path)
    _rewrite_csv(comparison / "feature_deltas.csv", lambda rows: rows[0].__setitem__("value_delta", "999"))
    names = [
        "feature_deltas.csv",
        "cell_coverage_deltas.csv",
        "stream_revision_stability.csv",
        "cell_revision_stability.csv",
        "comparison_summary.json",
    ]
    (comparison / "MANIFEST.sha256").write_text("".join(f"{sha256_file(comparison/name)}  {name}\n" for name in sorted(names)), encoding="utf-8")
    with pytest.raises(ProxyFeatureError):
        verify_feature_comparison_bundle(comparison)


@pytest.mark.parametrize("period,frequency,expected", [("2025-01", "MONTHLY", "2025-01"), ("2025-01-06", "WEEKLY", "2025-01"), ("2025-Q2", "QUARTERLY", "2025-06")])
def test_month_key(period, frequency, expected):
    assert month_key(period, frequency) == expected


@pytest.mark.parametrize("period,months,expected", [("2025-01", -1, "2024-12"), ("2025-03", -3, "2024-12"), ("2025-01", 12, "2026-01")])
def test_shift_month(period, months, expected):
    assert shift_month(period, months) == expected


def test_decimal_half_even():
    assert decimal_text(decimal_value("1.23445"), 4) == "1.2344"


def test_percent_change_zero_denominator_is_omitted():
    assert percent_change(decimal_value("2"), decimal_value("0"), 12) is None


def test_geography_alias_resolution():
    policy = load_policy(POLICY)
    assert resolve_geography(policy, "Germany") == "DEU"
    assert resolve_geography(policy, "unknown") is None


def test_mapping_exact_and_prefix():
    policy = load_policy(POLICY)
    exact = mapping_for_row(policy, {"source_id": "FAO_FOOD_PRICE_INDEX_MONTHLY", "series_id": "FAO_FFPI", "proxy_domain": "FOOD"})
    prefix = mapping_for_row(policy, {"source_id": "EUROSTAT_OOHPI_QUARTERLY", "series_id": "EUROSTAT_OOHPI_X", "proxy_domain": "HOUSING_OOH_SENSITIVITY"})
    assert exact["mapping_id"] == "FAO_FFPI_TO_CP01"
    assert prefix["mapping_id"] == "EUROSTAT_OOHPI_TO_CP04_SENSITIVITY"


def test_policy_rejects_open_gate():
    policy = json.loads(POLICY.read_text())
    policy["output_gates"]["model_training_allowed"] = True
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)


def test_policy_rejects_overlapping_exact_rule():
    policy = json.loads(POLICY.read_text())
    duplicate = dict(policy["category_mappings"][0]); duplicate["mapping_id"] = "DUPLICATE"
    policy["category_mappings"].append(duplicate)
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)


def test_policy_rejects_wrong_armilar_category():
    policy = json.loads(POLICY.read_text())
    policy["category_mappings"][0]["target_armilar_category"] = "ARM09"
    with pytest.raises(ProxyFeatureError):
        validate_policy(policy)


@pytest.mark.parametrize("filename,mutator", [
    ("feature_values.csv", lambda rows: rows[0].__setitem__("feature_age_days", "999")),
    ("feature_values.csv", lambda rows: rows[0].__setitem__("model_training_allowed", "true")),
    ("cell_coverage.csv", lambda rows: rows[0].__setitem__("primary_feature_count", "999")),
    ("cell_coverage.csv", lambda rows: rows[0].__setitem__("fixed_universe_weight", "0")),
    ("mapping_audit.csv", lambda rows: rows[0].__setitem__("matched_input_observation_count", "999")),
    ("unmapped_observations.csv", lambda rows: rows[0].__setitem__("reason", "INVENTED")),
    ("feature_stream_history.csv", lambda rows: rows[0].__setitem__("missing_expected_period_count", "999")),
    ("cell_period_coverage.csv", lambda rows: rows[0].__setitem__("period_status", "NO_FEATURE")),
    ("feature_concordance.csv", lambda rows: rows[0].__setitem__("concordance_status", "DESCRIPTIVE_ONLY")),
    ("cell_research_diagnostics.csv", lambda rows: rows[0].__setitem__("diagnostic_class", "PRIMARY_LONG_HISTORY")),
    ("feature_availability_profile.csv", lambda rows: rows[0].__setitem__("maximum_first_seen_lag_days", "9999")),
    ("cell_provenance_concentration.csv", lambda rows: rows[0].__setitem__("source_observation_hhi", "0.000000000000")),
    ("cell_research_risk_flags.csv", lambda rows: rows[0].__setitem__("descriptive_flag_count", "0")),
])
def test_verifier_rejects_semantic_tampering(tmp_path, filename, mutator):
    out = _build(tmp_path)
    _rewrite_csv(out / filename, mutator); _rehash(out)
    with pytest.raises(ProxyFeatureError):
        verify_feature_bundle(out)


def test_verifier_rejects_file_tampering_without_rehash(tmp_path):
    out = _build(tmp_path)
    with (out / "feature_values.csv").open("a") as handle:
        handle.write("tamper\n")
    with pytest.raises(ProxyFeatureError):
        verify_feature_bundle(out)


def test_stale_source_propagates_to_coverage(tmp_path):
    out = _build(tmp_path, stale_world_bank=True)
    rows = list(csv.DictReader((out / "cell_coverage.csv").open()))
    energy = next(r for r in rows if r["economy_code"] == "DEU" and r["category_code"] == "CP04")
    assert energy["coverage_status"] == "PRIMARY_FEATURE_FROM_STALE_SOURCE"


def test_future_period_rejected(tmp_path):
    info = _information_set(tmp_path)
    rows = list(csv.DictReader((info / "panel.csv").open()))
    rows[0]["period"] = "2025-04"
    (info / "panel.csv").write_bytes(csv_bytes(rows, PANEL_COLUMNS))
    entries = {name: sha256_file(info / name) for name in ["panel.csv", "source_cutoff_status.csv", "information_set_summary.json"]}
    (info / "MANIFEST.sha256").write_bytes(bundle_manifest_bytes(entries))
    with pytest.raises(ProxyFeatureError):
        build_feature_panel(information_set_dir=info, policy_path=POLICY, basket_path=BASKET, output_dir=tmp_path / "out")


def test_target_period_metadata_partial_and_complete():
    assert target_period_metadata("2025-03", "2025-03-15T00:00:00Z") == ("2025-03-31", 0, "PARTIAL_PERIOD_AS_OF_CUTOFF")
    assert target_period_metadata("2025-02", "2025-03-15T00:00:00Z") == ("2025-02-28", 15, "COMPLETE_PERIOD")
