# ARMILAR v0.9.6

## Official engine and temporal ledger

This milestone implements the ratified Research Core development constitution as an executable deterministic engine.

### Added

- `ARM-O`, `ARM-R` and `ARM-H` calculation paths;
- exact 2021 annual-average normalisation;
- Decimal arithmetic with precision 28 and `ROUND_HALF_EVEN`;
- canonical fixed-scale outputs with unrounded values and explicit contribution residuals;
- as-of-cutoff publication and retrieval selection;
- mandatory raw snapshot identifiers and SHA-256 provenance;
- fail-closed rejection of proxy, model and imputed price evidence;
- immutable run bundles and canonical manifests;
- append-only hash-chained temporal ledger;
- deterministic replay and tamper detection;
- original-versus-revised reconciliation;
- cell, economy and category contributions;
- a mechanical CP04 scenario harness labelled as non-evidence and incapable of satisfying the constitutional OOH requirement;
- DuckDB-backed Parquet derived views, exercised in CI through the `temporal` extra;
- closed JSON schemas, contract documentation and targeted tests.

### Unchanged

- Research Core basket and weights;
- ratified constitution and approval record;
- Eurostat source configuration;
- `public/latest`;
- all release, promotion, shadow-production, monetary and world-claim gates.

### Explicit limitations

The engine remains an internal research-development component. It does not start `ARM-L`, publish a research release, authorise shadow production or support monetary use.
