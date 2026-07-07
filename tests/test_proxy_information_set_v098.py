from __future__ import annotations

import csv
import json
import shutil
import tomllib
from pathlib import Path

import pytest
import yaml

from armilar_proxies.acquisition_v097 import acquire_source
from armilar_proxies.archive_builder_v098 import (
    build_archive,
    build_information_set,
    verify_archive_bundle,
    verify_information_set_bundle,
)
from armilar_proxies.archive_core_v098 import (
    ProxyInformationSetError,
    load_policy,
    validate_policy,
)
from armilar_proxies.information_set_v098 import main

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "proxy_source_registry_v097.json"
POLICY = ROOT / "config" / "proxy_information_set_v098.json"


def _payload(food_may: str = "120.0", extra: str = "") -> bytes:
    return (
        "Date,Food Price Index,Meat Price Index,Dairy Price Index,Cereals Price Index,Oils Price Index,Sugar Price Index\n"
        f"2026-05,{food_may},115.0,140.0,108.0,150.0,170.0\n"
        "2026-06,121.0,116.0,141.0,109.0,151.0,171.0\n"
        + extra
    ).encode("utf-8")




def _eurostat_payload() -> bytes:
    payload = {
        "version": "2.0",
        "class": "dataset",
        "id": ["unit", "purchase", "geo", "time"],
        "size": [1, 1, 2, 2],
        "dimension": {
            "unit": {"category": {"index": {"I15_Q": 0}}},
            "purchase": {"category": {"index": {"TOTAL": 0}}},
            "geo": {"category": {"index": {"PT": 0, "ES": 1}}},
            "time": {"category": {"index": {"2025-Q4": 0, "2026-Q1": 1}}},
        },
        "value": [110.1, 111.2, 112.3, 113.4],
    }
    return json.dumps(payload).encode("utf-8")


def _ooh_snapshot(root: Path, retrieved_at: str) -> Path:
    return acquire_source(
        registry_path=REGISTRY,
        source_id="EUROSTAT_OOHPI_QUARTERLY",
        output_root=root,
        retrieved_at=retrieved_at,
        raw_payload=_eurostat_payload(),
        response_headers={"content-type": "application/json"},
    )

def _snapshot(
    root: Path,
    retrieved_at: str,
    payload: bytes,
    published_at: str = "2026-07-03T09:00:00Z",
) -> Path:
    return acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=root,
        retrieved_at=retrieved_at,
        published_at=published_at,
        raw_payload=payload,
        response_headers={"content-type": "text/csv"},
    )


def _archive(tmp_path: Path, *, two: bool = False, changed: bool = False, gap: bool = False) -> tuple[Path, Path]:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    if two:
        second_time = "2027-02-01T12:00:00Z" if gap else "2026-08-07T12:00:00Z"
        _snapshot(
            snapshots,
            second_time,
            _payload("122.5" if changed else "120.0", "2026-07,123.0,117.0,142.0,110.0,152.0,172.0\n"),
            "2026-08-07T09:00:00Z",
        )
    output = tmp_path / "archive"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=output)
    return snapshots, output


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_policy_is_closed_and_all_gates_remain_false() -> None:
    policy = load_policy(POLICY)
    assert policy["contract_version"] == "0.9.8"
    assert policy["availability_policy"]["clock"] == "FIRST_VERIFIED_RETRIEVAL"
    assert policy["availability_policy"]["snapshot_level_publication_date_is_row_evidence"] is False
    assert all(value is False for value in policy["output_gates"].values())


def test_policy_rejects_retroactive_availability() -> None:
    policy = load_policy(POLICY)
    policy["availability_policy"]["retroactive_availability_forbidden"] = False
    with pytest.raises(ProxyInformationSetError, match="retroactive_availability_forbidden"):
        validate_policy(policy)


def test_policy_rejects_opened_arm_l_gate() -> None:
    policy = load_policy(POLICY)
    policy["output_gates"]["arm_l_use_allowed"] = True
    with pytest.raises(ProxyInformationSetError, match="arm_l_use_allowed"):
        validate_policy(policy)


