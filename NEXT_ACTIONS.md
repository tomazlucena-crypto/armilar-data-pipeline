# Next actions after v0.9.5-06 canonical ratification

## Completed

1. preserve the immutable v0.9.5-05 proposal version `0.2.0`;
2. preserve the draft predecessor under `constitution/archive/`;
3. record the explicit human approval dated `2026-07-03` without inventing a clock time;
4. ratify all seven decisions for Research Core engine development;
5. publish constitution `1.0.0-research` with status `RATIFIED_FOR_ENGINE_DEVELOPMENT`;
6. keep the basket, weights, snapshot and proxy classifications unchanged;
7. keep every release, model-promotion, shadow-production, monetary and world-claim gate closed;
8. add a fail-closed canonical checker and tamper tests.

## Current state

- package baseline remains `0.9.4`;
- Research Core constitution: `RATIFIED_FOR_ENGINE_DEVELOPMENT`;
- canonical methodological decisions pending: `0`;
- basket version remains `0.3.0-draft` because no basket row or weight changed;
- `research_release_allowed=false`;
- `model_promotion_allowed=false`;
- `shadow_production_allowed=false`;
- `monetary_release_allowed=false`;
- `world_claim_allowed=false`.

## Next bounded milestone: v0.9.6

Implement the official engine and temporal storage contract only after this ratification PR is merged.

### Scope

- annual-average 2021 normalization equal to 100;
- ARM-O first-published immutable vintages;
- ARM-R revised reconstructions without rewriting ARM-O;
- CP00 ARM-H benchmark kept separate;
- fixed-weight contributions and reconciliation;
- immutable run ledger, manifests and replay;
- Parquet and DuckDB temporal storage;
- OOH sensitivity analysis as a pre-external and pre-shadow blocker.

### Explicitly out of scope until later milestones

- ARM-L model promotion;
- public research release;
- shadow production;
- blockchain or oracle work;
- reserve management;
- monetary issuance;
- new economies, categories or basket weights.
