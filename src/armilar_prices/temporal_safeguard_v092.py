"""Temporal holdout evaluation for two minimal Armilar v0.9.2 safeguards."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from armilar_prices.paired_diagnostics_v091 import verify_manifest

getcontext().prec = 42

MODELS = (
    "B0_GLOBAL_EQUAL_HEADLINE",
    "B1_ARMILAR_WEIGHTED_HEADLINE",
    "B2_CATEGORY_CARRY_FORWARD",
    "B3_HIERARCHICAL_COMPLETION",
)
B1 = "B1_ARMILAR_WEIGHTED_HEADLINE"
B2 = "B2_CATEGORY_CARRY_FORWARD"
B3 = "B3_HIERARCHICAL_COMPLETION"
B4 = "B4_TEMPORAL_SAFEGUARD"
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
REQUIRED_CASE_FIELDS = {
    "case_id",
    "scenario",
    "origin_period",
    "target_period",
    "horizon_months",
    "masked_group",
    "model",
    "truth_index",
    "estimated_index",
    "absolute_error_bps",
    "masked_cell_mape_percent",
    "evidence_class",
    "economy_code",
    "source_category",
}
INVARIANT_FIELDS = (
    "case_id",
    "scenario",
    "origin_period",
    "target_period",
    "horizon_months",
    "masked_group",
    "truth_index",
    "economy_code",
    "source_category",
)


class TemporalSafeguardError(RuntimeError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class CandidateRule:
    rule_id: str
    rule_type: str
    source_category: str = ""
    scenario: str = ""
    horizon_months: int = 0

    def matches(self, case: "CaseResult") -> bool:
        if self.rule_type == "SOURCE_CATEGORY":
            return case.source_category == self.source_category
        if self.rule_type == "SCENARIO_HORIZON":
            return case.scenario == self.scenario and case.horizon_months == self.horizon_months
        raise TemporalSafeguardError("RULE_TYPE_UNSUPPORTED", self.rule_type)


@dataclass(frozen=True)
class SafeguardPolicy:
    policy_version: str
    required_backtest_policy_version: str
    required_vintage_mode: str
    development_target_start: str
    development_target_end: str
    evaluation_target_start: str
    evaluation_target_end: str
    base_model: str
    fallback_model: str
    minimum_development_cases_per_rule: int
    activation_mean_delta_bps_gt: Decimal
    activation_regression_rate_gte: Decimal
    candidate_rules: tuple[CandidateRule, ...]
    rejected_v089_experiment_reused: bool
    model_promotion_allowed: bool
    research_release_allowed: bool
    monetary_release_allowed: bool

    @classmethod
    def load(cls, path: Path | str) -> "SafeguardPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "policy_version",
            "required_backtest_policy_version",
            "required_vintage_mode",
            "development_target_start",
            "development_target_end",
            "evaluation_target_start",
            "evaluation_target_end",
            "base_model",
            "fallback_model",
            "minimum_development_cases_per_rule",
            "activation_mean_delta_bps_gt",
            "activation_regression_rate_gte",
            "candidate_rules",
            "rejected_v089_experiment_reused",
            "model_promotion_allowed",
            "research_release_allowed",
            "monetary_release_allowed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise TemporalSafeguardError("POLICY_FIELD_MISSING", ", ".join(missing))
        try:
            rules = tuple(
                CandidateRule(
                    rule_id=str(item["rule_id"]),
                    rule_type=str(item["rule_type"]),
                    source_category=str(item.get("source_category", "")),
                    scenario=str(item.get("scenario", "")),
                    horizon_months=int(item.get("horizon_months", 0)),
                )
                for item in payload["candidate_rules"]
            )
            policy = cls(
                policy_version=str(payload["policy_version"]),
                required_backtest_policy_version=str(payload["required_backtest_policy_version"]),
                required_vintage_mode=str(payload["required_vintage_mode"]),
                development_target_start=str(payload["development_target_start"]),
                development_target_end=str(payload["development_target_end"]),
                evaluation_target_start=str(payload["evaluation_target_start"]),
                evaluation_target_end=str(payload["evaluation_target_end"]),
                base_model=str(payload["base_model"]),
                fallback_model=str(payload["fallback_model"]),
                minimum_development_cases_per_rule=int(
                    payload["minimum_development_cases_per_rule"]
                ),
                activation_mean_delta_bps_gt=_decimal(
                    str(payload["activation_mean_delta_bps_gt"]),
                    "ACTIVATION_THRESHOLD_INVALID",
                    "activation_mean_delta_bps_gt",
                ),
                activation_regression_rate_gte=_decimal(
                    str(payload["activation_regression_rate_gte"]),
                    "ACTIVATION_THRESHOLD_INVALID",
                    "activation_regression_rate_gte",
                ),
                candidate_rules=rules,
                rejected_v089_experiment_reused=bool(
                    payload["rejected_v089_experiment_reused"]
                ),
                model_promotion_allowed=bool(payload["model_promotion_allowed"]),
                research_release_allowed=bool(payload["research_release_allowed"]),
                monetary_release_allowed=bool(payload["monetary_release_allowed"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TemporalSafeguardError("POLICY_INVALID", str(exc)) from exc
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.policy_version != "0.9.2":
            raise TemporalSafeguardError("POLICY_VERSION_UNSUPPORTED", self.policy_version)
        if self.required_backtest_policy_version != "0.9.0":
            raise TemporalSafeguardError(
                "BACKTEST_POLICY_VERSION_UNSUPPORTED", self.required_backtest_policy_version
            )
        if self.required_vintage_mode != "FINAL_VINTAGE_PSEUDO_REAL_TIME":
            raise TemporalSafeguardError("VINTAGE_MODE_UNSUPPORTED", self.required_vintage_mode)
        for period in (
            self.development_target_start,
            self.development_target_end,
            self.evaluation_target_start,
            self.evaluation_target_end,
        ):
            _validate_period(period)
        if self.development_target_start > self.development_target_end:
            raise TemporalSafeguardError("DEVELOPMENT_PERIOD_INVALID", "start after end")
        if self.evaluation_target_start > self.evaluation_target_end:
            raise TemporalSafeguardError("EVALUATION_PERIOD_INVALID", "start after end")
        if self.development_target_end >= self.evaluation_target_start:
            raise TemporalSafeguardError("TEMPORAL_SPLIT_OVERLAP", "development overlaps evaluation")
        if self.base_model != B3 or self.fallback_model != B2:
            raise TemporalSafeguardError(
                "MODEL_CONTRACT_MISMATCH", f"{self.base_model}/{self.fallback_model}"
            )
        if self.minimum_development_cases_per_rule < 1:
            raise TemporalSafeguardError("INVALID_MINIMUM_CASES", "must be positive")
        if self.activation_mean_delta_bps_gt < 0:
            raise TemporalSafeguardError("ACTIVATION_THRESHOLD_INVALID", "negative mean threshold")
        if not Decimal("0") <= self.activation_regression_rate_gte <= Decimal("1"):
            raise TemporalSafeguardError("ACTIVATION_THRESHOLD_INVALID", "rate outside [0,1]")
        if (
            self.rejected_v089_experiment_reused
            or self.model_promotion_allowed
            or self.research_release_allowed
            or self.monetary_release_allowed
        ):
            raise TemporalSafeguardError("RELEASE_OR_EXPERIMENT_GATE_WEAKENED", "flags must be false")
        expected = {
            "CP08_FALLBACK_TO_B2": ("SOURCE_CATEGORY", "CP08", "", 0),
            "CATEGORY_OUTAGE_H1_FALLBACK_TO_B2": (
                "SCENARIO_HORIZON",
                "",
                "CATEGORY_OUTAGE",
                1,
            ),
        }
        actual = {
            rule.rule_id: (
                rule.rule_type,
                rule.source_category,
                rule.scenario,
                rule.horizon_months,
            )
            for rule in self.candidate_rules
        }
        if actual != expected:
            raise TemporalSafeguardError("RULE_CONTRACT_MISMATCH", str(actual))

    def split_for(self, target_period: str) -> str:
        _validate_period(target_period)
        if self.development_target_start <= target_period <= self.development_target_end:
            return "DEVELOPMENT"
        if self.evaluation_target_start <= target_period <= self.evaluation_target_end:
            return "EVALUATION"
        raise TemporalSafeguardError("CASE_OUTSIDE_TEMPORAL_SPLIT", target_period)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    scenario: str
    origin_period: str
    target_period: str
    horizon_months: int
    masked_group: str
    model: str
    truth_index: Decimal
    estimated_index: Decimal
    absolute_error_bps: Decimal
    masked_cell_mape_percent: Decimal
    evidence_class: str
    economy_code: str
    source_category: str


@dataclass(frozen=True)
class ActivationResult:
    rule: CandidateRule
    development_case_count: int
    development_mean_b3_minus_b2_bps: Decimal
    development_regression_rate_b3_vs_b2: Decimal
    activated: bool
    activation_reasons: tuple[str, ...]


@dataclass(frozen=True)
class SafeguardCase:
    case_id: str
    split: str
    scenario: str
    origin_period: str
    target_period: str
    horizon_months: int
    masked_group: str
    economy_code: str
    source_category: str
    matched_rule_ids: tuple[str, ...]
    active_rule_ids: tuple[str, ...]
    selected_model: str
    b1_absolute_error_bps: Decimal
    b2_absolute_error_bps: Decimal
    b3_absolute_error_bps: Decimal
    b4_absolute_error_bps: Decimal
    b4_minus_b3_bps: Decimal
    b4_minus_b2_bps: Decimal
    b4_minus_b1_bps: Decimal


def _installed_version() -> str:
    try:
        return package_version("armilar-data-pipeline")
    except PackageNotFoundError:
        return "0+unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _decimal(value: str, code: str, detail: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise TemporalSafeguardError(code, detail) from exc
    if not result.is_finite():
        raise TemporalSafeguardError(code, detail)
    return result


def _validate_period(value: str) -> None:
    if not PERIOD_PATTERN.fullmatch(value):
        raise TemporalSafeguardError("PERIOD_INVALID", value)


def _load_summary(input_root: Path, policy: SafeguardPolicy) -> Mapping[str, Any]:
    path = input_root / "backtest_summary.json"
    if not path.is_file():
        raise TemporalSafeguardError("BACKTEST_SUMMARY_MISSING", str(path))
    summary = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "policy_version": policy.required_backtest_policy_version,
        "vintage_mode": policy.required_vintage_mode,
        "publication_aware": False,
        "headline_source_independent": True,
        "rejected_v089_experiment_reused": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    for field, expected in checks.items():
        if summary.get(field) != expected:
            raise TemporalSafeguardError("BACKTEST_CONTRACT_MISMATCH", f"{field}={summary.get(field)!r}")
    if summary.get("official_headline_source") != "EUROSTAT_CP00_INDEPENDENT_SNAPSHOT":
        raise TemporalSafeguardError(
            "HEADLINE_SOURCE_MISMATCH", str(summary.get("official_headline_source"))
        )
    return summary


def _load_cases(input_root: Path) -> tuple[CaseResult, ...]:
    path = input_root / "backtest_cases.csv"
    if not path.is_file():
        raise TemporalSafeguardError("BACKTEST_CASES_MISSING", str(path))
    rows: list[CaseResult] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_CASE_FIELDS - set(reader.fieldnames or ()))
        if missing:
            raise TemporalSafeguardError("BACKTEST_CASE_SCHEMA_MISMATCH", ", ".join(missing))
        for line_number, row in enumerate(reader, start=2):
            model = str(row["model"])
            if model not in MODELS:
                raise TemporalSafeguardError("UNKNOWN_MODEL", f"line {line_number}: {model}")
            try:
                horizon = int(row["horizon_months"])
            except ValueError as exc:
                raise TemporalSafeguardError("INVALID_HORIZON", f"line {line_number}") from exc
            if horizon <= 0:
                raise TemporalSafeguardError("INVALID_HORIZON", f"line {line_number}")
            origin = str(row["origin_period"])
            target = str(row["target_period"])
            _validate_period(origin)
            _validate_period(target)
            absolute_error = _decimal(
                row["absolute_error_bps"], "INVALID_ABSOLUTE_ERROR", f"line {line_number}"
            )
            mape = _decimal(
                row["masked_cell_mape_percent"], "INVALID_MAPE", f"line {line_number}"
            )
            if absolute_error < 0 or mape < 0:
                raise TemporalSafeguardError("NEGATIVE_ERROR_METRIC", f"line {line_number}")
            rows.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    scenario=str(row["scenario"]),
                    origin_period=origin,
                    target_period=target,
                    horizon_months=horizon,
                    masked_group=str(row["masked_group"]),
                    model=model,
                    truth_index=_decimal(
                        row["truth_index"], "INVALID_TRUTH_INDEX", f"line {line_number}"
                    ),
                    estimated_index=_decimal(
                        row["estimated_index"], "INVALID_ESTIMATED_INDEX", f"line {line_number}"
                    ),
                    absolute_error_bps=absolute_error,
                    masked_cell_mape_percent=mape,
                    evidence_class=str(row["evidence_class"]),
                    economy_code=str(row["economy_code"]),
                    source_category=str(row["source_category"]),
                )
            )
    if not rows:
        raise TemporalSafeguardError("EMPTY_BACKTEST_CASES", str(path))
    return tuple(rows)


def _index_cases(
    cases: Sequence[CaseResult], summary: Mapping[str, Any], policy: SafeguardPolicy
) -> Mapping[str, Mapping[str, CaseResult]]:
    indexed: MutableMapping[str, dict[str, CaseResult]] = defaultdict(dict)
    split_counts = {"DEVELOPMENT": 0, "EVALUATION": 0}
    for case in cases:
        if case.model in indexed[case.case_id]:
            raise TemporalSafeguardError("DUPLICATE_MODEL_CASE", f"{case.case_id}/{case.model}")
        indexed[case.case_id][case.model] = case
    for case_id, by_model in indexed.items():
        if set(by_model) != set(MODELS):
            raise TemporalSafeguardError("COMPARISON_SAMPLE_MISMATCH", f"{case_id}: {sorted(by_model)}")
        reference = by_model[MODELS[0]]
        split_counts[policy.split_for(reference.target_period)] += 1
        for model in MODELS[1:]:
            candidate = by_model[model]
            for field in INVARIANT_FIELDS:
                if getattr(reference, field) != getattr(candidate, field):
                    raise TemporalSafeguardError("CASE_METADATA_MISMATCH", f"{case_id}/{model}/{field}")
    declared = summary.get("common_case_count_per_model")
    if not isinstance(declared, int) or declared != len(indexed):
        raise TemporalSafeguardError(
            "CASE_COUNT_MISMATCH", f"declared={declared} actual={len(indexed)}"
        )
    if len(cases) != len(indexed) * len(MODELS):
        raise TemporalSafeguardError("CASE_COUNT_MISMATCH", str(len(cases)))
    if not all(split_counts.values()):
        raise TemporalSafeguardError("TEMPORAL_SPLIT_EMPTY", str(split_counts))
    return indexed


def _activate_rules(
    indexed: Mapping[str, Mapping[str, CaseResult]], policy: SafeguardPolicy
) -> tuple[ActivationResult, ...]:
    results: list[ActivationResult] = []
    for rule in policy.candidate_rules:
        matching: list[tuple[CaseResult, CaseResult]] = []
        for case_id in sorted(indexed):
            by_model = indexed[case_id]
            b3 = by_model[B3]
            if policy.split_for(b3.target_period) == "DEVELOPMENT" and rule.matches(b3):
                matching.append((b3, by_model[B2]))
        count = len(matching)
        if count:
            deltas = [b3.absolute_error_bps - b2.absolute_error_bps for b3, b2 in matching]
            mean_delta = sum(deltas, Decimal("0")) / Decimal(count)
            regression_rate = Decimal(sum(delta > 0 for delta in deltas)) / Decimal(count)
        else:
            mean_delta = Decimal("0")
            regression_rate = Decimal("0")
        reasons: list[str] = []
        if count < policy.minimum_development_cases_per_rule:
            reasons.append("INSUFFICIENT_DEVELOPMENT_CASES")
        if mean_delta <= policy.activation_mean_delta_bps_gt:
            reasons.append("MEAN_REGRESSION_THRESHOLD_NOT_MET")
        if regression_rate < policy.activation_regression_rate_gte:
            reasons.append("REGRESSION_RATE_THRESHOLD_NOT_MET")
        results.append(
            ActivationResult(
                rule=rule,
                development_case_count=count,
                development_mean_b3_minus_b2_bps=mean_delta,
                development_regression_rate_b3_vs_b2=regression_rate,
                activated=not reasons,
                activation_reasons=tuple(reasons) if reasons else ("ALL_DEVELOPMENT_CRITERIA_MET",),
            )
        )
    return tuple(results)


def _build_safeguard_cases(
    indexed: Mapping[str, Mapping[str, CaseResult]],
    policy: SafeguardPolicy,
    activations: Sequence[ActivationResult],
) -> tuple[SafeguardCase, ...]:
    active = {result.rule.rule_id for result in activations if result.activated}
    rows: list[SafeguardCase] = []
    for case_id in sorted(indexed):
        by_model = indexed[case_id]
        reference = by_model[B3]
        matched = tuple(rule.rule_id for rule in policy.candidate_rules if rule.matches(reference))
        active_matched = tuple(rule_id for rule_id in matched if rule_id in active)
        selected_model = B2 if active_matched else B3
        b1_error = by_model[B1].absolute_error_bps
        b2_error = by_model[B2].absolute_error_bps
        b3_error = by_model[B3].absolute_error_bps
        b4_error = by_model[selected_model].absolute_error_bps
        rows.append(
            SafeguardCase(
                case_id=case_id,
                split=policy.split_for(reference.target_period),
                scenario=reference.scenario,
                origin_period=reference.origin_period,
                target_period=reference.target_period,
                horizon_months=reference.horizon_months,
                masked_group=reference.masked_group,
                economy_code=reference.economy_code,
                source_category=reference.source_category,
                matched_rule_ids=matched,
                active_rule_ids=active_matched,
                selected_model=selected_model,
                b1_absolute_error_bps=b1_error,
                b2_absolute_error_bps=b2_error,
                b3_absolute_error_bps=b3_error,
                b4_absolute_error_bps=b4_error,
                b4_minus_b3_bps=b4_error - b3_error,
                b4_minus_b2_bps=b4_error - b2_error,
                b4_minus_b1_bps=b4_error - b1_error,
            )
        )
    return tuple(rows)


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise TemporalSafeguardError("EMPTY_METRIC_GROUP", "mean")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _aggregate(rows: Sequence[SafeguardCase]) -> Mapping[str, Any]:
    if not rows:
        raise TemporalSafeguardError("EMPTY_METRIC_GROUP", "safeguard rows")
    count = len(rows)
    n = Decimal(count)
    delta_b3 = [row.b4_minus_b3_bps for row in rows]
    delta_b1 = [row.b4_minus_b1_bps for row in rows]
    return {
        "case_count": count,
        "selected_b2_count": sum(row.selected_model == B2 for row in rows),
        "selected_b3_count": sum(row.selected_model == B3 for row in rows),
        "mean_b1_absolute_bps": _mean([row.b1_absolute_error_bps for row in rows]),
        "mean_b2_absolute_bps": _mean([row.b2_absolute_error_bps for row in rows]),
        "mean_b3_absolute_bps": _mean([row.b3_absolute_error_bps for row in rows]),
        "mean_b4_absolute_bps": _mean([row.b4_absolute_error_bps for row in rows]),
        "mean_b4_minus_b3_bps": _mean(delta_b3),
        "mean_b4_minus_b2_bps": _mean([row.b4_minus_b2_bps for row in rows]),
        "mean_b4_minus_b1_bps": _mean(delta_b1),
        "b4_improvement_rate_vs_b3": Decimal(sum(value < 0 for value in delta_b3)) / n,
        "b4_regression_rate_vs_b3": Decimal(sum(value > 0 for value in delta_b3)) / n,
        "b4_improvement_rate_vs_b1": Decimal(sum(value < 0 for value in delta_b1)) / n,
        "b4_regression_rate_vs_b1": Decimal(sum(value > 0 for value in delta_b1)) / n,
    }


def _decimal_text(value: Decimal, places: int = 8) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _serialise(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value, 10)
    if isinstance(value, Mapping):
        return {key: _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    return value


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_manifest(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256")
    lines = [f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}" for path in files]
    _atomic_write(root / "MANIFEST.sha256", ("\n".join(lines) + "\n").encode("utf-8"))


def _activation_payload(
    policy: SafeguardPolicy, activations: Sequence[ActivationResult]
) -> Mapping[str, Any]:
    return {
        "activation_data_split": "DEVELOPMENT_ONLY",
        "evaluation_data_used_for_activation": False,
        "development_target_start": policy.development_target_start,
        "development_target_end": policy.development_target_end,
        "criteria": {
            "minimum_development_cases_per_rule": policy.minimum_development_cases_per_rule,
            "activation_mean_delta_bps_gt": policy.activation_mean_delta_bps_gt,
            "activation_regression_rate_gte": policy.activation_regression_rate_gte,
        },
        "active_rule_count": sum(result.activated for result in activations),
        "rules": [
            {
                "rule_id": result.rule.rule_id,
                "rule_type": result.rule.rule_type,
                "development_case_count": result.development_case_count,
                "development_mean_b3_minus_b2_bps": result.development_mean_b3_minus_b2_bps,
                "development_regression_rate_b3_vs_b2": result.development_regression_rate_b3_vs_b2,
                "activated": result.activated,
                "activation_reasons": result.activation_reasons,
            }
            for result in activations
        ],
    }


def _metric_rows(
    cases: Sequence[SafeguardCase], policy: SafeguardPolicy
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("DEVELOPMENT", "EVALUATION"):
        split_cases = [case for case in cases if case.split == split]
        rows.append({"split": split, "scope": "OVERALL", "scope_value": "ALL", **_aggregate(split_cases)})
        for rule in policy.candidate_rules:
            subset = [case for case in split_cases if rule.rule_id in case.matched_rule_ids]
            if subset:
                rows.append(
                    {
                        "split": split,
                        "scope": "RULE_MATCH",
                        "scope_value": rule.rule_id,
                        **_aggregate(subset),
                    }
                )
    return rows


def _evaluation_payload(
    cases: Sequence[SafeguardCase],
    policy: SafeguardPolicy,
    activations: Sequence[ActivationResult],
) -> Mapping[str, Any]:
    evaluation = [case for case in cases if case.split == "EVALUATION"]
    overall = _aggregate(evaluation)
    active_by_id = {result.rule.rule_id: result.activated for result in activations}
    rule_results: list[dict[str, Any]] = []
    for rule in policy.candidate_rules:
        subset = [case for case in evaluation if rule.rule_id in case.matched_rule_ids]
        metrics = _aggregate(subset) if subset else None
        if not active_by_id[rule.rule_id]:
            status = "INACTIVE_FROM_DEVELOPMENT"
        elif metrics is None:
            status = "NO_EVALUATION_CASES"
        elif metrics["mean_b4_minus_b3_bps"] < 0:
            status = "HOLDOUT_MEAN_IMPROVEMENT_VS_B3"
        elif metrics["mean_b4_minus_b3_bps"] > 0:
            status = "HOLDOUT_MEAN_REGRESSION_VS_B3"
        else:
            status = "HOLDOUT_MEAN_TIE_VS_B3"
        rule_results.append(
            {
                "rule_id": rule.rule_id,
                "activated_from_development": active_by_id[rule.rule_id],
                "evaluation_status": status,
                "metrics": metrics,
            }
        )
    active_results = [item for item in rule_results if item["activated_from_development"]]
    all_active_rules_non_regressing = bool(active_results) and all(
        item["evaluation_status"] in {"HOLDOUT_MEAN_IMPROVEMENT_VS_B3", "HOLDOUT_MEAN_TIE_VS_B3"}
        for item in active_results
    )
    return {
        "evaluation_target_start": policy.evaluation_target_start,
        "evaluation_target_end": policy.evaluation_target_end,
        "evaluation_data_used_for_activation": False,
        "overall": overall,
        "rules": rule_results,
        "all_active_rules_non_regressing_vs_b3_on_holdout": all_active_rules_non_regressing,
        "b4_beats_b3_mean_on_holdout": overall["mean_b4_minus_b3_bps"] < 0,
        "b4_beats_b1_mean_on_holdout": overall["mean_b4_minus_b1_bps"] < 0,
        "model_promotion_allowed": False,
    }


def build_temporal_safeguard(
    policy_path: Path | str, input_dir: Path | str, output_dir: Path | str
) -> Mapping[str, Any]:
    policy = SafeguardPolicy.load(policy_path)
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise TemporalSafeguardError("OUTPUT_DIRECTORY_NOT_EMPTY", str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)

    verify_manifest(input_root)
    summary = _load_summary(input_root, policy)
    cases = _load_cases(input_root)
    indexed = _index_cases(cases, summary, policy)
    activations = _activate_rules(indexed, policy)
    safeguard_cases = _build_safeguard_cases(indexed, policy, activations)

    activation_payload = _serialise(_activation_payload(policy, activations))
    _atomic_write(output_root / "rule_activation.json", _canonical_json_bytes(activation_payload))

    case_rows = [
        {
            "case_id": case.case_id,
            "split": case.split,
            "scenario": case.scenario,
            "origin_period": case.origin_period,
            "target_period": case.target_period,
            "horizon_months": case.horizon_months,
            "masked_group": case.masked_group,
            "economy_code": case.economy_code,
            "source_category": case.source_category,
            "matched_rule_ids": ";".join(case.matched_rule_ids),
            "active_rule_ids": ";".join(case.active_rule_ids),
            "selected_model": case.selected_model,
            "b1_absolute_error_bps": _decimal_text(case.b1_absolute_error_bps),
            "b2_absolute_error_bps": _decimal_text(case.b2_absolute_error_bps),
            "b3_absolute_error_bps": _decimal_text(case.b3_absolute_error_bps),
            "b4_absolute_error_bps": _decimal_text(case.b4_absolute_error_bps),
            "b4_minus_b3_bps": _decimal_text(case.b4_minus_b3_bps),
            "b4_minus_b2_bps": _decimal_text(case.b4_minus_b2_bps),
            "b4_minus_b1_bps": _decimal_text(case.b4_minus_b1_bps),
        }
        for case in safeguard_cases
    ]
    _write_csv(output_root / "safeguard_case_results.csv", list(case_rows[0]), case_rows)

    metrics = [_serialise(row) for row in _metric_rows(safeguard_cases, policy)]
    _write_csv(output_root / "safeguard_metrics.csv", list(metrics[0]), metrics)

    evaluation_payload = _serialise(_evaluation_payload(safeguard_cases, policy, activations))
    _atomic_write(
        output_root / "evaluation_summary.json", _canonical_json_bytes(evaluation_payload)
    )

    input_manifest_hash = _sha256((input_root / "MANIFEST.sha256").read_bytes())
    split_counts = {
        split: sum(case.split == split for case in safeguard_cases)
        for split in ("DEVELOPMENT", "EVALUATION")
    }
    run_summary = {
        "schema_version": "1.0",
        "pipeline_version": _installed_version(),
        "policy_version": policy.policy_version,
        "input_backtest_policy_version": summary["policy_version"],
        "status": "TEMPORAL_SAFEGUARD_EVALUATED_WITH_VINTAGE_LIMITATION",
        "vintage_mode": summary["vintage_mode"],
        "publication_aware": False,
        "headline_source_independent": True,
        "common_case_count_per_model": len(indexed),
        "development_case_count": split_counts["DEVELOPMENT"],
        "evaluation_case_count": split_counts["EVALUATION"],
        "candidate_rule_count": len(policy.candidate_rules),
        "active_rule_count": sum(result.activated for result in activations),
        "input_backtest_manifest_sha256": input_manifest_hash,
        "evaluation_data_used_for_activation": False,
        "b0_b3_model_code_changed": False,
        "rejected_v089_experiment_reused": False,
        "model_promotion_allowed": False,
        "research_release_allowed": False,
        "monetary_release_allowed": False,
    }
    _atomic_write(output_root / "run_summary.json", _canonical_json_bytes(run_summary))
    _write_report(output_root, activation_payload, evaluation_payload, run_summary)
    _write_manifest(output_root)
    return run_summary


def _write_report(
    output_root: Path,
    activation: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    overall = evaluation["overall"]
    lines = [
        "# Armilar v0.9.2 temporal safeguard evaluation",
        "",
        "## Design",
        "",
        "B4 selects B3 by default and B2 only where a pre-declared rule was activated on the development period. Evaluation data were not used for activation.",
        "",
        "| Period | Targets | Cases |",
        "|---|---|---:|",
        f"| Development | 2022-01 to 2023-12 | {summary['development_case_count']} |",
        f"| Evaluation | 2024-01 to 2025-12 | {summary['evaluation_case_count']} |",
        "",
        "## Development-only activation",
        "",
        "| Rule | Cases | Mean B3-B2 (bps) | Regression rate | Activated |",
        "|---|---:|---:|---:|---|",
    ]
    for rule in activation["rules"]:
        lines.append(
            f"| {rule['rule_id']} | {rule['development_case_count']} | "
            f"{rule['development_mean_b3_minus_b2_bps']} | "
            f"{rule['development_regression_rate_b3_vs_b2']} | {rule['activated']} |"
        )
    lines.extend(
        [
            "",
            "## Sealed evaluation result",
            "",
            f"- Mean B4-minus-B3 error: {overall['mean_b4_minus_b3_bps']} bps.",
            f"- Mean B4-minus-B1 error: {overall['mean_b4_minus_b1_bps']} bps.",
            f"- B4 improves B3 in {overall['b4_improvement_rate_vs_b3']} of evaluation cases.",
            f"- B4 beats B3 on mean holdout error: {evaluation['b4_beats_b3_mean_on_holdout']}.",
            f"- B4 beats B1 on mean holdout error: {evaluation['b4_beats_b1_mean_on_holdout']}.",
            "",
            "## Rule-level holdout status",
            "",
        ]
    )
    for rule in evaluation["rules"]:
        lines.append(f"- `{rule['rule_id']}`: `{rule['evaluation_status']}`.")
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "No result from this experiment promotes B4 or changes B0-B3. The input remains final-vintage and not publication-aware.",
            "",
            "`model_promotion_allowed=false`",
            "",
            "`research_release_allowed=false`",
            "",
            "`monetary_release_allowed=false`",
        ]
    )
    _atomic_write(
        output_root / "TEMPORAL_SAFEGUARD_REPORT.md", ("\n".join(lines) + "\n").encode("utf-8")
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Armilar v0.9.2 temporal safeguard evaluation")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verify_only:
        verify_manifest(args.output_dir)
        print(json.dumps({"status": "MANIFEST_VERIFIED", "output_dir": args.output_dir}))
        return 0
    summary = build_temporal_safeguard(args.policy, args.input_dir, args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
