# Decision: explicit point-in-time proxy mapping and descriptive risk diagnostics

**Date:** 2026-07-04  
**Version:** 0.9.9

## Decision

Adopt a closed mapping registry linking selected official proxy series to Research Core categories and economies. The registry produces research features, longitudinal diagnostics, first-seen lag profiles, provenance concentration, descriptive risk flags and cutoff-to-cutoff stability reports only.

## Rationale

The v0.9.7 registry proves that official proxy datasets can be acquired. The v0.9.8 archive proves when values became available to Armilar. Neither step establishes that a series measures a complete consumer-price category, predicts official inflation or is suitable for training. An explicit mapping and diagnostic layer is required before empirical model selection.

## Mapping classes

- `PRIMARY_RESEARCH_DRIVER`: plausible partial cost driver used to measure availability and historical depth.
- `SENSITIVITY_ONLY`: informative series excluded from primary coverage.

All mappings use `PARTIAL_COST_DRIVER` or `SENSITIVITY_ONLY` evidence. No mapping is labelled as a direct category price.

## Additional diagnostics

The system may describe:

- first-seen lag relative to the target-period end;
- source and stream concentration based on observation counts;
- separate boolean risk flags for missingness, staleness, concentration, history gaps and absent transformations;
- value, provenance and metadata stability between ordered cutoffs.

These outputs are diagnostics. The first-seen lag is an Armilar observation lag, not an asserted official publication lag. Concentration cannot become a quality weight. Risk flags cannot be summed into a score used for eligibility. Stability cannot approve or reject a feature.

## Initial mappings

- World Bank food index and FAO food indices to CP01.
- World Bank energy and European natural gas to CP04.
- World Bank crude oil and EC road-fuel prices to CP07.
- EC heating oil to CP04.
- Eurostat OOHPI to CP04 as sensitivity-only.

## Rejected alternatives

- automatic semantic matching from names;
- broadcasting country-specific prices worldwide;
- filling unmapped cells with regional or global series;
- treating OOHPI as a primary HICP-compatible price;
- declaring mapped weight as price coverage;
- ranking or weighting features from descriptive concordance or stability;
- deriving an aggregate risk score from diagnostic flags;
- treating first-seen lag as a historical official publication calendar;
- comparing feature bundles built from different policies or baskets.

## Consequences

The panel remains intentionally sparse. Sparse, measured coverage is preferable to hidden completion. Successive cutoffs can now be compared while separating revisions, additions, metadata changes and provenance changes. Any future mapping or diagnostic-policy change requires a new policy hash, tests and impact report.
