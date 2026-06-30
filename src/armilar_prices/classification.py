from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from armilar_global_weights.models import CATEGORIES as SOURCE_CATEGORIES

ARMILAR_CLASSIFICATION_ID = "ARMILAR_CONSUMPTION_CLASSIFICATION"
ARMILAR_CLASSIFICATION_VERSION = "1.0.0"
ARMILAR_CATEGORY_CODES = tuple(f"ARM{i:02d}" for i in range(1, 10))
STRICT_MAPPING_TYPES = frozenset({"EXACT_ONE_TO_ONE", "EXACT_MERGE"})
ALLOWED_MAPPING_TYPES = STRICT_MAPPING_TYPES | frozenset(
    {"WEIGHTED_SPLIT_OFFICIAL", "WEIGHTED_SPLIT_ESTIMATED", "UNMAPPED"}
)


class ClassificationError(ValueError):
    """Raised when a category classification or mapping is not auditable."""


@dataclass(frozen=True, slots=True)
class ArmilarCategory:
    category_code: str
    label: str
    description: str
    display_order: int

    def validate(self) -> None:
        if self.category_code not in ARMILAR_CATEGORY_CODES:
            raise ClassificationError(
                f"invalid Armilar category code: {self.category_code!r}"
            )
        if not self.label.strip() or not self.description.strip():
            raise ClassificationError(
                f"label and description are required for {self.category_code}"
            )
        expected_order = ARMILAR_CATEGORY_CODES.index(self.category_code) + 1
        if self.display_order != expected_order:
            raise ClassificationError(
                f"display_order mismatch for {self.category_code}: "
                f"{self.display_order} != {expected_order}"
            )


@dataclass(frozen=True, slots=True)
class ArmilarClassification:
    classification_id: str
    version: str
    status: str
    categories: tuple[ArmilarCategory, ...]
    global_exclusions: tuple[str, ...]
    raw_source_detail_preserved: bool
    monetary_release_allowed: bool

    @property
    def category_codes(self) -> tuple[str, ...]:
        return tuple(row.category_code for row in self.categories)

    def validate(self) -> None:
        if self.classification_id != ARMILAR_CLASSIFICATION_ID:
            raise ClassificationError(
                f"unexpected classification_id: {self.classification_id!r}"
            )
        if self.version != ARMILAR_CLASSIFICATION_VERSION:
            raise ClassificationError(
                f"unexpected classification version: {self.version!r}"
            )
        if self.status != "EXPERIMENTAL_RESEARCH":
            raise ClassificationError("classification must remain experimental")
        if self.category_codes != ARMILAR_CATEGORY_CODES:
            raise ClassificationError(
                "classification must contain ARM01 to ARM09 in order"
            )
        for row in self.categories:
            row.validate()
        if len(set(self.category_codes)) != len(self.category_codes):
            raise ClassificationError("duplicate Armilar categories")
        if not self.raw_source_detail_preserved:
            raise ClassificationError("raw source detail must be preserved")
        if self.monetary_release_allowed:
            raise ClassificationError("classification cannot authorise monetary release")
        if "NARCOTICS" not in self.global_exclusions:
            raise ClassificationError("narcotics exclusion must be explicit")


