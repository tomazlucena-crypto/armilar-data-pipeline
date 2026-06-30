from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .builder import BuildError, build_release, load_cells, validate_complete_grid
from .models import EvidenceClass, WeightCell


class ReleaseGateError(ValueError):
    """Raised when release-gate inputs are invalid."""


@dataclass(frozen=True, slots=True)
class GlobalReleaseGatePolicy:
    policy_version: str
    minimum_validated_economies: int
    minimum_prediction_count: int
    maximum_mape: float
    minimum_interval_coverage: float
    maximum_estimated_expenditure_share: float
    maximum_fallback_e_expenditure_share: float
    require_validation_metrics_for_all_estimated_cells: bool
    require_complete_grid: bool
    research_release_allowed_when_all_gates_pass: bool
    monetary_release_allowed: bool = False

    def validate(self) -> None:
        if not self.policy_version.strip():
            raise ReleaseGateError("policy_version is required")
        if self.minimum_validated_economies < 1:
            raise ReleaseGateError("minimum_validated_economies must be positive")
        if self.minimum_prediction_count < 1:
            raise ReleaseGateError("minimum_prediction_count must be positive")
        for name, value in (
            ("maximum_mape", self.maximum_mape),
            ("minimum_interval_coverage", self.minimum_interval_coverage),
            ("maximum_estimated_expenditure_share", self.maximum_estimated_expenditure_share),
            ("maximum_fallback_e_expenditure_share", self.maximum_fallback_e_expenditure_share),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ReleaseGateError(f"{name} must be between 0 and 1")
        if self.monetary_release_allowed:
            raise ReleaseGateError("v0.7.3 cannot authorise monetary release")


def load_release_policy(path: Path) -> GlobalReleaseGatePolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        policy = GlobalReleaseGatePolicy(
            policy_version=str(payload["policy_version"]),
            minimum_validated_economies=int(payload["minimum_validated_economies"]),
            minimum_prediction_count=int(payload["minimum_prediction_count"]),
            maximum_mape=float(payload["maximum_mape"]),
            minimum_interval_coverage=float(payload["minimum_interval_coverage"]),
            maximum_estimated_expenditure_share=float(payload["maximum_estimated_expenditure_share"]),
            maximum_fallback_e_expenditure_share=float(payload["maximum_fallback_e_expenditure_share"]),
            require_validation_metrics_for_all_estimated_cells=bool(
                payload["require_validation_metrics_for_all_estimated_cells"]
            ),
            require_complete_grid=bool(payload["require_complete_grid"]),
            research_release_allowed_when_all_gates_pass=bool(
                payload["research_release_allowed_when_all_gates_pass"]
            ),
            monetary_release_allowed=bool(payload.get("monetary_release_allowed", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReleaseGateError(f"invalid global release policy: {exc}") from exc
    policy.validate()
    return policy


def load_validation_summary(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "validated_economy_count",
        "prediction_count",
        "mape",
        "interval_coverage",
        "leave_one_out",
        "result_driven_donor_selection",
        "monetary_release_allowed",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ReleaseGateError(f"validation summary missing fields: {missing}")
    return payload


def evaluate_global_release(
    cells: Sequence[WeightCell],
    validation_summary: Mapping[str, object],
    policy: GlobalReleaseGatePolicy,
) -> dict[str, object]:
    policy.validate()
    if not cells:
        raise ReleaseGateError("completed evidence grid is empty")
    for cell in cells:
        cell.validate()

    checks: list[dict[str, object]] = []

    complete_grid = True
    try:
        economies = validate_complete_grid(cells)
    except BuildError:
        economies = tuple(sorted({cell.economy_code for cell in cells}))
        complete_grid = False
    _check(checks, "complete_grid", complete_grid, policy.require_complete_grid, complete_grid)

    total = sum(cell.real_expenditure_central for cell in cells)
    if total <= 0:
        raise ReleaseGateError("central expenditure total must be positive")
    estimated = sum(
        cell.real_expenditure_central for cell in cells if cell.evidence_class.is_estimated
    ) / total
    fallback_e = sum(
        cell.real_expenditure_central
        for cell in cells
        if cell.evidence_class is EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK
    ) / total
    _threshold_max(
        checks,
        "estimated_expenditure_share",
        estimated,
        policy.maximum_estimated_expenditure_share,
    )
    _threshold_max(
        checks,
        "fallback_e_expenditure_share",
        fallback_e,
        policy.maximum_fallback_e_expenditure_share,
    )

    estimated_cells = [cell for cell in cells if cell.evidence_class.is_estimated]
    metric_coverage = (
        sum(cell.validation_mae is not None and cell.validation_bias is not None for cell in estimated_cells)
        / len(estimated_cells)
        if estimated_cells
        else 1.0
    )
    required_coverage = 1.0 if policy.require_validation_metrics_for_all_estimated_cells else 0.0
    _threshold_min(checks, "estimated_validation_metric_coverage", metric_coverage, required_coverage)

    validated_economies = _integer(validation_summary, "validated_economy_count")
    prediction_count = _integer(validation_summary, "prediction_count")
    mape = _ratio(validation_summary, "mape")
    interval_coverage = _ratio(validation_summary, "interval_coverage")
    _threshold_min(
        checks,
        "validated_economy_count",
        validated_economies,
        policy.minimum_validated_economies,
    )
    _threshold_min(checks, "prediction_count", prediction_count, policy.minimum_prediction_count)
    _threshold_max(checks, "mape", mape, policy.maximum_mape)
    _threshold_min(
        checks,
        "interval_coverage",
        interval_coverage,
        policy.minimum_interval_coverage,
    )

    leave_one_out = bool(validation_summary.get("leave_one_out"))
    result_driven = bool(validation_summary.get("result_driven_donor_selection"))
    validation_monetary = bool(validation_summary.get("monetary_release_allowed"))
    _check(checks, "leave_one_out_validation", leave_one_out, True, leave_one_out)
    _check(
        checks,
        "result_driven_donor_selection_disabled",
        not result_driven,
        True,
        not result_driven,
    )
    _check(
        checks,
        "validation_monetary_release_blocked",
        not validation_monetary,
        True,
        not validation_monetary,
    )

    all_passed = all(bool(check["passed"]) for check in checks)
    research_allowed = bool(
        all_passed and policy.research_release_allowed_when_all_gates_pass
    )
    return {
        "policy_version": policy.policy_version,
        "economy_count": len(economies),
        "cell_count": len(cells),
        "estimated_cell_count": len(estimated_cells),
        "estimated_expenditure_share": estimated,
        "fallback_e_expenditure_share": fallback_e,
        "estimated_validation_metric_coverage": metric_coverage,
        "gate_count": len(checks),
        "passed_gate_count": sum(bool(check["passed"]) for check in checks),
        "all_gates_passed": all_passed,
        "global_research_release_allowed": research_allowed,
        "monetary_release_allowed": False,
        "checks": checks,
    }


def evaluate_and_optionally_build(
    evidence_path: Path,
    validation_summary_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    build_when_eligible: bool = False,
    release_id: str = "ARM-WEIGHTS-GLOBAL-RESEARCH",
) -> dict[str, object]:
    cells = load_cells(evidence_path)
    validation_summary = load_validation_summary(validation_summary_path)
    policy = load_release_policy(policy_path)
    decision = evaluate_global_release(cells, validation_summary, policy)
    output_dir.mkdir(parents=True, exist_ok=True)
    decision["build_requested"] = bool(build_when_eligible)
    decision["global_weights_built"] = False

    if build_when_eligible and decision["global_research_release_allowed"]:
        release_dir = output_dir / "global_research_release"
        release = build_release(cells, release_dir, release_id=release_id)
        decision["global_weights_built"] = True
        decision["global_release_directory"] = str(release_dir)
        decision["global_release_manifest_sha256"] = release["manifest_sha256"]

    decision_path = output_dir / "global_release_gate.json"
    decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return decision


def _integer(payload: Mapping[str, object], name: str) -> int:
    try:
        value = int(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReleaseGateError(f"invalid integer validation metric {name}") from exc
    if value < 0:
        raise ReleaseGateError(f"validation metric {name} cannot be negative")
    return value


def _ratio(payload: Mapping[str, object], name: str) -> float:
    try:
        value = float(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReleaseGateError(f"invalid ratio validation metric {name}") from exc
    if not math.isfinite(value) or value < 0:
        raise ReleaseGateError(f"validation metric {name} must be finite and non-negative")
    return value


def _threshold_min(checks: list[dict[str, object]], name: str, actual: float | int, threshold: float | int) -> None:
    checks.append(
        {
            "gate": name,
            "operator": ">=",
            "actual": actual,
            "threshold": threshold,
            "passed": actual >= threshold,
        }
    )


def _threshold_max(checks: list[dict[str, object]], name: str, actual: float | int, threshold: float | int) -> None:
    checks.append(
        {
            "gate": name,
            "operator": "<=",
            "actual": actual,
            "threshold": threshold,
            "passed": actual <= threshold,
        }
    )


def _check(
    checks: list[dict[str, object]],
    name: str,
    actual: object,
    threshold: object,
    passed: bool,
) -> None:
    checks.append(
        {
            "gate": name,
            "operator": "is",
            "actual": actual,
            "threshold": threshold,
            "passed": bool(passed),
        }
    )
