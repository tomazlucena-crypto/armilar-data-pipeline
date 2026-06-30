# Armilar roadmap from v0.8.6 to v1.0.0

## Operating principle

Every material work item must either move the project towards a validated monthly series or reduce a risk that could invalidate that series.

The preferred delivery order is vertical:

```text
weights
-> official prices
-> normalisation
-> monthly index
-> historical series
-> backtest
-> economic report
```

Discovery, integration and production are separate states. A source is not integrated merely because it was found, and an integrated source is not production-ready merely because its parser runs.

## v0.8.6: contracts, reuse and development telemetry

### Objective

Remove avoidable ambiguity before further model or source expansion.

### Deliverables

- executable development contracts;
- a single authored version value in `pyproject.toml`;
- an evidence-based SDMX client decision;
- property-based tests for core invariants;
- automatically generated development telemetry;
- updated reuse audit, component registry and decision log.

### Pull-request split

1. contracts and roadmap;
2. version unification and SDMX spike;
3. property tests and telemetry.

### Gate

- every v0.8.6 capability has a contract;
- the full test suite passes with no unexplained test-count regression;
- one SDMX client is selected for the v0.8.7 pilot;
- the challenger is not installed unless a documented gap justifies it;
- version divergence is blocked automatically;
- telemetry is reproducible and published as an artefact;
- release flags remain false.

The historical figure of 221 tests is a reference, not a permanent constant. CI must measure the baseline on the current `main` and reject unexplained regression.

## v0.8.7: first real end-to-end Eurostat monthly series

### Scope

- official Eurostat HICP data;
- a fixed set of economies with complete declared category coverage;
- a common historical interval;
- exact mapping from ECOICOP source divisions to Armilar categories;
- primary index based on local price relatives;
- the common-currency layer remains separate and informational.

### Required chain

```text
raw official response
-> immutable receipt and SHA-256
-> normalised observation
-> fixed universe
-> monthly index
-> contributions and coverage
-> uncertainty
-> manifest
-> economic report
```

### Gate

- live acquisition is isolated from pull-request CI;
- replay reconstructs normalised observations from the exact hashed bytes;
- no synthetic fixture is represented as an official release;
- the declared monthly series is complete for its fixed universe;
- missing data never causes silent monthly renormalisation;
- `public/latest` is unchanged in pull requests;
- release flags remain false.

New country adapters remain frozen until this gate passes.

## v0.8.8: minimum economic backtest

Compare:

- B0: simple headline CPI baseline;
- B1: Armilar-weighted headline CPI;
- B2: Armilar category-price index;
- B3: Armilar category-price index with P3/P4/P5 completion.

Use rolling-origin evaluation and publication-aware vintages. Report errors by economy, category, horizon and evidence class. Test weight sensitivity, FX-methodology sensitivity and the effect of imputed economies.

The mandatory output is a ranked, quantitative list of the three largest error sources. Subsequent development must address those first unless a written decision explains a different priority.

## v0.9.0: world research-series candidate

Expand only where expected error reduction justifies integration cost. Add OECD through the selected SDMX client, use DBnomics only for discovery and reference, introduce DuckDB and Parquet when multi-vintage panels justify them, and adopt Pandera only if it replaces repetitive validation.

Priority is:

```text
economic weight * expected error reduction * integration probability
--------------------------------------------------------------------
implementation and maintenance cost
```

The gate requires a replayable world monthly series, out-of-sample validation, calibrated uncertainty and complete manifests. `research_release_allowed` may change only under predeclared empirical gates.

## v0.9.1 to v0.9.3: error-led expansion

Each source passes through:

```text
DISCOVERED
CONCEPTUALLY_ELIGIBLE
INTEGRATED
REPLAY_VALIDATED
PRODUCTION_MONITORED
```

Each investigation has a success condition, stop condition, fallback condition and maximum effort. Exact cells feed A/B evidence, partial evidence feeds C methods, and real absence feeds D/E methods. A country must not block the pipeline indefinitely.

Large adapter modules are split incrementally when touched. No isolated full rewrite is required.

## v0.10.0: nowcast and reconciliation

Use simple measured baselines before complex models. Statsmodels is the default candidate for state-space and Kalman models. Scikit-learn supports metrics and temporal evaluation. Sktime remains a challenger. MLflow is deferred until several real models require promotion, rollback and lineage.

No adaptive model may alter the basket, weights, official history or release gates.

## v0.11.0: public service

Introduce FastAPI, DuckDB/Parquet, production orchestration and structured logging only after the monthly series has passed its research gate. The dashboard must consume the public API and perform no independent index calculation.

## v0.12.0 and v1.0.0: oracle, shadow operation and research release

Add signed reports, independent operators, consensus, circuit breakers, shadow production and external audits. Monetary eligibility remains a separate constitutional decision after the research index is operational.

## Permanent invariants

- core and global constructions remain distinct;
- estimated evidence is never relabelled as official;
- current FX never enters the primary local-price inflation index;
- revisions preserve prior vintages;
- no hidden renormalisation;
- no live network acquisition in pull-request checks;
- `monetary_release_allowed=false` until separate ratification.
