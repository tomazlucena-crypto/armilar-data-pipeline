# Open-source reuse audit

## Rule

Before a material parser, storage layer, validator, workflow engine, API server or model registry is written, record whether an existing maintained component should be adopted, adapted, retained, rejected or deferred.

The Armilar economic definition, classification mappings, evidence hierarchy, imputation policy, index formula, uncertainty rules and monetary gates remain project-specific.

## Decision vocabulary

- `ADOPT`: introduce the component in the declared phase;
- `ADOPT_PILOT`: run a bounded spike before permanent adoption;
- `ADAPT_REFERENCE_ONLY`: use upstream acquisition knowledge without adding the client as a runtime dependency;
- `RETAIN_CUSTOM`: preserve Armilar-specific code;
- `EVALUATE_CHALLENGER`: compare only against a demonstrated unmet requirement;
- `DEFER`: do not integrate before the stated trigger;
- `REJECT`: documented incompatibility.

## Immediate decisions for v0.8.6

### SDMX

Pilot `sdmx1` against Eurostat and OECD. The spike must test data retrieval, metadata/DSD access, key construction, SDMX-CSV or SDMX-JSON parsing, error handling and preservation of raw provider bytes. Keep `pysdmx` as a challenger only for requirements that the pilot records as unmet. Do not install both permanently without measured benefit.

### Provider discovery

Use DBnomics APIs, fetchers and repository knowledge for discovery and connector research. Production evidence must still identify the official provider URL and preserve the official response, retrieval time and hash. Review the licence of each fetcher before copying code.

### Property testing

Adopt Hypothesis as a test-only dependency in v0.8.6. Initial properties cover exact sums, order invariance, duplicate rejection, future-period rejection, FX conventions, incomplete grids and absence of silent renormalisation.

### Storage and tabular validation

Retain CSV and JSON until historical multi-vintage panels make repeated joins a measured bottleneck. Adopt DuckDB and Parquet at that trigger. Defer Pandera until real price panels stabilise and it can replace repetitive dataframe validation.

### Backtest and nowcast

Adopt scikit-learn when the minimum backtest begins, while retaining custom publication-date and vintage logic. Adopt statsmodels for state-space candidates after the monthly baseline exists. Keep sktime as a challenger. Defer MLflow until multiple real models require promotion and rollback.

### Public operation

Defer Pydantic and FastAPI until the public response contract is stable. Defer Prefect and structured logging until several production connectors exist. Evaluate OpenLineage only when current manifests and provenance receipts become insufficient.

## Build-versus-reuse gate

Every material registry entry records:

- capability;
- candidate and upstream project;
- licence;
- maintenance status;
- security review status;
- integration cost;
- decision and trigger;
- reason;
- custom code replaced or retained.

The authoritative registry is `config/component_registry.yaml`.
