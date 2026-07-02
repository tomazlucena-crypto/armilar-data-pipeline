# ARMILAR_RESEARCH_CORE_V1 Constitution

The canonical source is `constitution/ARMILAR_RESEARCH_CORE_V1.json`.

## Status

- Constitution: `DRAFT`
- Constitution version: `0.3.0-draft`
- Schema version: `1.2`
- Basket: `BASKET_MATERIALIZED_FROM_EXISTING_V094_INPUTS`
- Eligibility: `RESEARCH_ONLY`
- Release, promotion, shadow, monetary and world-claim gates: `false`

## Research Core scope

The Research Core is an experimental five-economy euro-area price index using fixed Armilar 2021 HFCE-PPP weights and official Eurostat HICP category observations.

Economies: `DEU`, `ESP`, `FRA`, `ITA`, `PRT`.

Weighted categories: `CP01` to `CP12`.

`CP00` is an independent headline benchmark and is excluded from the weighted basket.

The Research Core must not be described as a world index, a complete HFCE index, a monetary-policy input or a blockchain oracle.

## Series

- `ARM-O`: provisional official first-published research series.
- `ARM-L`: provisional live estimate from the last official anchor.
- `ARM-R`: provisional revised reconstruction preserving original vintages.
- `ARM-H`: independent CP00 headline benchmark.

The exact semantics remain pending ratification. No series may silently replace another.

## Currency policy

The primary aggregation is `PPP_WEIGHTED_LOCAL_PRICE_RELATIVES`. Current FX is excluded from `ARM-O` and `ARM-L`. A separate informational common-currency layer may be produced. Any future use of FX as a proxy requires a separate decision and backtest.

## Basket materialization

The basket contains 60 cells from `public/latest/weights_observed_universe.csv`, source SHA-256 `743e9b35b079b784ef9a2ccadf3a61ae267005a0f768313541b9ea2be671df83`.

- Selected raw-world weight: `0.160150831582167491646292`
- Normalization: `FIXED_UNIVERSE_NORMALISE_ONCE`
- Decimal precision: `28`
- Rounding: `ROUND_HALF_EVEN`
- Fixed-universe sum: `1.000000000000000000000000000`
- Exact official cells: `30`
- Official deterministic derivations: `5`
- Experimental research cells: `25`

Evidence classes are derived from the preserved `ppp_scope` and `derivation` fields. Category codes alone are never used to infer evidence.

## Pending ratification

1. normalization base;
2. official formula;
3. vintage and revision policy;
4. precision and rounding;
5. exact series semantics;
6. HFCE/HICP conceptual treatment;
7. constitutional amendment process.

Materialization does not ratify any of these decisions.
