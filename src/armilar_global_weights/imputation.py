from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .models import CATEGORIES, EvidenceClass, WeightCell, parse_list


class ImputationError(ValueError):
    """Raised when an imputation run would violate its research contract."""


@dataclass(frozen=True, slots=True)
class EconomyProfile:
    economy_code: str
    region_code: str
    income_group: str
    total_real_expenditure: float
    covariates: tuple[tuple[str, float], ...] = ()

    def validate(self) -> None:
        if len(self.economy_code) != 3 or self.economy_code != self.economy_code.upper():
            raise ImputationError(f"invalid economy_code: {self.economy_code!r}")
        if not self.region_code.strip():
            raise ImputationError(f"region_code required for {self.economy_code}")
        if not self.income_group.strip():
            raise ImputationError(f"income_group required for {self.economy_code}")
        if not math.isfinite(self.total_real_expenditure) or self.total_real_expenditure <= 0:
            raise ImputationError(f"positive total_real_expenditure required for {self.economy_code}")
        for name, value in self.covariates:
            if not name.strip() or not math.isfinite(value):
                raise ImputationError(f"invalid covariate for {self.economy_code}: {name!r}={value!r}")

    @property
    def covariate_map(self) -> dict[str, float]:
        return dict(self.covariates)


@dataclass(frozen=True, slots=True)
class AggregateConstraint:
    economy_code: str
    aggregate_id: str
    category_codes: tuple[str, ...]
    aggregate_real_expenditure: float
    source_ids: tuple[str, ...]
    notes: str = ""

    def validate(self) -> None:
        if len(self.economy_code) != 3 or self.economy_code != self.economy_code.upper():
            raise ImputationError(f"invalid economy_code in aggregate: {self.economy_code!r}")
        if not self.aggregate_id.strip():
            raise ImputationError("aggregate_id is required")
        if len(self.category_codes) < 2:
            raise ImputationError(f"aggregate {self.aggregate_id} must contain at least two categories")
        if len(set(self.category_codes)) != len(self.category_codes):
            raise ImputationError(f"aggregate {self.aggregate_id} contains duplicate categories")
        invalid = sorted(set(self.category_codes) - set(CATEGORIES))
        if invalid:
            raise ImputationError(f"aggregate {self.aggregate_id} has invalid categories: {invalid}")
        if not math.isfinite(self.aggregate_real_expenditure) or self.aggregate_real_expenditure <= 0:
            raise ImputationError(f"aggregate {self.aggregate_id} must be positive")
        if not self.source_ids:
            raise ImputationError(f"aggregate {self.aggregate_id} requires source_ids")


@dataclass(frozen=True, slots=True)
class ImputationPolicy:
    model_version: str = "0.7.2"
    donor_count: int = 5
    minimum_donors: int = 3
    inverse_distance_floor: float = 0.05
    minimum_relative_interval: float = 0.10
    interval_quantile_lower: float = 0.10
    interval_quantile_upper: float = 0.90
    allocation_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def validate(self) -> None:
        if self.donor_count < 1:
            raise ImputationError("donor_count must be positive")
        if self.minimum_donors < 1 or self.minimum_donors > self.donor_count:
            raise ImputationError("minimum_donors must be between 1 and donor_count")
        if self.inverse_distance_floor <= 0:
            raise ImputationError("inverse_distance_floor must be positive")
        if not 0 < self.minimum_relative_interval < 1:
            raise ImputationError("minimum_relative_interval must be between 0 and 1")
        if not 0 <= self.interval_quantile_lower < self.interval_quantile_upper <= 1:
            raise ImputationError("invalid interval quantiles")
        for group_id, categories in self.allocation_groups:
            if not group_id.strip() or len(categories) < 2 or set(categories) - set(CATEGORIES):
                raise ImputationError(f"invalid allocation group {group_id!r}")


