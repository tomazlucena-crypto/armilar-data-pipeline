import json
from pathlib import Path


def test_v093_production_configs_use_canonical_vertical_universe():
    root = Path(__file__).resolve().parents[1]

    canonical = json.loads(
        (root / "config" / "eurostat_headline_v090.json").read_text(encoding="utf-8")
    )["universe_id"]

    assert canonical == "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7"

    for filename in (
        "information_set_v093.json",
        "first_published_v093.json",
        "release_time_backtest_v093.json",
    ):
        payload = json.loads(
            (root / "config" / filename).read_text(encoding="utf-8")
        )
        assert payload["universe_id"] == canonical
