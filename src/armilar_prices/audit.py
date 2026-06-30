from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .completion import (
    CompletionPolicy,
    PriceCompletionError,
    WeightCell,
    _metric_summary,
    build_global_indices,
    complete_price_grid,
    load_observations,
    load_policy,
    load_profiles,
    load_weights,
    validate_leave_one_out,
)

getcontext().prec = 40

AUDIT_VERSION = "price-model-audit-v0.8.5"
REQUIRED_COMPLETION_FILES = {
    "monthly_price_cells_complete.csv",
    "monthly_price_uncertainty.csv",
    "price_imputation_audit.csv",
    "price_validation_by_category.csv",
    "price_validation_by_region.csv",
    "price_validation_by_horizon.csv",
    "price_validation_by_fallback.csv",
    "price_validation_summary.json",
    "monthly_global_experimental_index.csv",
    "monthly_global_index_uncertainty.csv",
    "price_evidence_coverage.csv",
    "price_completion_summary.json",
}


class PriceModelAuditError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationGatePolicy:
    policy_version: str
    status: str
    ratified: bool
    required_completion_methodology: str
    minimum_history_months: int
    minimum_validation_observations: int
    minimum_validation_per_category: int
    minimum_validation_per_region: int
    maximum_mae: Decimal
    maximum_mape_percent: Decimal
    maximum_rmse: Decimal
    maximum_absolute_bias: Decimal
    minimum_interval_coverage: Decimal
    maximum_interval_coverage: Decimal
    minimum_improvement_vs_headline_percent: Decimal
    maximum_p3_world_weight: Decimal
    maximum_p5_world_weight: Decimal
    minimum_direct_world_weight: Decimal
    maximum_sensitivity_index_shift_bps: Decimal
    maximum_sensitivity_mae_degradation_percent: Decimal
    research_release_allowed: bool
    monetary_release_allowed: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ValidationGatePolicy":
        def dec(name: str) -> Decimal:
            try:
                value = Decimal(str(payload[name]))
            except (KeyError, InvalidOperation, TypeError) as exc:
                raise PriceModelAuditError(f"invalid gate policy field {name}") from exc
            if not value.is_finite():
                raise PriceModelAuditError(f"non-finite gate policy field {name}")
            return value

        try:
            policy = cls(
                policy_version=str(payload["policy_version"]).strip(),
                status=str(payload["status"]).strip(),
                ratified=(
                    payload.get("ratified", False)
                    if isinstance(payload.get("ratified", False), bool)
                    else (_ for _ in ()).throw(
                        PriceModelAuditError("ratified must be a JSON boolean")
                    )
                ),
                required_completion_methodology=str(
                    payload.get("required_completion_methodology", "0.8.4")
                ).strip(),
                minimum_history_months=int(payload["minimum_history_months"]),
                minimum_validation_observations=int(
                    payload["minimum_validation_observations"]
                ),
                minimum_validation_per_category=int(
                    payload["minimum_validation_per_category"]
                ),
                minimum_validation_per_region=int(
                    payload["minimum_validation_per_region"]
                ),
                maximum_mae=dec("maximum_mae"),
                maximum_mape_percent=dec("maximum_mape_percent"),
                maximum_rmse=dec("maximum_rmse"),
                maximum_absolute_bias=dec("maximum_absolute_bias"),
                minimum_interval_coverage=dec("minimum_interval_coverage"),
                maximum_interval_coverage=dec("maximum_interval_coverage"),
                minimum_improvement_vs_headline_percent=dec(
                    "minimum_improvement_vs_headline_percent"
                ),
                maximum_p3_world_weight=dec("maximum_p3_world_weight"),
                maximum_p5_world_weight=dec("maximum_p5_world_weight"),
                minimum_direct_world_weight=dec("minimum_direct_world_weight"),
                maximum_sensitivity_index_shift_bps=dec(
                    "maximum_sensitivity_index_shift_bps"
                ),
                maximum_sensitivity_mae_degradation_percent=dec(
                    "maximum_sensitivity_mae_degradation_percent"
                ),
                research_release_allowed=bool(
                    payload.get("research_release_allowed", False)
                ),
                monetary_release_allowed=bool(
                    payload.get("monetary_release_allowed", False)
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceModelAuditError(f"invalid validation gate policy: {exc}") from exc

        if not policy.policy_version or not policy.status:
            raise PriceModelAuditError("gate policy version and status are required")
        if policy.minimum_history_months < 2:
            raise PriceModelAuditError("minimum_history_months must be at least two")
        for name, value in (
            ("minimum_validation_observations", policy.minimum_validation_observations),
            ("minimum_validation_per_category", policy.minimum_validation_per_category),
            ("minimum_validation_per_region", policy.minimum_validation_per_region),
        ):
            if value < 1:
                raise PriceModelAuditError(f"{name} must be positive")
        for name, value in (
            ("maximum_mae", policy.maximum_mae),
            ("maximum_mape_percent", policy.maximum_mape_percent),
            ("maximum_rmse", policy.maximum_rmse),
            ("maximum_absolute_bias", policy.maximum_absolute_bias),
            ("maximum_p3_world_weight", policy.maximum_p3_world_weight),
            ("maximum_p5_world_weight", policy.maximum_p5_world_weight),
            ("minimum_direct_world_weight", policy.minimum_direct_world_weight),
            (
                "maximum_sensitivity_index_shift_bps",
                policy.maximum_sensitivity_index_shift_bps,
            ),
            (
                "maximum_sensitivity_mae_degradation_percent",
                policy.maximum_sensitivity_mae_degradation_percent,
            ),
        ):
            if value < 0:
                raise PriceModelAuditError(f"{name} cannot be negative")
        if not (
            Decimal("0")
            <= policy.minimum_interval_coverage
            <= policy.maximum_interval_coverage
            <= Decimal("1")
        ):
            raise PriceModelAuditError("invalid interval coverage range")
        if policy.maximum_p3_world_weight > 1 or policy.maximum_p5_world_weight > 1:
            raise PriceModelAuditError("fallback weight limits cannot exceed one")
        if policy.minimum_direct_world_weight > 1:
            raise PriceModelAuditError("minimum direct weight cannot exceed one")
        if policy.research_release_allowed or policy.monetary_release_allowed:
            raise PriceModelAuditError(
                "v0.8.5 gate policy cannot authorise research or monetary release"
            )
        return policy


def load_gate_policy(path: Path) -> ValidationGatePolicy:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriceModelAuditError(f"cannot read gate policy: {exc}") from exc
    if not isinstance(payload, dict):
        raise PriceModelAuditError("gate policy must be a JSON object")
    return ValidationGatePolicy.from_mapping(payload)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(output_dir: Path) -> dict[str, str]:
    manifest_path = output_dir / "MANIFEST.sha256"
    if not manifest_path.exists():
        raise PriceModelAuditError("completion manifest is missing")
    entries: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, filename = line.split("  ", 1)
        except ValueError as exc:
            raise PriceModelAuditError("invalid completion manifest line") from exc
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise PriceModelAuditError(f"invalid manifest digest for {filename}")
        if filename in entries:
            raise PriceModelAuditError(f"duplicate manifest entry: {filename}")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise PriceModelAuditError(f"unsafe manifest filename: {filename}")
        entries[filename] = digest
    missing = REQUIRED_COMPLETION_FILES - set(entries)
    if missing:
        raise PriceModelAuditError(
            f"completion manifest missing required files: {sorted(missing)}"
        )
    for filename, expected in entries.items():
        path = output_dir / filename
        if not path.is_file():
            raise PriceModelAuditError(f"manifest file is missing: {filename}")
        actual = _sha256(path)
        if actual != expected:
            raise PriceModelAuditError(f"manifest hash mismatch: {filename}")
    return entries


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriceModelAuditError(f"cannot read JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise PriceModelAuditError(f"{path.name} must contain a JSON object")
    return value


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise PriceModelAuditError(f"invalid decimal for {label}: {value!r}") from exc
    if not result.is_finite():
        raise PriceModelAuditError(f"non-finite decimal for {label}")
    return result


def verify_completion_contract(
    completion_dir: Path,
    policy: ValidationGatePolicy,
    input_paths: Mapping[str, Path],
) -> tuple[dict[str, object], dict[str, object]]:
    summary = _load_json(completion_dir / "price_completion_summary.json")
    validation_summary = _load_json(
        completion_dir / "price_validation_summary.json"
    )
    if str(summary.get("methodology_version")) != policy.required_completion_methodology:
        raise PriceModelAuditError("unexpected completion methodology version")
    if summary.get("research_release_allowed") is not False:
        raise PriceModelAuditError("completion research release flag is not false")
    if summary.get("monetary_release_allowed") is not False:
        raise PriceModelAuditError("completion monetary release flag is not false")
    if summary.get("input_provenance_complete") is not True:
        raise PriceModelAuditError("completion input provenance is incomplete")
    if summary.get("methodology_changes_allowed_silently") is not False:
        raise PriceModelAuditError("completion allows silent methodology changes")
    if validation_summary.get("research_release_allowed") is not False:
        raise PriceModelAuditError("validation research release flag is not false")
    if validation_summary.get("monetary_release_allowed") is not False:
        raise PriceModelAuditError("validation monetary release flag is not false")
    if validation_summary.get("donor_selection_uses_hidden_target_value") is not False:
        raise PriceModelAuditError("validation donor selection uses hidden target values")
    if validation_summary.get("future_period_observations_allowed") is not False:
        raise PriceModelAuditError("validation allows future observations")

    stored = summary.get("input_hashes")
    if not isinstance(stored, dict):
        raise PriceModelAuditError("completion input hashes are missing")
    if (
        "classification_mapping_sha256" in stored
        and "classification_mapping_sha256" not in input_paths
    ):
        raise PriceModelAuditError(
            "completion used a classification mapping but no mapping was supplied"
        )
    for name, path in input_paths.items():
        expected = stored.get(name)
        if expected is None:
            if name == "classification_mapping_sha256":
                continue
            raise PriceModelAuditError(f"completion input hash is missing: {name}")
        if str(expected) != _sha256(path):
            raise PriceModelAuditError(f"completion input hash mismatch: {name}")
    return summary, validation_summary


def _key(row: Mapping[str, object]) -> tuple[str, str, str, int]:
    return (
        str(row["economy_code"]),
        str(row["category_code"]),
        str(row["end_period"]),
        int(row["horizon_months"]),
    )


def _validation_for_mode(
    mode: str,
    weights: Sequence[WeightCell],
    profiles: Mapping[str, object],
    observations: Sequence[object],
    reference_period: str,
    policy: CompletionPolicy,
) -> list[dict[str, object]]:
    if mode == "CANDIDATE_SELECTED_PATTERN":
        configured = policy
    elif mode == "B0_TARGET_HEADLINE_ONLY":
        configured = replace(
            policy,
            minimum_region_donors=1000000,
            minimum_world_donors=1000000,
            maximum_donors=1000000,
        )
    elif mode == "B1_WORLD_PATTERN":
        configured = replace(
            policy,
            minimum_region_donors=1000000,
            maximum_donors=1000000,
        )
    else:
        raise PriceModelAuditError(f"unknown validation mode: {mode}")
    return validate_leave_one_out(
        weights, profiles, observations, reference_period, configured
    )


def build_baseline_comparison(
    weights: Sequence[WeightCell],
    profiles: Mapping[str, object],
    observations: Sequence[object],
    reference_period: str,
    completion_policy: CompletionPolicy,
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    models = (
        "CANDIDATE_SELECTED_PATTERN",
        "B0_TARGET_HEADLINE_ONLY",
        "B1_WORLD_PATTERN",
    )
    validation_by_model = {
        model: _validation_for_mode(
            model,
            weights,
            profiles,
            observations,
            reference_period,
            completion_policy,
        )
        for model in models
    }
    common_keys = set.intersection(
        *({ _key(row) for row in validation_by_model[model] } for model in models)
    )
    if not common_keys:
        raise PriceModelAuditError("baseline models have no common validation sample")
    aligned = {
        model: [row for row in validation_by_model[model] if _key(row) in common_keys]
        for model in models
    }
    summaries = {
        model: _metric_summary(rows) for model, rows in aligned.items()
    }
    candidate_mae = _decimal(summaries[models[0]]["mae"], "candidate mae")
    rows: list[dict[str, object]] = []
    for model in models:
        metrics = summaries[model]
        mae = _decimal(metrics["mae"], f"{model} mae") if metrics["observation_count"] else Decimal("0")
        if model == models[0]:
            improvement = Decimal("0")
        elif mae == 0:
            improvement = Decimal("0") if candidate_mae == 0 else Decimal("-100")
        else:
            improvement = (mae - candidate_mae) / mae * Decimal("100")
        rows.append({
            "model_id": model,
            **metrics,
            "candidate_mae_improvement_percent": improvement,
        })
    return rows, summaries


def _scenario_policies(policy: CompletionPolicy) -> list[tuple[str, CompletionPolicy]]:
    scenarios: list[tuple[str, CompletionPolicy]] = [("BASELINE", policy)]
    if policy.minimum_region_donors > 1:
        scenarios.append((
            "REGION_DONORS_MINUS_ONE",
            replace(policy, minimum_region_donors=policy.minimum_region_donors - 1),
        ))
    scenarios.append((
        "REGION_DONORS_PLUS_ONE",
        replace(
            policy,
            minimum_region_donors=policy.minimum_region_donors + 1,
            maximum_donors=max(policy.maximum_donors, policy.minimum_region_donors + 1),
        ),
    ))
    if policy.minimum_world_donors > 1:
        scenarios.append((
            "WORLD_DONORS_MINUS_ONE",
            replace(policy, minimum_world_donors=policy.minimum_world_donors - 1),
        ))
    scenarios.append((
        "WORLD_DONORS_PLUS_ONE",
        replace(
            policy,
            minimum_world_donors=policy.minimum_world_donors + 1,
            maximum_donors=max(policy.maximum_donors, policy.minimum_world_donors + 1),
        ),
    ))
    reduced_max = max(
        policy.minimum_region_donors,
        policy.minimum_world_donors,
        min(policy.maximum_donors, 10),
    )
    if reduced_max != policy.maximum_donors:
        scenarios.append((
            "MAX_DONORS_REDUCED",
            replace(policy, maximum_donors=reduced_max),
        ))
    return scenarios


def build_sensitivity_audit(
    weights: Sequence[WeightCell],
    profiles: Mapping[str, object],
    observations: Sequence[object],
    reference_period: str,
    completion_policy: CompletionPolicy,
) -> list[dict[str, object]]:
    scenario_outputs: dict[str, tuple[list[dict[str, object]], dict[str, object]]] = {}
    for scenario_id, scenario_policy in _scenario_policies(completion_policy):
        completed, _, _ = complete_price_grid(
            weights, profiles, observations, reference_period, scenario_policy
        )
        index_rows, _, _ = build_global_indices(completed, weights)
        validation = validate_leave_one_out(
            weights, profiles, observations, reference_period, scenario_policy
        )
        scenario_outputs[scenario_id] = (index_rows, validation)

    common_keys = set.intersection(
        *(
            { _key(row) for row in validation_rows }
            for _, validation_rows in scenario_outputs.values()
        )
    )
    if not common_keys:
        raise PriceModelAuditError("sensitivity scenarios have no common validation sample")
    base_indices = {
        str(row["period"]): _decimal(row["index_value"], "baseline index")
        for row in scenario_outputs["BASELINE"][0]
    }
    base_metrics = _metric_summary([
        row for row in scenario_outputs["BASELINE"][1] if _key(row) in common_keys
    ])
    base_mae = _decimal(base_metrics["mae"], "baseline sensitivity mae")
    rows: list[dict[str, object]] = []
    for scenario_id, (indices, validation_rows) in scenario_outputs.items():
        metrics = _metric_summary([
            row for row in validation_rows if _key(row) in common_keys
        ])
        shifts = []
        for row in indices:
            period = str(row["period"])
            candidate = _decimal(row["index_value"], "scenario index")
            baseline = base_indices[period]
            if baseline == 0:
                raise PriceModelAuditError("baseline index cannot be zero")
            shifts.append(abs(candidate / baseline - Decimal("1")) * Decimal("10000"))
        mae = _decimal(metrics["mae"], f"{scenario_id} mae")
        if base_mae == 0:
            degradation = Decimal("0") if mae == 0 else Decimal("Infinity")
        else:
            degradation = (mae - base_mae) / base_mae * Decimal("100")
        rows.append({
            "scenario_id": scenario_id,
            "period_count": len(indices),
            "validation_observation_count": metrics["observation_count"],
            "mae": mae,
            "mape_percent": metrics["mape_percent"],
            "rmse": metrics["rmse"],
            "bias": metrics["bias"],
            "interval_coverage": metrics["interval_coverage"],
            "maximum_absolute_index_shift_bps": max(shifts, default=Decimal("0")),
            "mae_degradation_percent": degradation,
        })
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise PriceModelAuditError(f"CSV has no header: {path.name}")
        return list(reader)


def _group_minimum(rows: Sequence[Mapping[str, object]], field: str) -> int:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row[field])] += 1
    return min(counts.values()) if counts else 0


def _coverage_metrics(completion_dir: Path) -> dict[str, Decimal]:
    rows = _read_csv(completion_dir / "price_evidence_coverage.csv")
    by_period: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for row in rows:
        by_period[row["period"]][row["evidence_class"]] += _decimal(
            row["world_weight"], "coverage world weight"
        )
    if not by_period:
        raise PriceModelAuditError("evidence coverage is empty")
    direct = []
    p3 = []
    p5 = []
    for period, values in by_period.items():
        total = sum(values.values(), Decimal("0"))
        if abs(total - Decimal("1")) > Decimal("0.000000000001"):
            raise PriceModelAuditError(f"coverage does not sum to one: {period}")
        direct.append(
            values["P1_OFFICIAL_CATEGORY"]
            + values["P2_OFFICIAL_COMPATIBLE_AGGREGATE"]
        )
        p3.append(values["P3_OFFICIAL_HEADLINE"])
        p5.append(values["P5_WORLD_PATTERN"])
    return {
        "minimum_direct_world_weight": min(direct),
        "maximum_p3_world_weight": max(p3),
        "maximum_p5_world_weight": max(p5),
    }


def _gate(
    gate_id: str,
    observed: object,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "gate_id": gate_id,
        "observed": observed,
        "threshold": threshold,
        "passed": passed,
        "reason": reason,
    }


def evaluate_gates(
    gate_policy: ValidationGatePolicy,
    validation_rows: Sequence[Mapping[str, object]],
    baseline_rows: Sequence[Mapping[str, object]],
    sensitivity_rows: Sequence[Mapping[str, object]],
    coverage: Mapping[str, Decimal],
    history_months: int,
) -> list[dict[str, object]]:
    overall = _metric_summary(validation_rows)
    if not overall["observation_count"]:
        raise PriceModelAuditError("validation produced no observations")
    candidate = next(
        row for row in baseline_rows if row["model_id"] == "CANDIDATE_SELECTED_PATTERN"
    )
    headline = next(
        row for row in baseline_rows if row["model_id"] == "B0_TARGET_HEADLINE_ONLY"
    )
    candidate_mae = _decimal(candidate["mae"], "candidate mae")
    headline_mae = _decimal(headline["mae"], "headline mae")
    improvement = (
        Decimal("0")
        if headline_mae == 0 and candidate_mae == 0
        else Decimal("-100")
        if headline_mae == 0
        else (headline_mae - candidate_mae) / headline_mae * Decimal("100")
    )
    non_base = [row for row in sensitivity_rows if row["scenario_id"] != "BASELINE"]
    max_shift = max(
        (_decimal(row["maximum_absolute_index_shift_bps"], "sensitivity shift") for row in non_base),
        default=Decimal("0"),
    )
    max_degradation = max(
        (_decimal(row["mae_degradation_percent"], "sensitivity degradation") for row in non_base),
        default=Decimal("0"),
    )
    mae = _decimal(overall["mae"], "overall mae")
    mape = _decimal(overall["mape_percent"], "overall mape")
    rmse = _decimal(overall["rmse"], "overall rmse")
    bias = abs(_decimal(overall["bias"], "overall bias"))
    interval_coverage = _decimal(
        overall["interval_coverage"], "overall interval coverage"
    )
    minimum_category = _group_minimum(validation_rows, "category_code")
    minimum_region = _group_minimum(validation_rows, "region")

    gates = [
        _gate(
            "HISTORY_LENGTH",
            history_months,
            gate_policy.minimum_history_months,
            history_months >= gate_policy.minimum_history_months,
            "complete fixed-universe monthly history",
        ),
        _gate(
            "VALIDATION_OBSERVATIONS",
            overall["observation_count"],
            gate_policy.minimum_validation_observations,
            int(overall["observation_count"]) >= gate_policy.minimum_validation_observations,
            "overall leave-one-out validation sample",
        ),
        _gate(
            "VALIDATION_PER_CATEGORY",
            minimum_category,
            gate_policy.minimum_validation_per_category,
            minimum_category >= gate_policy.minimum_validation_per_category,
            "worst category validation sample",
        ),
        _gate(
            "VALIDATION_PER_REGION",
            minimum_region,
            gate_policy.minimum_validation_per_region,
            minimum_region >= gate_policy.minimum_validation_per_region,
            "worst region validation sample",
        ),
        _gate("MAXIMUM_MAE", mae, gate_policy.maximum_mae, mae <= gate_policy.maximum_mae, "overall MAE"),
        _gate("MAXIMUM_MAPE", mape, gate_policy.maximum_mape_percent, mape <= gate_policy.maximum_mape_percent, "overall MAPE percent"),
        _gate("MAXIMUM_RMSE", rmse, gate_policy.maximum_rmse, rmse <= gate_policy.maximum_rmse, "overall RMSE"),
        _gate("MAXIMUM_ABSOLUTE_BIAS", bias, gate_policy.maximum_absolute_bias, bias <= gate_policy.maximum_absolute_bias, "absolute overall bias"),
        _gate(
            "INTERVAL_COVERAGE_MINIMUM",
            interval_coverage,
            gate_policy.minimum_interval_coverage,
            interval_coverage >= gate_policy.minimum_interval_coverage,
            "experimental interval coverage lower gate",
        ),
        _gate(
            "INTERVAL_COVERAGE_MAXIMUM",
            interval_coverage,
            gate_policy.maximum_interval_coverage,
            interval_coverage <= gate_policy.maximum_interval_coverage,
            "experimental interval coverage upper gate",
        ),
        _gate(
            "IMPROVEMENT_VS_HEADLINE",
            improvement,
            gate_policy.minimum_improvement_vs_headline_percent,
            improvement >= gate_policy.minimum_improvement_vs_headline_percent,
            "candidate MAE improvement over target-headline baseline",
        ),
        _gate(
            "MINIMUM_DIRECT_WORLD_WEIGHT",
            coverage["minimum_direct_world_weight"],
            gate_policy.minimum_direct_world_weight,
            coverage["minimum_direct_world_weight"] >= gate_policy.minimum_direct_world_weight,
            "worst-period P1 plus P2 world weight",
        ),
        _gate(
            "MAXIMUM_P3_WORLD_WEIGHT",
            coverage["maximum_p3_world_weight"],
            gate_policy.maximum_p3_world_weight,
            coverage["maximum_p3_world_weight"] <= gate_policy.maximum_p3_world_weight,
            "worst-period headline-only fallback weight",
        ),
        _gate(
            "MAXIMUM_P5_WORLD_WEIGHT",
            coverage["maximum_p5_world_weight"],
            gate_policy.maximum_p5_world_weight,
            coverage["maximum_p5_world_weight"] <= gate_policy.maximum_p5_world_weight,
            "worst-period world-pattern fallback weight",
        ),
        _gate(
            "SENSITIVITY_INDEX_SHIFT",
            max_shift,
            gate_policy.maximum_sensitivity_index_shift_bps,
            max_shift <= gate_policy.maximum_sensitivity_index_shift_bps,
            "maximum index shift under predeclared policy perturbations",
        ),
        _gate(
            "SENSITIVITY_MAE_DEGRADATION",
            max_degradation,
            gate_policy.maximum_sensitivity_mae_degradation_percent,
            max_degradation <= gate_policy.maximum_sensitivity_mae_degradation_percent,
            "maximum MAE degradation under predeclared policy perturbations",
        ),
        _gate(
            "POLICY_RATIFICATION",
            gate_policy.ratified,
            True,
            gate_policy.ratified,
            "formal ratification is required after empirical calibration",
        ),
    ]
    return gates


def _format(value: object) -> str:
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        text = format(value.quantize(Decimal("0.000000000001")), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format(row.get(field, "")) for field in fieldnames})


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return _format(value)
    raise TypeError(type(value).__name__)


def _write_manifest(output_dir: Path, filenames: Sequence[str]) -> None:
    lines = [
        f"{_sha256(output_dir / filename)}  {filename}"
        for filename in sorted(filenames)
    ]
    (output_dir / "MANIFEST.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def audit_global_price_model(
    weights_path: Path,
    observations_path: Path,
    profiles_path: Path,
    completion_policy_path: Path,
    completion_output_dir: Path,
    gate_policy_path: Path,
    reference_period: str,
    output_dir: Path,
    mapping_path: Path | None = None,
) -> dict[str, object]:
    manifest = verify_manifest(completion_output_dir)
    gate_policy = load_gate_policy(gate_policy_path)
    input_paths = {
        "weights_global_sha256": weights_path,
        "observed_prices_sha256": observations_path,
        "economy_profiles_sha256": profiles_path,
        "completion_policy_sha256": completion_policy_path,
    }
    if mapping_path is not None:
        input_paths["classification_mapping_sha256"] = mapping_path
    completion_summary, _ = verify_completion_contract(
        completion_output_dir, gate_policy, input_paths
    )

    completion_policy = load_policy(completion_policy_path)
    weights = load_weights(
        weights_path, completion_policy.required_categories, mapping_path
    )
    economies = sorted({row.economy_code for row in weights})
    profiles = load_profiles(profiles_path, economies)
    observations = load_observations(
        observations_path, completion_policy.required_categories, economies
    )
    validation_rows = validate_leave_one_out(
        weights, profiles, observations, reference_period, completion_policy
    )
    if not validation_rows:
        raise PriceModelAuditError("validation produced no observations")
    baseline_rows, _ = build_baseline_comparison(
        weights, profiles, observations, reference_period, completion_policy
    )
    sensitivity_rows = build_sensitivity_audit(
        weights, profiles, observations, reference_period, completion_policy
    )
    coverage = _coverage_metrics(completion_output_dir)
    history_months = int(completion_summary.get("index_period_count", 0))
    gates = evaluate_gates(
        gate_policy,
        validation_rows,
        baseline_rows,
        sensitivity_rows,
        coverage,
        history_months,
    )
    empirical_gate_passed = all(
        bool(row["passed"])
        for row in gates
        if row["gate_id"] != "POLICY_RATIFICATION"
    )
    release_gate_passed = empirical_gate_passed and gate_policy.ratified

    output_dir.mkdir(parents=True, exist_ok=True)
    detail_fields = list(validation_rows[0].keys())
    _write_csv(output_dir / "price_validation_detail.csv", detail_fields, validation_rows)
    _write_csv(
        output_dir / "price_baseline_comparison.csv",
        list(baseline_rows[0].keys()),
        baseline_rows,
    )
    _write_csv(
        output_dir / "price_sensitivity_audit.csv",
        list(sensitivity_rows[0].keys()),
        sensitivity_rows,
    )
    _write_csv(
        output_dir / "price_model_gate_results.csv",
        list(gates[0].keys()),
        gates,
    )
    summary = {
        "audit_version": AUDIT_VERSION,
        "gate_policy_version": gate_policy.policy_version,
        "gate_policy_status": gate_policy.status,
        "gate_policy_ratified": gate_policy.ratified,
        "completion_methodology_version": completion_summary.get("methodology_version"),
        "completion_model_version": completion_summary.get("model_version"),
        "completion_manifest_sha256": _sha256(
            completion_output_dir / "MANIFEST.sha256"
        ),
        "verified_completion_file_count": len(manifest),
        "validation_observation_count": len(validation_rows),
        "history_month_count": history_months,
        "empirical_gate_passed": empirical_gate_passed,
        "release_gate_passed": release_gate_passed,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
        "status": (
            "EMPIRICAL_GATES_PASSED_POLICY_UNRATIFIED"
            if empirical_gate_passed and not gate_policy.ratified
            else "AUDIT_FAILED"
            if not empirical_gate_passed
            else "RATIFIED_TECHNICAL_GATE_PASSED_RELEASE_STILL_DISABLED"
        ),
        "input_hashes": {
            **{name: _sha256(path) for name, path in input_paths.items()},
            "gate_policy_sha256": _sha256(gate_policy_path),
        },
        "hidden_target_value_used_for_donor_selection": False,
        "future_period_observations_allowed": False,
        "silent_monthly_renormalisation_allowed": False,
    }
    (output_dir / "price_model_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    filenames = [
        "price_validation_detail.csv",
        "price_baseline_comparison.csv",
        "price_sensitivity_audit.csv",
        "price_model_gate_results.csv",
        "price_model_audit_summary.json",
    ]
    _write_manifest(output_dir, filenames)
    return summary
