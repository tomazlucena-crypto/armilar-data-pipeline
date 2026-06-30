# Armilar price completion methodology v0.8.4

## Status

This component is experimental. It cannot authorise a research or monetary
release. Both release flags remain false.

## Purpose

The component completes the fixed economy-category-month price grid needed for
an experimental global Armilar price index. It works at the nine-category
canonical Armilar level and preserves the evidence class, source identifiers,
method, donors and uncertainty of every completed cell.

It does not claim that a real global data release has already been acquired.
The engine requires separately acquired and hash-preserved official category
and headline observations.

## Evidence hierarchy

- `P1_OFFICIAL_CATEGORY`: direct official category observation.
- `P2_OFFICIAL_COMPATIBLE_AGGREGATE`: compatible official aggregate.
- `P3_OFFICIAL_HEADLINE`: official headline inflation for the target economy.
- `P4_REGIONAL_PATTERN`: target headline plus a regional category deviation.
- `P5_WORLD_PATTERN`: target headline plus a world category deviation.

P1 and P2 levels are preserved. P3, P4 and P5 are estimates and cannot be
promoted to official observations.

## P4 and P5 construction

For target economy `i`, category `c` and month `t`, the donor residual is:

```text
residual_donor =
    category_monthly_change_donor
    - headline_monthly_change_donor
```

The estimated target category change is:

```text
target_category_monthly_change =
    target_official_headline_monthly_change
    + weighted_median(donor_residual)
```

P4 uses eligible donors from the target region. P5 uses the eligible world pool
when the regional donor gate is not met.

The completed category index is obtained by chaining monthly changes from the
fixed reference period.

## Donor rules

Donors are selected without access to the hidden target-category value.

Eligibility requires:

- direct P1 or P2 category observations for the donor in the relevant months;
- donor official headline observations for the same months;
- a declared economy profile;
- availability before or at the estimated month.

The deterministic ordering uses:

1. income-group match;
2. declared characteristic overlap;
3. economy code.

Donor weights use the fixed world expenditure weight and declared numeric
profile distance. The target value is absent from both selection and weighting.

## P3 fallback

When neither the regional nor world donor minimum is met, the target official
headline change is used without a category deviation. Its uncertainty interval
uses historical donor residuals when available, otherwise an explicit policy
width.

## Fixed weights and aggregation

The input world weights must form a complete economy by ARM01-ARM09 grid and
sum to one. CP01-CP12 inputs are accepted only through the ratified exact
classification mapping.

Every month must contain the full fixed grid. Missing completed cells cause a
failure. Monthly weights are never renormalised.

## Uncertainty

P4 and P5 cell bounds use configured weighted donor quantiles. P3 uses
historical residual quantiles or the explicit fallback width. Cell bounds are
chained and aggregated with the same fixed world weights.

The resulting interval is an experimental model interval. It is not yet a
formally calibrated confidence interval.

## Validation

Leave-one-economy-out validation hides direct P1 and P2 category observations,
reconstructs them using P3, P4 or P5 and reports:

- MAE;
- MAPE;
- RMSE;
- bias;
- interval coverage;
- category;
- region;
- forecast horizon;
- fallback class.

No future period may be used to predict an earlier period.

## Provenance

The output summary records SHA-256 hashes for:

- global weights;
- observed prices;
- economy profiles;
- completion policy;
- classification mapping, when used.

All generated outputs are included in `MANIFEST.sha256`.

## Required outputs

- `monthly_price_cells_complete.csv`
- `monthly_price_uncertainty.csv`
- `price_imputation_audit.csv`
- `price_validation_by_category.csv`
- `price_validation_by_region.csv`
- `price_validation_summary.json`
- `monthly_global_experimental_index.csv`
- `monthly_global_index_uncertainty.csv`
- `price_evidence_coverage.csv`
- `MANIFEST.sha256`

The implementation also publishes validation by horizon and fallback class, and
a completion summary with input hashes.

## Input observation contract

The canonical CSV fields are:

```text
economy_code
category_code
period
price_relative
evidence_class
source_ids
```

For compatibility with v0.8.2 pilot outputs, the loader also accepts:

- `price_evidence_class` in place of `evidence_class`;
- `price_series_ids` or `series_id` in place of `source_ids`;
- `price_index` in place of `price_relative`.

Headline records use category code `HEADLINE` and evidence class
`P3_OFFICIAL_HEADLINE`.

## Release blockers

Before any research release, the project still needs:

- a real, reproducible global official observation input;
- sufficient leave-one-out coverage across regions and categories;
- empirically ratified error and interval-coverage gates;
- reconciliation of price and weight concepts;
- independent methodological review.

`research_release_allowed=false`

`monetary_release_allowed=false`
