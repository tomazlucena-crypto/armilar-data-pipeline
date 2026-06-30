"""Monthly price registry and research index engine for Armilar."""

from .index_engine import AggregationMode, IndexBuildError, calculate_monthly_indices
from .models import PriceEvidenceClass, PriceObservation, PriceSeriesDefinition
from .classification import (
    ARMILAR_CATEGORY_CODES,
    ClassificationBundle,
    ClassificationError,
    load_classification_bundle,
)
from .pilot import PricePilotError, PriceUniverseSpec, build_eurostat_category_pilot
from .registry import RegistryError, load_registry

__all__ = [
    "AggregationMode",
    "ARMILAR_CATEGORY_CODES",
    "ClassificationBundle",
    "ClassificationError",
    "IndexBuildError",
    "PriceEvidenceClass",
    "PriceObservation",
    "PriceSeriesDefinition",
    "PricePilotError",
    "PriceUniverseSpec",
    "RegistryError",
    "build_eurostat_category_pilot",
    "calculate_monthly_indices",
    "load_classification_bundle",
    "load_registry",
]
