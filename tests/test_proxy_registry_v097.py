from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import sys
import tomllib
from pathlib import Path

import openpyxl
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from armilar_proxies.registry_v097 import (  # noqa: E402
    ProxyRegistryError,
    acquire_source,
    load_registry,
    parse_ec_oil_bulletin_xlsx,
    parse_eurostat_jsonstat,
    parse_fao_ffpi_csv,
    parse_quarter,
    parse_world_bank_pink_sheet_xlsx,
    registry_hash,
    replay_snapshot,
    source_by_id,
    validate_raw_magic,
    validate_registry,
    verify_ledger,
    verify_manifest,
)

REGISTRY = ROOT / "config/proxy_source_registry_v097.json"
RETRIEVED = "2026-07-03T12:00:00Z"
PUBLISHED = "2026-07-03T09:00:00Z"


def _context(source: dict) -> dict:
    return {
        "source": source,
        "published_at": PUBLISHED,
        "retrieved_at": RETRIEVED,
        "raw_snapshot_id": "SNAPSHOT",
        "source_sha256": "1" * 64,
        "registry_sha256": "2" * 64,
    }


def _xlsx_bytes(rows: list[list[object]], title: str = "Sheet1") -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _fao_payload(extra: str = "") -> bytes:
    return (
        "Date,Food Price Index,Meat Price Index,Dairy Price Index,Cereals Price Index,Oils Price Index,Sugar Price Index\n"
        "2026-05,128.1,119.2,145.4,109.8,152.3,171.6\n"
        "2026-06,129.0,120.0,146.0,110.0,153.0,172.0\n"
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


def _write_registry(tmp_path: Path, registry: dict) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_registry_is_closed_and_all_use_gates_remain_false() -> None:
    registry = load_registry(REGISTRY)
    assert registry["registry_version"] == "0.9.7"
    assert len(registry["sources"]) == 4
    assert {source["source_id"] for source in registry["sources"]} == {
        "WORLD_BANK_PINK_SHEET_MONTHLY",
        "FAO_FOOD_PRICE_INDEX_MONTHLY",
        "EC_WEEKLY_OIL_BULLETIN_HISTORY",
        "EUROSTAT_OOHPI_QUARTERLY",
    }
    for source in registry["sources"]:
        assert source["direct_index_use_allowed"] is False
        assert source["arm_l_use_allowed"] is False
        assert source["model_training_allowed"] is False
        assert source["shadow_production_allowed"] is False
        assert source["monetary_use_allowed"] is False


def test_registry_rejects_opened_gate() -> None:
    registry = load_registry(REGISTRY)
    registry["sources"][0]["arm_l_use_allowed"] = True
    with pytest.raises(ProxyRegistryError, match="arm_l_use_allowed must remain false"):
        validate_registry(registry)


def test_registry_rejects_missing_mandatory_domain() -> None:
    registry = load_registry(REGISTRY)
    for source in registry["sources"]:
        if "HOUSING_OOH_SENSITIVITY" in source["proxy_domains"]:
            source["proxy_domains"] = ["UNMAPPED_TEST_DOMAIN"]
    with pytest.raises(ProxyRegistryError, match="mandatory proxy domains missing"):
        validate_registry(registry)


def test_workflow_runs_current_checker_and_constitution_only() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/fetch-data.yml").read_text(encoding="utf-8")
    )
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

    current_step = next(
        step for step in build_steps if step.get("run") == versioned_commands[0]
    )
    assert current_step["name"].startswith(f"Validate v{version} ")

def test_registry_rejects_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_bytes(b"\xef\xbb\xbf" + REGISTRY.read_bytes())
    with pytest.raises(ProxyRegistryError, match="BOM"):
        load_registry(path)


def test_fao_parser_normalises_six_series() -> None:
    source = source_by_id(load_registry(REGISTRY), "FAO_FOOD_PRICE_INDEX_MONTHLY")
    rows = parse_fao_ffpi_csv(_fao_payload(), **_context(source))
    assert len(rows) == 12
    assert {row["series_id"] for row in rows} == {
        "FAO_FFPI", "FAO_MEAT", "FAO_DAIRY", "FAO_CEREALS", "FAO_OILS", "FAO_SUGAR"
    }
    assert {row["period"] for row in rows} == {"2026-05", "2026-06"}
    assert all(row["direct_index_use_allowed"] == "false" for row in rows)


