# Armilar Research Core V1 Scope

## Baseline

- Baseline: v0.9.4.
- PR #16 is integrated in `main`.
- Reference commit: `55b38a0`.
- v0.9.4 validated the official v0.9.3 first-published panel, replay, pre-release forecast backtest and paired diagnostics for the limited universe.
- The next step is to verticalise the system toward shadow production.

## Provisional universe

- Universe id: `ARMILAR_RESEARCH_CORE_V1`
- Economies: `DEU`, `ESP`, `FRA`, `ITA`, `PRT`
- Basket categories: `CP01` to `CP12`
- Separate benchmark: `CP00`

CP00 is outside the weighted sum and exists only for comparison and diagnostics.

## Series

- `ARM-O`: last calculated index with published official data.
- `ARM-L`: live estimate from the last official anchor.
- `ARM-R`: reconstructed history with later official revisions.
- `ARM-H`: separate CP00 headline benchmark.

None of these series may silently replace another.

## FX rule

- Current FX stays outside the primary index.
- FX moves may appear only as an informational layer.
- FX failures do not change ARM-O or ARM-L.
- Any future FX proxy needs a dedicated methodological decision and its own backtest.

## Allowed claim

The product may initially be described as:

> Experimental consumer price index based on fixed Armilar weights and official Eurostat category prices for five euro-area economies, accompanied by a live estimate and uncertainty metrics.

It may not be presented as:

- a world inflation index;
- monetarily eligible;
- a blockchain oracle;
- a monetary policy recommendation;
- a complete HFCE measure;
- a substitute for HICP.

## Pending ratification for v0.9.5

The following remain to be ratified:

1. base period and normalisation;
2. exact official formula;
3. vintage and revision policy;
4. precision and rounding;
5. exact meaning of ARM-O, ARM-L, ARM-R and ARM-H;
6. the conceptual gap between HFCE and HICP;
7. constitutional criteria for basket, formula or methodology changes.

## Gates

- `research_release_allowed=false`
- `model_promotion_allowed=false`
- `monetary_release_allowed=false`