@dataclass(frozen=True, slots=True)
class ValidationPrediction:
    method: str
    economy_code: str
    category_code: str
    actual_value: float
    predicted_central: float
    predicted_lower: float
    predicted_upper: float
    donor_economies: tuple[str, ...]
    group_id: str = ""

    @property
    def error(self) -> float:
        return self.predicted_central - self.actual_value

    @property
    def absolute_error(self) -> float:
        return abs(self.error)

    @property
    def absolute_percentage_error(self) -> float:
        return self.absolute_error / self.actual_value if self.actual_value else math.nan

    @property
    def covered(self) -> bool:
        return self.predicted_lower <= self.actual_value <= self.predicted_upper


def load_policy(path: Path) -> ImputationPolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = tuple(
        (str(item["group_id"]), tuple(str(code).upper() for code in item["category_codes"]))
        for item in payload.get("allocation_groups", [])
    )
    policy = ImputationPolicy(
        model_version=str(payload.get("model_version", "0.7.2")),
        donor_count=int(payload.get("donor_count", 5)),
        minimum_donors=int(payload.get("minimum_donors", 3)),
        inverse_distance_floor=float(payload.get("inverse_distance_floor", 0.05)),
        minimum_relative_interval=float(payload.get("minimum_relative_interval", 0.10)),
        interval_quantile_lower=float(payload.get("interval_quantile_lower", 0.10)),
        interval_quantile_upper=float(payload.get("interval_quantile_upper", 0.90)),
        allocation_groups=groups,
    )
    policy.validate()
    return policy


def load_evidence_cells(path: Path) -> list[WeightCell]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ImputationError("evidence input contains no rows")
    cells: list[WeightCell] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            central = _first_float(row, "real_expenditure_central", "real_expenditure", "value")
            lower = _optional_float(row.get("real_expenditure_lower"), central)
            upper = _optional_float(row.get("real_expenditure_upper"), central)
            evidence = EvidenceClass(str(row["evidence_class"]).strip())
            cell = WeightCell(
                economy_code=str(row["economy_code"]).strip().upper(),
                category_code=str(row["category_code"]).strip().upper(),
                real_expenditure_central=central,
                real_expenditure_lower=lower,
                real_expenditure_upper=upper,
                evidence_class=evidence,
                method_id=(row.get("method_id") or "staged-evidence").strip(),
                model_version=(row.get("model_version") or "0.7.1").strip(),
                source_ids=parse_list(row.get("source_ids") or "STAGED-EVIDENCE"),
                donor_economies=parse_list(row.get("donor_economies")),
                validation_mae=_nullable_float(row.get("validation_mae")),
                validation_bias=_nullable_float(row.get("validation_bias")),
                notes=(row.get("notes") or "").strip(),
            )
            cell.validate()
        except (KeyError, TypeError, ValueError, ImputationError) as exc:
            raise ImputationError(f"invalid evidence cell at CSV line {line_number}: {exc}") from exc
        cells.append(cell)
    _reject_duplicate_cells(cells)
    return cells


def load_profiles(path: Path) -> dict[str, EconomyProfile]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = tuple(reader.fieldnames or ())
    if not rows:
        raise ImputationError("profile input contains no rows")
    reserved = {"economy_code", "region_code", "income_group", "total_real_expenditure"}
    covariate_names = tuple(sorted(name for name in fieldnames if name not in reserved))
    profiles: dict[str, EconomyProfile] = {}
    for line_number, row in enumerate(rows, start=2):
        try:
            code = str(row["economy_code"]).strip().upper()
            covariates = tuple(
                (name, float(row[name]))
                for name in covariate_names
                if row.get(name) is not None and str(row[name]).strip()
            )
            profile = EconomyProfile(
                economy_code=code,
                region_code=str(row["region_code"]).strip().upper(),
                income_group=str(row["income_group"]).strip().upper(),
                total_real_expenditure=float(row["total_real_expenditure"]),
                covariates=covariates,
            )
            profile.validate()
        except (KeyError, TypeError, ValueError, ImputationError) as exc:
            raise ImputationError(f"invalid economy profile at CSV line {line_number}: {exc}") from exc
        if code in profiles:
            raise ImputationError(f"duplicate economy profile: {code}")
        profiles[code] = profile
    return profiles


