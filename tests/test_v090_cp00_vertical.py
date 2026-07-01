from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from armilar_prices.backtest_core_v088 import BacktestPolicy, predict_masked_cell as predict_v088
from armilar_prices.backtest_core_v090 import (
    BacktestError,
    load_headline_panel,
    load_panel,
    predict_masked_cell,
)
from armilar_prices.backtest_v090 import build_backtest, verify_manifest as verify_backtest_manifest
from armilar_prices.eurostat_headline_v090 import (
    HeadlinePolicy,
    EurostatHeadlineError,
    build_headline_series,
    build_request_url,
    verify_manifest as verify_headline_manifest,
)

UNIVERSE = "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7"
ECONOMIES = [
    ("DE", "DEU", "Germany", Decimal("0.28")),
    ("ES", "ESP", "Spain", Decimal("0.18")),
    ("FR", "FRA", "France", Decimal("0.25")),
    ("IT", "ITA", "Italy", Decimal("0.23")),
    ("PT", "PRT", "Portugal", Decimal("0.06")),
]
CATEGORIES = [f"CP{i:02d}" for i in range(1, 13)]
CATEGORY_SHARES = [Decimal("0.10")] * 8 + [Decimal("0.05")] * 4
PERIODS = [f"2021-{month:02d}" for month in range(1, 13)] + [
    f"2022-{month:02d}" for month in range(1, 13)
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(root: Path) -> None:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"
    )
    lines = [f"{sha(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def policy_payload(*, source_category: str = "CP00", official_gates: bool = False) -> dict:
    return {
        "policy_version": "0.9.0",
        "universe_id": UNIVERSE,
        "dataset": "prc_hicp_midx",
        "api_base": "https://example.invalid/prc_hicp_midx",
        "unit": "I15",
        "frequency": "M",
        "classification_version": "ECOICOP_V1_PRE_2026",
        "source_category": source_category,
        "reference_year": 2021,
        "start_period": "2021-01",
        "end_period": "2022-12",
        "economies": [
            {"eurostat_code": euro, "armilar_code": armilar, "name": name}
            for euro, armilar, name, _ in ECONOMIES
        ],
        "request_timeout_seconds": 5,
        "max_response_bytes": 1000000,
        "research_release_allowed": official_gates,
        "monetary_release_allowed": False,
    }


def write_policy(path: Path, **kwargs) -> HeadlinePolicy:
    path.write_text(json.dumps(policy_payload(**kwargs)), encoding="utf-8")
    return HeadlinePolicy.load(path)


def make_jsonstat(*, drop_last: bool = False) -> bytes:
    values = []
    statuses = {}
    for econ_idx, _economy in enumerate(ECONOMIES):
        for period_idx, _period in enumerate(PERIODS):
            value = Decimal("100") + Decimal(econ_idx) + Decimal(period_idx) * (
                Decimal("0.20") + Decimal(econ_idx) * Decimal("0.03")
            )
            values.append(float(value))
    if drop_last:
        values[-1] = None
    payload = {
        "id": ["freq", "unit", "coicop", "geo", "time"],
        "size": [1, 1, 1, len(ECONOMIES), len(PERIODS)],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "unit": {"category": {"index": {"I15": 0}}},
            "coicop": {"category": {"index": {"CP00": 0}}},
            "geo": {
                "category": {
                    "index": {euro: idx for idx, (euro, *_rest) in enumerate(ECONOMIES)}
                }
            },
            "time": {
                "category": {"index": {period: idx for idx, period in enumerate(PERIODS)}}
            },
        },
        "value": values,
        "status": statuses,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def make_snapshot(root: Path, policy: HeadlinePolicy, *, official: bool, drop_last: bool = False) -> None:
    raw = make_jsonstat(drop_last=drop_last)
    digest = sha(raw)
    relative = Path("raw/eurostat/prc_hicp_midx") / f"cp00.{digest[:16]}.json"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest = {
        "snapshot_schema_version": "1.0",
        "parser_id": "armilar-eurostat-headline-v090",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "policy_version": "0.9.0",
        "policy_sha256": policy.policy_sha256,
        "universe_id": UNIVERSE,
        "retrieved_at": "2026-07-01T00:00:00+00:00",
        "snapshot_kind": (
            "OFFICIAL_PROVIDER_ACQUISITION" if official else "SYNTHETIC_TEST_FIXTURE"
        ),
        "requests": [
            {
                "request_id": "prc_hicp_midx-I15-CP00",
                "provider": "EUROSTAT",
                "dataset": "prc_hicp_midx",
                "source_category": "CP00",
                "request_url": "https://example.invalid",
                "final_url": "https://example.invalid",
                "retrieved_at": "2026-07-01T00:00:00+00:00",
                "http_status": 200,
                "content_type": "application/json",
                "etag": None,
                "last_modified": None,
                "raw_file": relative.as_posix(),
                "raw_sha256": digest,
                "raw_bytes": len(raw),
            }
        ],
    }
    (root / "snapshot_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    write_manifest(root)


def category_value(economy_index: int, category_index: int, period_index: int) -> Decimal:
    return (
        Decimal("1")
        + Decimal(period_index) * (Decimal("0.002") + Decimal(economy_index) * Decimal("0.0002"))
        + Decimal(category_index) * Decimal("0.0003")
    )


def make_category_output(root: Path) -> None:
    normalized: list[dict[str, str]] = []
    weights: list[dict[str, str]] = []
    cell_weights: dict[tuple[str, str], Decimal] = {}
    for econ_idx, (_euro, armilar, name, economy_weight) in enumerate(ECONOMIES):
        for category_idx, category in enumerate(CATEGORIES):
            weight = economy_weight * CATEGORY_SHARES[category_idx]
            cell_weights[(armilar, category)] = weight
            weights.append(
                {
                    "economy_code": armilar,
                    "economy_name": name,
                    "source_category": category,
                    "armilar_category": f"ARM{category_idx + 1:02d}",
                    "raw_world_weight": str(weight),
                    "fixed_universe_weight": str(weight),
                    "quality_flags": "",
                    "numerator_source_id": "fixture",
                    "numerator_source_file": "fixture.csv",
                    "numerator_source_hash": "0" * 64,
                    "ppp_source_heading": category,
                    "ppp_scope": "HFCE",
                    "derivation": "TEST_ONLY",
                }
            )
            for period_idx, period in enumerate(PERIODS):
                normalized.append(
                    {
                        "universe_id": UNIVERSE,
                        "economy_code": armilar,
                        "economy_name": name,
                        "source_category": category,
                        "armilar_category": f"ARM{category_idx + 1:02d}",
                        "period": period,
                        "price_relative": str(category_value(econ_idx, category_idx, period_idx)),
                        "fixed_universe_weight": str(weight),
                        "price_evidence_class": "P1_OFFICIAL_CATEGORY",
                    }
                )
    monthly = []
    for period_idx, period in enumerate(PERIODS):
        total = Decimal("0")
        for econ_idx, (_euro, armilar, _name, _economy_weight) in enumerate(ECONOMIES):
            for category_idx, category in enumerate(CATEGORIES):
                total += Decimal("100") * cell_weights[(armilar, category)] * category_value(
                    econ_idx, category_idx, period_idx
                )
        monthly.append({"period": period, "index_value": str(total)})
    write_csv(
        root / "normalized_price_observations.csv",
        [
            "universe_id",
            "economy_code",
            "economy_name",
            "source_category",
            "armilar_category",
            "period",
            "price_relative",
            "fixed_universe_weight",
            "price_evidence_class",
        ],
        normalized,
    )
    write_csv(root / "monthly_index.csv", ["period", "index_value"], monthly)
    write_csv(
        root / "fixed_universe_weights.csv",
        list(weights[0].keys()),
        weights,
    )
    (root / "run_summary.json").write_text(
        json.dumps(
            {
                "universe_id": UNIVERSE,
                "snapshot_kind": "OFFICIAL_PROVIDER_ACQUISITION",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    write_manifest(root)


def make_backtest_policy(path: Path) -> BacktestPolicy:
    payload = {
        "policy_version": "0.9.0",
        "input_universe_id": UNIVERSE,
        "evaluation_start": "2022-01",
        "evaluation_end": "2022-12",
        "horizons": [1, 3],
        "scenarios": ["SINGLE_CELL", "ECONOMY_OUTAGE", "CATEGORY_OUTAGE"],
        "models": [
            "B0_GLOBAL_EQUAL_HEADLINE",
            "B1_ARMILAR_WEIGHTED_HEADLINE",
            "B2_CATEGORY_CARRY_FORWARD",
            "B3_HIERARCHICAL_COMPLETION",
        ],
        "minimum_history_months": 12,
        "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
        "publication_aware": False,
        "same_period_donor_assumption": True,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
        "top_source_minimum_cases": 2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return BacktestPolicy.load(path)


def build_inputs(tmp_path: Path, *, official: bool = True):
    policy_path = tmp_path / "headline_policy.json"
    policy = write_policy(policy_path)
    snapshot = tmp_path / "headline_snapshot"
    make_snapshot(snapshot, policy, official=official)
    category = tmp_path / "category"
    make_category_output(category)
    headline = tmp_path / "headline"
    build_headline_series(policy_path, snapshot, category, headline)
    backtest_policy_path = tmp_path / "backtest_policy.json"
    backtest_policy = make_backtest_policy(backtest_policy_path)
    return policy_path, snapshot, category, headline, backtest_policy_path, backtest_policy


def test_policy_requires_cp00(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy_payload(source_category="CP01")), encoding="utf-8")
    with pytest.raises(EurostatHeadlineError, match="SOURCE_CONCEPT_MISMATCH"):
        HeadlinePolicy.load(path)


def test_policy_keeps_release_gates_false(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy_payload(official_gates=True)), encoding="utf-8")
    with pytest.raises(EurostatHeadlineError, match="RELEASE_GATE_WEAKENED"):
        HeadlinePolicy.load(path)


def test_request_url_contains_only_cp00_and_all_five_geos(tmp_path: Path) -> None:
    policy = write_policy(tmp_path / "policy.json")
    url = build_request_url(policy)
    assert "coicop=CP00" in url
    assert "CP01" not in url
    for euro, *_rest in ECONOMIES:
        assert f"geo={euro}" in url


def test_headline_replay_builds_complete_panel(tmp_path: Path) -> None:
    policy_path, _snapshot, _category, headline, *_rest = build_inputs(tmp_path)
    summary = json.loads((headline / "run_summary.json").read_text())
    assert summary["observation_count"] == 120
    assert summary["month_count"] == 24
    assert summary["headline_source_independent"] is True
    assert summary["category_panel_used_to_construct_headline"] is False
    verify_headline_manifest(headline)
    assert HeadlinePolicy.load(policy_path).source_category == "CP00"


def test_headline_b0_b1_identities(tmp_path: Path) -> None:
    *_prefix, headline, _bt_path, _bt_policy = build_inputs(tmp_path)
    rows = list(csv.DictReader((headline / "monthly_headline_indices.csv").open()))
    normalized = list(csv.DictReader((headline / "normalized_headline_observations.csv").open()))
    first_period = rows[0]["period"]
    first = [row for row in normalized if row["period"] == first_period]
    b0 = Decimal("100") * sum((Decimal(row["price_relative"]) for row in first), Decimal("0")) / Decimal("5")
    b1 = Decimal("100") * sum(
        (
            Decimal(row["price_relative"]) * Decimal(row["economy_fixed_universe_weight"])
            for row in first
        ),
        Decimal("0"),
    )
    assert abs(b0 - Decimal(rows[0]["b0_equal_country_official_headline"])) < Decimal("1e-9")
    assert abs(b1 - Decimal(rows[0]["b1_armilar_economy_weighted_official_headline"])) < Decimal("1e-9")


def test_headline_rows_preserve_raw_hash(tmp_path: Path) -> None:
    _policy_path, snapshot, _category, headline, *_rest = build_inputs(tmp_path)
    manifest = json.loads((snapshot / "snapshot_manifest.json").read_text())
    expected = manifest["requests"][0]["raw_sha256"]
    rows = list(csv.DictReader((headline / "normalized_headline_observations.csv").open()))
    assert {row["raw_sha256"] for row in rows} == {expected}


def test_snapshot_tamper_is_rejected(tmp_path: Path) -> None:
    policy_path, snapshot, category, _headline, *_rest = build_inputs(tmp_path)
    raw = next((snapshot / "raw").rglob("*.json"))
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(EurostatHeadlineError, match="MANIFEST_HASH_MISMATCH"):
        build_headline_series(policy_path, snapshot, category, tmp_path / "tampered")


def test_incomplete_cp00_grid_is_rejected(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy = write_policy(policy_path)
    snapshot = tmp_path / "snapshot"
    make_snapshot(snapshot, policy, official=True, drop_last=True)
    category = tmp_path / "category"
    make_category_output(category)
    with pytest.raises(EurostatHeadlineError, match="INCOMPLETE_COMMON_INTERVAL"):
        build_headline_series(policy_path, snapshot, category, tmp_path / "output")


def test_nonempty_output_is_rejected(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy = write_policy(policy_path)
    snapshot = tmp_path / "snapshot"
    make_snapshot(snapshot, policy, official=True)
    category = tmp_path / "category"
    make_category_output(category)
    output = tmp_path / "output"
    output.mkdir()
    (output / "stale.txt").write_text("stale")
    with pytest.raises(EurostatHeadlineError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_headline_series(policy_path, snapshot, category, output)


def test_headline_values_do_not_depend_on_category_prices(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy = write_policy(policy_path)
    snapshot = tmp_path / "snapshot"
    make_snapshot(snapshot, policy, official=True)
    category_a = tmp_path / "category_a"
    category_b = tmp_path / "category_b"
    make_category_output(category_a)
    make_category_output(category_b)
    panel_path = category_b / "normalized_price_observations.csv"
    rows = list(csv.DictReader(panel_path.open()))
    for row in rows:
        row["price_relative"] = str(Decimal(row["price_relative"]) * Decimal("9"))
    write_csv(panel_path, list(rows[0].keys()), rows)
    write_manifest(category_b)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    build_headline_series(policy_path, snapshot, category_a, out_a)
    build_headline_series(policy_path, snapshot, category_b, out_b)
    assert (out_a / "monthly_headline_indices.csv").read_bytes() == (
        out_b / "monthly_headline_indices.csv"
    ).read_bytes()


def test_backtest_requires_official_headline(tmp_path: Path) -> None:
    *_, category, headline, _bt_path, bt_policy = build_inputs(tmp_path, official=False)
    panel = load_panel(category, bt_policy)
    with pytest.raises(BacktestError, match="OFFICIAL_HEADLINE_REQUIRED"):
        load_headline_panel(headline, panel, bt_policy)


def test_b0_prediction_is_independent_of_category_mask(tmp_path: Path) -> None:
    *_, category, headline, _bt_path, bt_policy = build_inputs(tmp_path)
    panel = load_panel(category, bt_policy)
    hp = load_headline_panel(headline, panel, bt_policy)
    cell = panel.cells[0]
    origin, target = "2022-01", "2022-02"
    first = predict_masked_cell(panel, hp, "B0_GLOBAL_EQUAL_HEADLINE", cell, origin, target, {cell.key}, {})
    second = predict_masked_cell(
        panel,
        hp,
        "B0_GLOBAL_EQUAL_HEADLINE",
        cell,
        origin,
        target,
        {candidate.key for candidate in panel.cells if candidate.economy_code == cell.economy_code},
        {},
    )
    assert first == second


def test_b1_uses_armilar_economy_weights(tmp_path: Path) -> None:
    *_, category, headline, _bt_path, bt_policy = build_inputs(tmp_path)
    panel = load_panel(category, bt_policy)
    hp = load_headline_panel(headline, panel, bt_policy)
    factor = hp.factor("B1_ARMILAR_WEIGHTED_HEADLINE", "2022-01", "2022-02")
    expected = sum(
        (
            hp.values[(economy, "2022-02")] / hp.values[(economy, "2022-01")]
            * hp.economy_weights[economy]
            for economy in hp.economies
        ),
        Decimal("0"),
    )
    assert factor == expected


def test_b2_and_b3_definitions_are_unchanged(tmp_path: Path) -> None:
    *_, category, headline, _bt_path, bt_policy = build_inputs(tmp_path)
    panel = load_panel(category, bt_policy)
    hp = load_headline_panel(headline, panel, bt_policy)
    cell = panel.cells[0]
    origin, target = "2022-01", "2022-02"
    masked = {cell.key}
    donor_factors = {
        candidate.key: panel.values[(candidate.economy_code, candidate.source_category, target)]
        / panel.values[(candidate.economy_code, candidate.source_category, origin)]
        for candidate in panel.cells
        if candidate.key not in masked
    }
    for model in ("B2_CATEGORY_CARRY_FORWARD", "B3_HIERARCHICAL_COMPLETION"):
        old = predict_v088(panel, model, cell, origin, target, masked, donor_factors)
        new = predict_masked_cell(panel, hp, model, cell, origin, target, masked, donor_factors)
        assert new == old


def test_full_backtest_completes_with_independent_headline(tmp_path: Path) -> None:
    *_prefix, category, headline, bt_path, _bt_policy = build_inputs(tmp_path)
    output = tmp_path / "backtest"
    summary = build_backtest(bt_path, category, headline, output)
    assert summary["official_headline_comparison_available"] is True
    assert summary["headline_source_independent"] is True
    assert summary["rejected_v089_experiment_reused"] is False
    assert summary["research_release_allowed"] is False
    assert summary["monetary_release_allowed"] is False
    assert summary["vintage_mode"] == "FINAL_VINTAGE_PSEUDO_REAL_TIME"
    verify_backtest_manifest(output)


def test_all_models_use_identical_common_sample(tmp_path: Path) -> None:
    *_prefix, category, headline, bt_path, _bt_policy = build_inputs(tmp_path)
    output = tmp_path / "backtest"
    build_backtest(bt_path, category, headline, output)
    rows = list(csv.DictReader((output / "backtest_cases.csv").open()))
    samples: dict[str, set[str]] = {}
    for row in rows:
        samples.setdefault(row["model"], set()).add(row["case_id"])
    assert len(samples) == 4
    assert len({frozenset(sample) for sample in samples.values()}) == 1


def test_backtest_report_keeps_vintage_limitation(tmp_path: Path) -> None:
    *_prefix, category, headline, bt_path, _bt_policy = build_inputs(tmp_path)
    output = tmp_path / "backtest"
    build_backtest(bt_path, category, headline, output)
    report = (output / "BACKTEST_REPORT.md").read_text()
    assert "independently acquired Eurostat CP00" in report
    assert "fully publication-aware" in report
    assert "research_release_allowed=false" in report


def test_backtest_does_not_create_public_latest(tmp_path: Path) -> None:
    *_prefix, category, headline, bt_path, _bt_policy = build_inputs(tmp_path)
    output = tmp_path / "backtest"
    build_backtest(bt_path, category, headline, output)
    assert not (tmp_path / "public" / "latest").exists()


def test_backtest_manifest_detects_tampering(tmp_path: Path) -> None:
    *_prefix, category, headline, bt_path, _bt_policy = build_inputs(tmp_path)
    output = tmp_path / "backtest"
    build_backtest(bt_path, category, headline, output)
    report = output / "BACKTEST_REPORT.md"
    report.write_text(report.read_text() + "tamper")
    with pytest.raises(BacktestError, match="MANIFEST_HASH_MISMATCH"):
        verify_backtest_manifest(output)
