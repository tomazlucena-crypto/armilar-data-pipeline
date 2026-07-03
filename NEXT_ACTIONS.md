# Next actions after v0.9.5-05 proposal revision 0.2.0

The immediate objective is to obtain explicit approval or rejection of the seven Research Core methodological decisions after incorporating the weight, proxy, OOH, ARM-L and basket-version clarifications.

## Completed

1. repair and validate the v0.9.5-04 executable contracts;
2. preserve the 60-cell basket, source provenance and cross-platform canonical hashes via an immutable constitutional snapshot;
3. draft seven executable methodological decision records;
4. create a closed ratification proposal and fail-closed checker;
5. define PPP-adjusted fixed weights and explicit AIC-PPP exceptions;
6. publish a machine-readable annex for all 25 proxy cells and their weight exposure;
7. define a mandatory OOH sensitivity analysis;
8. define the ARM-L information set and immutable reconciliation rules;
9. fix economies and categories within a basket version;
10. define evidence, numerical-weight, scope and method change classes;
11. keep the canonical constitution `DRAFT`;
12. keep every release, promotion, shadow, monetary and world-claim gate `false`.

## Current state

- package baseline: `0.9.4`;
- canonical constitution: `DRAFT`, version `0.3.0-draft`;
- ratification proposal: `PROPOSED`, version `0.2.0`;
- human approval: required;
- approval status: `NOT_APPROVED`;
- basket: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`;
- constitutional input snapshot: `constitution/inputs/ARMILAR_RESEARCH_CORE_V1_WEIGHTS_OBSERVED_UNIVERSE_V094.csv`;
- eligibility: `RESEARCH_ONLY`;
- proxy cells: `25`;
- proxy fixed-universe weight: `0.589731681350816432896035605`;
- all seven canonical decisions remain `PENDING_RATIFICATION`;
- all gates remain `false`.

## Next bounded step

1. review the revised seven decisions and the proxy-exposure annex;
2. record explicit human approval or requested amendments;
3. in a separate PR, update the canonical constitution to `1.0.0-research` and `RATIFIED_FOR_ENGINE_DEVELOPMENT`;
4. update its schema, rendering, manifest and tests;
5. only after that PR is green and merged, begin v0.9.6.

## Proposal links

- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.md`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.sha256`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.md`;
- `schemas/research_core_ratification_proposal.schema.json`;
- `schemas/research_core_proxy_exposure.schema.json`;
- `scripts/check_research_core_ratification.py`;
- the seven `docs/DECISION_RESEARCH_CORE_*.md` records.

## Do not start yet

- canonical ratification without explicit approval;
- v0.9.6 official-engine implementation;
- temporal storage;
- proxy acquisition;
- live-estimator implementation;
- API or dashboard work;
- model auto-promotion;
- blockchain or monetary use;
- basket weight changes;
- any release-gate activation.
