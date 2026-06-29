import json
from pathlib import Path


def test_global_weight_policy_separates_core_and_global() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root / "config" / "global_weight_policy.json").read_text(encoding="utf-8"))
    assert policy["core_construction"]["world_claim_allowed"] is False
    assert policy["global_construction"]["requires_complete_economy_category_grid"] is True
    assert policy["global_construction"]["requires_uncertainty_for_estimates"] is True
    assert policy["monetary_release_allowed"] is False
    assert len(policy["canonical_categories"]) == 12


def test_reuse_registry_exists_and_has_decisions() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "config" / "component_registry.yaml").read_text(encoding="utf-8")
    for token in ("sdmx1", "pysdmx", "DBnomics", "DuckDB", "Pandera", "Hypothesis", "FastAPI", "Prefect", "MLflow"):
        assert token in text
    assert "decision:" in text
    assert "REVIEW_PER_FETCHER" in text