def load_constraints(path: Path | None) -> list[AggregateConstraint]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    constraints: list[AggregateConstraint] = []
    seen: set[tuple[str, str]] = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            constraint = AggregateConstraint(
                economy_code=str(row["economy_code"]).strip().upper(),
                aggregate_id=str(row["aggregate_id"]).strip(),
                category_codes=parse_list(row["category_codes"]),
                aggregate_real_expenditure=float(row["aggregate_real_expenditure"]),
                source_ids=parse_list(row.get("source_ids") or "OWN-ECONOMY-AGGREGATE"),
                notes=(row.get("notes") or "").strip(),
            )
            constraint.validate()
        except (KeyError, TypeError, ValueError, ImputationError) as exc:
            raise ImputationError(f"invalid aggregate constraint at CSV line {line_number}: {exc}") from exc
        key = (constraint.economy_code, constraint.aggregate_id)
        if key in seen:
            raise ImputationError(f"duplicate aggregate constraint: {key}")
        seen.add(key)
        constraints.append(constraint)
    return constraints


def complete_research_grid(
    evidence_cells: Iterable[WeightCell],
    profiles: Mapping[str, EconomyProfile],
    constraints: Iterable[AggregateConstraint],
    policy: ImputationPolicy,
    validation_metrics: Mapping[tuple[EvidenceClass, str], tuple[float, float]] | None = None,
) -> tuple[list[WeightCell], dict]:
    """Fill a research-only economy-category grid without publishing world weights.

    A/B inputs are preserved byte-for-value at the object level. C is produced only
    from explicit own-economy aggregate constraints. D uses deterministic donors
    selected from profile attributes. E uses a regional or global share template.
    """
    policy.validate()
    observed = sorted(evidence_cells, key=lambda c: (c.economy_code, c.category_code))
    _reject_duplicate_cells(observed)
    for cell in observed:
        cell.validate()
    if not profiles:
        raise ImputationError("at least one economy profile is required")

    by_key: dict[tuple[str, str], WeightCell] = {(c.economy_code, c.category_code): c for c in observed}
    unknown = sorted({c.economy_code for c in observed} - set(profiles))
    if unknown:
        raise ImputationError(f"evidence economies missing from profiles: {unknown}")

    core_vectors = _complete_core_vectors(observed, profiles)
    if not core_vectors:
        raise ImputationError("no complete A/B donor economies available")
    scales = _covariate_scales(profiles.values())

    generated_counts: dict[str, int] = defaultdict(int)
    generated_with_validation = 0
    validation_metrics = dict(validation_metrics or {})
    constraints_by_economy: dict[str, list[AggregateConstraint]] = defaultdict(list)
    for constraint in constraints:
        constraint.validate()
        if constraint.economy_code not in profiles:
            raise ImputationError(f"constraint economy missing from profiles: {constraint.economy_code}")
        constraints_by_economy[constraint.economy_code].append(constraint)

    # C: own-economy aggregate-constrained allocations.
    for economy in sorted(profiles):
        for constraint in sorted(constraints_by_economy.get(economy, []), key=lambda c: c.aggregate_id):
            missing = [code for code in constraint.category_codes if (economy, code) not in by_key]
            if not missing:
                continue
            observed_sum = sum(
                by_key[(economy, code)].real_expenditure_central
                for code in constraint.category_codes
                if (economy, code) in by_key
            )
            residual = constraint.aggregate_real_expenditure - observed_sum
            if residual <= 0:
                raise ImputationError(
                    f"aggregate {economy}/{constraint.aggregate_id} has non-positive residual after observed cells"
                )
            donors = select_donors(economy, profiles, core_vectors, policy, scales)
            template = _template_distribution(core_vectors, donors, missing, policy)
            for category in missing:
                central_share, lower_share, upper_share = template[category]
                central = residual * central_share
                lower, upper = _bounded_interval(
                    central,
                    residual * lower_share,
                    residual * upper_share,
                    policy.minimum_relative_interval,
                )
                metric = validation_metrics.get((EvidenceClass.C_OWN_ECONOMY_ESTIMATE, category))
                cell = WeightCell(
                    economy_code=economy,
                    category_code=category,
                    real_expenditure_central=central,
                    real_expenditure_lower=lower,
                    real_expenditure_upper=upper,
                    evidence_class=EvidenceClass.C_OWN_ECONOMY_ESTIMATE,
                    method_id="own-economy-constrained-allocation-v1",
                    model_version=policy.model_version,
                    source_ids=tuple(sorted(set(constraint.source_ids) | {f"AGGREGATE:{constraint.aggregate_id}"})),
                    donor_economies=tuple(donors),
                    validation_mae=None if metric is None else metric[0],
                    validation_bias=None if metric is None else metric[1],
                    notes=f"Allocated residual of own-economy aggregate {constraint.aggregate_id}. {constraint.notes}".strip(),
                )
                cell.validate()
                if metric is not None:
                    generated_with_validation += 1
                by_key[(economy, category)] = cell
                generated_counts[cell.evidence_class.value] += 1

    # D/E: fill remaining cells while respecting each economy's own total.
    for economy, profile in sorted(profiles.items()):
        missing = [category for category in CATEGORIES if (economy, category) not in by_key]
        if not missing:
            continue
        observed_sum = sum(
            by_key[(economy, category)].real_expenditure_central
            for category in CATEGORIES
            if (economy, category) in by_key
        )
        residual = profile.total_real_expenditure - observed_sum
        if residual <= 0:
            raise ImputationError(f"economy {economy} has non-positive residual expenditure")
        donors = select_donors(economy, profiles, core_vectors, policy, scales)
        use_donor = len(donors) >= policy.minimum_donors
        if use_donor:
            template = _template_distribution(core_vectors, donors, missing, policy)
            evidence_class = EvidenceClass.D_DONOR_IMPUTATION
            method_id = "deterministic-profile-donor-imputation-v1"
            source_ids = ("PROFILE-DISTANCE-DONOR-TEMPLATE",)
            provenance_donors = tuple(donors)
        else:
            template, scope = _fallback_distribution(
                target=economy,
                profiles=profiles,
                core_vectors=core_vectors,
                categories=missing,
                policy=policy,
            )
            evidence_class = EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK
            method_id = f"{scope.lower()}-share-fallback-v1"
            source_ids = (f"{scope}-SHARE-TEMPLATE",)
            provenance_donors = ()

        for category in missing:
            central_share, lower_share, upper_share = template[category]
            central = residual * central_share
            lower, upper = _bounded_interval(
                central,
                residual * lower_share,
                residual * upper_share,
                policy.minimum_relative_interval,
            )
            metric = validation_metrics.get((evidence_class, category))
            cell = WeightCell(
                economy_code=economy,
                category_code=category,
                real_expenditure_central=central,
                real_expenditure_lower=lower,
                real_expenditure_upper=upper,
                evidence_class=evidence_class,
                method_id=method_id,
                model_version=policy.model_version,
                source_ids=source_ids,
                donor_economies=provenance_donors,
                validation_mae=None if metric is None else metric[0],
                validation_bias=None if metric is None else metric[1],
                notes="Research baseline; not eligible for official or monetary release.",
            )
            cell.validate()
            if metric is not None:
                generated_with_validation += 1
            by_key[(economy, category)] = cell
            generated_counts[cell.evidence_class.value] += 1

    completed = [by_key[(economy, category)] for economy in sorted(profiles) for category in CATEGORIES]
    for economy, profile in sorted(profiles.items()):
        total = sum(c.real_expenditure_central for c in completed if c.economy_code == economy)
        tolerance = 1e-9 * max(1.0, profile.total_real_expenditure)
        if abs(total - profile.total_real_expenditure) > tolerance:
            raise ImputationError(
                f"completed economy total mismatch for {economy}: {total} != {profile.total_real_expenditure}"
            )

    summary = {
        "model_version": policy.model_version,
        "economy_count": len(profiles),
        "cell_count": len(completed),
        "complete_grid": len(completed) == len(profiles) * len(CATEGORIES),
        "input_evidence_cell_count": len(observed),
        "generated_cell_count": sum(generated_counts.values()),
        "generated_by_evidence_class": dict(sorted(generated_counts.items())),
        "generated_cells_with_validation_metrics": generated_with_validation,
        "generated_validation_metric_coverage": (
            generated_with_validation / sum(generated_counts.values()) if generated_counts else 1.0
        ),
        "donor_pool_economy_count": len(core_vectors),
        "research_release_only": True,
        "global_weight_release_produced": False,
        "monetary_release_allowed": False,
    }
    return completed, summary


