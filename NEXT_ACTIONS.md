# Next actions after v0.9.5-05

The immediate objective is to obtain explicit approval or rejection of the seven Research Core methodological decisions before changing the canonical constitution.

## Completed

1. repair and validate the v0.9.5-04 executable contracts;
2. preserve the 60-cell basket, source provenance and cross-platform canonical hashes;
3. draft seven executable methodological decision records;
4. create a closed ratification proposal and fail-closed checker;
5. keep the canonical constitution `DRAFT`;
6. keep every release, promotion, shadow, monetary and world-claim gate `false`.

## Current state

- package baseline: `0.9.4`;
- canonical constitution: `DRAFT`, version `0.3.0-draft`;
- ratification proposal: `PROPOSED`, version `0.1.0`;
- human approval: required;
- approval status: `NOT_APPROVED`;
- basket: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`;
- eligibility: `RESEARCH_ONLY`;
- all seven canonical decisions remain `PENDING_RATIFICATION`;
- all gates remain `false`.

## Next bounded step

1. review the seven proposed decisions;
2. record explicit human approval or requested amendments;
3. in a separate PR, update the canonical constitution to `1.0.0-research` and `RATIFIED_FOR_ENGINE_DEVELOPMENT`;
4. update its schema, rendering, manifest and tests;
5. only after that PR is green and merged, begin v0.9.6.

## Proposal links

- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.md`;
- `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.sha256`;
- `schemas/research_core_ratification_proposal.schema.json`;
- `scripts/check_research_core_ratification.py`;
- the seven `docs/DECISION_RESEARCH_CORE_*.md` records added by v0.9.5-05.

## Do not start yet

- canonical ratification without explicit approval;
- v0.9.6 official-engine implementation;
- temporal storage;
- proxy acquisition;
- live estimator work;
- API or dashboard work;
- model auto-promotion;
- blockchain or monetary use;
- basket weight changes;
- any release-gate activation.