def test_world_bank_parser_selects_only_declared_series() -> None:
    source = source_by_id(load_registry(REGISTRY), "WORLD_BANK_PINK_SHEET_MONTHLY")
    payload = _xlsx_bytes(
        [
            ["Metadata", None, None, None, None, None],
            ["Date", "Energy", "Crude oil, average", "Natural gas, Europe", "Food", "Coal"],
            ["2026-05", 101.1, 72.5, 10.2, 115.0, 99.0],
            ["2026-06", 102.2, 73.0, 10.4, 116.0, 98.0],
        ],
        "Monthly Prices",
    )
    rows = parse_world_bank_pink_sheet_xlsx(payload, **_context(source))
    assert len(rows) == 8
    assert {row["series_id"] for row in rows} == set(source["series_selection"])
    assert "Coal" not in {row["series_id"] for row in rows}


def test_oil_bulletin_parser_supports_long_format() -> None:
    source = source_by_id(load_registry(REGISTRY), "EC_WEEKLY_OIL_BULLETIN_HISTORY")
    payload = _xlsx_bytes(
        [
            ["Date", "Country", "Product", "Price", "Unit"],
            ["2026-06-29", "PT", "Diesel", 1550.2, "EUR_PER_1000_LITRES"],
            ["2026-06-29", "ES", "Eurosuper 95", 1600.4, "EUR_PER_1000_LITRES"],
        ],
        "Consumer Prices",
    )
    rows = parse_ec_oil_bulletin_xlsx(payload, **_context(source))
    assert len(rows) == 2
    assert {row["series_id"] for row in rows} == {"EC_OIL_DIESEL", "EC_OIL_PETROL_95"}
    assert {row["proxy_domain"] for row in rows} == {"TRANSPORT"}


def test_eurostat_jsonstat_parser_preserves_geo_and_quarter() -> None:
    source = source_by_id(load_registry(REGISTRY), "EUROSTAT_OOHPI_QUARTERLY")
    rows = parse_eurostat_jsonstat(_eurostat_payload(), **_context(source))
    assert len(rows) == 4
    assert {row["geography"] for row in rows} == {"PT", "ES"}
    assert {row["period"] for row in rows} == {"2025-Q4", "2026-Q1"}
    assert {row["proxy_domain"] for row in rows} == {"HOUSING_OOH_SENSITIVITY"}


@pytest.mark.parametrize("value, expected", [("2026Q1", "2026-Q1"), ("2026-Q2", "2026-Q2"), ("Q32026", "2026-Q3")])
def test_quarter_parser(value: str, expected: str) -> None:
    assert parse_quarter(value) == expected


def test_snapshot_is_immutable_manifested_and_replayable(tmp_path: Path) -> None:
    snapshot = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
        response_headers={"content-type": "text/csv"},
    )
    assert verify_manifest(snapshot)
    summary = json.loads((snapshot / "normalization_summary.json").read_text(encoding="utf-8"))
    receipt = json.loads((snapshot / "receipt.json").read_text(encoding="utf-8"))
    assert summary["information_set_ready"] is False
    assert summary["direct_index_use_allowed"] is False
    assert summary["arm_l_use_allowed"] is False
    assert receipt["model_training_allowed"] is False
    replay = replay_snapshot(registry_path=REGISTRY, snapshot_dir=snapshot)
    assert replay["status"] == "PROXY_SNAPSHOT_REPLAY_VALID"
    assert replay["observation_count"] == 12


def test_duplicate_snapshot_is_rejected(tmp_path: Path) -> None:
    kwargs = dict(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    acquire_source(**kwargs)
    with pytest.raises(ProxyRegistryError, match="snapshot already exists"):
        acquire_source(**kwargs)


def test_ledger_chains_multiple_snapshots(tmp_path: Path) -> None:
    first = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at="2026-07-03T12:00:00Z",
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    second = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at="2026-08-07T12:00:00Z",
        published_at="2026-08-07T09:00:00Z",
        raw_payload=_fao_payload("2026-07,130.0,121.0,147.0,111.0,154.0,173.0\n"),
    )
    assert first != second
    entries = verify_ledger(tmp_path / "snapshot_ledger.jsonl")
    assert len(entries) == 2
    assert entries[0]["previous_entry_hash"] == "0" * 64
    assert entries[1]["previous_entry_hash"] == entries[0]["entry_hash"]


def test_tampered_snapshot_is_rejected(tmp_path: Path) -> None:
    snapshot = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    with (snapshot / "normalized.csv").open("ab") as handle:
        handle.write(b"tamper\n")
    with pytest.raises(ProxyRegistryError, match="manifest hash mismatch"):
        replay_snapshot(registry_path=REGISTRY, snapshot_dir=snapshot)


def test_tampered_ledger_is_rejected(tmp_path: Path) -> None:
    acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path,
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    ledger = tmp_path / "snapshot_ledger.jsonl"
    data = json.loads(ledger.read_text(encoding="utf-8"))
    data["source_sha256"] = "0" * 64
    ledger.write_text(json.dumps(data) + "\n", encoding="utf-8")
    with pytest.raises(ProxyRegistryError, match="entry hash mismatch"):
        verify_ledger(ledger)