@dataclass(frozen=True, slots=True)
class CategoryMapping:
    mapping_id: str
    source_provider: str
    source_classification: str
    source_classification_version: str
    source_code: str
    source_label: str
    armilar_category: str
    mapping_type: str
    effective_from: str
    effective_to: str
    strict_pilot_admissible: bool
    bridge_status: str
    notes: str = ""

    def validate(self, classification: ArmilarClassification) -> None:
        if not self.mapping_id.strip():
            raise ClassificationError("mapping_id is required")
        if self.source_provider != "EUROSTAT":
            raise ClassificationError(
                f"unsupported mapping provider: {self.source_provider!r}"
            )
        if self.source_classification not in {"ECOICOP"}:
            raise ClassificationError(
                f"unsupported source classification: {self.source_classification!r}"
            )
        if self.mapping_type not in ALLOWED_MAPPING_TYPES:
            raise ClassificationError(
                f"unsupported mapping type: {self.mapping_type!r}"
            )
        if self.armilar_category not in classification.category_codes:
            raise ClassificationError(
                f"unknown Armilar category: {self.armilar_category!r}"
            )
        if not self.source_code.strip() or not self.source_label.strip():
            raise ClassificationError("source code and label are required")
        if self.effective_to and self.effective_from > self.effective_to:
            raise ClassificationError(
                f"invalid mapping interval for {self.source_code}"
            )
        if self.strict_pilot_admissible:
            if self.mapping_type not in STRICT_MAPPING_TYPES:
                raise ClassificationError(
                    f"strict mapping uses non-exact method: {self.source_code}"
                )
            if self.bridge_status != "RATIFIED_FOR_SOURCE_VERSION":
                raise ClassificationError(
                    f"strict mapping bridge is not ratified: {self.source_code}"
                )


@dataclass(frozen=True, slots=True)
class ClassificationBundle:
    classification: ArmilarClassification
    mappings: tuple[CategoryMapping, ...]
    classification_sha256: str
    mapping_sha256: str

    @property
    def mapping_id(self) -> str:
        ids = {row.mapping_id for row in self.mappings}
        if len(ids) != 1:
            raise ClassificationError(f"mapping rows use multiple ids: {sorted(ids)}")
        return next(iter(ids))

    @property
    def source_classification(self) -> str:
        values = {row.source_classification for row in self.mappings}
        if len(values) != 1:
            raise ClassificationError(
                f"mapping rows use multiple source classifications: {sorted(values)}"
            )
        return next(iter(values))

    @property
    def source_classification_version(self) -> str:
        values = {row.source_classification_version for row in self.mappings}
        if len(values) != 1:
            raise ClassificationError(
                f"mapping rows use multiple source versions: {sorted(values)}"
            )
        return next(iter(values))

    def validate_mapping_rows(self) -> None:
        self.classification.validate()
        rows = list(self.mappings)
        if not rows:
            raise ClassificationError("classification mapping is empty")
        for row in rows:
            row.validate(self.classification)
        _ = self.mapping_id
        _ = self.source_classification
        _ = self.source_classification_version
        if len(self.classification_sha256) != 64 or len(self.mapping_sha256) != 64:
            raise ClassificationError("classification hashes must be SHA-256")

    def validate_strict_source_grid(
        self, expected_source_codes: Iterable[str] = SOURCE_CATEGORIES
    ) -> None:
        self.validate_mapping_rows()
        rows = list(self.mappings)
        expected = tuple(expected_source_codes)
        actual = tuple(sorted(row.source_code for row in rows))
        if actual != tuple(sorted(expected)):
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise ClassificationError(
                f"strict source grid mismatch; missing={missing}, extra={extra}"
            )
        if len(actual) != len(set(actual)):
            raise ClassificationError("source categories must map exactly once")
        if not all(row.strict_pilot_admissible for row in rows):
            blocked = sorted(
                row.source_code for row in rows if not row.strict_pilot_admissible
            )
            raise ClassificationError(
                f"mapping is not admissible for strict pilot: {blocked}"
            )
        targets = {row.armilar_category for row in rows}
        if targets != set(self.classification.category_codes):
            missing_targets = sorted(set(self.classification.category_codes) - targets)
            raise ClassificationError(
                f"Armilar categories lack source coverage: {missing_targets}"
            )
    def mapping_by_source(self) -> dict[str, CategoryMapping]:
        self.validate_strict_source_grid()
        return {row.source_code: row for row in self.mappings}


