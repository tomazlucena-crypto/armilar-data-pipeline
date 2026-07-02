# Research Core V1 Decisions

## Status

This decision note records the scope for the future Research Core workstream. It does not change runtime behaviour or release gates.

The executable draft contracts are:

- [`constitution/ARMILAR_RESEARCH_CORE_V1.json`](../constitution/ARMILAR_RESEARCH_CORE_V1.json)
- [`constitution/ARMILAR_RESEARCH_CORE_V1.md`](../constitution/ARMILAR_RESEARCH_CORE_V1.md)
- [`schemas/research_core_constitution.schema.json`](../schemas/research_core_constitution.schema.json)
- [`schemas/research_core_basket.schema.json`](../schemas/research_core_basket.schema.json)

The JSON constitution is canonical. Its status is `DRAFT`.

## Preserved gates

- `research_release_allowed=false`
- `model_promotion_allowed=false`
- `monetary_release_allowed=false`
- `shadow_production_allowed=false`

## FX decision

- FX stays outside the primary index.
- FX may appear only as an informational layer.
- FX failures do not alter ARM-O or ARM-L.
- Future FX proxy use needs a separate methodological decision and backtest.

## Current claim boundary

The current product may be described as an experimental consumer price index based on fixed Armilar weights and official Eurostat category prices for five euro-area economies, accompanied by a live estimate and uncertainty metrics.

It is not yet allowed to claim:

- world inflation index;
- monetary eligibility;
- blockchain oracle;
- monetary policy recommendation;
- complete HFCE measure;
- HICP substitute.

## Basket materialisation status

`BASKET_MATERIALIZATION_BLOCKED`

The exact 60 fixed-universe weights used by v0.9.4 must be extracted from the preserved v0.9.3 first-published panel artifact with their original precision and provenance. The synthetic weights used in unit-test fixtures are not admissible. No basket CSV is created until the exact artifact is available.

## Decisions still pending

To be ratified in v0.9.5:

1. base period and normalisation;
2. exact official formula;
3. vintage and revision policy;
4. precision and rounding;
5. exact meaning of ARM-O, ARM-L, ARM-R and ARM-H;
6. the HFCE versus HICP distinction;
7. constitutional criteria for basket, formula or methodology changes.

## Document rule

When a future milestone closes one of these items, the decision must be recorded explicitly rather than inferred from code or release notes.