def test_replay_rejects_changed_registry(tmp_path: Path) -> None:
    snapshot = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path / "snapshots",
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    registry = load_registry(REGISTRY)
    registry["sources"][0]["conceptual_limitations"][0] += " Clarification."
    changed = _write_registry(tmp_path, registry)
    assert registry_hash(changed) != registry_hash(REGISTRY)
    with pytest.raises(ProxyRegistryError, match="registry hash"):
        replay_snapshot(registry_path=changed, snapshot_dir=snapshot)


def test_exact_timestamp_source_requires_published_at(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY)
    source = next(item for item in registry["sources"] if item["source_id"] == "FAO_FOOD_PRICE_INDEX_MONTHLY")
    source["publication_time_status"] = "EXACT_TIMESTAMP"
    path = _write_registry(tmp_path, registry)
    with pytest.raises(ProxyRegistryError, match="published_at timestamp is mandatory"):
        acquire_source(
            registry_path=path,
            source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
            output_root=tmp_path / "out",
            retrieved_at=RETRIEVED,
            raw_payload=_fao_payload(),
        )


def test_current_sources_cannot_be_information_set_ready(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY)
    for source in registry["sources"]:
        assert source["historical_vintage_support"] is False
    snapshot = acquire_source(
        registry_path=REGISTRY,
        source_id="EUROSTAT_OOHPI_QUARTERLY",
        output_root=tmp_path,
        retrieved_at=RETRIEVED,
        raw_payload=_eurostat_payload(),
    )
    summary = json.loads((snapshot / "normalization_summary.json").read_text(encoding="utf-8"))
    assert summary["published_at"] is None
    assert summary["information_set_ready"] is False


def test_raw_magic_rejects_invalid_xlsx_and_json() -> None:
    registry = load_registry(REGISTRY)
    wb = source_by_id(registry, "WORLD_BANK_PINK_SHEET_MONTHLY")
    eu = source_by_id(registry, "EUROSTAT_OOHPI_QUARTERLY")
    with pytest.raises(ProxyRegistryError, match="ZIP magic"):
        validate_raw_magic(wb, b"not xlsx")
    with pytest.raises(ProxyRegistryError, match="invalid JSON"):
        validate_raw_magic(eu, b"{broken")


def test_normalized_csv_hash_is_reproducible(tmp_path: Path) -> None:
    one = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path / "one",
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    two = acquire_source(
        registry_path=REGISTRY,
        source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
        output_root=tmp_path / "two",
        retrieved_at=RETRIEVED,
        published_at=PUBLISHED,
        raw_payload=_fao_payload(),
    )
    assert hashlib.sha256((one / "normalized.csv").read_bytes()).hexdigest() == hashlib.sha256((two / "normalized.csv").read_bytes()).hexdigest()


def test_acquisition_rejects_unapproved_resolved_host(tmp_path: Path) -> None:
    with pytest.raises(ProxyRegistryError, match="resolved URL host is not approved"):
        acquire_source(
            registry_path=REGISTRY,
            source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
            output_root=tmp_path,
            retrieved_at=RETRIEVED,
            published_at=PUBLISHED,
            raw_payload=_fao_payload(),
            final_url="https://example.com/redirected.csv",
        )


def test_acquisition_rejects_publication_after_retrieval(tmp_path: Path) -> None:
    with pytest.raises(ProxyRegistryError, match="published_at cannot be after retrieved_at"):
        acquire_source(
            registry_path=REGISTRY,
            source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
            output_root=tmp_path,
            retrieved_at="2026-07-03T12:00:00Z",
            published_at="2026-07-04T12:00:00Z",
            raw_payload=_fao_payload(),
        )


def test_acquisition_rejects_future_observation_period(tmp_path: Path) -> None:
    future = (
        "Date,Food Price Index\n"
        "2026-08,130.0\n"
    ).encode("utf-8")
    with pytest.raises(ProxyRegistryError, match="observation period is after retrieval time"):
        acquire_source(
            registry_path=REGISTRY,
            source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
            output_root=tmp_path,
            retrieved_at="2026-07-03T12:00:00Z",
            published_at=PUBLISHED,
            raw_payload=future,
        )


def test_acquisition_rejects_duplicate_observation_identity(tmp_path: Path) -> None:
    duplicate = (
        "Date,Food Price Index\n"
        "2026-06,129.0\n"
        "2026-06,130.0\n"
    ).encode("utf-8")
    with pytest.raises(ProxyRegistryError, match="duplicate proxy observation identity"):
        acquire_source(
            registry_path=REGISTRY,
            source_id="FAO_FOOD_PRICE_INDEX_MONTHLY",
            output_root=tmp_path,
            retrieved_at=RETRIEVED,
            published_at=PUBLISHED,
            raw_payload=duplicate,
        )
