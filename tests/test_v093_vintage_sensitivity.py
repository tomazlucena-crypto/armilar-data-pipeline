from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from armilar_prices.release_time_backtest_v093 import build_release_time_backtest
from armilar_prices.vintage_sensitivity_v093 import (
    VintageSensitivityError,
    build_vintage_sensitivity,
    verify_manifest,
)
from test_v093_release_time_backtest import _policy, _write_first_published


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path) -> None:
    lines = [
        f"{_sha(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.sha256"
    ]
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _inputs(tmp_path: Path):
    fp = _write_first_published(tmp_path / "fp")
    release = tmp_path / "release"
    build_release_time_backtest(_policy(tmp_path), fp, release)

    with (release / "backtest_cases.csv").open(newline="", encoding="utf-8") as handle:
        release_rows = list(csv.DictReader(handle))
    final = tmp_path / "final"
    final.mkdir()
    core_rows = []
    for row in release_rows:
        if row["model"] == "B4_TEMPORAL_SAFEGUARD":
            continue
        candidate = {
            key: row[key]
            for key in (
                "case_id",
                "scenario",
                "origin_period",
                "target_period",
                "horizon_months",
                "masked_group",
                "model",
                "truth_index",
                "estimated_index",
                "absolute_error_bps",
                "masked_cell_mape_percent",
                "evidence_class",
                "economy_code",
                "source_category",
            )
        }
        candidate["absolute_error_bps"] = str(float(candidate["absolute_error_bps"]) + 0.1)
        core_rows.append(candidate)
    with (final / "backtest_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(core_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(core_rows)
    (final / "backtest_summary.json").write_text(
        json.dumps(
            {
                "policy_version": "0.9.0",
                "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
                "publication_aware": False,
                "headline_source_independent": True,
                "rejected_v089_experiment_reused": False,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    _manifest(final)

    safeguard = tmp_path / "safeguard"
    safeguard.mkdir()
    b4_rows = []
    for row in release_rows:
        if row["model"] != "B4_TEMPORAL_SAFEGUARD":
            continue
        b4_rows.append(
            {
                "case_id": row["case_id"],
                "scenario": row["scenario"],
                "horizon_months": row["horizon_months"],
                "economy_code": row["economy_code"],
                "source_category": row["source_category"],
                "target_period": row["target_period"],
                "b4_absolute_error_bps": str(float(row["absolute_error_bps"]) + 0.2),
            }
        )
    with (safeguard / "safeguard_case_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(b4_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(b4_rows)
    (safeguard / "run_summary.json").write_text(
        json.dumps(
            {
                "policy_version": "0.9.2",
                "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
                "publication_aware": False,
                "model_promotion_allowed": False,
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    _manifest(safeguard)
    return release, final, safeguard


def test_vintage_sensitivity_compares_identical_cases(tmp_path: Path) -> None:
    release, final, safeguard = _inputs(tmp_path)
    output = tmp_path / "output"
    summary = build_vintage_sensitivity(release, final, safeguard, output)
    assert summary["status"] == "FIRST_PUBLISHED_VS_FINAL_VINTAGE_SENSITIVITY_COMPLETED"
    assert summary["model_count"] == 5
    assert summary["model_promotion_allowed"] is False
    verify_manifest(output)
    ranking = json.loads((output / "model_ranking_sensitivity.json").read_text())
    assert set(ranking["first_published_ranking"]) == {
        "B0_GLOBAL_EQUAL_HEADLINE",
        "B1_ARMILAR_WEIGHTED_HEADLINE",
        "B2_CATEGORY_CARRY_FORWARD",
        "B3_HIERARCHICAL_COMPLETION",
        "B4_TEMPORAL_SAFEGUARD",
    }


def test_vintage_sensitivity_rejects_sample_mismatch(tmp_path: Path) -> None:
    release, final, safeguard = _inputs(tmp_path)
    path = safeguard / "safeguard_case_results.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows.pop()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _manifest(safeguard)
    with pytest.raises(VintageSensitivityError, match="SAMPLE_MISMATCH"):
        build_vintage_sensitivity(release, final, safeguard, tmp_path / "output")


def test_vintage_sensitivity_rejects_open_final_gate(tmp_path: Path) -> None:
    release, final, safeguard = _inputs(tmp_path)
    summary_path = final / "backtest_summary.json"
    payload = json.loads(summary_path.read_text())
    payload["research_release_allowed"] = True
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    _manifest(final)
    with pytest.raises(VintageSensitivityError, match="CONTRACT_MISMATCH"):
        build_vintage_sensitivity(release, final, safeguard, tmp_path / "output")


def test_vintage_sensitivity_manifest_detects_tampering(tmp_path: Path) -> None:
    release, final, safeguard = _inputs(tmp_path)
    output = tmp_path / "output"
    build_vintage_sensitivity(release, final, safeguard, output)
    (output / "run_summary.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(Exception, match="MANIFEST_HASH_MISMATCH"):
        verify_manifest(output)
