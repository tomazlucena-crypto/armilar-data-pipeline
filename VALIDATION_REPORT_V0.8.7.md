# Validation report: v0.8.7

## Scope validated locally

- policy contract and fixed universe;
- official-response acquisition boundary using injected HTTP responses;
- exact-byte preservation and SHA-256 receipts;
- JSON-stat parsing;
- deterministic replay;
- complete 5 × 12 × 60 observation grid;
- fail-closed behaviour for missing cells, duplicate data and changed bytes;
- fixed-universe weight normalisation performed once;
- monthly index and contribution identities;
- output manifest verification;
- explicit absence of fabricated confidence bounds;
- no writes to `public/latest`;
- one-command local empirical gate with before/after tree hashes;
- rejection of stale non-empty snapshot/output directories;
- explicit blocking of 2026 data until an ECOICOP v2 mapping exists;
- project version and user agent obtained from the shared version helper.

## Results

- dedicated unit tests: 20 discovered and passed;
- full repository suite: 261 tests discovered and passed;
- Python compile check: passed;
- real `weights_observed_universe.csv` schema validation: passed;
- selected universe: 60 weight cells;
- selected pre-normalisation world weight: `0.160150831582167492`;
- official full-grid replay: 3,600 observations and 60 monthly index rows;
- output manifest verification: passed.

## Empirical gate

`py scripts\validate_official_v087.py --repo-root .` passed in a network-enabled local environment. It acquired the official Eurostat bytes, verified the snapshot, replayed the complete series, wrote `artifacts/v087/OFFICIAL_GATE_REPORT.json`, generated `artifacts/v087/eurostat_vertical/ECONOMIC_REPORT.md` and confirmed that `public/latest` was unchanged.

## Release gates

- `research_release_allowed=false`
- `monetary_release_allowed=false`
