"""Closed mapping policy and canonical primitives for ARMILAR v0.9.9 proxy features."""
from __future__ import annotations

import csv
import io
import json
import re
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .archive_core_v098 import ProxyInformationSetError, canonical_json_bytes, canonical_text_bytes, parse_utc
from .core_v097 import sha256_bytes, sha256_file, utc_timestamp

CONTRACT_VERSION = "0.9.9"
FEATURE_PANEL_STATUS = "POINT_IN_TIME_PROXY_FEATURE_PANEL_V099_VALID"
POLICY_ID = "ARMILAR_PROXY_FEATURE_MAPPING_V099"

FALSE_GATES = (
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
    "shadow_production_allowed",
    "monetary_use_allowed",
    "price_coverage_claim_allowed",
    "model_ready_claim_allowed",
    "backtest_eligibility_claim_allowed",
    "concordance_approval_claim_allowed",
)

VALID_FREQUENCIES = {"WEEKLY", "MONTHLY", "QUARTERLY"}
VALID_MATCH_TYPES = {"EXACT", "PREFIX"}
VALID_SCOPES = {"GLOBAL_BROADCAST", "SOURCE_GEOGRAPHY"}
VALID_ROLES = {"PRIMARY_RESEARCH_DRIVER", "SENSITIVITY_ONLY"}
VALID_AGGREGATIONS = {"MONTHLY_DIRECT", "WEEKLY_MEAN_TO_MONTH", "QUARTER_END_DIRECT"}
VALID_EVIDENCE = {"PARTIAL_COST_DRIVER", "SENSITIVITY_ONLY"}
VALID_TRANSFORMATIONS = {"LEVEL", "PERIOD_CHANGE_PCT", "YEAR_OVER_YEAR_PCT"}

CP_TO_ARM = {
    "CP01": "ARM01",
    "CP02": "ARM02",
    "CP03": "ARM03",
    "CP04": "ARM04",
    "CP05": "ARM04",
    "CP06": "ARM05",
    "CP07": "ARM06",
    "CP08": "ARM06",
    "CP09": "ARM07",
    "CP10": "ARM07",
    "CP11": "ARM08",
    "CP12": "ARM09",
}

FEATURE_COLUMNS = [
    "feature_id",
    "cutoff",
    "mapping_id",
    "source_id",
    "series_id",
    "source_proxy_domain",
    "source_geography",
    "target_economy_code",
    "target_category_code",
    "target_armilar_category",
    "feature_role",
    "mapping_evidence",
    "native_frequency",
    "target_frequency",
    "target_period",
    "target_period_end",
    "feature_age_days",
    "period_completeness_status",
    "transformation",
    "value",
    "unit",
    "aggregation_method",
    "component_count",
    "component_observation_keys_sha256",
    "latest_available_at",
    "source_freshness_status",
    "direct_index_use_allowed",
    "arm_l_use_allowed",
    "model_training_allowed",
]

CELL_COVERAGE_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "primary_feature_count",
    "sensitivity_feature_count",
    "current_primary_source_count",
    "stale_primary_source_count",
    "primary_source_ids",
    "sensitivity_source_ids",
    "latest_primary_target_period",
    "latest_sensitivity_target_period",
    "minimum_primary_feature_age_days",
    "maximum_primary_feature_age_days",
    "coverage_status",
    "price_coverage_claim_allowed",
]

MAPPING_AUDIT_COLUMNS = [
    "mapping_id",
    "source_id",
    "series_match_type",
    "series_match_value",
    "target_scope",
    "target_category_code",
    "target_armilar_category",
    "feature_role",
    "matched_input_observation_count",
    "mapped_target_observation_count",
    "distinct_source_geography_count",
    "first_source_period",
    "last_source_period",
]

UNMAPPED_COLUMNS = [
    "source_id",
    "series_id",
    "proxy_domain",
    "geography",
    "frequency",
    "reason",
    "observation_count",
]

