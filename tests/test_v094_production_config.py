from __future__ import annotations

import json
import tomllib
from pathlib import Path


def test_v094_production_policy_uses_canonical_universe_and_closed_gates() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "config" / "pre_release_backtest_v094.json").read_text(encoding="utf-8")
    )
    assert payload["universe_id"] == "ARM-EUROSTAT-HICP-FIVE-ECONOMY-V0.8.7"
    assert payload["pre_release_forecast"] is True
    assert payload["target_period_values_allowed"] is False
    assert payload["target_period_donors_allowed"] is False
    assert payload["future_period_source_values_allowed"] is False
    assert payload["historical_as_of_revisions_available"] is False
    assert payload["model_promotion_allowed"] is False
    assert payload["research_release_allowed"] is False
    assert payload["monetary_release_allowed"] is False


def test_v094_pyproject_version_and_entrypoint() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.9.4"
    assert payload["project"]["scripts"]["armilar-pre-release-backtest-v094"] == (
        "armilar_prices.pre_release_backtest_v094:main"
    )
