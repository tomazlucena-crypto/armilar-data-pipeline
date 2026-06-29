# Armilar v0.7.2 imputation baselines

## Scope

This release implements research baselines for evidence classes C, D and E. It does not publish a world-weight release and does not alter strict A/B outputs.

## Class C: own-economy constrained allocation

A class C cell requires an explicit official or otherwise documented aggregate for the target economy. Observed cells inside the aggregate are subtracted. The residual is split across missing categories with a deterministic donor template. The own-economy aggregate anchors the level; donor information only supplies the split.

## Class D: deterministic donor imputation

Donors are ranked using only pre-declared profile attributes:

1. region match;
2. income-group match;
3. standardised distance over supplied numeric covariates;
4. economy code as a deterministic tie-breaker.

Category outcomes do not enter the donor-ranking function. The target economy is always excluded.

## Class E: regional or global fallback

If the minimum number of donors is unavailable, the system uses a regional template. If no regional template exists, it uses a global template. Class E does not report named donor economies, preventing a fallback from being presented as targeted donor imputation.

## Validation

Leave-one-economy-out validation is run on economies with complete A/B grids. It reports:

- absolute error;
- absolute percentage error;
- bias;
- interval coverage;
- results by method and category.

Class C is tested by reconstructing pre-declared category groups from their own-economy aggregate totals. D and E are tested by reconstructing full category vectors.

## Release boundary

Outputs are named `*_research` and explicitly state:

- `research_release_only=true`;
- `global_weight_release_produced=false`;
- `monetary_release_allowed=false`.

Promotion to a complete world-weight release belongs to v0.7.3 and requires review of measured validation error.
