# Next actions after v0.9.4

The immediate objective is to complete the v0.9.5 executable Research Core constitution before any engine or data expansion.

## Completed

1. declare the Research Core scope and vertical roadmap;
2. define the five-economy universe, CP01-CP12 basket, CP00 benchmark and ARM-O/ARM-L/ARM-R/ARM-H separation;
3. materialize the Research Core basket and canonical hash artefacts.

## Current state

- baseline: v0.9.4;
- PR #16 is integrated in `main`;
- v0.9.4 validated official acquisition, replay, pre-release backtests and paired diagnostics;
- Research Core constitution status: `DRAFT`;
- basket materialization status: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`;
- `public/latest` remains unchanged;
- `research_release_allowed=false`;
- `model_promotion_allowed=false`;
- `monetary_release_allowed=false`;
- `shadow_production_allowed=false`.

## Current contract links

- `constitution/ARMILAR_RESEARCH_CORE_V1.md`;
- `constitution/ARMILAR_RESEARCH_CORE_V1.json`;
- `basket/ARMILAR_RESEARCH_CORE_V1.csv`;
- `constitution/ARMILAR_RESEARCH_CORE_V1.sha256`;
- `schemas/research_core_constitution.schema.json`;
- `schemas/research_core_basket.schema.json`.

## Do not start yet

- expansion to new countries;
- official engine implementation before ratification;
- temporal storage before the basket is materialised;
- proxy acquisition;
- live estimator work;
- advanced model optimisation;
- MLflow;
- Prefect or Dagster;
- public API work;
- blockchain;
- monetary policy claims;
- basket weight changes;
- live acquisition in CI;
- v0.9.6 work.
