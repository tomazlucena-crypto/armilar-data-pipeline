# v0.8.4 price completion input contract

The engine consumes three data inputs plus a policy.

## World weights

Accepted weight columns:

- `world_weight`
- `weight`
- `weight_central`

The file must contain a complete economy-category grid and sum to one. Source
CP categories require the exact classification mapping.

## Economy profiles

Required columns:

- `economy_code`
- `income_group`
- `region_code` or `region`

Optional columns can contain numeric profile covariates. A pipe-separated
`characteristics` column may also be supplied.

## Observed prices

Canonical fields:

```csv
economy_code,category_code,period,price_relative,evidence_class,source_ids
```

Category observations must be P1 or P2. Headline observations use
`category_code=HEADLINE` and P3.

This directory contains no fabricated production data. Tests generate synthetic
fixtures at runtime.
