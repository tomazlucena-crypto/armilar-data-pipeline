from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Iterable

from .util import normalize_text
from .worldbank import Observation, Variable


@dataclass(frozen=True)
class MeasureSelection:
    ppp_id: str
    nominal_id: str
    real_id: str
    diagnostics: list[dict[str, str]]


def semantic_kind(name: str) -> str:
    text = normalize_text(name)
    forbidden = ("per capita", "index", "share", "percentage", "percent")
    if any(token in text for token in forbidden):
        return "OTHER"
    if "purchasing power parity" in text or re_contains_ppp(text):
        if "expenditure" not in text and "price level" not in text:
            return "PPP"
    if "expenditure" in text:
        if any(token in text for token in ("local currency", "national currency", "lcu", "nominal")):
            return "NOMINAL_EXPENDITURE"
        if any(token in text for token in ("based on ppp", "ppp based", "real expenditure", "international dollar")) or "real" in text.split():
            return "REAL_EXPENDITURE"
    return "OTHER"


def re_contains_ppp(text: str) -> bool:
    words = text.split()
    return "ppp" in words or "ppps" in words


def select_measures(
    measure_variables: list[Variable], observations: Iterable[Observation], measure_concept: str,
    country_concept: str, heading_concept: str,
) -> MeasureSelection:
    candidates: dict[str, list[Variable]] = {"PPP": [], "NOMINAL_EXPENDITURE": [], "REAL_EXPENDITURE": []}
    diagnostics: list[dict[str, str]] = []
    for item in measure_variables:
        kind = semantic_kind(item.value)
        diagnostics.append(
            {
                "measure_id": item.variable_id,
                "measure_name": item.value,
                "semantic_kind": kind,
                "selected": "false",
            }
        )
        if kind in candidates:
            candidates[kind].append(item)
    missing = [kind for kind, values in candidates.items() if not values]
    if missing:
        raise ValueError(f"Could not find measure candidates for: {', '.join(missing)}")

    by_key: dict[tuple[str, str, str], Decimal] = {}
    for obs in observations:
        try:
            country = obs.variables[country_concept][0]
            heading = obs.variables[heading_concept][0]
            measure = obs.variables[measure_concept][0]
        except KeyError:
            continue
        key = (country, heading, measure)
        if key in by_key:
            raise ValueError(f"Duplicate observation for {key}")
        by_key[key] = obs.value

    scored: list[tuple[Decimal, int, str, str, str]] = []
    for ppp in candidates["PPP"]:
        for nominal in candidates["NOMINAL_EXPENDITURE"]:
            for real in candidates["REAL_EXPENDITURE"]:
                errors: list[float] = []
                for country, heading, _ in list(by_key.keys()):
                    p = by_key.get((country, heading, ppp.variable_id))
                    n = by_key.get((country, heading, nominal.variable_id))
                    r = by_key.get((country, heading, real.variable_id))
                    if p is None or n is None or r is None or p <= 0 or r == 0:
                        continue
                    errors.append(float(abs((n / p) - r) / abs(r)))
                if errors:
                    scored.append((Decimal(str(median(errors))), len(errors), ppp.variable_id, nominal.variable_id, real.variable_id))
    if not scored:
        if all(len(candidates[kind]) == 1 for kind in candidates):
            chosen = (
                candidates["PPP"][0].variable_id,
                candidates["NOMINAL_EXPENDITURE"][0].variable_id,
                candidates["REAL_EXPENDITURE"][0].variable_id,
            )
        else:
            raise ValueError("Measure selection is ambiguous and cannot be reconciled numerically")
    else:
        scored.sort(key=lambda item: (item[0], -item[1], item[2], item[3], item[4]))
        _, _, *chosen_list = scored[0]
        chosen = tuple(chosen_list)  # type: ignore[assignment]
    selected_ids = set(chosen)
    for row in diagnostics:
        if row["measure_id"] in selected_ids:
            row["selected"] = "true"
    return MeasureSelection(
        ppp_id=chosen[0], nominal_id=chosen[1], real_id=chosen[2], diagnostics=diagnostics
    )
