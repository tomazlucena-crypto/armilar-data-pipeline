from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

OVERLAY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OVERLAY_ROOT / "src"))

from armilar_prices.paired_diagnostics_v091 import (  # noqa: E402
    PairedDiagnosticsError,
    build_diagnostics,
    verify_manifest,
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


def _write_policy(path: Path, minimum_cases: int = 1, **updates: object) -> Path:
    payload = json.loads((OVERLAY_ROOT / "config" / "paired_diagnostics_v091.json").read_text(encoding="utf-8"))
    payload["minimum_cases_per_priority"] = minimum_cases
    payload.update(updates)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _base_cases() -> list[dict[str, object]]:
    # Errors are B0, B1, B2, B3. B3 vs B2: improvement, regression, tie,
    # regression, regression, regression. Italy and CP04 are deliberately worst.
    return [
        {
            "case_id": "case-001",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-02",
            "horizon_months": 1,
            "masked_group": "ITA|CP04",
            "economy_code": "ITA",
            "source_category": "CP04",
            "errors": ("10", "8", "6", "4"),
            "mapes": ("5", "4", "3", "2"),
        },
        {
            "case_id": "case-002",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-04",
            "horizon_months": 3,
            "masked_group": "ITA|CP04",
            "economy_code": "ITA",
            "source_category": "CP04",
            "errors": ("10", "9", "5", "9"),
            "mapes": ("6", "5", "2", "6"),
        },
        {
            "case_id": "case-003",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-07",
            "horizon_months": 6,
            "masked_group": "DEU|CP01",
            "economy_code": "DEU",
            "source_category": "CP01",
            "errors": ("12", "10", "8", "8"),
            "mapes": ("7", "6", "4", "4"),
        },
        {
            "case_id": "case-004",
            "scenario": "ECONOMY_OUTAGE",
            "origin_period": "2023-01",
            "target_period": "2024-01",
            "horizon_months": 12,
            "masked_group": "ITA",
            "economy_code": "ITA",
            "source_category": "",
            "errors": ("14", "11", "7", "12"),
            "mapes": ("8", "7", "4", "9"),
        },
        {
            "case_id": "case-005",
            "scenario": "CATEGORY_OUTAGE",
            "origin_period": "2023-01",
            "target_period": "2024-01",
            "horizon_months": 12,
            "masked_group": "CP04",
            "economy_code": "",
            "source_category": "CP04",
            "errors": ("15", "12", "10", "13"),
            "mapes": ("9", "8", "6", "9"),
        },
        {
            "case_id": "case-006",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-02",
            "horizon_months": 1,
            "masked_group": "PRT|CP09",
            "economy_code": "PRT",
            "source_category": "CP09",
            "errors": ("9", "7", "4", "5"),
            "mapes": ("5", "4", "2", "3"),
        },
    ]


def _write_input(
    root: Path,
    *,
    summary_updates: dict[str, object] | None = None,
    cases: list[dict[str, object]] | None = None,
) -> Path:
    root.mkdir(parents=True)
    cases = cases or _base_cases()
    summary = {
        "schema_version": "1.0",
        "pipeline_version": "0.9.0",
        "policy_version": "0.9.0",
        "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
        "publication_aware": False,
        "headline_source_independent": True,
        "official_headline_source": "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT",
        "rejected_v089_experiment_reused": False,
        "common_case_count_per_model": len(cases),
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    if summary_updates:
        summary.update(summary_updates)
    (root / "backtest_summary.json").write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    fields = [
        "case_id",
        "scenario",
        "origin_period",
        "target_period",
        "horizon_months",
        "masked_group",
        "model",
        "truth_index",
        "estimated_index",
        "index_error",
        "absolute_error_bps",
        "masked_cell_mape_percent",
        "evidence_class",
        "economy_code",
        "source_category",
    ]
    with (root / "backtest_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for case in cases:
            for model, error, mape in zip(MODELS, case["errors"], case["mapes"]):
                writer.writerow(
                    {
                        "case_id": case["case_id"],
                        "scenario": case["scenario"],
                        "origin_period": case["origin_period"],
                        "target_period": case["target_period"],
                        "horizon_months": case["horizon_months"],
                        "masked_group": case["masked_group"],
                        "model": model,
                        "truth_index": "100.000000000000",
                        "estimated_index": "100.000000000000",
                        "index_error": "0.000000000000",
                        "absolute_error_bps": error,
                        "masked_cell_mape_percent": mape,
                        "evidence_class": "P1" if model in MODELS[:2] else "P3",
                        "economy_code": case["economy_code"],
                        "source_category": case["source_category"],
                    }
                )
    _write_manifest(root)
    return root


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_builds_complete_verified_artifact(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    output = tmp_path / "output"

    summary = build_diagnostics(policy, input_dir, output)

    assert summary["status"] == "PAIRED_DIAGNOSTICS_COMPLETED_WITH_VINTAGE_LIMITATION"
    assert summary["common_case_count_per_model"] == 6
    assert summary["paired_case_row_count"] == 24
    assert summary["research_release_allowed"] is False
    assert summary["monetary_release_allowed"] is False
    verify_manifest(output)
    assert {
        "paired_case_deltas.csv",
        "pair_summary.csv",
        "pair_by_scenario_horizon.csv",
        "pair_by_economy.csv",
        "pair_by_category.csv",
        "priority_error_sources.json",
        "run_summary.json",
        "PAIRED_DIAGNOSTICS_REPORT.md",
        "MANIFEST.sha256",
    } == {path.name for path in output.iterdir()}


def test_b3_vs_b2_summary_is_paired_case_by_case(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    output = tmp_path / "output"
    build_diagnostics(policy, input_dir, output)

    row = next(item for item in _read_csv(output / "pair_summary.csv") if item["pair_id"] == "B3_VS_B2")
    # Deltas: -2, +4, 0, +5, +3, +1. Mean = 11/6.
    assert row["case_count"] == "6"
    assert row["improvement_count"] == "1"
    assert row["tie_count"] == "1"
    assert row["regression_count"] == "4"
    assert row["mean_delta_absolute_bps"] == "1.83333333"
    assert row["improvement_rate"] == "0.1666666667"
    assert row["regression_rate"] == "0.6666666667"


def test_priorities_rank_measured_b3_regressions(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    output = tmp_path / "output"
    build_diagnostics(policy, input_dir, output)

    priorities = json.loads((output / "priority_error_sources.json").read_text(encoding="utf-8"))
    deltas = [Decimal(row["mean_delta_absolute_bps_vs_b2"]) for row in priorities["top_regressions"]]
    assert len(deltas) == 3
    assert deltas == sorted(deltas, reverse=True)
    assert all(delta > 0 for delta in deltas)
    assert priorities["regression_priority_count"] == 7
    assert "top_three" not in priorities
    assert priorities["model_promotion_allowed"] is False


def test_priority_regressions_do_not_include_improvements_or_underfilled_slots(tmp_path: Path) -> None:
    cases = [
        {
            "case_id": "case-r1",
            "scenario": "CATEGORY_OUTAGE",
            "origin_period": "2023-01",
            "target_period": "2023-02",
            "horizon_months": 1,
            "masked_group": "CP08",
            "economy_code": "DEU",
            "source_category": "CP08",
            "errors": ("10", "9", "10", "16"),
            "mapes": ("5", "4", "3", "9"),
        },
        {
            "case_id": "case-r2",
            "scenario": "CATEGORY_OUTAGE",
            "origin_period": "2023-01",
            "target_period": "2023-02",
            "horizon_months": 1,
            "masked_group": "CP08",
            "economy_code": "FRA",
            "source_category": "CP08",
            "errors": ("10", "9", "10", "14"),
            "mapes": ("5", "4", "3", "8"),
        },
        {
            "case_id": "case-under-minimum",
            "scenario": "CATEGORY_OUTAGE",
            "origin_period": "2023-01",
            "target_period": "2023-02",
            "horizon_months": 1,
            "masked_group": "CP09",
            "economy_code": "ESP",
            "source_category": "CP09",
            "errors": ("10", "9", "10", "9"),
            "mapes": ("5", "4", "3", "2"),
        },
        {
            "case_id": "case-i1",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-04",
            "horizon_months": 3,
            "masked_group": "PRT|CP10",
            "economy_code": "PRT",
            "source_category": "CP10",
            "errors": ("10", "9", "10", "6"),
            "mapes": ("5", "4", "3", "1"),
        },
        {
            "case_id": "case-i2",
            "scenario": "SINGLE_CELL",
            "origin_period": "2023-01",
            "target_period": "2023-04",
            "horizon_months": 3,
            "masked_group": "PRT|CP11",
            "economy_code": "PRT",
            "source_category": "CP11",
            "errors": ("10", "9", "10", "8"),
            "mapes": ("5", "4", "3", "2"),
        },
    ]
    input_dir = _write_input(tmp_path / "input", cases=cases)
    policy = _write_policy(tmp_path / "policy.json", minimum_cases=2)
    output = tmp_path / "output"
    build_diagnostics(policy, input_dir, output)

    priorities = json.loads((output / "priority_error_sources.json").read_text(encoding="utf-8"))
    regression_labels = [row["label"] for row in priorities["top_regressions"]]
    improvement_labels = [row["label"] for row in priorities["top_improvements"]]

    assert priorities["regression_priority_count"] == 2
    assert len(priorities["top_regressions"]) == 2
    assert regression_labels == [
        "source_category=CP08",
        "scenario=CATEGORY_OUTAGE | horizon_months=1",
    ]
    assert improvement_labels == [
        "economy_code=PRT",
        "scenario=SINGLE_CELL | horizon_months=3",
    ]
    assert all(Decimal(row["mean_delta_absolute_bps_vs_b2"]) > 0 for row in priorities["top_regressions"])
    assert all(Decimal(row["mean_delta_absolute_bps_vs_b2"]) < 0 for row in priorities["top_improvements"])
    assert all("CP09" not in row["label"] for row in priorities["top_regressions"])
    assert "top_three" not in priorities


def test_missing_model_in_case_fails_closed(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    rows = _read_csv(input_dir / "backtest_cases.csv")
    rows = [row for row in rows if not (row["case_id"] == "case-001" and row["model"] == MODELS[-1])]
    with (input_dir / "backtest_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _write_manifest(input_dir)
    policy = _write_policy(tmp_path / "policy.json")

    with pytest.raises(PairedDiagnosticsError, match="COMPARISON_SAMPLE_MISMATCH"):
        build_diagnostics(policy, input_dir, tmp_path / "output")


def test_case_metadata_mismatch_fails_closed(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    rows = _read_csv(input_dir / "backtest_cases.csv")
    for row in rows:
        if row["case_id"] == "case-001" and row["model"] == MODELS[-1]:
            row["target_period"] = "2099-01"
    with (input_dir / "backtest_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _write_manifest(input_dir)
    policy = _write_policy(tmp_path / "policy.json")

    with pytest.raises(PairedDiagnosticsError, match="CASE_METADATA_MISMATCH"):
        build_diagnostics(policy, input_dir, tmp_path / "output")


@pytest.mark.parametrize("gate", ["research_release_allowed", "monetary_release_allowed"])
def test_open_input_release_gate_fails_closed(tmp_path: Path, gate: str) -> None:
    input_dir = _write_input(tmp_path / "input", summary_updates={gate: True})
    policy = _write_policy(tmp_path / "policy.json")

    with pytest.raises(PairedDiagnosticsError, match="RELEASE_GATE_WEAKENED"):
        build_diagnostics(policy, input_dir, tmp_path / "output")


def test_single_space_manifest_remains_compatible(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    manifest = input_dir / "MANIFEST.sha256"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("  ", " "),
        encoding="utf-8",
    )
    verify_manifest(input_dir)


def test_tampered_input_manifest_is_rejected(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    with (input_dir / "backtest_cases.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    policy = _write_policy(tmp_path / "policy.json")

    with pytest.raises(PairedDiagnosticsError, match="MANIFEST_HASH_MISMATCH"):
        build_diagnostics(policy, input_dir, tmp_path / "output")


def test_tampered_output_manifest_is_rejected(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    output = tmp_path / "output"
    build_diagnostics(policy, input_dir, output)
    with (output / "pair_summary.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")

    with pytest.raises(PairedDiagnosticsError, match="MANIFEST_HASH_MISMATCH"):
        verify_manifest(output)


def test_outputs_are_byte_deterministic(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_diagnostics(policy, input_dir, first)
    build_diagnostics(policy, input_dir, second)

    first_files = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second) for path in second.rglob("*") if path.is_file())
    assert first_files == second_files
    for relative in first_files:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_nonempty_output_directory_is_rejected(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    policy = _write_policy(tmp_path / "policy.json")
    output = tmp_path / "output"
    output.mkdir()
    (output / "sentinel.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(PairedDiagnosticsError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_diagnostics(policy, input_dir, output)


def test_policy_cannot_weaken_release_gate_or_drop_pair(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path / "input")
    payload = json.loads((OVERLAY_ROOT / "config" / "paired_diagnostics_v091.json").read_text(encoding="utf-8"))
    payload["research_release_allowed"] = True
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PairedDiagnosticsError, match="RELEASE_GATE_WEAKENED"):
        build_diagnostics(policy, input_dir, tmp_path / "output-a")

    payload["research_release_allowed"] = False
    payload["pairs"] = payload["pairs"][:-1]
    policy.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PairedDiagnosticsError, match="PAIR_CONTRACT_MISMATCH"):
        build_diagnostics(policy, input_dir, tmp_path / "output-b")


def test_public_latest_sentinel_is_untouched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    public_latest = repo / "public" / "latest"
    public_latest.mkdir(parents=True)
    sentinel = public_latest / "sentinel.json"
    sentinel.write_text('{"unchanged":true}\n', encoding="utf-8")
    before = sentinel.read_bytes()
    input_dir = _write_input(repo / "artifacts" / "v090" / "backtest")
    policy = _write_policy(repo / "policy.json")

    build_diagnostics(policy, input_dir, repo / "artifacts" / "v091" / "paired")

    assert sentinel.read_bytes() == before
