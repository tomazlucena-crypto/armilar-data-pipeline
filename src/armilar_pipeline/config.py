from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .version import build_user_agent, installed_version


@dataclass(frozen=True)
class Step2Config:
    path: Path
    schema_version: str
    pipeline_version: str
    source_id: str
    reference_year: int
    expected_participating_economies: int
    expected_officially_imputed_economies: int
    user_agent: str
    timeout_seconds: int
    retries: int
    source_probe_max_workers: int
    backoff_seconds: float
    max_response_bytes: int
    per_page: int
    weight_decimal_places: int
    weight_sum_tolerance: Decimal
    identity_relative_tolerance: Decimal
    hierarchy_relative_tolerance: Decimal
    source_conflict_relative_tolerance: Decimal
    urls: dict[str, str]
    required_heading_codes: tuple[str, ...]
    classification_required_heading_codes: tuple[str, ...]
    aggregate_country_name_tokens: tuple[str, ...]
    aggregate_country_codes: tuple[str, ...]
    imputation_detection_heading_codes: tuple[str, ...]
    direct_ppp_heading_by_category: dict[str, str]
    proxy_ppp_heading_by_category: dict[str, str]
    nominal_source_priority: tuple[str, ...]
    minimum_complete_participating_economies: int
    exclude_officially_imputed_from_research_universe: bool

    @property
    def repo_root(self) -> Path:
        return self.path.parent.parent

    @property
    def headings_path(self) -> Path:
        return self.path.parent / "icp_headings_to_armilar.csv"

    @property
    def categories_path(self) -> Path:
        return self.path.parent / "armilar_categories.csv"

    @property
    def country_aliases_path(self) -> Path:
        return self.path.parent / "country_name_aliases.csv"

    @property
    def external_code_crosswalk_path(self) -> Path:
        return self.path.parent / "external_economy_codes.csv"

    @property
    def methodology_policy_path(self) -> Path:
        return self.path.parent / "methodology_policy.json"

    @property
    def source_probe_candidates_path(self) -> Path:
        return self.path.parent / "source_probe_candidates.csv"

    @property
    def proxy_ppp_benchmarks_path(self) -> Path:
        return self.path.parent / "proxy_ppp_benchmarks.csv"


def load_config(path: str | Path) -> Step2Config:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "source_id", "reference_year",
        "expected_participating_economies", "expected_officially_imputed_economies",
        "timeout_seconds", "retries", "backoff_seconds", "max_response_bytes", "per_page",
        "weight_decimal_places", "weight_sum_tolerance", "identity_relative_tolerance",
        "hierarchy_relative_tolerance", "source_conflict_relative_tolerance", "urls",
        "required_heading_codes", "classification_required_heading_codes", "aggregate_country_name_tokens", "aggregate_country_codes",
        "imputation_detection_heading_codes", "direct_ppp_heading_by_category",
        "proxy_ppp_heading_by_category", "nominal_source_priority",
        "minimum_complete_participating_economies",
        "exclude_officially_imputed_from_research_universe",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"Missing configuration keys: {', '.join(missing)}")
    if str(raw["source_id"]) != "90":
        raise ValueError("Step 2 is pinned to World Bank source 90 (ICP 2021)")
    if int(raw["reference_year"]) != 2021:
        raise ValueError("Research vintage must remain ICP 2021")
    direct = {str(k): str(v) for k, v in raw["direct_ppp_heading_by_category"].items()}
    proxy = {str(k): str(v) for k, v in raw["proxy_ppp_heading_by_category"].items()}
    if set(direct) | set(proxy) != {f"CP{i:02d}" for i in range(1, 13)}:
        raise ValueError("Direct and proxy PPP maps must cover exactly CP01-CP12")
    if set(direct) & set(proxy):
        raise ValueError("A category cannot be both direct and proxy PPP")
    return Step2Config(
        path=config_path,
        schema_version=str(raw["schema_version"]),
        pipeline_version=installed_version(),
        source_id=str(raw["source_id"]),
        reference_year=int(raw["reference_year"]),
        expected_participating_economies=int(raw["expected_participating_economies"]),
        expected_officially_imputed_economies=int(raw["expected_officially_imputed_economies"]),
        user_agent=build_user_agent(),
        timeout_seconds=int(raw["timeout_seconds"]),
        retries=int(raw["retries"]),
        source_probe_max_workers=max(1, int(raw.get("source_probe_max_workers", 5))),
        backoff_seconds=float(raw["backoff_seconds"]),
        max_response_bytes=int(raw["max_response_bytes"]),
        per_page=int(raw["per_page"]),
        weight_decimal_places=int(raw["weight_decimal_places"]),
        weight_sum_tolerance=Decimal(str(raw["weight_sum_tolerance"])),
        identity_relative_tolerance=Decimal(str(raw["identity_relative_tolerance"])),
        hierarchy_relative_tolerance=Decimal(str(raw["hierarchy_relative_tolerance"])),
        source_conflict_relative_tolerance=Decimal(str(raw["source_conflict_relative_tolerance"])),
        urls={str(k): str(v) for k, v in raw["urls"].items()},
        required_heading_codes=tuple(str(v) for v in raw["required_heading_codes"]),
        classification_required_heading_codes=tuple(str(v) for v in raw["classification_required_heading_codes"]),
        aggregate_country_name_tokens=tuple(str(v).lower() for v in raw["aggregate_country_name_tokens"]),
        aggregate_country_codes=tuple(str(v).upper() for v in raw["aggregate_country_codes"]),
        imputation_detection_heading_codes=tuple(str(v) for v in raw["imputation_detection_heading_codes"]),
        direct_ppp_heading_by_category=direct,
        proxy_ppp_heading_by_category=proxy,
        nominal_source_priority=tuple(str(v) for v in raw["nominal_source_priority"]),
        minimum_complete_participating_economies=int(raw["minimum_complete_participating_economies"]),
        exclude_officially_imputed_from_research_universe=bool(raw["exclude_officially_imputed_from_research_universe"]),
    )
