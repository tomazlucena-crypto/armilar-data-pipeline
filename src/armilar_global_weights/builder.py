from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Iterable

from .models import CATEGORIES, EvidenceClass, WeightCell, parse_list

getcontext().prec = 50


class BuildError(ValueError):
    """Raised when a global-weight release would violate its contract."""


def load_cells(path: Path) -> list[WeightCell]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise BuildError("input contains no cells")
    cells: list[WeightCell] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            evidence = EvidenceClass(row["evidence_class"].strip())
            cell = WeightCell(
                economy_code=row["economy_code"].strip().upper(),
                category_code=row["category_code"].strip().upper(),
                real_expenditure_central=float(row["real_expenditure_central"]),
                real_expenditure_lower=float(row["real_expenditure_lower"]),
                real_expenditure_upper=float(row["real_expenditure_upper"]),
                evidence_class=evidence,
                method_id=row["method_id"].strip(),
                model_version=row["model_version"].strip(),
                source_ids=parse_list(row.get("source_ids")),
                donor_economies=parse_list(row.get("donor_economies")),
                validation_mae=_optional_float(row.get("validation_mae")),
                validation_bias=_optional_float(row.get("validation_bias")),
                notes=(row.get("notes") or "").strip(),
            )
            cell.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise BuildError(f"invalid cell at CSV line {line_number}: {exc}") from exc
        cells.append(cell)
    return cells


def validate_complete_grid(cells: Iterable[WeightCell]) -> tuple[str, ...]:
    cell_list = list(cells)
    keys = [(cell.economy_code, cell.category_code) for cell in cell_list]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        raise BuildError(f"duplicate economy-category cells: {duplicates[:5]}")
    economies = tuple(sorted({cell.economy_code for cell in cell_list}))
    expected = {(economy, category) for economy in economies for category in CATEGORIES}
    actual = set(keys)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={missing[:10]}")
        if extra:
            details.append(f"extra={extra[:10]}")
        raise BuildError("global grid is incomplete: " + "; ".join(details))
    if len(cell_list) != len(economies) * len(CATEGORIES):
        raise BuildError("global grid cardinality is inconsistent")
    return economies


