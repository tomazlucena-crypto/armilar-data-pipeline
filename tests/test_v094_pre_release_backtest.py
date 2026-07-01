from __future__ import annotations

import csv
import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from armilar_prices.pre_release_backtest_v094 import (
    AS_OF_DEFINITION,
    FORECAST_MODE,
    MODELS,
    P0,
    P1,
    P2,
    P3,
    P4,
    PRICE_CATEGORIES,
    REQUIRED_CATEGORIES,
    REQUIRED_ECONOMIES,
    TRUTH_DEFINITION,
    PreReleaseBacktestError,
    PreReleasePolicy,
    _cell_forecast,
    _forecast_pairs,
    _global_forecast,
    _truth_global,
    add_months,
    build_pre_release_backtest,
    load_first_published_panel,
    verify_manifest,
)

UNIVERSE = "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            lines.append(f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _periods() -> list[str]:
    result = []
    current = "2021-01"
    while current <= "2025-12":
        result.append(current)
        current = add_months(current, 1)
    return result


def _weights() -> tuple[dict[tuple[str, str], Decimal], dict[str, Decimal]]:
    cell = {
        (economy, category): Decimal("0.01")
        for economy in REQUIRED_ECONOMIES
        for category in PRICE_CATEGORIES
    }
    cell[("PRT", "CP12")] = Decimal("0.41")
    economy = {
        code: sum((cell[(code, category)] for category in PRICE_CATEGORIES), Decimal("0"))
        for code in REQUIRED_ECONOMIES
    }
    assert sum(cell.values(), Decimal("0")) == Decimal("1")
    assert sum(economy.values(), Decimal("0")) == Decimal("1")
    return cell, economy


def _release_date(period: str) -> str:
    next_month = add_months(period, 1)
    return f"{next_month}-18"


def _value(economy_index: int, category_index: int, month_index: int) -> Decimal:
    base = Decimal("1") + Decimal(economy_index) / Decimal("1000")
    trend = Decimal(month_index) * (
        Decimal("0.0007") + Decimal(category_index) / Decimal("100000")
    )
    seasonal = Decimal((month_index % 12) - 5) * Decimal((category_index % 4)) / Decimal(
        "100000"
    )
    if economy_index == 3 and category_index == 4:
        trend += Decimal(month_index) * Decimal("0.0004")
    return base + trend + seasonal