def load_armilar_classification(path: Path) -> ArmilarClassification:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"invalid classification JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClassificationError("classification JSON must be an object")
    category_rows = payload.get("categories")
    if not isinstance(category_rows, list):
        raise ClassificationError("classification categories must be a list")
    try:
        categories = tuple(
            ArmilarCategory(
                category_code=str(row["category_code"]).strip().upper(),
                label=str(row["label"]).strip(),
                description=str(row["description"]).strip(),
                display_order=int(row["display_order"]),
            )
            for row in category_rows
        )
        result = ArmilarClassification(
            classification_id=str(payload["classification_id"]).strip(),
            version=str(payload["version"]).strip(),
            status=str(payload["status"]).strip(),
            categories=categories,
            global_exclusions=tuple(
                str(value).strip().upper()
                for value in payload.get("global_exclusions", [])
                if str(value).strip()
            ),
            raw_source_detail_preserved=bool(
                payload.get("raw_source_detail_preserved", False)
            ),
            monetary_release_allowed=bool(
                payload.get("monetary_release_allowed", False)
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClassificationError(f"invalid classification fields: {exc}") from exc
    result.validate()
    return result


def load_category_mappings(path: Path) -> tuple[CategoryMapping, ...]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ClassificationError(f"mapping CSV is not UTF-8: {exc}") from exc
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ClassificationError("mapping CSV is empty")
    result: list[CategoryMapping] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            item = CategoryMapping(
                mapping_id=(row.get("mapping_id") or "").strip(),
                source_provider=(row.get("source_provider") or "").strip().upper(),
                source_classification=(
                    row.get("source_classification") or ""
                ).strip().upper(),
                source_classification_version=(
                    row.get("source_classification_version") or ""
                ).strip().upper(),
                source_code=(row.get("source_code") or "").strip().upper(),
                source_label=(row.get("source_label") or "").strip(),
                armilar_category=(
                    row.get("armilar_category") or ""
                ).strip().upper(),
                mapping_type=(row.get("mapping_type") or "").strip().upper(),
                effective_from=(row.get("effective_from") or "").strip(),
                effective_to=(row.get("effective_to") or "").strip(),
                strict_pilot_admissible=_parse_bool(
                    row.get("strict_pilot_admissible"), line_number
                ),
                bridge_status=(row.get("bridge_status") or "").strip().upper(),
                notes=(row.get("notes") or "").strip(),
            )
        except (TypeError, ValueError) as exc:
            raise ClassificationError(
                f"invalid mapping row at line {line_number}: {exc}"
            ) from exc
        result.append(item)
    return tuple(sorted(result, key=lambda row: row.source_code))


def load_classification_bundle(
    classification_path: Path,
    mapping_path: Path,
    *,
    expected_source_codes: Iterable[str] = SOURCE_CATEGORIES,
    require_strict: bool = True,
) -> ClassificationBundle:
    bundle = ClassificationBundle(
        classification=load_armilar_classification(classification_path),
        mappings=load_category_mappings(mapping_path),
        classification_sha256=hashlib.sha256(
            classification_path.read_bytes()
        ).hexdigest(),
        mapping_sha256=hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
    )
    if require_strict:
        bundle.validate_strict_source_grid(expected_source_codes)
    else:
        bundle.validate_mapping_rows()
    return bundle


def mapping_audit_rows(bundle: ClassificationBundle) -> list[dict[str, object]]:
    bundle.validate_strict_source_grid()
    return [
        {
            "mapping_id": row.mapping_id,
            "source_provider": row.source_provider,
            "source_classification": row.source_classification,
            "source_classification_version": row.source_classification_version,
            "source_code": row.source_code,
            "source_label": row.source_label,
            "armilar_category": row.armilar_category,
            "mapping_type": row.mapping_type,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "strict_pilot_admissible": row.strict_pilot_admissible,
            "bridge_status": row.bridge_status,
            "classification_id": bundle.classification.classification_id,
            "classification_version": bundle.classification.version,
            "classification_sha256": bundle.classification_sha256,
            "mapping_sha256": bundle.mapping_sha256,
            "notes": row.notes,
        }
        for row in bundle.mappings
    ]


def _parse_bool(value: object, line_number: int) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean at line {line_number}: {value!r}")
