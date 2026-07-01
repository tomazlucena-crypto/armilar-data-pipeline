from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from armilar_prices.release_time_backtest_v093 import (
    B2,
    B3,
    COMPLETION_MODE,
    CandidateRule,
    ReleaseTimeBacktestError,
    ReleaseTimePolicy,
    _activate_rules,
    _build_b4_cases,
    build_release_time_backtest,
    load_first_published_panel,
    verify_manifest,
)

ECONOMIES = ("DEU", "ESP", "FRA", "ITA", "PRT")
CATEGORIES = tuple(f"CP{i:02d}" for i in range(13))


def _periods() -> list[str]:
    values: list[str] = []
    year, month = 2021, 1
    while (year, month) <= (2025, 12):
        values.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return values


def _release_date(period: str) -> str:
    year, month = int(period[:4]), int(period[5:])
    if month == 12:
        return date(year + 1, 1, 18).isoformat()
    return date(year, month + 1, 18).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path) -> None:
    lines = [
        f"{_sha(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.sha256"
    ]
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _weights() -> tuple[dict[tuple[str, str], Decimal], dict[str, Decimal]]:
    cell: dict[tuple[str, str], Decimal] = {}
    for economy in ECONOMIES:
        for category in CATEGORIES[1:]:
            cell[(economy, category)] = Decimal("0.01")
    cell[("PRT", "CP12")] = Decimal("0.41")
    economy = {
        code: sum((cell[(code, category)] for category in CATEGORIES[1:]), Decimal("0"))
        for code in ECONOMIES
    }
    assert sum(cell.values(), Decimal("0")) == Decimal("1")
    assert sum(economy.values(), Decimal("0")) == Decimal("1")
    return cell, economy


def _write_first_published(root: Path, mutate=None) -> Path:
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
    for economy_index, economy in enumerate(ECONOMIES):
        for category_index, category in enumerate(CATEGORIES):
            for month_index, period in enumerate(_periods()):
                if category == "CP08":
                    relative = Decimal("1") + Decimal(economy_index) / Decimal("1000")
                else:
                    relative = (
                        Decimal("1")
                        + Decimal(economy_index) / Decimal("1000")
                        + Decimal(category_index) / Decimal("10000")
                        + Decimal(month_index) / Decimal("1000")
                    )
                weight = (
                    economy_weights[economy]
                    if category == "CP00"
                    else cell_weights[(economy, category)]
                )
                rows.append(
                    {
                        "universe_id": "ARMILAR_EUROSTAT_5_ECONOMY_VERTICAL",
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
                        "economy_fixed_universe_weight": str(economy_weights[economy]),
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
        "universe_id": "ARMILAR_EUROSTAT_5_ECONOMY_VERTICAL",
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
        "policy_version": "0.9.3",
        "universe_id": "ARMILAR_EUROSTAT_5_ECONOMY_VERTICAL",
        "required_first_published_policy_version": "0.9.3",
        "evaluation_start": "2022-01",
        "evaluation_end": "2022-04",
        "horizons": [1],
        "scenarios": ["SINGLE_CELL", "ECONOMY_OUTAGE", "CATEGORY_OUTAGE"],
        "models": [
            "B0_GLOBAL_EQUAL_HEADLINE",
            "B1_ARMILAR_WEIGHTED_HEADLINE",
            "B2_CATEGORY_CARRY_FORWARD",
            "B3_HIERARCHICAL_COMPLETION",
        ],
        "minimum_history_months": 12,
        "completion_mode": COMPLETION_MODE,
        "target_period_donors_allowed_at_release": True,
        "pre_release_forecast": False,
        "development_target_start": "2022-01",
        "development_target_end": "2022-02",
        "evaluation_target_start": "2022-03",
        "evaluation_target_end": "2022-04",
        "minimum_development_cases_per_rule": 1,
        "activation_mean_delta_bps_gt": "0",
        "activation_regression_rate_gte": "0",
        "candidate_rules": [
            {
                "rule_id": "CP08_FALLBACK_TO_B2",
                "rule_type": "SOURCE_CATEGORY",
                "source_category": "CP08",
            },
            {
                "rule_id": "CATEGORY_OUTAGE_H1_FALLBACK_TO_B2",
                "rule_type": "SCENARIO_HORIZON",
                "scenario": "CATEGORY_OUTAGE",
                "horizon_months": 1,
            },
        ],
        "rejected_v089_experiment_reused": False,
        "release_time_completion_comparison_allowed": True,
        "pre_release_forecast_comparison_allowed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    payload.update(updates)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_policy_declares_release_time_completion_not_forecast(tmp_path: Path) -> None:
    policy = ReleaseTimePolicy.load(_policy(tmp_path))
    assert policy.completion_mode == COMPLETION_MODE
    assert policy.target_period_donors_allowed_at_release is True
    assert policy.pre_release_forecast is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("pre_release_forecast", True),
        ("pre_release_forecast_comparison_allowed", True),
        ("model_promotion_allowed", True),
        ("research_release_allowed", True),
        ("monetary_release_allowed", True),
        ("rejected_v089_experiment_reused", True),
    ],
)
def test_policy_rejects_false_claims_and_open_gates(
    tmp_path: Path, field: str, value: object
) -> None:
    with pytest.raises(ReleaseTimeBacktestError):
        ReleaseTimePolicy.load(_policy(tmp_path, **{field: value}))


