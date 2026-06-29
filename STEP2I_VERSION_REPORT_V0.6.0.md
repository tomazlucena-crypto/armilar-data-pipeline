# Step 2I version report v0.6.0

## Summary

Step 2I is complete diagnostically. China, India, Russia, Indonesia and Brazil now have reproducible per-cell decisions for CP04, CP06, CP09, CP10 and CP12.

## Coverage

- Exact cells added: 0
- Experimental cells added: 0
- Complete economies added: 0
- `weights_final.csv`: remains empty

## Remaining blockers

- India: PFCE parser and item reconciliation are valid, but strict S14/P31DC household boundary and NPISH exclusion are not confirmed.
- Russia: no accepted deterministic official 2021 household-purpose table.
- China: official NBS evidence remains survey/grouped or not exact national-accounts HFCE.
- Indonesia: official BPS source family remains grouped or requires disaggregation.
- Brazil: official IBGE source family remains product/resource-use based without exact COICOP bridge.

## Step 2H exceptions

- Belarus CP02: blocked.
- Kuwait CP02: blocked.
- Saudi Arabia CP02: blocked.
- Bonaire all categories: blocked.
- Liberia proxy categories: blocked by unit/concept reconciliation.

## Tests

The v0.6.0 implementation adds Step 2I tests and keeps the full suite green locally.
