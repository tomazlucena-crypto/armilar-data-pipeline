from __future__ import annotations

import csv
import hashlib
import itertools
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

OVERLAY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OVERLAY_ROOT / "src"))

from armilar_prices.first_published_v093 import (  # noqa: E402
    CAPABILITY,
    DATASET,
    FirstPublishedError,
    FirstPublishedPolicy,
    SNAPSHOT_KIND,
    TEST_SNAPSHOT_KIND,
    VINTAGE_CLASS,
    acquire_snapshot,
    build_data_url,
    build_first_published_panel,
    build_probe_url,
    discover_codes,
    iter_periods,
    load_snapshot,
    parse_observations,
    verify_manifest,
)

ECONOMIES = (("DE", "DEU", "Germany"), ("ES", "ESP", "Spain"), ("FR", "FRA", "France"), ("IT", "ITA", "Italy"), ("PT", "PRT", "Portugal"))
CATEGORIES = tuple(f"CP{i:02d}" for i in range(13))
PERIODS = iter_periods("2021-01", "2025-12")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    (root / "MANIFEST.sha256").write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _policy(tmp_path: Path, **updates: Any) -> Path:
    payload = json.loads((OVERLAY_ROOT / "config" / "first_published_v093.json").read_text(encoding="utf-8"))
    payload.update(updates)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _jsonstat(
    *,
    probe: bool = False,
    missing: tuple[str, str, str] | None = None,
    ambiguous_unit: bool = False,
    ambiguous_release: bool = False,
) -> bytes:
    units = ["I15", "RCH_A"] if not ambiguous_unit else ["I15", "I15B"]
    unit_labels = {
        units[0]: "Index, 2015=100",
        units[1]: "Index, 2015=100" if ambiguous_unit else "Annual rate of change",
    }
    releases = ["F", "E"] if not ambiguous_release else ["F", "F2"]
    release_labels = {
        releases[0]: "Final",
        releases[1]: "Final full data" if ambiguous_release else "Flash estimate",
    }
    dimensions = {
        "freq": ["M"],
        "unit": units if probe else ["I15"],
        "coicop": ["CP00"] if probe else list(CATEGORIES),
        "release": releases if probe else ["F"],
        "geo": ["DE"] if probe else [item[0] for item in ECONOMIES],
        "time": ["2025-12"] if probe else list(PERIODS),
    }
    ids = list(dimensions)
    sizes = [len(dimensions[key]) for key in ids]
    dimension: dict[str, Any] = {}
    for dim_id, codes in dimensions.items():
        labels = {code: code for code in codes}
        if dim_id == "unit":
            labels = unit_labels
        elif dim_id == "release":
            labels = release_labels
        dimension[dim_id] = {"category": {"index": {code: idx for idx, code in enumerate(codes)}, "label": labels}}
    values: dict[str, float] = {}
    statuses: dict[str, str] = {}
    for linear, coordinate_values in enumerate(itertools.product(*(dimensions[key] for key in ids))):
        coordinate = dict(zip(ids, coordinate_values))
        if probe:
            values[str(linear)] = 100.0 + linear
            continue
        key = (coordinate["geo"], coordinate["coicop"], coordinate["time"])
        if key == missing:
            continue
        econ_idx = [item[0] for item in ECONOMIES].index(coordinate["geo"])
        category_idx = CATEGORIES.index(coordinate["coicop"])
        period_idx = PERIODS.index(coordinate["time"])
        values[str(linear)] = 95.0 + econ_idx * 2 + category_idx * 0.4 + period_idx * 0.15
        if coordinate["time"] == "2021-01" and coordinate["coicop"] == "CP00":
            statuses[str(linear)] = "p"
    return json.dumps(
        {
            "version": "2.0",
            "class": "dataset",
            "id": ids,
            "size": sizes,
            "dimension": dimension,
            "value": values,
            "status": statuses,
        },
        sort_keys=True,
    ).encode("utf-8")


class _Response:
    def __init__(self, data: bytes, url: str) -> None:
        self._data = data
        self.status = 200
        self.url = url
        self.headers = {"Content-Type": "application/json", "ETag": '"test"'}

    def read(self, _limit: int = -1) -> bytes:
        return self._data

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _opener_factory(responses: list[bytes]):
    calls: list[str] = []

    def opener(request, timeout: int):
        del timeout
        calls.append(request.full_url)
        return _Response(responses[len(calls) - 1], request.full_url)

    return opener, calls


