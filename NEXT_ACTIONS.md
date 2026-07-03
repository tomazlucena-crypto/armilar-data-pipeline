# Next actions after v0.9.5-04

The immediate objective is to complete the executable Research Core contract before beginning the official engine.

## Completed

1. declare the Research Core scope and vertical roadmap;
2. define the five-economy universe, CP01-CP12 basket, CP00 benchmark and four separate series;
3. materialize the 60-cell basket from preserved v0.9.4 inputs;
4. preserve raw-world and fixed-universe weights;
5. restore complete per-cell provenance;
6. derive evidence classes from source scope and derivation;
7. make constitution and basket schemas internally coherent;
8. add deterministic multi-file SHA-256 verification;
9. keep all release and promotion gates closed.

## Current state

- package baseline: `0.9.4`;
- Research Core constitution: `DRAFT`, version `0.3.0-draft`;
- basket: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`;
- eligibility: `RESEARCH_ONLY`;
- exact official cells: `30`;
- official deterministic derivations: `5`;
- experimental research cells: `25`;
- seven methodological decisions remain `PENDING_RATIFICATION`;
- `research_release_allowed=false`;
- `model_promotion_allowed=false`;
- `shadow_production_allowed=false`;
- `monetary_release_allowed=false`;
- `world_claim_allowed=false`.

## Next bounded step

1. run the repaired contracts against the complete repository suite;
2. review and ratify the seven methodological decisions in separate decision records;
3. add a fail-closed ratification checker;
4. only then begin v0.9.6 official-engine and temporal-storage work.

## Contract links

- `constitution/ARMILAR_RESEARCH_CORE_V1.json`;
- `constitution/ARMILAR_RESEARCH_CORE_V1.md`;
- `constitution/ARMILAR_RESEARCH_CORE_V1.sha256`;
- `basket/ARMILAR_RESEARCH_CORE_V1.csv`;
- `schemas/research_core_constitution.schema.json`;
- `schemas/research_core_basket.schema.json`;
- `docs/DECISION_RESEARCH_CORE_V1.md`;
- `docs/DECISION_RESEARCH_CORE_BASKET_MATERIALIZATION.md`;
- `docs/DECISION_RESEARCH_CORE_CONTRACT_REPAIR.md`.

## Do not start yet

- expansion to new countries;
- v0.9.6 official-engine implementation;
- temporal storage;
- proxy acquisition;
- live estimator work;
- API or dashboard work;
- model auto-promotion;
- blockchain or monetary use;
- basket weight changes;
- live acquisition in CI.
