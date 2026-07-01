from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

OVERLAY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OVERLAY_ROOT / "src"))

from armilar_prices.paired_diagnostics_v091 import verify_manifest  # noqa: E402
from armilar_prices.temporal_safeguard_v092 import (  # noqa: E402
    B2,
    B3,
    SafeguardPolicy,
    TemporalSafeguardError,
    build_temporal_safeguard,
)

MODELS = (
    "B0_GLOBAL_EQUAL_HEADLINE",
    "B1_ARMILAR_WEIGHTED_HEADLINE",
    "B2_CATEGORY_CARRY_FORWARD",
    "B3_HIERARCHICAL_COMPLETION",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    lines = [f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in files]
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _policy(tmp_path: Path, **updates: object) -> Path:
    payload = json.loads(
        (OVERLAY_ROOT / "config" / "temporal_safeguard_v092.json").read_text(encoding="utf-8")
    )
    payload["minimum_development_cases_per_rule"] = 2
    payload.update(updates)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _case_rows(
    case_id: str,
    target: str,
    scenario: str,
    horizon: int,
    category: str,
    errors: tuple[float, float, float, float],
    economy: str = "PRT",
) -> list[dict[str, object]]:
    rows = []
    for model, error in zip(MODELS, errors):
        rows.append(
            {
                "case_id": case_id,
                "scenario": scenario,
                "origin_period": "2021-12" if target.startswith("2022") else "2023-12",
                "target_period": target,
                "horizon_months": horizon,
                "masked_group": f"{economy}:{category}",
                "model": model,
                "truth_index": "100.00000000",
                "estimated_index": "100.00000000",
                "absolute_error_bps": f"{error:.8f}",
                "masked_cell_mape_percent": f"{error / 10:.8f}",
                "evidence_class": "P3",
                "economy_code": economy,
                "source_category": category,
            }
        )
    return rows


def _default_cases(eval_cp08_b3: float = 6.0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    # Development: CP08 activates because B3 is worse than B2 in both cases.
    rows += _case_rows("dev-cp08-1", "2022-03", "SINGLE_CELL", 1, "CP08", (5, 4, 2, 6))
    rows += _case_rows("dev-cp08-2", "2023-03", "ECONOMY_OUTAGE", 3, "CP08", (5, 4, 2, 5))
    # Development: CATEGORY_OUTAGE H1 activates.
    rows += _case_rows("dev-outage-1", "2022-06", "CATEGORY_OUTAGE", 1, "CP04", (6, 5, 3, 7))
    rows += _case_rows("dev-outage-2", "2023-06", "CATEGORY_OUTAGE", 1, "CP09", (6, 5, 4, 8))
    # Development control.
    rows += _case_rows("dev-control", "2023-09", "SINGLE_CELL", 6, "CP01", (4, 3, 5, 2))
    # Evaluation cases.
    rows += _case_rows("eval-cp08-1", "2024-03", "SINGLE_CELL", 1, "CP08", (5, 4, 2, eval_cp08_b3))
    rows += _case_rows("eval-cp08-2", "2025-03", "ECONOMY_OUTAGE", 3, "CP08", (5, 4, 2, eval_cp08_b3 + 1))
    rows += _case_rows("eval-outage-1", "2024-06", "CATEGORY_OUTAGE", 1, "CP04", (6, 5, 3, 7))
    rows += _case_rows("eval-outage-2", "2025-06", "CATEGORY_OUTAGE", 1, "CP09", (6, 5, 4, 8))
    rows += _case_rows("eval-control", "2025-09", "SINGLE_CELL", 6, "CP01", (4, 3, 5, 2))
    # Overlap of both rules, one selection only.
    rows += _case_rows("dev-overlap", "2023-11", "CATEGORY_OUTAGE", 1, "CP08", (6, 5, 2, 9))
    rows += _case_rows("eval-overlap", "2025-11", "CATEGORY_OUTAGE", 1, "CP08", (6, 5, 2, 9))
    return rows


def _input(tmp_path: Path, rows: list[dict[str, object]] | None = None, **summary_updates: object) -> Path:
    root = tmp_path / "input"
    root.mkdir(parents=True)
    rows = rows or _default_cases()
    with (root / "backtest_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "policy_version": "0.9.0",
        "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
        "publication_aware": False,
        "headline_source_independent": True,
        "official_headline_source": "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT",
        "common_case_count_per_model": len(rows) // 4,
        "rejected_v089_experiment_reused": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    summary.update(summary_updates)
    (root / "backtest_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_manifest(root)
    return root


def _build(tmp_path: Path, rows: list[dict[str, object]] | None = None, **policy_updates: object):
    input_root = _input(tmp_path, rows)
    output_root = tmp_path / "output"
    summary = build_temporal_safeguard(_policy(tmp_path, **policy_updates), input_root, output_root)
    return input_root, output_root, summary


def test_policy_loads_exact_two_rule_contract(tmp_path: Path) -> None:
    policy = SafeguardPolicy.load(_policy(tmp_path))
    assert [rule.rule_id for rule in policy.candidate_rules] == [
        "CP08_FALLBACK_TO_B2",
        "CATEGORY_OUTAGE_H1_FALLBACK_TO_B2",
    ]


def test_build_writes_expected_outputs_and_verified_manifest(tmp_path: Path) -> None:
    _, output, summary = _build(tmp_path)
    expected = {
        "rule_activation.json",
        "safeguard_case_results.csv",
        "safeguard_metrics.csv",
        "evaluation_summary.json",
        "run_summary.json",
        "TEMPORAL_SAFEGUARD_REPORT.md",
        "MANIFEST.sha256",
    }
    assert {path.name for path in output.iterdir()} == expected
    verify_manifest(output)
    assert summary["evaluation_data_used_for_activation"] is False


def test_both_rules_activate_from_development_only(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path)
    payload = json.loads((output / "rule_activation.json").read_text(encoding="utf-8"))
    assert payload["active_rule_count"] == 2
    assert all(rule["activated"] for rule in payload["rules"])
    assert payload["evaluation_data_used_for_activation"] is False


def test_evaluation_errors_do_not_change_activation(tmp_path: Path) -> None:
    _, first, _ = _build(tmp_path / "a", _default_cases(eval_cp08_b3=100.0))
    _, second, _ = _build(tmp_path / "b", _default_cases(eval_cp08_b3=0.1))
    first_activation = json.loads((first / "rule_activation.json").read_text(encoding="utf-8"))
    second_activation = json.loads((second / "rule_activation.json").read_text(encoding="utf-8"))
    assert first_activation == second_activation


def test_insufficient_development_cases_prevent_activation(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path, minimum_development_cases_per_rule=100)
    payload = json.loads((output / "rule_activation.json").read_text(encoding="utf-8"))
    assert payload["active_rule_count"] == 0
    assert all("INSUFFICIENT_DEVELOPMENT_CASES" in rule["activation_reasons"] for rule in payload["rules"])


def test_non_regressing_development_rule_stays_inactive(tmp_path: Path) -> None:
    rows = _default_cases()
    for row in rows:
        if str(row["case_id"]).startswith("dev-") and row["source_category"] == "CP08" and row["model"] == B3:
            row["absolute_error_bps"] = "1.00000000"
    _, output, _ = _build(tmp_path, rows)
    payload = json.loads((output / "rule_activation.json").read_text(encoding="utf-8"))
    cp08 = next(rule for rule in payload["rules"] if rule["rule_id"] == "CP08_FALLBACK_TO_B2")
    assert cp08["activated"] is False
    assert "MEAN_REGRESSION_THRESHOLD_NOT_MET" in cp08["activation_reasons"]


def test_active_matches_select_b2_and_controls_select_b3(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path)
    with (output / "safeguard_case_results.csv").open(newline="", encoding="utf-8") as handle:
        rows = {row["case_id"]: row for row in csv.DictReader(handle)}
    assert rows["eval-cp08-1"]["selected_model"] == B2
    assert rows["eval-outage-1"]["selected_model"] == B2
    assert rows["eval-control"]["selected_model"] == B3


def test_overlap_selects_b2_once_and_preserves_both_rule_ids(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path)
    with (output / "safeguard_case_results.csv").open(newline="", encoding="utf-8") as handle:
        row = next(row for row in csv.DictReader(handle) if row["case_id"] == "eval-overlap")
    assert row["selected_model"] == B2
    assert row["active_rule_ids"].split(";") == [
        "CP08_FALLBACK_TO_B2",
        "CATEGORY_OUTAGE_H1_FALLBACK_TO_B2",
    ]
    assert row["b4_absolute_error_bps"] == row["b2_absolute_error_bps"]


def test_inactive_rules_leave_b4_identical_to_b3(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path, minimum_development_cases_per_rule=100)
    with (output / "safeguard_case_results.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["selected_model"] == B3 for row in rows)
    assert all(row["b4_absolute_error_bps"] == row["b3_absolute_error_bps"] for row in rows)


def test_holdout_summary_reports_improvement_without_promotion(tmp_path: Path) -> None:
    _, output, _ = _build(tmp_path)
    payload = json.loads((output / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert payload["b4_beats_b3_mean_on_holdout"] is True
    assert payload["model_promotion_allowed"] is False


def test_temporal_split_overlap_is_rejected(tmp_path: Path) -> None:
    path = _policy(tmp_path, development_target_end="2024-01")
    with pytest.raises(TemporalSafeguardError, match="TEMPORAL_SPLIT_OVERLAP"):
        SafeguardPolicy.load(path)


def test_case_outside_declared_split_is_rejected(tmp_path: Path) -> None:
    rows = _default_cases()
    rows[0]["target_period"] = "2021-12"
    input_root = _input(tmp_path, rows)
    with pytest.raises(TemporalSafeguardError, match="CASE_OUTSIDE_TEMPORAL_SPLIT"):
        build_temporal_safeguard(_policy(tmp_path), input_root, tmp_path / "output")


@pytest.mark.parametrize(
    "field",
    [
        "rejected_v089_experiment_reused",
        "model_promotion_allowed",
        "research_release_allowed",
        "monetary_release_allowed",
    ],
)
def test_policy_gates_must_remain_false(tmp_path: Path, field: str) -> None:
    with pytest.raises(TemporalSafeguardError, match="RELEASE_OR_EXPERIMENT_GATE_WEAKENED"):
        SafeguardPolicy.load(_policy(tmp_path, **{field: True}))


def test_input_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    input_root = _input(tmp_path)
    with (input_root / "backtest_cases.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")
    with pytest.raises(RuntimeError, match="MANIFEST_HASH_MISMATCH"):
        build_temporal_safeguard(_policy(tmp_path), input_root, tmp_path / "output")


def test_input_requires_publication_aware_false(tmp_path: Path) -> None:
    input_root = _input(tmp_path, publication_aware=True)
    with pytest.raises(TemporalSafeguardError, match="BACKTEST_CONTRACT_MISMATCH"):
        build_temporal_safeguard(_policy(tmp_path), input_root, tmp_path / "output")


def test_incomplete_model_sample_is_rejected(tmp_path: Path) -> None:
    rows = _default_cases()
    rows = [row for row in rows if not (row["case_id"] == "eval-control" and row["model"] == B3)]
    input_root = _input(tmp_path, rows)
    # Correct declared count for all distinct cases so the model-grid error is reached first.
    summary_path = input_root / "backtest_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["common_case_count_per_model"] = len({str(row["case_id"]) for row in rows})
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(input_root)
    with pytest.raises(TemporalSafeguardError, match="COMPARISON_SAMPLE_MISMATCH"):
        build_temporal_safeguard(_policy(tmp_path), input_root, tmp_path / "output")


def test_nonempty_output_directory_is_rejected(tmp_path: Path) -> None:
    input_root = _input(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "existing.txt").write_text("x", encoding="utf-8")
    with pytest.raises(TemporalSafeguardError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_temporal_safeguard(_policy(tmp_path), input_root, output)


def test_outputs_are_deterministic(tmp_path: Path) -> None:
    input_root = _input(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    policy = _policy(tmp_path)
    build_temporal_safeguard(policy, input_root, first)
    build_temporal_safeguard(policy, input_root, second)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files


def test_run_summary_keeps_all_release_boundaries_closed(tmp_path: Path) -> None:
    _, output, summary = _build(tmp_path)
    assert summary["b0_b3_model_code_changed"] is False
    assert summary["rejected_v089_experiment_reused"] is False
    assert summary["model_promotion_allowed"] is False
    assert summary["research_release_allowed"] is False
    assert summary["monetary_release_allowed"] is False
    stored = json.loads((output / "run_summary.json").read_text(encoding="utf-8"))
    assert stored == summary