def build_release(cells: Iterable[WeightCell], output_dir: Path, release_id: str = "ARM-WEIGHTS-GLOBAL-RESEARCH") -> dict:
    cell_list = sorted(cells, key=lambda cell: (cell.economy_code, cell.category_code))
    for cell in cell_list:
        cell.validate()
    economies = validate_complete_grid(cell_list)
    output_dir.mkdir(parents=True, exist_ok=True)

    central_total = sum(Decimal(str(cell.real_expenditure_central)) for cell in cell_list)
    if central_total <= 0:
        raise BuildError("central expenditure total must be positive")

    central_weights: dict[tuple[str, str], Decimal] = {}
    lower_weights: dict[tuple[str, str], Decimal] = {}
    upper_weights: dict[tuple[str, str], Decimal] = {}
    sum_lower = sum(Decimal(str(cell.real_expenditure_lower)) for cell in cell_list)
    sum_upper = sum(Decimal(str(cell.real_expenditure_upper)) for cell in cell_list)

    for cell in cell_list:
        key = (cell.economy_code, cell.category_code)
        central = Decimal(str(cell.real_expenditure_central))
        lower = Decimal(str(cell.real_expenditure_lower))
        upper = Decimal(str(cell.real_expenditure_upper))
        central_weights[key] = central / central_total
        lower_denominator = lower + (sum_upper - upper)
        upper_denominator = upper + (sum_lower - lower)
        lower_weights[key] = lower / lower_denominator
        upper_weights[key] = upper / upper_denominator
        if not lower_weights[key] <= central_weights[key] <= upper_weights[key]:
            raise BuildError(f"normalised bounds do not contain central weight for {key}")

    global_rows = []
    uncertainty_rows = []
    audit_rows = []
    evidence_weight_shares: dict[str, Decimal] = defaultdict(Decimal)
    for cell in cell_list:
        key = (cell.economy_code, cell.category_code)
        central_weight = central_weights[key]
        evidence_weight_shares[cell.evidence_class.value] += central_weight
        global_rows.append({
            "economy_code": cell.economy_code,
            "category_code": cell.category_code,
            "weight": _decimal_text(central_weight),
            "evidence_class": cell.evidence_class.value,
            "method_id": cell.method_id,
            "model_version": cell.model_version,
        })
        uncertainty_rows.append({
            "economy_code": cell.economy_code,
            "category_code": cell.category_code,
            "weight_lower": _decimal_text(lower_weights[key]),
            "weight_central": _decimal_text(central_weight),
            "weight_upper": _decimal_text(upper_weights[key]),
        })
        audit_rows.append({
            "economy_code": cell.economy_code,
            "category_code": cell.category_code,
            "evidence_class": cell.evidence_class.value,
            "real_expenditure_lower": _float_text(cell.real_expenditure_lower),
            "real_expenditure_central": _float_text(cell.real_expenditure_central),
            "real_expenditure_upper": _float_text(cell.real_expenditure_upper),
            "method_id": cell.method_id,
            "model_version": cell.model_version,
            "source_ids": "|".join(cell.source_ids),
            "donor_economies": "|".join(cell.donor_economies),
            "validation_mae": "" if cell.validation_mae is None else _float_text(cell.validation_mae),
            "validation_bias": "" if cell.validation_bias is None else _float_text(cell.validation_bias),
            "notes": cell.notes,
        })

    core_cells = [cell for cell in cell_list if cell.evidence_class.is_core]
    core_total = sum(Decimal(str(cell.real_expenditure_central)) for cell in core_cells)
    core_rows = []
    if core_total > 0:
        for cell in core_cells:
            core_rows.append({
                "economy_code": cell.economy_code,
                "category_code": cell.category_code,
                "observed_universe_weight": _decimal_text(Decimal(str(cell.real_expenditure_central)) / core_total),
                "global_weight": _decimal_text(central_weights[(cell.economy_code, cell.category_code)]),
                "evidence_class": cell.evidence_class.value,
            })

    _write_csv(output_dir / "weights_global.csv", global_rows)
    _write_csv(output_dir / "weights_uncertainty.csv", uncertainty_rows)
    _write_csv(output_dir / "weights_method_audit.csv", audit_rows)
    _write_csv(output_dir / "weights_core.csv", core_rows, fieldnames=[
        "economy_code", "category_code", "observed_universe_weight", "global_weight", "evidence_class"
    ])

    coverage = {
        "release_id": release_id,
        "policy_version": "2.0",
        "economy_count": len(economies),
        "cell_count": len(cell_list),
        "complete_grid": True,
        "weight_sum": float(sum(central_weights.values())),
        "core_global_weight_share": float(sum(central_weights[(cell.economy_code, cell.category_code)] for cell in core_cells)),
        "estimated_global_weight_share": float(sum(central_weights[(cell.economy_code, cell.category_code)] for cell in cell_list if cell.evidence_class.is_estimated)),
        "evidence_weight_shares": {key: float(value) for key, value in sorted(evidence_weight_shares.items())},
        "monetary_release_allowed": False,
    }
    uncertainty = {
        "release_id": release_id,
        "method": "cellwise_conservative_compositional_bounds",
        "minimum_lower_weight": float(min(lower_weights.values())),
        "maximum_upper_weight": float(max(upper_weights.values())),
        "estimated_cell_count": sum(cell.evidence_class.is_estimated for cell in cell_list),
        "core_cell_count": len(core_cells),
    }
    _write_json(output_dir / "coverage_summary.json", coverage)
    _write_json(output_dir / "uncertainty_summary.json", uncertainty)

    manifest_path = output_dir / "MANIFEST.sha256"
    manifest_entries = _write_manifest(output_dir, manifest_path)
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    release_summary = {
        **coverage,
        "manifest_sha256": manifest_hash,
        "manifest_entry_count": len(manifest_entries),
    }
    _write_json(output_dir / "global_weight_release.json", release_summary)
    return release_summary


def _optional_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    return float(value)


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000000000001")), "f")


def _float_text(value: float) -> str:
    return format(value, ".17g")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_manifest(output_dir: Path, manifest_path: Path) -> list[str]:
    excluded = {manifest_path.name, "global_weight_release.json"}
    paths = sorted(path for path in output_dir.iterdir() if path.is_file() and path.name not in excluded)
    entries = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in paths]
    manifest_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return entries
