# Armilar v0.7.2

## Added

- research-only own-economy aggregate allocation baseline for class C;
- deterministic profile-based donor selection for class D;
- regional/global fallback for class E;
- leave-one-economy-out validation over complete A/B grids;
- error, bias and interval-coverage reports;
- `armilar-imputation` CLI;
- schemas and policy for economy profiles and aggregate constraints.

## Safety and methodology

- A/B evidence is preserved and never overwritten;
- donor ranking never uses target category outcomes;
- the target economy is excluded from validation donors;
- no world-weight release is produced;
- `monetary_release_allowed=false` remains mandatory.