def test_single_snapshot_builds_verified_archive(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    summary = verify_archive_bundle(archive)
    assert summary["status"] == "FIRST_SEEN_PROXY_ARCHIVE_VALID"
    assert summary["snapshot_count"] == 1
    assert summary["snapshot_observation_count"] == 12
    assert summary["distinct_observation_count"] == 12
    assert summary["value_version_count"] == 12
    assert summary["revision_event_count"] == 0
    continuity = _rows(archive / "source_continuity.csv")
    assert continuity[0]["continuity_status"] == "SINGLE_SNAPSHOT"


def test_snapshot_publication_date_does_not_backdate_rows(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    versions = _rows(archive / "value_versions.csv")
    assert {row["available_at"] for row in versions} == {"2026-07-03T12:00:00Z"}
    assert {row["availability_basis"] for row in versions} == {"FIRST_VERIFIED_RETRIEVAL"}


def test_same_value_reobservation_is_not_revision(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=False)
    summary = verify_archive_bundle(archive)
    assert summary["snapshot_observation_count"] == 30
    assert summary["distinct_observation_count"] == 18
    assert summary["value_version_count"] == 18
    assert summary["revision_event_count"] == 0


def test_changed_value_creates_revision_version_and_event(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    summary = verify_archive_bundle(archive)
    assert summary["value_version_count"] == 19
    assert summary["revision_event_count"] == 1
    revision = _rows(archive / "revision_events.csv")[0]
    assert revision["old_value"] == "120"
    assert revision["new_value"] == "122.5"
    assert revision["revision_first_seen_at"] == "2026-08-07T12:00:00Z"


def test_cutoff_before_archive_start_is_rejected(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    with pytest.raises(ProxyInformationSetError, match="no proxy value"):
        build_information_set(
            archive_dir=archive,
            cutoff="2026-07-03T11:59:59Z",
            output_dir=tmp_path / "early",
        )


def test_cutoff_between_snapshots_preserves_old_value(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    panel = tmp_path / "panel_before_revision"
    build_information_set(
        archive_dir=archive,
        cutoff="2026-07-20T00:00:00Z",
        output_dir=panel,
    )
    rows = _rows(panel / "panel.csv")
    target = next(row for row in rows if row["series_id"] == "FAO_FFPI" and row["period"] == "2026-05")
    assert target["value"] == "120"
    assert target["version_sequence"] == "1"


def test_cutoff_after_revision_uses_new_value(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    panel = tmp_path / "panel_after_revision"
    build_information_set(
        archive_dir=archive,
        cutoff="2026-08-08T00:00:00Z",
        output_dir=panel,
    )
    summary = verify_information_set_bundle(panel)
    rows = _rows(panel / "panel.csv")
    target = next(row for row in rows if row["series_id"] == "FAO_FFPI" and row["period"] == "2026-05")
    assert target["value"] == "122.5"
    assert target["version_sequence"] == "2"
    assert summary["selected_observation_count"] == 18


def test_cutoff_bundle_keeps_all_use_gates_closed(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    summary = verify_information_set_bundle(panel)
    assert summary["historical_first_published_claim_allowed"] is False
    assert summary["direct_index_use_allowed"] is False
    assert summary["arm_l_use_allowed"] is False
    assert summary["model_training_allowed"] is False
    assert summary["shadow_production_allowed"] is False
    assert summary["monetary_use_allowed"] is False
    assert all(row["arm_l_use_allowed"] == "false" for row in _rows(panel / "panel.csv"))


def test_archive_output_is_immutable(tmp_path: Path) -> None:
    snapshots, archive = _archive(tmp_path)
    with pytest.raises(ProxyInformationSetError, match="output already exists"):
        build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=archive)


def test_cutoff_output_is_immutable(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    with pytest.raises(ProxyInformationSetError, match="output already exists"):
        build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)


def test_archive_manifest_rejects_tampering(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    with (archive / "value_versions.csv").open("ab") as handle:
        handle.write(b"tamper\n")
    with pytest.raises(ProxyInformationSetError, match="manifest hash mismatch"):
        verify_archive_bundle(archive)


def test_cutoff_manifest_rejects_tampering(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    with (panel / "panel.csv").open("ab") as handle:
        handle.write(b"tamper\n")
    with pytest.raises(ProxyInformationSetError, match="manifest hash mismatch"):
        verify_information_set_bundle(panel)


def test_missing_ledger_snapshot_is_rejected(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    first = _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    shutil.rmtree(first)
    with pytest.raises(ProxyInformationSetError, match="filesystem/ledger mismatch"):
        build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=tmp_path / "archive")


def test_extra_snapshot_not_in_ledger_is_rejected(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    first = _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    extra = snapshots / "FAO_FOOD_PRICE_INDEX_MONTHLY" / "EXTRA_SNAPSHOT"
    shutil.copytree(first, extra)
    receipt_path = extra / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["snapshot_id"] = "EXTRA_SNAPSHOT"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises((ProxyInformationSetError, Exception), match="filesystem/ledger mismatch|manifest hash mismatch"):
        build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=tmp_path / "archive")


def test_ledger_clock_regression_is_rejected(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-08-07T12:00:00Z", _payload())
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload("119.0"), "2026-07-03T09:00:00Z")
    with pytest.raises(ProxyInformationSetError, match="clock regressed"):
        build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=tmp_path / "archive")


def test_contiguous_archive_status(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True)
    continuity = _rows(archive / "source_continuity.csv")
    assert continuity[0]["continuity_status"] == "CONTIGUOUS_WITHIN_EXPECTED_LAG"


def test_gapped_archive_status(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, gap=True)
    continuity = _rows(archive / "source_continuity.csv")
    assert continuity[0]["continuity_status"] == "GAPPED_ARCHIVE"


def test_deterministic_archive_outputs(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    first = tmp_path / "archive_one"
    second = tmp_path / "archive_two"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=first)
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=second)
    for name in (
        "snapshot_observations.csv",
        "value_versions.csv",
        "revision_events.csv",
        "snapshot_deltas.csv",
        "source_continuity.csv",
        "archive_lineage.json",
        "archive_summary.json",
        "MANIFEST.sha256",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_deterministic_cutoff_outputs(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    first = tmp_path / "panel_one"
    second = tmp_path / "panel_two"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=first)
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=second)
    assert (first / "panel.csv").read_bytes() == (second / "panel.csv").read_bytes()
    assert (first / "source_cutoff_status.csv").read_bytes() == (second / "source_cutoff_status.csv").read_bytes()
    assert (first / "information_set_summary.json").read_bytes() == (second / "information_set_summary.json").read_bytes()
    assert (first / "MANIFEST.sha256").read_bytes() == (second / "MANIFEST.sha256").read_bytes()


def test_archive_summary_anchors_input_ledger_and_policy(tmp_path: Path) -> None:
    snapshots, archive = _archive(tmp_path)
    summary = verify_archive_bundle(archive)
    assert len(summary["input_ledger_sha256"]) == 64
    assert len(summary["policy_sha256"]) == 64
    assert summary["archive_start_at"] == "2026-07-03T12:00:00Z"
    assert summary["archive_end_at"] == "2026-07-03T12:00:00Z"
    assert (snapshots / "snapshot_ledger.jsonl").is_file()


def test_value_version_sequences_are_contiguous(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    versions = _rows(archive / "value_versions.csv")
    target = [row for row in versions if row["series_id"] == "FAO_FFPI" and row["period"] == "2026-05"]
    assert [row["version_sequence"] for row in target] == ["1", "2"]


def test_cutoff_panel_has_one_row_per_observation_key(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-08-08T00:00:00Z", output_dir=panel)
    rows = _rows(panel / "panel.csv")
    assert len(rows) == len({row["observation_key"] for row in rows})


def test_cli_validate_policy(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--policy", str(POLICY), "validate-policy"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PROXY_INFORMATION_SET_POLICY_V098_VALID"


def test_cli_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0

def test_workflow_uses_current_checker_only_when_present() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "fetch-data.yml"
    if not workflow_path.exists():
        pytest.skip("workflow is unavailable in the isolated overlay test")

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    build_steps = workflow["jobs"]["build-step2"]["steps"]
    commands = [
        step.get("run")
        for step in build_steps
        if isinstance(step, dict) and "run" in step
    ]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    current_suffix = "v" + version.replace(".", "")
    versioned_commands = [
        command
        for command in commands
        if isinstance(command, str)
        and command.startswith("python scripts/check_")
        and "_v" in command
        and command.endswith(".py --root .")
    ]

    assert len(versioned_commands) == 1
    assert f"_{current_suffix}.py --root ." in versioned_commands[0]
    assert "python scripts/check_research_core_constitution.py --root ." in commands
    assert "python scripts/check_research_core_ratification.py --root ." in commands

def test_multi_source_archive_and_cutoff(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    _ooh_snapshot(snapshots, "2026-07-03T13:00:00Z")
    archive = tmp_path / "archive"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=archive)
    summary = verify_archive_bundle(archive)
    assert summary["source_count"] == 2
    assert summary["snapshot_count"] == 2
    assert summary["snapshot_observation_count"] == 16
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    panel_summary = verify_information_set_bundle(panel)
    assert panel_summary["source_count"] == 2
    assert panel_summary["selected_observation_count"] == 16



def test_snapshot_delta_diagnostics_distinguish_reobservation_revision_and_addition(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path, two=True, changed=True)
    deltas = _rows(archive / "snapshot_deltas.csv")
    assert len(deltas) == 2
    assert deltas[0]["delta_status"] == "INITIAL_SNAPSHOT"
    assert deltas[0]["added_count"] == "12"
    assert deltas[1]["delta_status"] == "CONTENT_CHANGED"
    assert deltas[1]["added_count"] == "6"
    assert deltas[1]["revised_count"] == "1"
    assert deltas[1]["reobserved_count"] == "11"
    assert deltas[1]["missing_from_previous_count"] == "0"


def test_snapshot_delta_records_disappearing_rows_without_deleting_history(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    reduced = (
        "Date,Food Price Index,Meat Price Index,Dairy Price Index,Cereals Price Index,Oils Price Index,Sugar Price Index\n"
        "2026-06,121.0,116.0,141.0,109.0,151.0,171.0\n"
    ).encode("utf-8")
    _snapshot(snapshots, "2026-08-07T12:00:00Z", reduced, "2026-08-07T09:00:00Z")
    archive = tmp_path / "archive"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=archive)
    deltas = _rows(archive / "snapshot_deltas.csv")
    assert deltas[1]["missing_from_previous_count"] == "6"
    assert deltas[1]["delta_status"] == "CONTENT_CHANGED"
    assert len(_rows(archive / "value_versions.csv")) == 12


def test_root_archive_has_explicit_lineage(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    summary = verify_archive_bundle(archive)
    lineage = json.loads((archive / "archive_lineage.json").read_text(encoding="utf-8"))
    assert summary["lineage_mode"] == "ROOT"
    assert lineage["lineage_mode"] == "ROOT"
    assert lineage["parent_archive_manifest_sha256"] is None
    assert lineage["appended_snapshot_count"] == 1


def test_successor_archive_links_parent_and_preserves_predecessor(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    first = tmp_path / "archive_one"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=first)
    _snapshot(
        snapshots,
        "2026-08-07T12:00:00Z",
        _payload("122.5", "2026-07,123.0,117.0,142.0,110.0,152.0,172.0\n"),
        "2026-08-07T09:00:00Z",
    )
    second = tmp_path / "archive_two"
    build_archive(
        registry_path=REGISTRY,
        policy_path=POLICY,
        snapshot_root=snapshots,
        output_dir=second,
        previous_archive_dir=first,
    )
    summary = verify_archive_bundle(second)
    lineage = json.loads((second / "archive_lineage.json").read_text(encoding="utf-8"))
    assert summary["lineage_mode"] == "SUCCESSOR"
    assert summary["appended_snapshot_count"] == 1
    assert lineage["parent_snapshot_count"] == 1
    assert lineage["parent_archive_manifest_sha256"] is not None
    previous_rows = _rows(first / "snapshot_observations.csv")
    successor_rows = _rows(second / "snapshot_observations.csv")
    assert all(row in successor_rows for row in previous_rows)


def test_successor_archive_rejects_missing_predecessor_snapshot(tmp_path: Path) -> None:
    first_root = tmp_path / "first_snapshots"
    _snapshot(first_root, "2026-07-03T12:00:00Z", _payload())
    first = tmp_path / "archive_one"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=first_root, output_dir=first)
    second_root = tmp_path / "second_snapshots"
    _snapshot(second_root, "2026-08-07T12:00:00Z", _payload("122.5"), "2026-08-07T09:00:00Z")
    with pytest.raises(ProxyInformationSetError, match="every predecessor snapshot"):
        build_archive(
            registry_path=REGISTRY,
            policy_path=POLICY,
            snapshot_root=second_root,
            output_dir=tmp_path / "archive_two",
            previous_archive_dir=first,
        )


def test_cutoff_reports_current_source_freshness(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    summary = verify_information_set_bundle(panel)
    rows = _rows(panel / "source_cutoff_status.csv")
    assert rows[0]["freshness_status"] == "CURRENT_WITHIN_EXPECTED_WINDOW"
    assert rows[0]["age_days"] == "0"
    assert summary["current_source_count"] == 1
    assert summary["stale_source_count"] == 0


def test_cutoff_reports_stale_source_without_removing_values(tmp_path: Path) -> None:
    _, archive = _archive(tmp_path)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2027-01-15T00:00:00Z", output_dir=panel)
    summary = verify_information_set_bundle(panel)
    rows = _rows(panel / "source_cutoff_status.csv")
    assert rows[0]["freshness_status"] == "STALE_BEYOND_EXPECTED_WINDOW"
    assert int(rows[0]["age_days"]) > int(rows[0]["allowed_age_days"])
    assert summary["stale_source_count"] == 1
    assert summary["selected_observation_count"] == 12


def test_cutoff_reports_source_not_yet_observed(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    _ooh_snapshot(snapshots, "2026-08-03T13:00:00Z")
    archive = tmp_path / "archive"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=archive)
    panel = tmp_path / "panel"
    build_information_set(archive_dir=archive, cutoff="2026-07-04T00:00:00Z", output_dir=panel)
    summary = verify_information_set_bundle(panel)
    statuses = {row["source_id"]: row for row in _rows(panel / "source_cutoff_status.csv")}
    assert statuses["EUROSTAT_OOHPI_QUARTERLY"]["freshness_status"] == "NO_SNAPSHOT_BY_CUTOFF"
    assert statuses["EUROSTAT_OOHPI_QUARTERLY"]["selected_observation_count"] == "0"
    assert summary["archive_source_count"] == 2
    assert summary["no_snapshot_source_count"] == 1



def test_cli_extend_archive_builds_successor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    first = tmp_path / "archive_one"
    build_archive(registry_path=REGISTRY, policy_path=POLICY, snapshot_root=snapshots, output_dir=first)
    _snapshot(
        snapshots,
        "2026-08-07T12:00:00Z",
        _payload("122.5", "2026-07,123.0,117.0,142.0,110.0,152.0,172.0\n"),
        "2026-08-07T09:00:00Z",
    )
    second = tmp_path / "archive_two"
    assert main([
        "--registry", str(REGISTRY),
        "--policy", str(POLICY),
        "extend-archive",
        "--snapshot-root", str(snapshots),
        "--previous-archive", str(first),
        "--output-dir", str(second),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["lineage_mode"] == "SUCCESSOR"
    assert output["appended_snapshot_count"] == 1


def test_successor_archive_rejects_policy_change(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    _snapshot(snapshots, "2026-07-03T12:00:00Z", _payload())
    first_policy = tmp_path / "policy_first.json"
    policy = load_policy(POLICY)
    policy["quality_policy"]["continuity_gap_multiplier"] = 2
    first_policy.write_text(json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")
    first = tmp_path / "archive_one"
    build_archive(registry_path=REGISTRY, policy_path=first_policy, snapshot_root=snapshots, output_dir=first)
    _snapshot(
        snapshots,
        "2026-08-07T12:00:00Z",
        _payload("122.5", "2026-07,123.0,117.0,142.0,110.0,152.0,172.0\n"),
        "2026-08-07T09:00:00Z",
    )
    with pytest.raises(ProxyInformationSetError, match="policy does not match"):
        build_archive(
            registry_path=REGISTRY,
            policy_path=POLICY,
            snapshot_root=snapshots,
            output_dir=tmp_path / "archive_two",
            previous_archive_dir=first,
        )