STREAM_HISTORY_COLUMNS = [
    "stream_id",
    "mapping_id",
    "source_id",
    "series_id",
    "source_geography",
    "target_economy_code",
    "target_category_code",
    "feature_role",
    "native_frequency",
    "source_freshness_status",
    "expected_period_step_months",
    "first_target_period",
    "last_target_period",
    "observed_level_period_count",
    "complete_level_period_count",
    "partial_level_period_count",
    "missing_expected_period_count",
    "longest_gap_months_beyond_expected",
    "history_span_months",
    "period_change_count",
    "year_over_year_count",
    "latest_feature_age_days",
    "research_diagnostic_status",
    "backtest_eligibility_claim_allowed",
    "model_ready_claim_allowed",
]

CELL_PERIOD_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "target_period",
    "fixed_universe_weight",
    "primary_stream_count",
    "sensitivity_stream_count",
    "current_primary_source_count",
    "stale_primary_source_count",
    "complete_primary_stream_count",
    "partial_primary_stream_count",
    "primary_source_ids",
    "sensitivity_source_ids",
    "period_status",
    "price_coverage_claim_allowed",
]

CONCORDANCE_COLUMNS = [
    "target_economy_code",
    "target_category_code",
    "transformation",
    "left_stream_id",
    "right_stream_id",
    "left_source_id",
    "left_series_id",
    "right_source_id",
    "right_series_id",
    "overlap_period_count",
    "first_overlap_period",
    "last_overlap_period",
    "direction_agreement_count",
    "direction_disagreement_count",
    "direction_agreement_ratio",
    "mean_absolute_spread",
    "maximum_absolute_spread",
    "pearson_correlation",
    "concordance_status",
    "concordance_approval_claim_allowed",
    "model_ready_claim_allowed",
]

CELL_DIAGNOSTIC_COLUMNS = [
    "economy_code",
    "economy_name",
    "category_code",
    "fixed_universe_weight",
    "distinct_primary_stream_count",
    "distinct_primary_source_count",
    "first_complete_primary_period",
    "last_complete_primary_period",
    "complete_primary_period_count",
    "complete_multi_source_period_count",
    "longest_contiguous_primary_months",
    "period_change_available",
    "year_over_year_available",
    "current_source_present",
    "stale_source_only",
    "diagnostic_class",
    "backtest_eligibility_claim_allowed",
    "model_ready_claim_allowed",
]