def select_donors(
    target: str,
    profiles: Mapping[str, EconomyProfile],
    core_vectors: Mapping[str, Mapping[str, float]],
    policy: ImputationPolicy,
    scales: Mapping[str, float] | None = None,
) -> list[str]:
    """Select donors solely from profile attributes and economy codes.

    Category outcomes are deliberately absent from the ranking function.
    """
    if target not in profiles:
        raise ImputationError(f"target profile not found: {target}")
    scales = dict(scales or _covariate_scales(profiles.values()))
    target_profile = profiles[target]
    ranked: list[tuple[float, str]] = []
    for candidate in sorted(core_vectors):
        if candidate == target or candidate not in profiles:
            continue
        candidate_profile = profiles[candidate]
        region_penalty = 0.0 if candidate_profile.region_code == target_profile.region_code else 4.0
        income_penalty = 0.0 if candidate_profile.income_group == target_profile.income_group else 2.0
        covariate_distance = _profile_distance(target_profile, candidate_profile, scales)
        ranked.append((region_penalty + income_penalty + covariate_distance, candidate))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _, candidate in ranked[: policy.donor_count]]


def validate_baselines(
    evidence_cells: Iterable[WeightCell],
    profiles: Mapping[str, EconomyProfile],
    policy: ImputationPolicy,
) -> tuple[list[ValidationPrediction], dict]:
    """Run leave-one-economy-out validation on complete A/B economies."""
    policy.validate()
    observed = list(evidence_cells)
    core_vectors = _complete_core_vectors(observed, profiles)
    if len(core_vectors) < 2:
        raise ImputationError("leave-one-out validation requires at least two complete A/B economies")
    scales = _covariate_scales(profiles.values())
    predictions: list[ValidationPrediction] = []

    for target in sorted(core_vectors):
        target_profile = profiles[target]
        donors_pool = {code: vector for code, vector in core_vectors.items() if code != target}
        donors = select_donors(target, profiles, donors_pool, policy, scales)
        actual_values = core_vectors[target]
        total = sum(actual_values.values())

        if len(donors) >= policy.minimum_donors:
            template = _template_distribution(donors_pool, donors, CATEGORIES, policy)
            method = "D_DONOR_LOO"
            validation_donors = tuple(donors)
        else:
            template, scope = _fallback_distribution(target, profiles, donors_pool, CATEGORIES, policy)
            method = f"E_{scope}_LOO"
            validation_donors = ()

        for category in CATEGORIES:
            central_share, lower_share, upper_share = template[category]
            predictions.append(
                ValidationPrediction(
                    method=method,
                    economy_code=target,
                    category_code=category,
                    actual_value=actual_values[category],
                    predicted_central=total * central_share,
                    predicted_lower=total * lower_share,
                    predicted_upper=total * upper_share,
                    donor_economies=validation_donors,
                )
            )

        for group_id, categories in policy.allocation_groups:
            group_total = sum(actual_values[category] for category in categories)
            group_template = _template_distribution(donors_pool, donors, categories, policy) if donors else None
            if group_template is None:
                group_template, _ = _fallback_distribution(target, profiles, donors_pool, categories, policy)
            for category in categories:
                central_share, lower_share, upper_share = group_template[category]
                predictions.append(
                    ValidationPrediction(
                        method="C_OWN_AGGREGATE_LOO",
                        economy_code=target,
                        category_code=category,
                        actual_value=actual_values[category],
                        predicted_central=group_total * central_share,
                        predicted_lower=group_total * lower_share,
                        predicted_upper=group_total * upper_share,
                        donor_economies=tuple(donors),
                        group_id=group_id,
                    )
                )

    summary = _validation_summary(predictions)
    summary.update({
        "model_version": policy.model_version,
        "validated_economy_count": len(core_vectors),
        "prediction_count": len(predictions),
        "leave_one_out": True,
        "result_driven_donor_selection": False,
        "research_release_only": True,
        "monetary_release_allowed": False,
    })
    return predictions, summary