def test_loader_builds_exact_first_published_panels(tmp_path: Path) -> None:
    input_dir = _write_first_published(tmp_path / "input")
    loaded = load_first_published_panel(ReleaseTimePolicy.load(_policy(tmp_path)), input_dir)
    assert len(loaded.panel.cells) == 60
    assert len(loaded.panel.values) == 3600
    assert len(loaded.headline.values) == 300
    assert len(loaded.release_dates) == 60
    assert loaded.panel.economies == ECONOMIES


def test_loader_rejects_missing_observation(tmp_path: Path) -> None:
    input_dir = _write_first_published(tmp_path / "input", lambda rows: rows.pop())
    with pytest.raises(ReleaseTimeBacktestError, match="GRID_INCOMPLETE"):
        load_first_published_panel(ReleaseTimePolicy.load(_policy(tmp_path)), input_dir)


def test_loader_rejects_release_date_inconsistency(tmp_path: Path) -> None:
    def mutate(rows):
        rows[1]["available_from_date"] = "2021-03-01"

    input_dir = _write_first_published(tmp_path / "input", mutate)
    with pytest.raises(ReleaseTimeBacktestError, match="TARGET_RELEASE_DATE_INCONSISTENT"):
        load_first_published_panel(ReleaseTimePolicy.load(_policy(tmp_path)), input_dir)


def _fake_case(case_id: str, target: str, b2: str, b3: str, *, category="CP08", scenario="SINGLE_CELL", horizon=1):
    common = dict(
        case_id=case_id,
        scenario=scenario,
        origin_period="2021-12" if target.startswith("2022-01") else "2022-02",
        target_period=target,
        horizon_months=horizon,
        masked_group=f"DEU|{category}",
        truth_index=Decimal("100"),
        economy_code="DEU",
        source_category=category,
    )
    return {
        B2: SimpleNamespace(
            **common,
            model=B2,
            absolute_error_bps=Decimal(b2),
            estimated_index=Decimal("100"),
            index_error=Decimal("0"),
            masked_cell_mape_percent=Decimal("0"),
        ),
        B3: SimpleNamespace(
            **common,
            model=B3,
            absolute_error_bps=Decimal(b3),
            estimated_index=Decimal("100"),
            index_error=Decimal("0"),
            masked_cell_mape_percent=Decimal("0"),
        ),
    }


def test_b4_activation_uses_development_only(tmp_path: Path) -> None:
    policy = ReleaseTimePolicy.load(_policy(tmp_path))
    indexed = {
        "dev": _fake_case("dev", "2022-01", "1", "3"),
        "eval": _fake_case("eval", "2022-03", "100", "0"),
    }
    first = _activate_rules(indexed, policy)
    indexed["eval"] = _fake_case("eval", "2022-03", "0", "1000")
    second = _activate_rules(indexed, policy)
    assert first == second
    assert first[0].activated is True


def test_b4_selects_b2_only_for_active_matching_rules(tmp_path: Path) -> None:
    policy = ReleaseTimePolicy.load(_policy(tmp_path))
    indexed = {
        "dev": _fake_case("dev", "2022-01", "1", "3"),
        "eval-match": _fake_case("eval-match", "2022-03", "2", "4"),
        "eval-control": _fake_case(
            "eval-control", "2022-03", "2", "1", category="CP07"
        ),
    }
    activations = _activate_rules(indexed, policy)
    b4 = _build_b4_cases(indexed, policy, activations)
    assert b4["eval-match"].selected_model == B2
    assert b4["eval-control"].selected_model == B3


def test_full_build_writes_release_time_audit_and_manifest(tmp_path: Path) -> None:
    input_dir = _write_first_published(tmp_path / "input")
    output = tmp_path / "output"
    summary = build_release_time_backtest(_policy(tmp_path), input_dir, output)
    assert summary["status"] == "FIRST_PUBLISHED_RELEASE_TIME_COMPLETION_BACKTEST_COMPLETED"
    assert summary["release_time_completion_comparison_allowed"] is True
    assert summary["pre_release_forecast"] is False
    assert summary["model_promotion_allowed"] is False
    verify_manifest(output)
    with (output / "backtest_cases.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["model"] for row in rows} == {
        "B0_GLOBAL_EQUAL_HEADLINE",
        "B1_ARMILAR_WEIGHTED_HEADLINE",
        "B2_CATEGORY_CARRY_FORWARD",
        "B3_HIERARCHICAL_COMPLETION",
        "B4_TEMPORAL_SAFEGUARD",
    }
    assert all(row["as_of_date"] == _release_date(row["target_period"]) for row in rows)
    assert all(row["target_period_donors_available_at_as_of"] == "true" for row in rows)
    assert all(row["pre_release_forecast"] == "false" for row in rows)


def test_full_build_is_deterministic(tmp_path: Path) -> None:
    input_dir = _write_first_published(tmp_path / "input")
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_release_time_backtest(_policy(tmp_path), input_dir, first)
    build_release_time_backtest(_policy(tmp_path), input_dir, second)
    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    input_dir = _write_first_published(tmp_path / "input")
    output = tmp_path / "output"
    build_release_time_backtest(_policy(tmp_path), input_dir, output)
    (output / "model_metrics.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ReleaseTimeBacktestError, match="MANIFEST_HASH_MISMATCH"):
        verify_manifest(output)
