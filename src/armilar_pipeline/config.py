from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


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
    backoff_seconds: float
    max_response_bytes: int
    per_page: int
    weight_decimal_places: int
    weight_sum_tolerance: Decimal
    identity_relative_tolerance: Decimal
    hierarchy_relative_tolerance: Decimal
    urls: dict[str, str]
    required_heading_codes: tuple[str, ...]
    forbidden_scope_prefixes: tuple[str, ...]
    aggregate_country_name_tokens: tuple[str, ...]
    imputation_detection_heading_codes: tuple[str, ...]
    publication_audit_alternative_codes: tuple[str, ...]

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
    def publication_scope_rules_path(self) -> Path:
        return self.path.parent / "publication_scope_rules.csv"


def load_config(path: str | Path) -> Step2Config:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "pipeline_version", "source_id", "reference_year",
        "expected_participating_economies", "expected_officially_imputed_economies", "user_agent",
        "timeout_seconds", "retries", "backoff_seconds", "max_response_bytes", "per_page",
        "weight_decimal_places", "weight_sum_tolerance", "identity_relative_tolerance",
        "hierarchy_relative_tolerance", "urls",
        "required_heading_codes", "forbidden_scope_prefixes", "aggregate_country_name_tokens",
        "imputation_detection_heading_codes", "publication_audit_alternative_codes",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"Missing configuration keys: {', '.join(missing)}")
    if str(raw["source_id"]) != "90":
        raise ValueError("Step 2 is pinned to World Bank source 90 (ICP 2021)")
    if int(raw["reference_year"]) != 2021:
        raise ValueError("Research vintage must remain ICP 2021")
    return Step2Config(
        path=config_path,
        schema_version=str(raw["schema_version"]),
        pipeline_version=str(raw["pipeline_version"]),
        source_id=str(raw["source_id"]),
        reference_year=int(raw["reference_year"]),
        expected_participating_economies=int(raw["expected_participating_economies"]),
        expected_officially_imputed_economies=int(raw["expected_officially_imputed_economies"]),
        user_agent=str(raw["user_agent"]),
        timeout_seconds=int(raw["timeout_seconds"]),
        retries=int(raw["retries"]),
        backoff_seconds=float(raw["backoff_seconds"]),
        max_response_bytes=int(raw["max_response_bytes"]),
        per_page=int(raw["per_page"]),
        weight_decimal_places=int(raw["weight_decimal_places"]),
        weight_sum_tolerance=Decimal(str(raw["weight_sum_tolerance"])),
        identity_relative_tolerance=Decimal(str(raw["identity_relative_tolerance"])),
        hierarchy_relative_tolerance=Decimal(str(raw["hierarchy_relative_tolerance"])),
        urls={str(k): str(v) for k, v in raw["urls"].items()},
        required_heading_codes=tuple(str(v) for v in raw["required_heading_codes"]),
        forbidden_scope_prefixes=tuple(str(v) for v in raw["forbidden_scope_prefixes"]),
        aggregate_country_name_tokens=tuple(str(v).lower() for v in raw["aggregate_country_name_tokens"]),
        imputation_detection_heading_codes=tuple(str(v) for v in raw["imputation_detection_heading_codes"]),
        publication_audit_alternative_codes=tuple(str(v) for v in raw["publication_audit_alternative_codes"]),
    )
