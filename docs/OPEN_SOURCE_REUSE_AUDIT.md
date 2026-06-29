# Open-source reuse audit

## Rule

Before a new parser, storage layer, validator, workflow engine, API server or model registry is written, the developer must record whether an existing open-source component can be adopted or adapted.

The economic definition of the Armilar, its mapping rules, evidence hierarchy, imputation policy, index formula and monetary gates remain project-specific.

## Immediate decisions

### SDMX

Run a narrow retrieval spike with `sdmx1` against the OECD and Eurostat before writing any new SDMX parser. Keep `pysdmx` as a challenger because its information model and serializers may be useful, but do not add both as runtime dependencies without a measured benefit.

### DBnomics

Use DBnomics fetchers to discover datasets and inspect provider-specific acquisition logic. Runtime data should still preserve the official source URL, response, retrieval time and hash. Each fetcher licence must be reviewed before code is copied or modified.

### Storage

Continue with CSV and JSON for the v0.7 contract layer. Introduce DuckDB and Parquet when monthly panels and historical vintages make repeated CSV joins a measurable bottleneck.

### Validation

Keep zero runtime dependencies in v0.7. JSON Schema and standard-library semantic checks make the contract independently auditable. Evaluate Pandera when price observations become dataframe-heavy.

### Testing

Add Hypothesis in the next development increment to test mathematical invariants and randomly generated incomplete or contradictory grids.

## Build versus reuse gate

A new material component requires a registry entry with:

- capability;
- candidate project;
- licence;
- maintenance status;
- security considerations;
- integration cost;
- decision;
- reason;
- custom code that would be replaced.

`ADOPT`, `ADAPT`, `RETAIN`, `REJECT` and `DEFER` are the permitted decisions. `ADOPT_PILOT` and `ADOPT_NEXT` are temporary implementation states.
