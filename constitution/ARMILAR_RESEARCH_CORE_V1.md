# ARMILAR Research Core V1 constitution

## Canonical state

- constitution id: `ARMILAR_RESEARCH_CORE_V1`
- constitution version: `1.0.0-research`
- constitution status: `RATIFIED_FOR_ENGINE_DEVELOPMENT`
- canonical SHA-256: `5d0b6eb1a0f8111c3d8c3d5a8d8f70ed05789a9de82c1d68dab4233ea3f135e6`
- approved proposal version: `0.2.0`
- approved proposal SHA-256: `24f5df7e31ff604db11a43457f98e6fab16d27713d3761e4c595fb1a752bc674`
- predecessor constitution SHA-256: `3e97eb4ca423f14203c92092d310527d9bc1fbcdcfb6438e46e01401d1496734`
- approval date: `2026-07-03` with date-only precision
- scope: Research Core engine development only

## Human approval preserved verbatim

> Aprovo as sete decisões metodológicas da proposta ARMILAR_RESEARCH_CORE_V1 para ratificação exclusiva como constituição de desenvolvimento do Research Core, mantendo fechados todos os gates de release, model promotion, shadow production e utilização monetária.

## Ratified methodological decisions

1. `normalization_base`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Re-reference every economy-category official price series to the arithmetic mean of its twelve 2021 monthly non-seasonally-adjusted index levels, with the annual average equal to 100.
2. `official_formula`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Use a fixed-weight arithmetic Laspeyres-type index with PPP-adjusted 2021 expenditure weights over the 60 Research Core cells, preserving explicit AIC-PPP proxy exceptions.
3. `vintage_and_revision_policy`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Preserve immutable first-published ARM-O vintages and expose later official revisions only through a separate ARM-R reconstruction.
4. `precision_and_rounding`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Use Decimal arithmetic with precision 28 and ROUND_HALF_EVEN, avoid intermediate rounding and publish canonical decimal strings at fixed scales.
5. `exact_series_semantics`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Keep ARM-O, ARM-R, ARM-H and ARM-L separate; make every ARM-L release reproducible from an immutable, cutoff-bound information set and a versioned per-cell source registry.
6. `hfce_hicp_conceptual_treatment`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Treat the HFCE-weight/HICP-price mismatch and the 58.97% AIC-PPP proxy exposure as material research limitations, and require an OOH sensitivity analysis before external or shadow release.
7. `constitutional_amendment_process`: `RATIFIED_FOR_ENGINE_DEVELOPMENT` - Distinguish evidence-only patches, numerical weight revisions, basket scope changes and constitutional method changes, preserving every prior release and requiring explicit approval.

## Fixed Research Core

- economies: `DEU`, `ESP`, `FRA`, `ITA`, `PRT`
- weighted categories: `CP01` to `CP12`
- separate benchmark: `CP00`
- basket cells: `60`
- basket SHA-256: `5f6d3e515f4e703d47e10234af5187a0d4cdb5ba0f1acded3d516b3e1baaae1c`
- immutable weight snapshot SHA-256: `51ed567c1eea6badd077d2bd1fe1f4009a7ce1b542e16971c79c389a4370042f`
- AIC-PPP experimental proxy exposure: `0.589731681350816432896035605`

## Release gates

- `model_promotion_allowed=false`
- `monetary_release_allowed=false`
- `research_release_allowed=false`
- `shadow_production_allowed=false`
- `world_claim_allowed=false`

The ratification authorises implementation of the official engine. It does not authorise v0.9.6 outputs, public research release, model promotion, shadow production, monetary use, a world-index claim or a blockchain oracle claim.

## Binding limitations

The 25 AIC-PPP proxy cells remain experimental. The HFCE-weight and HICP-price scope mismatch remains material. The declared OOH sensitivity analysis remains mandatory before external research release or shadow production. ARM-L requires a separately approved, versioned release schedule and an approved model or explicit carry-forward baseline.