def _write_panel(root: Path, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cell_weights, economy_weights = _weights()
    fields = [
        "universe_id",
        "economy_code",
        "economy_name",
        "eurostat_geo",
        "source_category",
        "armilar_category",
        "period",
        "available_from_date",
        "price_value_first_published",
        "reference_period",
        "reference_price_value_first_published",
        "price_relative_first_published",
        "fixed_universe_weight",
        "economy_fixed_universe_weight",
        "price_evidence_class",
        "value_vintage_class",
        "provider",
        "dataset",
        "status",
        "request_id",
        "raw_file",
        "raw_sha256",
    ]
    rows: list[dict[str, str]] = []
    periods = _periods()
    for economy_index, economy in enumerate(REQUIRED_ECONOMIES):
        for month_index, period in enumerate(periods):
            category_values = {
                category: _value(economy_index, category_index, month_index)
                for category_index, category in enumerate(PRICE_CATEGORIES, start=1)
            }
            economy_weight = economy_weights[economy]
            headline = sum(
                (
                    cell_weights[(economy, category)]
                    / economy_weight
                    * category_values[category]
                    for category in PRICE_CATEGORIES
                ),
                Decimal("0"),
            )
            all_values = {"CP00": headline, **category_values}
            for category in REQUIRED_CATEGORIES:
                relative = all_values[category]
                weight = (
                    economy_weight
                    if category == "CP00"
                    else cell_weights[(economy, category)]
                )
                rows.append(
                    {
                        "universe_id": UNIVERSE,
                        "economy_code": economy,
                        "economy_name": economy,
                        "eurostat_geo": economy[:2],
                        "source_category": category,
                        "armilar_category": category,
                        "period": period,
                        "available_from_date": _release_date(period),
                        "price_value_first_published": str(relative * Decimal("100")),
                        "reference_period": "2021",
                        "reference_price_value_first_published": "100",
                        "price_relative_first_published": str(relative),
                        "fixed_universe_weight": str(weight),
                        "economy_fixed_universe_weight": str(economy_weight),
                        "price_evidence_class": "P1_OFFICIAL_FIRST_PUBLISHED_HICP",
                        "value_vintage_class": "FIRST_PUBLISHED_FULL_DATA_RELEASE",
                        "provider": "EUROSTAT",
                        "dataset": "prc_hicp_fp",
                        "status": "",
                        "request_id": "first_published_panel",
                        "raw_file": "raw/panel.json",
                        "raw_sha256": "a" * 64,
                    }
                )
    if mutate is not None:
        mutate(rows)
    with (root / "first_published_observations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": "1.0",
        "pipeline_version": "0.9.3",
        "policy_version": "0.9.3",
        "status": "OFFICIAL_FIRST_PUBLISHED_HICP_PANEL_BUILT",
        "historical_value_vintages_available": True,
        "value_vintage_class": "FIRST_PUBLISHED_FULL_DATA_RELEASE",
        "universe_id": UNIVERSE,
        "observation_count": 3900,
        "release_timing_attached": True,
        "first_published_values_attached": True,
        "snapshot_manifest_sha256": "b" * 64,
        "model_code_changed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    (root / "run_summary.json").write_text(
        json.dumps(summary, sort_keys=True), encoding="utf-8"
    )
    _manifest(root)
    return root


def _policy(tmp_path: Path, **updates) -> Path:
    payload = {
        "policy_version": "0.9.4",
        "universe_id": UNIVERSE,
        "required_first_published_policy_version": "0.9.3",
        "history_start": "2021-01",
        "history_end": "2025-12",
        "evaluation_target_start": "2023-01",
        "evaluation_target_end": "2025-12",
        "development_target_start": "2023-01",
        "development_target_end": "2023-12",
        "holdout_target_start": "2024-01",
        "holdout_target_end": "2025-12",
        "horizons": [1, 3, 6, 12],
        "models": list(MODELS),
        "minimum_history_months": 12,
        "seasonal_lag_months": 12,
        "ensemble_carry_forward_weight": "0.5",
        "ensemble_seasonal_weight": "0.5",
        "forecast_mode": FORECAST_MODE,
        "truth_definition": TRUTH_DEFINITION,
        "as_of_definition": AS_OF_DEFINITION,
        "pre_release_forecast": True,
        "target_period_values_allowed": False,
        "target_period_donors_allowed": False,
        "future_period_source_values_allowed": False,
        "target_release_date_used_for_prediction": False,
        "uses_first_published_history": True,
        "historical_as_of_revisions_available": False,
        "development_data_used_for_model_selection": False,
        "holdout_data_used_for_model_selection": False,
        "rejected_v089_experiment_reused": False,
        "pre_release_forecast_comparison_allowed": True,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    payload.update(updates)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def panel_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _write_panel(tmp_path_factory.mktemp("panel"))


@pytest.fixture(scope="module")
def built_output(tmp_path_factory: pytest.TempPathFactory, panel_dir: Path) -> Path:
    root = tmp_path_factory.mktemp("built")
    policy = _policy(root)
    output = root / "output"
    build_pre_release_backtest(policy, panel_dir, output)
    return output


def test_policy_accepts_pre_release_contract(tmp_path: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    assert policy.pre_release_forecast is True
    assert policy.forecast_mode == FORECAST_MODE
    assert policy.models == MODELS
    assert policy.pre_release_forecast_comparison_allowed is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_period_values_allowed", True),
        ("target_period_donors_allowed", True),
        ("future_period_source_values_allowed", True),
        ("target_release_date_used_for_prediction", True),
        ("historical_as_of_revisions_available", True),
        ("development_data_used_for_model_selection", True),
        ("holdout_data_used_for_model_selection", True),
        ("rejected_v089_experiment_reused", True),
        ("model_promotion_allowed", True),
        ("research_release_allowed", True),
        ("monetary_release_allowed", True),
        ("pre_release_forecast", False),
        ("pre_release_forecast_comparison_allowed", False),
        ("uses_first_published_history", False),
    ],
)
def test_policy_rejects_leakage_false_claims_and_open_gates(
    tmp_path: Path, field: str, value: object
) -> None:
    with pytest.raises(PreReleaseBacktestError):
        PreReleasePolicy.load(_policy(tmp_path, **{field: value}))


def test_policy_rejects_changed_universe_or_time_window(tmp_path: Path) -> None:
    with pytest.raises(PreReleaseBacktestError, match="UNIVERSE_CONTRACT_MISMATCH"):
        PreReleasePolicy.load(_policy(tmp_path, universe_id="OTHER"))
    with pytest.raises(PreReleaseBacktestError, match="TEMPORAL_CONTRACT_MISMATCH"):
        PreReleasePolicy.load(_policy(tmp_path, holdout_target_start="2024-02"))
    with pytest.raises(PreReleaseBacktestError, match="MINIMUM_HISTORY_CONTRACT_MISMATCH"):
        PreReleasePolicy.load(_policy(tmp_path, minimum_history_months=24))


def test_policy_rejects_tuned_ensemble_weights(tmp_path: Path) -> None:
    with pytest.raises(PreReleaseBacktestError, match="ENSEMBLE_WEIGHT_CONTRACT_MISMATCH"):
        PreReleasePolicy.load(
            _policy(
                tmp_path,
                ensemble_carry_forward_weight="0.7",
                ensemble_seasonal_weight="0.3",
            )
        )


def test_loader_builds_exact_panel(tmp_path: Path, panel_dir: Path) -> None:
    panel = load_first_published_panel(PreReleasePolicy.load(_policy(tmp_path)), panel_dir)
    assert len(panel.values) == 3900
    assert len(panel.cell_weights) == 60
    assert len(panel.economy_weights) == 5
    assert len(panel.release_dates) == 60
    assert panel.periods[0] == "2021-01"
    assert panel.periods[-1] == "2025-12"


def test_loader_rejects_missing_observation(tmp_path: Path) -> None:
    input_dir = _write_panel(tmp_path / "input", lambda rows: rows.pop())
    with pytest.raises(PreReleaseBacktestError, match="GRID_INCOMPLETE"):
        load_first_published_panel(PreReleasePolicy.load(_policy(tmp_path)), input_dir)


def test_loader_rejects_universe_mismatch(tmp_path: Path) -> None:
    def mutate(rows):
        rows[0]["universe_id"] = "WRONG"

    input_dir = _write_panel(tmp_path / "input", mutate)
    with pytest.raises(PreReleaseBacktestError, match="UNIVERSE_MISMATCH"):
        load_first_published_panel(PreReleasePolicy.load(_policy(tmp_path)), input_dir)


def test_loader_rejects_weight_drift(tmp_path: Path) -> None:
    def mutate(rows):
        rows[-1]["fixed_universe_weight"] = "0.42"

    input_dir = _write_panel(tmp_path / "input", mutate)
    with pytest.raises(PreReleaseBacktestError, match="CELL_WEIGHT_CHANGED"):
        load_first_published_panel(PreReleasePolicy.load(_policy(tmp_path)), input_dir)


def test_forecast_pairs_are_complete_and_pre_release(tmp_path: Path, panel_dir: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    panel = load_first_published_panel(policy, panel_dir)
    pairs = _forecast_pairs(policy, panel)
    assert len(pairs) == 144
    assert {horizon for _, _, horizon in pairs} == {1, 3, 6, 12}
    assert all(origin < target for origin, target, _ in pairs)
    assert all(panel.release_dates[origin] < panel.release_dates[target] for origin, target, _ in pairs)


def test_seasonal_forecast_uses_only_origin_or_earlier(tmp_path: Path, panel_dir: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    panel = load_first_published_panel(policy, panel_dir)
    result = _cell_forecast(panel, policy, P3, "ITA", "CP04", "2023-12", "2024-01")
    assert max(result.source_periods) == "2023-12"
    assert "2024-01" not in result.source_periods
    expected = panel.values[("ITA", "CP04", "2023-01")] * (
        panel.values[("ITA", "CP04", "2023-12")]
        / panel.values[("ITA", "CP04", "2022-12")]
    )
    assert result.value == expected


def test_half_ensemble_is_fixed_average(tmp_path: Path, panel_dir: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    panel = load_first_published_panel(policy, panel_dir)
    carry = _cell_forecast(panel, policy, P2, "DEU", "CP04", "2023-12", "2024-01")
    seasonal = _cell_forecast(panel, policy, P3, "DEU", "CP04", "2023-12", "2024-01")
    ensemble = _cell_forecast(panel, policy, P4, "DEU", "CP04", "2023-12", "2024-01")
    assert ensemble.value == (carry.value + seasonal.value) / Decimal("2")


def test_headline_models_use_origin_only(tmp_path: Path, panel_dir: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    panel = load_first_published_panel(policy, panel_dir)
    for model in (P0, P1):
        forecast = _global_forecast(panel, policy, model, "2023-12", "2024-01")
        assert forecast.source_periods == ("2023-12",)


def test_truth_is_category_weighted_not_cp00(tmp_path: Path, panel_dir: Path) -> None:
    policy = PreReleasePolicy.load(_policy(tmp_path))
    panel = load_first_published_panel(policy, panel_dir)
    truth = _truth_global(panel, "2024-01")
    expected = sum(
        (
            panel.cell_weights[(economy, category)]
            * panel.values[(economy, category, "2024-01")]
            for economy in REQUIRED_ECONOMIES
            for category in PRICE_CATEGORIES
        ),
        Decimal("0"),
    )
    assert truth == expected


def test_build_outputs_complete_counts(built_output: Path) -> None:
    summary = json.loads((built_output / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["global_case_count_per_model"] == 144
    assert summary["global_case_row_count"] == 720
    assert summary["economy_case_row_count"] == 2880
    assert summary["cell_case_row_count"] == 25920
    assert summary["target_period_values_used_for_prediction"] is False
    assert summary["target_period_donors_used"] is False
    assert summary["historical_as_of_revisions_available"] is False
    assert summary["model_promotion_allowed"] is False


def test_forecast_rows_prove_no_lookahead(built_output: Path) -> None:
    with (built_output / "forecast_cases.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 720
    assert all(row["maximum_source_period"] <= row["origin_period"] for row in rows)
    assert all(row["target_period"] not in row["source_periods"].split(";") for row in rows)
    assert all(row["target_period_values_used_for_prediction"] == "false" for row in rows)
    assert all(row["target_period_donors_used"] == "false" for row in rows)


def test_holdout_evaluation_is_sealed_and_unpromoted(built_output: Path) -> None:
    payload = json.loads((built_output / "holdout_evaluation.json").read_text(encoding="utf-8"))
    assert payload["holdout_data_used_for_model_selection"] is False
    assert payload["model_promotion_allowed"] is False
    assert len(payload["model_ranking"]) == 5
    assert {item["model"] for item in payload["model_ranking"]} == set(MODELS)


def test_focus_metrics_include_italy_cp04_and_twelve_months(built_output: Path) -> None:
    with (built_output / "error_by_economy.csv").open(newline="", encoding="utf-8") as handle:
        economy_rows = list(csv.DictReader(handle))
    with (built_output / "error_by_category.csv").open(newline="", encoding="utf-8") as handle:
        category_rows = list(csv.DictReader(handle))
    with (built_output / "model_metrics.csv").open(newline="", encoding="utf-8") as handle:
        model_rows = list(csv.DictReader(handle))
    assert any(row["economy_code"] == "ITA" and row["split"] == "HOLDOUT" for row in economy_rows)
    assert any(row["source_category"] == "CP04" and row["split"] == "HOLDOUT" for row in category_rows)
    assert any(row["horizon_months"] == "12" and row["split"] == "HOLDOUT" for row in model_rows)


def test_manifest_verifies_and_detects_tampering(tmp_path: Path, built_output: Path) -> None:
    copied = tmp_path / "copied"
    shutil.copytree(built_output, copied)
    verify_manifest(copied)
    with (copied / "forecast_cases.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    with pytest.raises(PreReleaseBacktestError, match="MANIFEST_HASH_MISMATCH"):
        verify_manifest(copied)


def test_build_rejects_nonempty_output(tmp_path: Path, panel_dir: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "existing.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PreReleaseBacktestError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_pre_release_backtest(_policy(tmp_path), panel_dir, output)


def test_build_is_deterministic(tmp_path: Path, panel_dir: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    policy = _policy(tmp_path)
    build_pre_release_backtest(policy, panel_dir, first)
    build_pre_release_backtest(policy, panel_dir, second)
    first_hashes = {
        path.relative_to(first): _sha256(path.read_bytes())
        for path in first.rglob("*")
        if path.is_file()
    }
    second_hashes = {
        path.relative_to(second): _sha256(path.read_bytes())
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_hashes == second_hashes


def test_report_states_historical_vintage_limitation(built_output: Path) -> None:
    report = (built_output / "PRE_RELEASE_BACKTEST_REPORT.md").read_text(encoding="utf-8")
    assert "No target-month value or target-month donor is used" in report
    assert "Later revisions" in report
    assert "model_promotion_allowed=false" in report


def test_extended_diagnostic_outputs_exist(built_output: Path) -> None:
    assert (built_output / "paired_model_comparisons.csv").is_file()
    assert (built_output / "ranking_stability.json").is_file()
    assert (built_output / "focus_diagnostics.json").is_file()


def test_paired_comparisons_cover_fixed_pairs_splits_and_horizons(
    built_output: Path,
) -> None:
    with (built_output / "paired_model_comparisons.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 90
    assert {row["split"] for row in rows} == {"ALL", "DEVELOPMENT", "HOLDOUT"}
    assert {row["horizon_months"] for row in rows} == {"ALL", "1", "3", "6", "12"}
    assert all(int(row["case_count"]) > 0 for row in rows)
    assert all(Decimal(row["improvement_rate"]) >= 0 for row in rows)
    assert all(Decimal(row["regression_rate"]) >= 0 for row in rows)


def test_ranking_stability_is_descriptive_and_unpromoted(built_output: Path) -> None:
    payload = json.loads(
        (built_output / "ranking_stability.json").read_text(encoding="utf-8")
    )
    assert set(payload["development_ranking"]) == set(MODELS)
    assert set(payload["holdout_ranking"]) == set(MODELS)
    assert len(payload["by_horizon"]) == 4
    assert payload["development_data_used_for_model_selection"] is False
    assert payload["holdout_data_used_for_model_selection"] is False
    assert payload["model_promotion_allowed"] is False


def test_focus_diagnostics_cover_italy_portugal_cp04_and_twelve_months(
    built_output: Path,
) -> None:
    payload = json.loads(
        (built_output / "focus_diagnostics.json").read_text(encoding="utf-8")
    )
    assert len(payload["italy_holdout"]) == 4
    assert len(payload["portugal_holdout"]) == 4
    assert len(payload["cp04_holdout"]) == 3
    assert len(payload["twelve_month_holdout"]) == 5
    assert payload["model_promotion_allowed"] is False
    for key in (
        "italy_holdout",
        "portugal_holdout",
        "cp04_holdout",
        "twelve_month_holdout",
    ):
        assert [row["rank"] for row in payload[key]] == list(
            range(1, len(payload[key]) + 1)
        )


def test_model_metrics_include_signed_bias(built_output: Path) -> None:
    with (built_output / "model_metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "mean_signed_error_bps" in rows[0]
    assert all(Decimal(row["mean_signed_error_bps"]).is_finite() for row in rows)


def test_run_summary_confirms_common_sample_and_diagnostics(built_output: Path) -> None:
    summary = json.loads((built_output / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["common_global_sample_verified"] is True
    assert summary["common_global_case_id_count"] == 144
    assert summary["paired_comparison_count"] == 6
    assert summary["paired_comparison_row_count"] == 90
    assert isinstance(summary["development_holdout_ranking_changed"], bool)
    assert isinstance(summary["development_holdout_winner_changed"], bool)


def test_report_includes_bias_and_ranking_stability(built_output: Path) -> None:
    report = (built_output / "PRE_RELEASE_BACKTEST_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "Holdout bias (bps)" in report
    assert "## Ranking stability" in report
    assert "## Holdout paired comparisons" in report
    assert "Development ranking:" in report
    assert "Holdout ranking:" in report
