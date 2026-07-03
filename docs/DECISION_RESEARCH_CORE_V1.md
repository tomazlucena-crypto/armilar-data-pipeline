# Decision: ARMILAR_RESEARCH_CORE_V1 pre-ratification contract

## Status

`DRAFT`, version `0.3.0-draft`.

## Decision

Maintain a bounded five-economy Research Core while the vertical index is developed. The executable constitution is `constitution/ARMILAR_RESEARCH_CORE_V1.json` and the human-readable rendering is `constitution/ARMILAR_RESEARCH_CORE_V1.md`.

The Research Core contains Germany, Spain, France, Italy and Portugal. CP01 to CP12 form the weighted basket. CP00 is an external headline benchmark and never enters the weighted sum.

Current FX remains outside the primary local-price-relative index. Every release, promotion, shadow, monetary and world-claim gate remains false.

## Series

`ARM-O`, `ARM-L`, `ARM-R` and `ARM-H` remain separate provisional series. Their exact semantics are still pending ratification. No model or operational component may silently substitute one series for another.

## Basket

The basket is materialized at `basket/ARMILAR_RESEARCH_CORE_V1.csv` from the preserved v0.9.4 observed-universe weights. Its provenance and normalization are documented in `docs/DECISION_RESEARCH_CORE_BASKET_MATERIALIZATION.md`.

## Contract repair

The v0.9.5-04 repair replaces incomplete schemas, restores source-level provenance and derives evidence classes from preserved source fields rather than category codes. See `docs/DECISION_RESEARCH_CORE_CONTRACT_REPAIR.md`.

## Consequences

The basket may be used for research and development of the official engine. This decision does not ratify the index formula, series semantics, revisions, rounding, conceptual HFCE/HICP treatment or constitutional amendment process.
