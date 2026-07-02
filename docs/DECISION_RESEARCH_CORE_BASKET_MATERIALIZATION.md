# Decision: Research Core basket materialization

## Decision

Materialize the 60-cell `ARMILAR_RESEARCH_CORE_V1` basket exclusively from `public/latest/weights_observed_universe.csv`.

## Source

- Source pipeline version: `0.9.4`
- Source rows: `744`
- Source SHA-256: `743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83`
- Source global weight sum: `1.000000000000000000000000`

## Selection

Economies: `DEU`, `ESP`, `FRA`, `ITA`, `PRT`.

Categories: `CP01` to `CP12`.

The selection must contain exactly 60 unique cells. Its preserved raw-world weight is `0.160150831582167491646292`.

## Normalization

The existing v0.8.7 policy `FIXED_UNIVERSE_NORMALISE_ONCE` is reapplied without changing the source weights:

`fixed_universe_weight = raw_world_weight / covered_world_weight`

Decimal precision is 28 and rounding is `ROUND_HALF_EVEN`. The committed fixed-universe weights sum to `1.000000000000000000000000000`.

This is a deterministic derivation for a declared limited universe. It is not evidence that the five economies represent the world.

## Evidence classes

Evidence is classified from each source row's `ppp_scope` and `derivation`:

- `STRICT_HFCE` plus `DIRECT_SOURCE90_HFCE`: `EXACT_OFFICIAL`;
- `STRICT_HFCE_COMPOSITE` plus `ALCOHOL_PLUS_TOBACCO_EXCLUDING_NARCOTICS`: `OFFICIAL_DETERMINISTIC_DERIVATION`;
- `ACTUAL_CONSUMPTION_PROXY_RATIFIED_OPTION_B` plus the matching Option B derivation: `EXPERIMENTAL_RESEARCH`.

Expected counts are 30 exact official cells, 5 official deterministic derivations and 25 experimental research cells.

## Limitations

The 25 experimental cells remain explicit. The basket is `RESEARCH_ONLY`, cannot support monetary use and does not remove the HFCE/HICP conceptual mismatch.
