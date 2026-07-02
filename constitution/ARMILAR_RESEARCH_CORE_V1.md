# ARMILAR_RESEARCH_CORE_V1 Constitution

## Status

- Constitution version: `0.1.0-draft`
- Constitution status: `DRAFT`
- Research Core id: `ARMILAR_RESEARCH_CORE_V1`

The canonical source is [`ARMILAR_RESEARCH_CORE_V1.json`](ARMILAR_RESEARCH_CORE_V1.json). This Markdown file is a human-readable representation and must not be used as a substitute for the JSON contract.

## Scope

The Research Core is an experimental consumer price index based on fixed Armilar weights and official Eurostat category prices for five euro-area economies, accompanied by a live estimate and uncertainty metrics.

This draft does not authorise a world-index claim, monetary use, a policy recommendation or blockchain-oracle use.

## Economies

- `DEU`
- `ESP`
- `FRA`
- `ITA`
- `PRT`

No economy may be added silently.

## Basket categories

The weighted basket contains exactly:

`CP01`, `CP02`, `CP03`, `CP04`, `CP05`, `CP06`, `CP07`, `CP08`, `CP09`, `CP10`, `CP11`, `CP12`.

`CP00` is a separate headline benchmark. It remains outside the weighted basket and may be used only for comparison and diagnostics.

## Series

- `ARM-O`: last index calculated only from published official data.
- `ARM-L`: live estimate from the last official anchor.
- `ARM-R`: history reconstructed with later official revisions.
- `ARM-H`: separate CP00 headline benchmark.

No series may silently replace another.

## Currency policy

- Current FX is outside `ARM-O`.
- Current FX is outside `ARM-L`.
- FX may appear in an informational layer.
- An FX failure does not change `ARM-O` or `ARM-L`.
- Future use of FX as a proxy requires a separate methodological decision and a dedicated backtest.

## Release gates

All gates remain closed:

- `research_release_allowed=false`
- `model_promotion_allowed=false`
- `monetary_release_allowed=false`
- `shadow_production_allowed=false`

A draft constitution cannot activate any gate.

## Basket materialisation

Status: `BASKET_MATERIALIZATION_BLOCKED`.

The Research Core requires exactly 60 economy-category weights. The exact weights used by v0.9.4 are stored in the preserved v0.9.3 first-published panel artifact:

`artifacts/v093/first_published_panel/first_published_observations.csv`

That artifact is not committed in the repository. The v0.9.4 unit-test fixture uses synthetic weights and is not an admissible source. No empty basket, artificial weight or new renormalisation may be committed.

## Decisions pending ratification

- base period and normalisation;
- exact official formula;
- vintage and revision policy;
- precision and rounding;
- exact series semantics;
- treatment of the HFCE-HICP conceptual difference;
- constitutional amendment process.

Each remains `PENDING_RATIFICATION`.

## Prohibitions

The draft prohibits:

- silent economy expansion;
- category additions without constitutional change;
- CP00 in the weighted basket;
- silent renormalisation of an incomplete basket;
- automatic weight changes;
- model-driven rewriting of official history;
- automatic gate activation;
- monetary use;
- presentation as a world index;
- blockchain-oracle use.

## Conditions for ratification

Ratification requires, at minimum:

1. closure of every pending decision through an explicit decision record;
2. materialisation of all 60 exact weights with preserved provenance;
3. validation of the constitution and basket contracts;
4. deterministic canonicalisation and hash rules;
5. confirmation that all release and promotion gates remain separately controlled;
6. explicit approval through a dedicated pull request.