class ProxyFeatureError(ProxyInformationSetError):
    """Raised when the v0.9.9 feature contract is violated."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProxyFeatureError(f"{label} must be an object")
    return value


def _nonempty_string(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProxyFeatureError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def canonical_alias(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def validate_policy(value: Any) -> None:
    policy = _object(value, "policy")
    expected_root = {
        "contract_id",
        "contract_version",
        "upstream_information_set_version",
        "constitutional_scope",
        "mapping_policy",
        "geography_aliases",
        "category_mappings",
        "transformation_policy",
        "diagnostic_policy",
        "output_gates",
    }
    if set(policy) != expected_root:
        raise ProxyFeatureError("policy root keys do not match the closed v0.9.9 contract")
    if policy.get("contract_id") != POLICY_ID:
        raise ProxyFeatureError("unexpected feature mapping contract_id")
    if policy.get("contract_version") != CONTRACT_VERSION:
        raise ProxyFeatureError("unexpected feature mapping contract_version")
    if policy.get("upstream_information_set_version") != "0.9.8":
        raise ProxyFeatureError("unexpected upstream information-set version")
    if policy.get("constitutional_scope") != "RESEARCH_CORE_ENGINE_DEVELOPMENT_ONLY":
        raise ProxyFeatureError("constitutional scope changed")

    mapping_policy = _object(policy.get("mapping_policy"), "mapping_policy")
    expected_mapping_policy = {
        "unmapped_series_retained_in_audit",
        "unresolved_geography_retained_in_audit",
        "global_features_broadcast_only_to_basket_economies",
        "sensitivity_features_excluded_from_primary_coverage",
        "source_freshness_propagated",
        "no_value_imputation",
        "no_carry_forward",
        "no_future_periods",
        "no_silent_rule_overlap",
        "outside_research_core_retained_in_audit",
    }
    if set(mapping_policy) != expected_mapping_policy:
        raise ProxyFeatureError("mapping_policy keys do not match the closed contract")
    if any(mapping_policy.get(key) is not True for key in expected_mapping_policy):
        raise ProxyFeatureError("all mapping_policy invariants must remain true")

    aliases = _object(policy.get("geography_aliases"), "geography_aliases")
    if not aliases:
        raise ProxyFeatureError("geography_aliases cannot be empty")
    canonical_seen: set[str] = set()
    for raw, code in aliases.items():
        if not isinstance(raw, str) or not raw.strip():
            raise ProxyFeatureError("geography alias keys must be non-empty strings")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{3}", code):
            raise ProxyFeatureError(f"invalid economy code for geography alias: {raw}")
        canonical = canonical_alias(raw)
        if not canonical or canonical in canonical_seen:
            raise ProxyFeatureError(f"duplicate canonical geography alias: {raw}")
        canonical_seen.add(canonical)

    mappings = policy.get("category_mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ProxyFeatureError("category_mappings must be a non-empty array")
    mapping_ids: set[str] = set()
    exact_keys: set[tuple[str, str]] = set()
    prefix_keys: set[tuple[str, str]] = set()
    source_prefixes: dict[str, list[str]] = {}
    for index, raw in enumerate(mappings):
        label = f"category_mappings[{index}]"
        item = _object(raw, label)
        expected = {
            "mapping_id",
            "source_id",
            "series_match",
            "required_proxy_domain",
            "target_scope",
            "target_category_code",
            "target_armilar_category",
            "feature_role",
            "allowed_frequency",
            "aggregation_method",
            "mapping_evidence",
        }
        if set(item) != expected:
            raise ProxyFeatureError(f"{label} keys do not match the closed contract")
        mapping_id = _nonempty_string(item, "mapping_id", label)
        if mapping_id in mapping_ids:
            raise ProxyFeatureError(f"duplicate mapping_id: {mapping_id}")
        mapping_ids.add(mapping_id)
        source_id = _nonempty_string(item, "source_id", label)
        match = _object(item.get("series_match"), f"{label}.series_match")
        if set(match) != {"type", "value"}:
            raise ProxyFeatureError(f"{label}.series_match keys changed")
        match_type = _nonempty_string(match, "type", f"{label}.series_match")
        match_value = _nonempty_string(match, "value", f"{label}.series_match")
        if match_type not in VALID_MATCH_TYPES:
            raise ProxyFeatureError(f"invalid series match type: {mapping_id}")
        key = (source_id, match_value)
        if match_type == "EXACT":
            if key in exact_keys:
                raise ProxyFeatureError(f"duplicate exact series rule: {key}")
            exact_keys.add(key)
        else:
            if key in prefix_keys:
                raise ProxyFeatureError(f"duplicate prefix series rule: {key}")
            prefix_keys.add(key)
            source_prefixes.setdefault(source_id, []).append(match_value)
        domain = _nonempty_string(item, "required_proxy_domain", label)
        if not re.fullmatch(r"[A-Z0-9_]+", domain):
            raise ProxyFeatureError(f"invalid required_proxy_domain: {mapping_id}")
        scope = _nonempty_string(item, "target_scope", label)
        if scope not in VALID_SCOPES:
            raise ProxyFeatureError(f"invalid target_scope: {mapping_id}")
        category = _nonempty_string(item, "target_category_code", label)
        armilar = _nonempty_string(item, "target_armilar_category", label)
        if category not in CP_TO_ARM or CP_TO_ARM[category] != armilar:
            raise ProxyFeatureError(f"category mapping is inconsistent: {mapping_id}")
        role = _nonempty_string(item, "feature_role", label)
        if role not in VALID_ROLES:
            raise ProxyFeatureError(f"invalid feature_role: {mapping_id}")
        frequency = _nonempty_string(item, "allowed_frequency", label)
        if frequency not in VALID_FREQUENCIES:
            raise ProxyFeatureError(f"invalid allowed_frequency: {mapping_id}")
        aggregation = _nonempty_string(item, "aggregation_method", label)
        expected_aggregation = {
            "MONTHLY": "MONTHLY_DIRECT",
            "WEEKLY": "WEEKLY_MEAN_TO_MONTH",
            "QUARTERLY": "QUARTER_END_DIRECT",
        }[frequency]
        if aggregation != expected_aggregation or aggregation not in VALID_AGGREGATIONS:
            raise ProxyFeatureError(f"aggregation does not match frequency: {mapping_id}")
        evidence = _nonempty_string(item, "mapping_evidence", label)
        if evidence not in VALID_EVIDENCE:
            raise ProxyFeatureError(f"invalid mapping_evidence: {mapping_id}")
        if role == "SENSITIVITY_ONLY" and evidence != "SENSITIVITY_ONLY":
            raise ProxyFeatureError(f"sensitivity mapping evidence mismatch: {mapping_id}")
        if role != "SENSITIVITY_ONLY" and evidence == "SENSITIVITY_ONLY":
            raise ProxyFeatureError(f"primary mapping cannot use sensitivity evidence: {mapping_id}")

    # A prefix may not overlap another prefix for the same source. Exact matches are
    # permitted alongside a prefix only when the exact value does not start with it.
    for source_id, prefixes in source_prefixes.items():
        ordered = sorted(prefixes)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                if left.startswith(right) or right.startswith(left):
                    raise ProxyFeatureError(f"overlapping prefix rules for {source_id}: {left}, {right}")
        for exact_source, exact_value in exact_keys:
            if exact_source == source_id and any(exact_value.startswith(prefix) for prefix in prefixes):
                raise ProxyFeatureError(f"exact and prefix rules overlap for {source_id}: {exact_value}")

    transformation = _object(policy.get("transformation_policy"), "transformation_policy")
    expected_transformation = {
        "target_frequency",
        "transformations",
        "decimal_precision",
        "output_decimal_places",
        "zero_denominator_policy",
        "exact_calendar_lag_required",
        "weekly_aggregation",
        "monthly_aggregation",
        "quarterly_aggregation",
    }
    if set(transformation) != expected_transformation:
        raise ProxyFeatureError("transformation_policy keys do not match the closed contract")
    if transformation.get("target_frequency") != "MONTHLY":
        raise ProxyFeatureError("target feature frequency must remain MONTHLY")
    transformations = transformation.get("transformations")
    if transformations != ["LEVEL", "PERIOD_CHANGE_PCT", "YEAR_OVER_YEAR_PCT"]:
        raise ProxyFeatureError("feature transformations changed")
    if set(transformations) != VALID_TRANSFORMATIONS:
        raise ProxyFeatureError("unexpected feature transformation")
    if transformation.get("decimal_precision") != 28:
        raise ProxyFeatureError("decimal precision must remain 28")
    places = transformation.get("output_decimal_places")
    if not isinstance(places, int) or not 6 <= places <= 18:
        raise ProxyFeatureError("output_decimal_places must be between 6 and 18")
    if transformation.get("zero_denominator_policy") != "OMIT_TRANSFORMATION":
        raise ProxyFeatureError("zero denominator policy changed")
    if transformation.get("exact_calendar_lag_required") is not True:
        raise ProxyFeatureError("exact calendar lag must remain required")
    if transformation.get("weekly_aggregation") != "ARITHMETIC_MEAN_BY_CALENDAR_MONTH":
        raise ProxyFeatureError("weekly aggregation changed")
    if transformation.get("monthly_aggregation") != "IDENTITY":
        raise ProxyFeatureError("monthly aggregation changed")
    if transformation.get("quarterly_aggregation") != "QUARTER_END_MONTH_ONLY":
        raise ProxyFeatureError("quarterly aggregation changed")

    diagnostic = _object(policy.get("diagnostic_policy"), "diagnostic_policy")
    expected_diagnostic = {
        "long_history_min_complete_periods",
        "multi_source_min_complete_periods",
        "concordance_min_overlap_periods",
        "concordance_complete_periods_only",
        "availability_lag_diagnostic_days",
        "provenance_concentration_diagnostic_percent",
        "no_automatic_eligibility_promotion",
        "no_quality_weighting",
        "no_feature_selection",
        "no_model_scoring",
        "no_aggregate_risk_score",
        "no_eligibility_from_risk_flags",
    }
    if set(diagnostic) != expected_diagnostic:
        raise ProxyFeatureError("diagnostic_policy keys do not match the closed contract")
    for key in (
        "long_history_min_complete_periods",
        "multi_source_min_complete_periods",
        "concordance_min_overlap_periods",
    ):
        value = diagnostic.get(key)
        if not isinstance(value, int) or value < 2 or value > 240:
            raise ProxyFeatureError(f"invalid diagnostic threshold: {key}")
    availability_lag = diagnostic.get("availability_lag_diagnostic_days")
    if not isinstance(availability_lag, int) or availability_lag < 1 or availability_lag > 3650:
        raise ProxyFeatureError("invalid diagnostic threshold: availability_lag_diagnostic_days")
    concentration = diagnostic.get("provenance_concentration_diagnostic_percent")
    if not isinstance(concentration, int) or concentration < 50 or concentration > 100:
        raise ProxyFeatureError("invalid diagnostic threshold: provenance_concentration_diagnostic_percent")
    if diagnostic["multi_source_min_complete_periods"] > diagnostic["long_history_min_complete_periods"]:
        raise ProxyFeatureError("multi-source diagnostic threshold cannot exceed long-history threshold")
    for key in (
        "concordance_complete_periods_only",
        "no_automatic_eligibility_promotion",
        "no_quality_weighting",
        "no_feature_selection",
        "no_model_scoring",
        "no_aggregate_risk_score",
        "no_eligibility_from_risk_flags",
    ):
        if diagnostic.get(key) is not True:
            raise ProxyFeatureError(f"diagnostic invariant must remain true: {key}")

    gates = _object(policy.get("output_gates"), "output_gates")
    if set(gates) != set(FALSE_GATES):
        raise ProxyFeatureError("output gate keys do not match the closed contract")
    if any(gates.get(key) is not False for key in FALSE_GATES):
        raise ProxyFeatureError("all v0.9.9 output gates must remain false")


def load_policy(path: Path) -> dict[str, Any]:
    try:
        payload = canonical_text_bytes(path.read_bytes())
        policy = json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxyFeatureError(f"cannot load v0.9.9 feature policy: {path}") from exc
    validate_policy(policy)
    return policy


def policy_hash(path: Path) -> str:
    return sha256_bytes(canonical_text_bytes(path.read_bytes()))


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        text = canonical_text_bytes(path.read_bytes()).decode("utf-8")
    except OSError as exc:
        raise ProxyFeatureError(f"cannot read CSV: {path}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ProxyFeatureError(f"CSV has no header: {path}")
    return [{str(k): str(v or "") for k, v in row.items()} for row in reader]


def csv_bytes(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for raw in rows:
        writer.writerow({key: raw.get(key, "") for key in columns})
    return stream.getvalue().encode("utf-8")


def false_text() -> str:
    return "false"


def decimal_value(value: Any) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ProxyFeatureError(f"invalid decimal value: {value!r}") from exc
    if not result.is_finite():
        raise ProxyFeatureError(f"non-finite decimal value: {value!r}")
    return result


def decimal_text(value: Decimal, places: int) -> str:
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = 28
        rounded = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, f".{places}f")


def percent_change(current: Decimal, previous: Decimal, places: int) -> str | None:
    if previous == 0:
        return None
    with localcontext() as context:
        context.prec = 28
        result = (current / previous - Decimal(1)) * Decimal(100)
    return decimal_text(result, places)


def month_key(period: str, frequency: str) -> str:
    if frequency == "MONTHLY":
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
            raise ProxyFeatureError(f"invalid monthly period: {period}")
        return period
    if frequency == "WEEKLY":
        try:
            return date.fromisoformat(period).strftime("%Y-%m")
        except ValueError as exc:
            raise ProxyFeatureError(f"invalid weekly period: {period}") from exc
    if frequency == "QUARTERLY":
        match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
        if not match:
            raise ProxyFeatureError(f"invalid quarterly period: {period}")
        month = int(match.group(2)) * 3
        return f"{match.group(1)}-{month:02d}"
    raise ProxyFeatureError(f"unsupported frequency: {frequency}")


def shift_month(period: str, months: int) -> str:
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", period)
    if not match:
        raise ProxyFeatureError(f"invalid target month: {period}")
    year = int(match.group(1))
    month = int(match.group(2))
    serial = year * 12 + (month - 1) + months
    if serial < 0:
        raise ProxyFeatureError("target month shift underflow")
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"



def target_period_metadata(target_period: str, cutoff: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", target_period)
    if not match:
        raise ProxyFeatureError(f"invalid target month: {target_period}")
    year = int(match.group(1))
    month = int(match.group(2))
    end = date(year, month, monthrange(year, month)[1])
    cutoff_date = parse_utc(utc_timestamp(cutoff)).date()
    if (year, month) > (cutoff_date.year, cutoff_date.month):
        raise ProxyFeatureError("target period is after cutoff month")
    if (year, month) == (cutoff_date.year, cutoff_date.month) and cutoff_date < end:
        return end.isoformat(), 0, "PARTIAL_PERIOD_AS_OF_CUTOFF"
    return end.isoformat(), (cutoff_date - end).days, "COMPLETE_PERIOD"

def target_month_not_after_cutoff(target_period: str, cutoff: str) -> bool:
    cutoff_date = parse_utc(utc_timestamp(cutoff)).date()
    year, month = (int(part) for part in target_period.split("-"))
    return (year, month) <= (cutoff_date.year, cutoff_date.month)


def mapping_for_row(policy: Mapping[str, Any], row: Mapping[str, str]) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for mapping in policy["category_mappings"]:
        if mapping["source_id"] != row.get("source_id"):
            continue
        if mapping["required_proxy_domain"] != row.get("proxy_domain"):
            continue
        match = mapping["series_match"]
        series = row.get("series_id", "")
        matched = series == match["value"] if match["type"] == "EXACT" else series.startswith(match["value"])
        if matched:
            matches.append(mapping)
    if len(matches) > 1:
        raise ProxyFeatureError(
            f"multiple mapping rules matched {row.get('source_id')}:{row.get('series_id')}: "
            + ",".join(item["mapping_id"] for item in matches)
        )
    return matches[0] if matches else None


def resolve_geography(policy: Mapping[str, Any], geography: str) -> str | None:
    aliases = {canonical_alias(key): value for key, value in policy["geography_aliases"].items()}
    return aliases.get(canonical_alias(geography))


def month_index(period: str) -> int:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
        raise ProxyFeatureError(f"invalid monthly period: {period}")
    year, month = map(int, period.split("-"))
    return year * 12 + month - 1


def months_inclusive(first: str, last: str) -> int:
    distance = month_index(last) - month_index(first)
    if distance < 0:
        raise ProxyFeatureError("monthly period range is reversed")
    return distance + 1


def month_range(first: str, last: str) -> list[str]:
    count = months_inclusive(first, last)
    return [shift_month(first, offset) for offset in range(count)]


def stream_identity(row: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        "mapping_id",
        "source_id",
        "series_id",
        "source_geography",
        "target_economy_code",
        "target_category_code",
    )
    result: dict[str, str] = {}
    for key in keys:
        value = str(row.get(key, "")).strip()
        if not value:
            raise ProxyFeatureError(f"stream identity field is empty: {key}")
        result[key] = value
    return result


def stream_id(row: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(stream_identity(row)))


def feature_identity(row: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        "cutoff",
        "mapping_id",
        "source_id",
        "series_id",
        "source_geography",
        "target_economy_code",
        "target_category_code",
        "target_period",
        "transformation",
        "unit",
    )
    result: dict[str, str] = {}
    for key in keys:
        value = str(row.get(key, "")).strip()
        if not value:
            raise ProxyFeatureError(f"feature identity field is empty: {key}")
        result[key] = value
    return result


def feature_id(row: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(feature_identity(row)))


def component_hash(keys: Iterable[str]) -> str:
    clean = sorted(str(item).strip() for item in keys if str(item).strip())
    if not clean:
        raise ProxyFeatureError("feature aggregation has no component observation keys")
    return sha256_bytes(canonical_json_bytes(clean))


def manifest_bytes(entries: Mapping[str, str]) -> bytes:
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())).encode("utf-8")


def write_manifest(root: Path, names: Iterable[str]) -> str:
    entries = {name: sha256_file(root / name) for name in names}
    payload = manifest_bytes(entries)
    (root / "MANIFEST.sha256").write_bytes(payload)
    return sha256_bytes(payload)