def validation_metrics_by_class_category(
    predictions: Sequence[ValidationPrediction],
) -> dict[tuple[EvidenceClass, str], tuple[float, float]]:
    """Return MAE and bias by generated evidence class and category."""
    grouped: dict[tuple[EvidenceClass, str], list[ValidationPrediction]] = defaultdict(list)
    for prediction in predictions:
        if prediction.method.startswith("C_"):
            evidence = EvidenceClass.C_OWN_ECONOMY_ESTIMATE
        elif prediction.method.startswith("D_"):
            evidence = EvidenceClass.D_DONOR_IMPUTATION
        elif prediction.method.startswith("E_"):
            evidence = EvidenceClass.E_REGIONAL_GLOBAL_FALLBACK
        else:
            continue
        grouped[(evidence, prediction.category_code)].append(prediction)
    result: dict[tuple[EvidenceClass, str], tuple[float, float]] = {}
    for key, items in grouped.items():
        result[key] = (
            statistics.fmean(item.absolute_error for item in items),
            statistics.fmean(item.error for item in items),
        )
    return result


def write_imputation_outputs(
    completed_cells: Sequence[WeightCell],
    run_summary: Mapping[str, object],
    output_dir: Path,
    predictions: Sequence[ValidationPrediction] | None = None,
    validation_summary: Mapping[str, object] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = [cell for cell in completed_cells if cell.evidence_class.is_estimated]
    _write_csv(
        output_dir / "imputed_cells_research.csv",
        [_cell_row(cell) for cell in sorted(generated, key=lambda c: (c.economy_code, c.category_code))],
        fieldnames=_cell_fields(),
    )
    _write_csv(
        output_dir / "completed_evidence_grid_research.csv",
        [_cell_row(cell) for cell in sorted(completed_cells, key=lambda c: (c.economy_code, c.category_code))],
        fieldnames=_cell_fields(),
    )
    _write_json(output_dir / "imputation_run_summary.json", dict(run_summary))

    if predictions is not None:
        prediction_rows = [
            {
                "method": item.method,
                "economy_code": item.economy_code,
                "category_code": item.category_code,
                "group_id": item.group_id,
                "actual_value": _number(item.actual_value),
                "predicted_central": _number(item.predicted_central),
                "predicted_lower": _number(item.predicted_lower),
                "predicted_upper": _number(item.predicted_upper),
                "error": _number(item.error),
                "absolute_error": _number(item.absolute_error),
                "absolute_percentage_error": _number(item.absolute_percentage_error),
                "covered": str(item.covered).lower(),
                "donor_economies": "|".join(item.donor_economies),
            }
            for item in predictions
        ]
        _write_csv(output_dir / "imputation_validation_predictions.csv", prediction_rows)
        _write_csv(output_dir / "imputation_error_by_category.csv", _grouped_metrics(predictions, "category_code"))
        _write_csv(output_dir / "imputation_error_by_method.csv", _grouped_metrics(predictions, "method"))
        _write_json(output_dir / "imputation_validation_summary.json", dict(validation_summary or {}))


def _complete_core_vectors(
    cells: Iterable[WeightCell], profiles: Mapping[str, EconomyProfile]
) -> dict[str, dict[str, float]]:
    by_economy: dict[str, dict[str, WeightCell]] = defaultdict(dict)
    for cell in cells:
        if cell.evidence_class.is_core:
            by_economy[cell.economy_code][cell.category_code] = cell
    result: dict[str, dict[str, float]] = {}
    for economy, categories in sorted(by_economy.items()):
        if economy in profiles and set(categories) == set(CATEGORIES):
            result[economy] = {
                category: categories[category].real_expenditure_central for category in CATEGORIES
            }
    return result


def _covariate_scales(profiles: Iterable[EconomyProfile]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for profile in profiles:
        for name, value in profile.covariates:
            values[name].append(value)
    scales: dict[str, float] = {}
    for name, series in values.items():
        scale = statistics.pstdev(series) if len(series) > 1 else 0.0
        scales[name] = scale if scale > 1e-12 else 1.0
    return scales


def _profile_distance(left: EconomyProfile, right: EconomyProfile, scales: Mapping[str, float]) -> float:
    left_map = left.covariate_map
    right_map = right.covariate_map
    common = sorted(set(left_map) & set(right_map) & set(scales))
    if not common:
        return 0.0
    squared = [((left_map[name] - right_map[name]) / scales[name]) ** 2 for name in common]
    return math.sqrt(sum(squared) / len(squared))


def _template_distribution(
    core_vectors: Mapping[str, Mapping[str, float]],
    donors: Sequence[str],
    categories: Sequence[str],
    policy: ImputationPolicy,
) -> dict[str, tuple[float, float, float]]:
    if not donors:
        raise ImputationError("template distribution requires at least one donor")
    category_set = tuple(categories)
    donor_distributions: list[tuple[str, dict[str, float]]] = []
    for donor in donors:
        vector = core_vectors[donor]
        denominator = sum(vector[category] for category in category_set)
        if denominator <= 0:
            continue
        donor_distributions.append((donor, {category: vector[category] / denominator for category in category_set}))
    if not donor_distributions:
        raise ImputationError("no usable donor distributions")

    # Donor ranking already encodes similarity. Fixed rank weights avoid using outcomes in selection.
    rank_weights = [1.0 / (index + 1) for index in range(len(donor_distributions))]
    weight_total = sum(rank_weights)
    central_raw: dict[str, float] = {}
    for category in category_set:
        central_raw[category] = sum(
            rank_weights[index] * distribution[category]
            for index, (_, distribution) in enumerate(donor_distributions)
        ) / weight_total
    central_total = sum(central_raw.values())
    central = {category: central_raw[category] / central_total for category in category_set}

    result: dict[str, tuple[float, float, float]] = {}
    for category in category_set:
        values = sorted(distribution[category] for _, distribution in donor_distributions)
        lower = _quantile(values, policy.interval_quantile_lower)
        upper = _quantile(values, policy.interval_quantile_upper)
        minimum = policy.minimum_relative_interval
        lower = min(lower, central[category] * (1.0 - minimum))
        upper = max(upper, central[category] * (1.0 + minimum))
        result[category] = (central[category], max(0.0, lower), upper)
    return result


def _fallback_distribution(
    target: str,
    profiles: Mapping[str, EconomyProfile],
    core_vectors: Mapping[str, Mapping[str, float]],
    categories: Sequence[str],
    policy: ImputationPolicy,
) -> tuple[dict[str, tuple[float, float, float]], str]:
    region = profiles[target].region_code
    regional = [
        economy
        for economy in sorted(core_vectors)
        if economy != target and economy in profiles and profiles[economy].region_code == region
    ]
    if regional:
        return _template_distribution(core_vectors, regional, categories, policy), "REGIONAL"
    global_pool = [economy for economy in sorted(core_vectors) if economy != target]
    if not global_pool:
        raise ImputationError(f"no regional or global fallback available for {target}")
    return _template_distribution(core_vectors, global_pool, categories, policy), "GLOBAL"


def _bounded_interval(central: float, lower: float, upper: float, minimum_relative: float) -> tuple[float, float]:
    floor = max(central * (1.0 - minimum_relative), 1e-15)
    ceiling = central * (1.0 + minimum_relative)
    result_lower = min(lower, floor)
    result_upper = max(upper, ceiling)
    if result_lower <= 0:
        result_lower = max(central * 1e-6, 1e-15)
    if not result_lower < central < result_upper:
        raise ImputationError("failed to construct non-zero interval around imputed value")
    return result_lower, result_upper


def _validation_summary(predictions: Sequence[ValidationPrediction]) -> dict:
    if not predictions:
        raise ImputationError("validation produced no predictions")
    absolute_errors = [item.absolute_error for item in predictions]
    percentage_errors = [item.absolute_percentage_error for item in predictions if math.isfinite(item.absolute_percentage_error)]
    errors = [item.error for item in predictions]
    return {
        "mae": statistics.fmean(absolute_errors),
        "mape": statistics.fmean(percentage_errors),
        "bias": statistics.fmean(errors),
        "interval_coverage": statistics.fmean(1.0 if item.covered else 0.0 for item in predictions),
    }


def _grouped_metrics(predictions: Sequence[ValidationPrediction], attribute: str) -> list[dict]:
    groups: dict[str, list[ValidationPrediction]] = defaultdict(list)
    for prediction in predictions:
        groups[str(getattr(prediction, attribute))].append(prediction)
    rows: list[dict] = []
    for key, items in sorted(groups.items()):
        summary = _validation_summary(items)
        rows.append({attribute: key, "count": len(items), **{name: _number(value) for name, value in summary.items()}})
    return rows


def _cell_fields() -> list[str]:
    return [
        "economy_code",
        "category_code",
        "real_expenditure_central",
        "real_expenditure_lower",
        "real_expenditure_upper",
        "evidence_class",
        "method_id",
        "model_version",
        "source_ids",
        "donor_economies",
        "validation_mae",
        "validation_bias",
        "notes",
    ]


def _cell_row(cell: WeightCell) -> dict:
    return {
        "economy_code": cell.economy_code,
        "category_code": cell.category_code,
        "real_expenditure_central": _number(cell.real_expenditure_central),
        "real_expenditure_lower": _number(cell.real_expenditure_lower),
        "real_expenditure_upper": _number(cell.real_expenditure_upper),
        "evidence_class": cell.evidence_class.value,
        "method_id": cell.method_id,
        "model_version": cell.model_version,
        "source_ids": "|".join(cell.source_ids),
        "donor_economies": "|".join(cell.donor_economies),
        "validation_mae": "" if cell.validation_mae is None else _number(cell.validation_mae),
        "validation_bias": "" if cell.validation_bias is None else _number(cell.validation_bias),
        "notes": cell.notes,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str] | None = None) -> None:
    fields = list(fieldnames or (list(rows[0].keys()) if rows else []))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ImputationError("cannot calculate a quantile from no values")
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return values[lower_index]
    fraction = position - lower_index
    return values[lower_index] * (1.0 - fraction) + values[upper_index] * fraction


def _reject_duplicate_cells(cells: Iterable[WeightCell]) -> None:
    seen: set[tuple[str, str]] = set()
    for cell in cells:
        key = (cell.economy_code, cell.category_code)
        if key in seen:
            raise ImputationError(f"duplicate evidence cell: {key}")
        seen.add(key)


def _first_float(row: Mapping[str, str], *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return float(value)
    raise ImputationError(f"missing numeric field; expected one of {names}")


def _optional_float(value: str | None, default: float) -> float:
    return default if value is None or not str(value).strip() else float(value)


def _nullable_float(value: str | None) -> float | None:
    return None if value is None or not str(value).strip() else float(value)


def _number(value: float) -> str:
    return format(value, ".17g")