def _snapshot(tmp_path: Path, policy_path: Path, *, missing=None) -> Path:
    policy = FirstPublishedPolicy.load(policy_path)
    root = tmp_path / "snapshot"
    probe = _jsonstat(probe=True)
    panel = _jsonstat(missing=missing)
    requests = []
    for request_id, data in (("structure_probe", probe), ("first_published_panel", panel)):
        digest = hashlib.sha256(data).hexdigest()
        relative = Path("raw/eurostat") / DATASET / f"{request_id}.{digest[:16]}.json"
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)
        requests.append({"request_id": request_id, "raw_file": relative.as_posix(), "raw_sha256": digest})
    manifest = {
        "snapshot_schema_version": "1.0",
        "provider": "EUROSTAT",
        "dataset": DATASET,
        "snapshot_kind": TEST_SNAPSHOT_KIND,
        "policy_version": policy.policy_version,
        "policy_sha256": policy.policy_sha256,
        "universe_id": policy.universe_id,
        "retrieved_at": "2026-07-01T12:00:00+00:00",
        "selected_codes": {"unit_code": "I15", "unit_label": "Index, 2015=100", "release_code": "F", "release_label": "Final"},
        "requests": requests,
    }
    (root / "snapshot_manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    _write_manifest(root)
    return root


def _first_relative(geo: str, category: str, period: str) -> Decimal:
    econ_idx = [item[0] for item in ECONOMIES].index(geo)
    category_idx = CATEGORIES.index(category)
    period_idx = PERIODS.index(period)
    value = Decimal("95") + Decimal(econ_idx * 2) + Decimal(category_idx) * Decimal("0.4") + Decimal(period_idx) * Decimal("0.15")
    base = sum(
        Decimal("95") + Decimal(econ_idx * 2) + Decimal(category_idx) * Decimal("0.4") + Decimal(idx) * Decimal("0.15")
        for idx in range(12)
    ) / Decimal(12)
    return value / base


def _inputs(tmp_path: Path, policy_path: Path) -> tuple[Path, Path]:
    policy = FirstPublishedPolicy.load(policy_path)
    info = tmp_path / "information_set"
    info.mkdir()
    cell_weights = [Decimal("0.016666666666666666")] * 59 + [Decimal("0.016666666666666706")]
    weight_map: dict[tuple[str, str], Decimal] = {}
    cursor = 0
    for _geo, armilar, _name in ECONOMIES:
        for category in CATEGORIES[1:]:
            weight_map[(armilar, category)] = cell_weights[cursor]
            cursor += 1
    economy_weights = {
        armilar: sum(weight_map[(armilar, category)] for category in CATEGORIES[1:])
        for _geo, armilar, _name in ECONOMIES
    }
    info_rows = []
    for geo, armilar, name in ECONOMIES:
        for period_idx, period in enumerate(PERIODS):
            relative = _first_relative(geo, "CP00", period)
            if period_idx >= 36:
                relative += Decimal("0.0002")
            info_rows.append(
                {
                    "universe_id": policy.universe_id,
                    "economy_code": armilar,
                    "source_category": "CP00",
                    "reference_period": period,
                    "available_from_date": f"{period[:4]}-{int(period[5:])+1:02d}-18" if period[5:] != "12" else f"{int(period[:4])+1}-01-18",
                    "price_relative": str(relative),
                    "economy_fixed_universe_weight": str(economy_weights[armilar]),
                }
            )
    _write_csv(info / "cp00_publication_availability.csv", info_rows)
    (info / "run_summary.json").write_text(
        json.dumps(
            {
                "policy_version": "0.9.3",
                "universe_id": policy.universe_id,
                "source_category": "CP00",
                "research_release_allowed": False,
                "monetary_release_allowed": False,
            },
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    _write_manifest(info)

    vertical = tmp_path / "vertical"
    vertical.mkdir()
    weight_rows = []
    observation_rows = []
    for geo, armilar, name in ECONOMIES:
        for category in CATEGORIES[1:]:
            weight = weight_map[(armilar, category)]
            weight_rows.append({"economy_code": armilar, "source_category": category, "fixed_universe_weight": str(weight)})
            for period_idx, period in enumerate(PERIODS):
                relative = _first_relative(geo, category, period)
                if category == "CP08" and period_idx >= 24:
                    relative -= Decimal("0.0004")
                observation_rows.append(
                    {
                        "universe_id": policy.universe_id,
                        "economy_code": armilar,
                        "economy_name": name,
                        "source_category": category,
                        "armilar_category": category,
                        "period": period,
                        "price_relative": str(relative),
                        "fixed_universe_weight": str(weight),
                        "price_evidence_class": "P1_OFFICIAL_CATEGORY",
                    }
                )
    _write_csv(vertical / "fixed_universe_weights.csv", weight_rows)
    _write_csv(vertical / "normalized_price_observations.csv", observation_rows)
    (vertical / "run_summary.json").write_text(
        json.dumps({"policy_version": "0.8.7", "universe_id": policy.universe_id}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_manifest(vertical)
    return info, vertical


def test_policy_requires_exact_universe_and_closed_gates(tmp_path: Path) -> None:
    policy = FirstPublishedPolicy.load(_policy(tmp_path))
    assert policy.dataset == DATASET
    assert policy.categories == CATEGORIES
    assert policy.historical_value_vintages_available is True
    with pytest.raises(FirstPublishedError, match="RELEASE_GATE_MUST_BE_FALSE"):
        FirstPublishedPolicy.load(_policy(tmp_path, model_promotion_allowed=True))


def test_probe_and_data_urls_use_official_dataset(tmp_path: Path) -> None:
    policy = FirstPublishedPolicy.load(_policy(tmp_path))
    assert "prc_hicp_fp" in build_probe_url(policy)
    data_url = build_data_url(policy, "I15", "F")
    assert data_url.count("coicop=") == 13
    assert data_url.count("geo=") == 5
    assert "release=F" in data_url


def test_discovery_selects_final_and_2015_index(tmp_path: Path) -> None:
    policy = FirstPublishedPolicy.load(_policy(tmp_path))
    unit, release, selected = discover_codes(_jsonstat(probe=True), policy)
    assert (unit, release) == ("I15", "F")
    assert selected["release_label"] == "Final"


def test_discovery_rejects_ambiguous_unit(tmp_path: Path) -> None:
    with pytest.raises(FirstPublishedError, match="UNIT_DISCOVERY_AMBIGUOUS"):
        discover_codes(_jsonstat(probe=True, ambiguous_unit=True), FirstPublishedPolicy.load(_policy(tmp_path)))


def test_discovery_rejects_ambiguous_release(tmp_path: Path) -> None:
    with pytest.raises(FirstPublishedError, match="RELEASE_DISCOVERY_AMBIGUOUS"):
        discover_codes(_jsonstat(probe=True, ambiguous_release=True), FirstPublishedPolicy.load(_policy(tmp_path)))


def test_acquisition_preserves_probe_and_panel(tmp_path: Path) -> None:
    opener, calls = _opener_factory([_jsonstat(probe=True), _jsonstat()])
    root = tmp_path / "acquired"
    manifest = acquire_snapshot(_policy(tmp_path), root, retrieved_at="2026-07-01T12:00:00+00:00", opener=opener)
    assert manifest["snapshot_kind"] == SNAPSHOT_KIND
    assert len(manifest["requests"]) == 2
    assert len(calls) == 2
    verify_manifest(root)


def test_acquisition_rejects_nonempty_output(tmp_path: Path) -> None:
    root = tmp_path / "acquired"
    root.mkdir()
    (root / "x").write_text("x")
    with pytest.raises(FirstPublishedError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        acquire_snapshot(_policy(tmp_path), root, opener=lambda *_args, **_kwargs: None)


def test_snapshot_replay_has_exact_3900_cells(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    rows, manifest = load_snapshot(FirstPublishedPolicy.load(policy_path), _snapshot(tmp_path, policy_path))
    assert len(rows) == 3900
    assert manifest["selected_codes"]["release_code"] == "F"
    assert {row.status for row in rows} >= {"", "p"}


def test_snapshot_rejects_missing_cell(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    root = _snapshot(tmp_path, policy_path, missing=("PT", "CP12", "2025-12"))
    with pytest.raises(FirstPublishedError, match="FIRST_PUBLISHED_GRID_INCOMPLETE"):
        load_snapshot(FirstPublishedPolicy.load(policy_path), root)


def test_snapshot_tamper_is_detected(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    root = _snapshot(tmp_path, policy_path)
    target = next((root / "raw").rglob("first_published_panel*.json"))
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(FirstPublishedError, match="MANIFEST_HASH_MISMATCH"):
        load_snapshot(FirstPublishedPolicy.load(policy_path), root)


def test_build_creates_first_published_panel_and_revision_audit(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    snapshot = _snapshot(tmp_path, policy_path)
    info, vertical = _inputs(tmp_path, policy_path)
    output = tmp_path / "output"
    summary = build_first_published_panel(policy_path, snapshot, info, vertical, output)
    assert summary["capability"] == CAPABILITY
    assert summary["observation_count"] == 3900
    assert summary["historical_value_vintages_available"] is True
    assert summary["publication_aware_model_comparison_allowed"] is False
    assert len(list(csv.DictReader((output / "first_published_observations.csv").open()))) == 3900
    assert len(list(csv.DictReader((output / "first_published_monthly_indices.csv").open()))) == 60
    assert len(list(csv.DictReader((output / "revision_audit.csv").open()))) == 3900
    verify_manifest(output)


def test_build_output_has_vintage_and_release_date(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    output = tmp_path / "output"
    build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, output)
    row = next(csv.DictReader((output / "first_published_observations.csv").open()))
    assert row["value_vintage_class"] == VINTAGE_CLASS
    assert row["available_from_date"]
    assert row["raw_sha256"]


def test_revision_summary_detects_known_differences(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    output = tmp_path / "output"
    build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, output)
    summary = json.loads((output / "revision_summary.json").read_text())
    assert summary["revised_observation_count"] > 0
    assert Decimal(summary["maximum_absolute_revision_bps"]) > 0


def test_build_rejects_open_input_gate(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    summary_path = info / "run_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["research_release_allowed"] = True
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n")
    _write_manifest(info)
    with pytest.raises(FirstPublishedError, match="INPUT_RELEASE_GATE_OPEN"):
        build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, tmp_path / "output")


def test_build_rejects_missing_information_set_economy(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    rows = list(csv.DictReader((info / "cp00_publication_availability.csv").open()))
    rows = [row for row in rows if row["economy_code"] != "PRT"]
    _write_csv(info / "cp00_publication_availability.csv", rows)
    _write_manifest(info)
    with pytest.raises(FirstPublishedError, match="INFORMATION_SET_GRID_INCOMPLETE"):
        build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, tmp_path / "output")


def test_build_rejects_inconsistent_release_dates(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    rows = list(csv.DictReader((info / "cp00_publication_availability.csv").open()))
    rows[1]["available_from_date"] = "2099-01-01"
    _write_csv(info / "cp00_publication_availability.csv", rows)
    _write_manifest(info)
    with pytest.raises(FirstPublishedError, match="RELEASE_DATE_INCONSISTENT"):
        build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, tmp_path / "output")


def test_build_rejects_weights_not_summing_to_one(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    rows = list(csv.DictReader((vertical / "fixed_universe_weights.csv").open()))
    rows[0]["fixed_universe_weight"] = "0.1"
    _write_csv(vertical / "fixed_universe_weights.csv", rows)
    _write_manifest(vertical)
    with pytest.raises(FirstPublishedError, match="WEIGHTS_DO_NOT_SUM_TO_ONE"):
        build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, tmp_path / "output")


def test_build_rejects_nonempty_output(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "x").write_text("x")
    with pytest.raises(FirstPublishedError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, output)


def test_build_is_deterministic(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    snapshot = _snapshot(tmp_path, policy_path)
    first, second = tmp_path / "first", tmp_path / "second"
    build_first_published_panel(policy_path, snapshot, info, vertical, first)
    build_first_published_panel(policy_path, snapshot, info, vertical, second)
    first_files = {p.relative_to(first).as_posix(): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    second_files = {p.relative_to(second).as_posix(): p.read_bytes() for p in second.rglob("*") if p.is_file()}
    assert first_files == second_files


def test_report_forbids_model_promotion(tmp_path: Path) -> None:
    policy_path = _policy(tmp_path)
    info, vertical = _inputs(tmp_path, policy_path)
    output = tmp_path / "output"
    build_first_published_panel(policy_path, _snapshot(tmp_path, policy_path), info, vertical, output)
    report = (output / "FIRST_PUBLISHED_PANEL_REPORT.md").read_text()
    assert "publication_aware_model_comparison_allowed=false" in report
    assert "model_promotion_allowed=false" in report
    summary = json.loads((output / "run_summary.json").read_text())
    assert summary["research_release_allowed"] is False
    assert summary["monetary_release_allowed"] is False
