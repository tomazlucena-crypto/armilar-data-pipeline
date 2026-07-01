from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from armilar_prices.information_set_v093 import (
    BACKTEST_CLASS,
    CAPABILITY,
    InformationSetError,
    InformationSetPolicy,
    build_information_set_audit,
    seal_release_snapshot,
    verify_manifest,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path, *, one_space: bool = False) -> None:
    separator = " " if one_space else "  "
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    (root / "MANIFEST.sha256").write_text(
        "".join(f"{_sha(path)}{separator}{path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
    )


def _policy(tmp_path: Path, **changes: object) -> Path:
    payload = {
        "policy_version": "0.9.3",
        "universe_id": "TEST_EUROSTAT_2",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "source_category": "CP00",
        "economy_codes": ["AAA", "BBB"],
        "start_period": "2021-01",
        "end_period": "2021-03",
        "release_timezone": "Europe/Luxembourg",
        "availability_precision": "DAY",
        "minimum_release_lag_days": 1,
        "maximum_release_lag_days": 31,
        "required_headline_policy_version": "0.9.0",
        "required_backtest_policy_version": "0.9.0",
        "required_input_vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
        "output_capability": CAPABILITY,
        "historical_value_vintages_available": True,
        "publication_aware_model_comparison_allowed": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    payload.update(changes)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _release_source(tmp_path: Path, *, duplicate: bool = False, unofficial: bool = False) -> tuple[Path, Path]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    rows = []
    for period, released in [("2021-01", "2021-02-23"), ("2021-02", "2021-03-17"), ("2021-03", "2021-04-16")]:
        raw = evidence / f"{period}.html"
        raw.write_text(f"Official HICP release {period} on {released}\n", encoding="utf-8")
        rows.append(
            {
                "reference_period": period,
                "release_date": released,
                "source_url": (
                    "https://example.com/not-official"
                    if unofficial and period == "2021-01"
                    else f"https://ec.europa.eu/eurostat/web/products-euro-indicators/{period}"
                ),
                "raw_file": raw.name,
            }
        )
    if duplicate:
        rows[-1]["reference_period"] = "2021-02"
    registry = tmp_path / "registry.csv"
    with registry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return registry, evidence


def _release_snapshot(tmp_path: Path, **kwargs: object) -> Path:
    registry, evidence = _release_source(tmp_path, **kwargs)
    output = tmp_path / "release_snapshot"
    seal_release_snapshot(_policy(tmp_path), registry, evidence, output)
    return output


def _headline(
    tmp_path: Path,
    *,
    official: bool = True,
    one_space_manifest: bool = False,
    drop_economy: str | None = None,
    retrieved_at: str = "2026-07-01T00:00:00+00:00",
) -> Path:
    root = tmp_path / "headline"
    root.mkdir()
    rows = []
    for period_index, period in enumerate(("2021-01", "2021-02", "2021-03"), start=1):
        for economy, weight in (("AAA", "0.4"), ("BBB", "0.6")):
            if economy == drop_economy:
                continue
            rows.append(
                {
                    "universe_id": "TEST_EUROSTAT_2",
                    "economy_code": economy,
                    "period": period,
                    "source_category": "CP00",
                    "price_value": str(100 + period_index),
                    "price_relative": str(1 + period_index / 100),
                    "economy_fixed_universe_weight": weight,
                    "provider": "EUROSTAT",
                    "dataset": "prc_hicp_midx",
                    "raw_file": f"raw/{economy}-{period}.json",
                    "raw_sha256": hashlib.sha256(f"{economy}-{period}".encode()).hexdigest(),
                }
            )
    with (root / "normalized_headline_observations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "policy_version": "0.9.0",
        "universe_id": "TEST_EUROSTAT_2",
        "provider": "EUROSTAT",
        "dataset": "prc_hicp_midx",
        "source_category": "CP00",
        "start_period": "2021-01",
        "end_period": "2021-03",
        "month_count": 3,
        "economy_count": len({row["economy_code"] for row in rows}),
        "observation_count": len(rows),
        "snapshot_kind": "OFFICIAL_PROVIDER_ACQUISITION" if official else "SYNTHETIC_TEST_FIXTURE",
        "headline_source_independent": True,
        "category_panel_used_to_construct_headline": False,
        "snapshot_manifest_sha256": "a" * 64,
        "source_snapshot_retrieved_at": retrieved_at,
    }
    (root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _manifest(root, one_space=one_space_manifest)
    return root


def _backtest(
    tmp_path: Path,
    *,
    publication_aware: bool = False,
    donor: bool = True,
    headline: Path | None = None,
) -> Path:
    root = tmp_path / "backtest"
    root.mkdir()
    headline_root = headline or (tmp_path / "headline")
    headline_summary = json.loads((headline_root / "run_summary.json").read_text(encoding="utf-8"))
    summary = {
        "policy_version": "0.9.0",
        "vintage_mode": "FINAL_VINTAGE_PSEUDO_REAL_TIME",
        "publication_aware": publication_aware,
        "same_period_donor_assumption": donor,
        "headline_input_manifest_sha256": _sha(headline_root / "MANIFEST.sha256"),
        "headline_snapshot_manifest_sha256": headline_summary["snapshot_manifest_sha256"],
    }
    (root / "backtest_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (root / "backtest_cases.csv").write_text("case_id\nX\n", encoding="utf-8")
    _manifest(root)
    return root


def _build(tmp_path: Path):
    release = _release_snapshot(tmp_path)
    headline = _headline(tmp_path)
    backtest = _backtest(tmp_path)
    output = tmp_path / "output"
    summary = build_information_set_audit(_policy(tmp_path), headline, backtest, release, output)
    return output, summary


def test_policy_requires_first_published_capability_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(InformationSetError, match="HISTORICAL_VINTAGE_CAPABILITY_DISABLED"):
        InformationSetPolicy.load(_policy(tmp_path, historical_value_vintages_available=False))


def test_policy_rejects_publication_aware_model_comparison(tmp_path: Path) -> None:
    with pytest.raises(InformationSetError, match="MODEL_COMPARISON_CLAIM_UNSUPPORTED"):
        InformationSetPolicy.load(_policy(tmp_path, publication_aware_model_comparison_allowed=True))


@pytest.mark.parametrize("field", ["model_promotion_allowed", "research_release_allowed", "monetary_release_allowed"])
def test_policy_gates_must_remain_false(tmp_path: Path, field: str) -> None:
    with pytest.raises(InformationSetError, match="RELEASE_GATE_WEAKENED"):
        InformationSetPolicy.load(_policy(tmp_path, **{field: True}))


def test_seal_release_snapshot_preserves_and_hashes_evidence(tmp_path: Path) -> None:
    root = _release_snapshot(tmp_path)
    verify_manifest(root)
    rows = list(csv.DictReader((root / "release_events.csv").open(newline="", encoding="utf-8")))
    assert len(rows) == 3
    assert all((root / row["raw_file"]).is_file() for row in rows)
    assert all(_sha(root / row["raw_file"]) == row["raw_sha256"] for row in rows)


def test_release_registry_requires_official_source(tmp_path: Path) -> None:
    registry, evidence = _release_source(tmp_path, unofficial=True)
    with pytest.raises(InformationSetError, match="RELEASE_SOURCE_NOT_OFFICIAL"):
        seal_release_snapshot(_policy(tmp_path), registry, evidence, tmp_path / "out")


def test_release_registry_rejects_duplicates_and_missing_periods(tmp_path: Path) -> None:
    registry, evidence = _release_source(tmp_path, duplicate=True)
    with pytest.raises(InformationSetError, match="DUPLICATE_RELEASE_PERIOD"):
        seal_release_snapshot(_policy(tmp_path), registry, evidence, tmp_path / "out")


def test_release_lag_outside_policy_is_rejected(tmp_path: Path) -> None:
    release = _release_snapshot(tmp_path)
    with pytest.raises(InformationSetError, match="RELEASE_LAG_OUTSIDE_POLICY"):
        build_information_set_audit(
            _policy(tmp_path, maximum_release_lag_days=10),
            _headline(tmp_path),
            _backtest(tmp_path),
            release,
            tmp_path / "out",
        )


def test_build_attaches_release_dates_to_all_economy_months(tmp_path: Path) -> None:
    output, summary = _build(tmp_path)
    rows = list(csv.DictReader((output / "cp00_publication_availability.csv").open(newline="", encoding="utf-8")))
    assert len(rows) == 6
    assert summary["release_event_count"] == 3
    assert summary["headline_observation_count"] == 6
    assert {row["value_vintage_class"] for row in rows} == {"FINAL_VALUE_ONLY"}
    assert {row["availability_precision"] for row in rows} == {"DAY"}


def test_capability_classification_is_explicit_and_fail_closed(tmp_path: Path) -> None:
    output, summary = _build(tmp_path)
    classification = json.loads((output / "backtest_capability_classification.json").read_text(encoding="utf-8"))
    assert summary["supported_capability"] == CAPABILITY
    assert classification["current_backtest_classification"] == BACKTEST_CLASS
    assert classification["real_time_backtest_ready"] is False
    assert classification["historical_value_vintages_available"] is True
    assert classification["this_output_contains_first_published_values"] is False
    assert classification["first_published_dataset"] == "prc_hicp_fp"
    assert "PUBLICATION_AWARE_B0_B4_MODEL_COMPARISON" in classification["unsupported_claims"]


def test_existing_backtest_publication_claim_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InformationSetError, match="BACKTEST_PUBLICATION_CLAIM_UNEXPECTED"):
        build_information_set_audit(
            _policy(tmp_path),
            _headline(tmp_path),
            _backtest(tmp_path, publication_aware=True),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_same_period_donor_assumption_must_be_declared(tmp_path: Path) -> None:
    with pytest.raises(InformationSetError, match="BACKTEST_DONOR_ASSUMPTION_UNDECLARED"):
        build_information_set_audit(
            _policy(tmp_path),
            _headline(tmp_path),
            _backtest(tmp_path, donor=False),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_official_headline_input_is_required(tmp_path: Path) -> None:
    with pytest.raises(InformationSetError, match="OFFICIAL_HEADLINE_REQUIRED"):
        build_information_set_audit(
            _policy(tmp_path),
            _headline(tmp_path, official=False),
            _backtest(tmp_path),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_input_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    headline = _headline(tmp_path)
    with (headline / "normalized_headline_observations.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")
    with pytest.raises(InformationSetError, match="MANIFEST_HASH_MISMATCH"):
        build_information_set_audit(
            _policy(tmp_path),
            headline,
            _backtest(tmp_path),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_manifest_reader_accepts_one_or_two_spaces(tmp_path: Path) -> None:
    headline = _headline(tmp_path, one_space_manifest=True)
    verify_manifest(headline)


def test_missing_entire_economy_is_rejected(tmp_path: Path) -> None:
    headline = _headline(tmp_path, drop_economy="BBB")
    with pytest.raises(InformationSetError, match="HEADLINE_ECONOMY_UNIVERSE_MISMATCH"):
        build_information_set_audit(
            _policy(tmp_path),
            headline,
            _backtest(tmp_path, headline=headline),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_final_value_snapshot_lineage_is_attached(tmp_path: Path) -> None:
    output, summary = _build(tmp_path)
    rows = list(csv.DictReader((output / "cp00_publication_availability.csv").open(newline="", encoding="utf-8")))
    assert {row["value_snapshot_retrieved_at"] for row in rows} == {"2026-07-01T00:00:00+00:00"}
    assert {row["value_snapshot_manifest_sha256"] for row in rows} == {"a" * 64}
    assert all(row["value_raw_file"].startswith("raw/") for row in rows)
    assert all(len(row["value_raw_sha256"]) == 64 for row in rows)
    assert summary["headline_value_snapshot_manifest_sha256"] == "a" * 64


def test_naive_snapshot_retrieval_timestamp_is_rejected(tmp_path: Path) -> None:
    headline = _headline(tmp_path, retrieved_at="2026-07-01T00:00:00")
    with pytest.raises(InformationSetError, match="HEADLINE_RETRIEVAL_TIMESTAMP_INVALID"):
        build_information_set_audit(
            _policy(tmp_path),
            headline,
            _backtest(tmp_path, headline=headline),
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_backtest_must_reference_exact_headline_output(tmp_path: Path) -> None:
    headline = _headline(tmp_path)
    backtest = _backtest(tmp_path, headline=headline)
    summary_path = backtest / "backtest_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["headline_input_manifest_sha256"] = "b" * 64
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    _manifest(backtest)
    with pytest.raises(InformationSetError, match="BACKTEST_HEADLINE_INPUT_MISMATCH"):
        build_information_set_audit(
            _policy(tmp_path),
            headline,
            backtest,
            _release_snapshot(tmp_path),
            tmp_path / "out",
        )


def test_output_manifest_verifies(tmp_path: Path) -> None:
    output, _ = _build(tmp_path)
    verify_manifest(output)


def test_outputs_are_deterministic(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    release = _release_snapshot(tmp_path)
    headline = _headline(tmp_path)
    backtest = _backtest(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_information_set_audit(policy, headline, backtest, release, first)
    build_information_set_audit(policy, headline, backtest, release, second)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files


def test_nonempty_output_directory_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "x").write_text("x", encoding="utf-8")
    with pytest.raises(InformationSetError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        build_information_set_audit(
            _policy(tmp_path),
            _headline(tmp_path),
            _backtest(tmp_path),
            _release_snapshot(tmp_path),
            output,
        )


def test_run_summary_keeps_all_boundaries_closed(tmp_path: Path) -> None:
    _, summary = _build(tmp_path)
    assert summary["model_code_changed"] is False
    assert summary["model_promotion_allowed"] is False
    assert summary["research_release_allowed"] is False
    assert summary["monetary_release_allowed"] is False
    assert summary["publication_aware_model_comparison_allowed"] is False


class _FakeResponse:
    def __init__(self, url: str, data: bytes, content_type: str = "text/html") -> None:
        self.status = 200
        self._url = url
        self._data = data
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._data

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status


def _calendar_registry(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    events = [
        ("2021-01", "2021-02-23", "January 2021", "23 February 2021"),
        ("2021-02", "2021-03-17", "February 2021", "17 March 2021"),
        ("2021-03", "2021-04-16", "March 2021", "16 April 2021"),
    ]
    rows = []
    pages: dict[str, bytes] = {}
    for period, released, reference_label, release_label in events:
        release_month = datetime.fromisoformat(released).replace(day=1, tzinfo=ZoneInfo("Europe/Luxembourg"))
        start_ms = int(release_month.timestamp() * 1000)
        url = (
            "https://ec.europa.eu/eurostat/web/main/news/release-calendar"
            f"?start={start_ms}&type=listMonth"
        )
        raw_file = f"release_calendar_{released[:7]}.html"
        html = (
            "<html><body><main>Inflation (HICP), "
            f"{reference_label}. {release_label}. Data release Euro indicators release."
            + (" official Eurostat calendar evidence" * 50)
            + "</main></body></html>"
        ).encode("utf-8")
        pages[url] = html
        rows.append(
            {
                "reference_period": period,
                "release_date": released,
                "source_url": url,
                "raw_file": raw_file,
            }
        )
    registry = tmp_path / "calendar_registry.csv"
    with registry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return registry, pages


def test_curated_release_registry_is_complete_and_contains_known_dates() -> None:
    registry = Path(__file__).resolve().parents[1] / "config" / "cp00_release_registry_v093.csv"
    rows = list(csv.DictReader(registry.open(newline="", encoding="utf-8")))
    assert len(rows) == 60
    assert rows[0]["reference_period"] == "2021-01"
    assert rows[0]["release_date"] == "2021-02-23"
    assert rows[-1]["reference_period"] == "2025-12"
    assert rows[-1]["release_date"] == "2026-01-19"
    by_period = {row["reference_period"]: row for row in rows}
    assert by_period["2021-12"]["release_date"] == "2022-01-20"
    assert by_period["2023-03"]["release_date"] == "2023-04-19"
    assert by_period["2024-01"]["release_date"] == "2024-02-22"
    assert by_period["2025-06"]["release_date"] == "2025-07-17"
    assert all(row["source_url"].startswith("https://ec.europa.eu/eurostat/") for row in rows)
    assert len({row["raw_file"] for row in rows}) == 60


def test_acquire_release_evidence_validates_calendar_pages(tmp_path: Path) -> None:
    from armilar_prices.information_set_v093 import acquire_release_evidence

    registry, pages = _calendar_registry(tmp_path)

    def opener(request, timeout=0):
        assert timeout == 5
        return _FakeResponse(request.full_url, pages[request.full_url])

    output = tmp_path / "evidence"
    summary = acquire_release_evidence(
        _policy(tmp_path), registry, output, timeout_seconds=5, opener=opener
    )
    assert summary["release_event_count"] == 3
    verify_manifest(output)
    receipts = list(csv.DictReader((output / "acquisition_receipts.csv").open(newline="", encoding="utf-8")))
    assert len(receipts) == 3
    assert {row["http_status"] for row in receipts} == {"200"}
    assert {row["content_type"] for row in receipts} == {"text/html"}
    assert all((output / row["raw_file"]).is_file() for row in receipts)
    assert all(_sha(output / row["raw_file"]) == row["raw_sha256"] for row in receipts)


def test_acquire_release_evidence_rejects_wrong_calendar_content(tmp_path: Path) -> None:
    from armilar_prices.information_set_v093 import acquire_release_evidence

    registry, pages = _calendar_registry(tmp_path)
    first_url = next(iter(pages))
    pages[first_url] = ("<html><body>Unrelated release</body></html>" + ("x" * 600)).encode("utf-8")

    def opener(request, timeout=0):
        return _FakeResponse(request.full_url, pages[request.full_url])

    with pytest.raises(InformationSetError, match="RELEASE_EVENT_NOT_FOUND"):
        acquire_release_evidence(_policy(tmp_path), registry, tmp_path / "evidence", opener=opener)


def test_acquire_release_evidence_accepts_official_dynamic_calendar_shell(tmp_path: Path) -> None:
    from armilar_prices.information_set_v093 import acquire_release_evidence

    registry, pages = _calendar_registry(tmp_path)
    shell = (
        "<!doctype html><html><head><title>Release calendar - Eurostat</title></head>"
        "<body><div id='calendar'></div><script>"
        "calendar = new FullCalendar.Calendar(calendarEl, {"
        "timeZone: 'Europe/Luxembourg',"
        "events: { url: '/eurostat/o/calendars/eventsJson' }"
        "});"
        "</script></body></html>"
        + (" official dynamic Eurostat release calendar shell" * 30)
    ).encode("utf-8")
    pages = {url: shell for url in pages}

    def opener(request, timeout=0):
        return _FakeResponse(request.full_url, pages[request.full_url])

    output = tmp_path / "evidence"
    acquire_release_evidence(_policy(tmp_path), registry, output, opener=opener)
    assert (output / "MANIFEST.sha256").is_file()


def test_seal_revalidates_calendar_evidence_content(tmp_path: Path) -> None:
    registry, pages = _calendar_registry(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    rows = list(csv.DictReader(registry.open(newline="", encoding="utf-8")))
    for row in rows:
        (evidence / row["raw_file"]).write_bytes(pages[row["source_url"]])
    (evidence / rows[1]["raw_file"]).write_bytes(
        ("<html><body>Inflation (HICP), February 2021. 18 March 2021.</body></html>" + ("x" * 600)).encode("utf-8")
    )
    with pytest.raises(InformationSetError, match="RELEASE_DATE_NOT_FOUND"):
        seal_release_snapshot(_policy(tmp_path), registry, evidence, tmp_path / "sealed")
