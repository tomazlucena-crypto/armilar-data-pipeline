"""Frozen ARMILAR v0.10.0 target-alignment and baseline protocol."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core_v0100 import BacktestProtocolError

TARGET_METRICS = ("MONTHLY_CHANGE_PCT", "YEAR_OVER_YEAR_CHANGE_PCT")
BASELINES = ("ZERO_CHANGE", "LAST_OBSERVED_TARGET", "SEASONAL_12M")


@dataclass(frozen=True, slots=True)
class ProtocolPolicy:
    policy_id: str
    policy_version: str
    target_metrics: tuple[str, ...]
    horizons_months: tuple[int, ...]
    baselines: tuple[str, ...]
    accepted_feature_roles: tuple[str, ...]
    accepted_transformations: tuple[str, ...]
    minimum_distinct_cutoffs_for_claim: int
    minimum_cases_per_cell_metric_horizon_for_claim: int
    output_decimal_places: int
    target_archive_claim_allowed: bool
    backtest_execution_claim_allowed: bool
    out_of_sample_claim_allowed: bool
    feature_selection_allowed: bool
    model_training_allowed: bool
    model_selection_allowed: bool
    arm_l_use_allowed: bool
    shadow_production_allowed: bool
    monetary_use_allowed: bool

    @classmethod
    def load(cls, path: Path) -> "ProtocolPolicy":
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BacktestProtocolError(f"cannot load v0.10.0 protocol: {path}") from exc
        required = {
            "policy_id", "policy_version", "target_metrics", "horizons_months",
            "baselines", "accepted_feature_roles", "accepted_transformations",
            "minimum_distinct_cutoffs_for_claim",
            "minimum_cases_per_cell_metric_horizon_for_claim",
            "output_decimal_places", "gates",
        }
        if set(payload) != required:
            raise BacktestProtocolError(
                f"protocol keys mismatch; missing={sorted(required-set(payload))}, extra={sorted(set(payload)-required)}"
            )
        if payload["policy_id"] != "ARMILAR_POINT_IN_TIME_BACKTEST_PROTOCOL_V0100":
            raise BacktestProtocolError("unexpected v0.10.0 policy_id")
        if payload["policy_version"] != "0.10.0":
            raise BacktestProtocolError("policy_version must be 0.10.0")
        metrics = tuple(payload["target_metrics"])
        if metrics != TARGET_METRICS:
            raise BacktestProtocolError("target_metrics must remain frozen in canonical order")
        horizons = tuple(payload["horizons_months"])
        if horizons != (0, 1, 3) or any(not isinstance(item, int) for item in horizons):
            raise BacktestProtocolError("horizons_months must be exactly [0, 1, 3]")
        baselines = tuple(payload["baselines"])
        if baselines != BASELINES:
            raise BacktestProtocolError("baselines must remain frozen in canonical order")
        roles = tuple(payload["accepted_feature_roles"])
        if roles != ("PRIMARY_RESEARCH_DRIVER", "SENSITIVITY_ONLY"):
            raise BacktestProtocolError("accepted_feature_roles mismatch")
        transformations = tuple(payload["accepted_transformations"])
        if transformations != ("LEVEL", "PERIOD_CHANGE_PCT", "YEAR_OVER_YEAR_PCT"):
            raise BacktestProtocolError("accepted_transformations mismatch")
        min_cutoffs = int(payload["minimum_distinct_cutoffs_for_claim"])
        min_cases = int(payload["minimum_cases_per_cell_metric_horizon_for_claim"])
        if min_cutoffs < 12 or min_cases < 12:
            raise BacktestProtocolError("claim thresholds must remain conservative")
        places = int(payload["output_decimal_places"])
        if places != 12:
            raise BacktestProtocolError("output_decimal_places must be 12")
        gates = payload["gates"]
        gate_names = {
            "target_archive_claim_allowed", "backtest_execution_claim_allowed",
            "out_of_sample_claim_allowed", "feature_selection_allowed",
            "model_training_allowed", "model_selection_allowed", "arm_l_use_allowed",
            "shadow_production_allowed", "monetary_use_allowed",
        }
        if not isinstance(gates, dict) or set(gates) != gate_names:
            raise BacktestProtocolError("protocol gate set mismatch")
        if any(bool(gates[name]) for name in gate_names):
            raise BacktestProtocolError("all v0.10.0 gates must remain false")
        return cls(
            policy_id=payload["policy_id"], policy_version=payload["policy_version"],
            target_metrics=metrics, horizons_months=horizons, baselines=baselines,
            accepted_feature_roles=roles, accepted_transformations=transformations,
            minimum_distinct_cutoffs_for_claim=min_cutoffs,
            minimum_cases_per_cell_metric_horizon_for_claim=min_cases,
            output_decimal_places=places,
            target_archive_claim_allowed=False,
            backtest_execution_claim_allowed=False,
            out_of_sample_claim_allowed=False,
            feature_selection_allowed=False,
            model_training_allowed=False,
            model_selection_allowed=False,
            arm_l_use_allowed=False,
            shadow_production_allowed=False,
            monetary_use_allowed=False,
        )

    @property
    def gates(self) -> dict[str, bool]:
        return {
            "target_archive_claim_allowed": False,
            "backtest_execution_claim_allowed": False,
            "out_of_sample_claim_allowed": False,
            "feature_selection_allowed": False,
            "model_training_allowed": False,
            "model_selection_allowed": False,
            "arm_l_use_allowed": False,
            "shadow_production_allowed": False,
            "monetary_use_allowed": False,
        }
