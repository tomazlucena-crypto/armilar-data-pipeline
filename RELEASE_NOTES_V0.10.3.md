# ARMILAR v0.10.3

## ECOICOP v1/v2 comparability and backtest protocol

Version 0.10.3 turns the transition blocker from v0.10.2 into an executable protocol for the evidence panel and economic backtest that must precede any constitutional decision.

Eurostat now disseminates ECOICOP version 2 monthly indices and rates in `prc_hicp_minr`, item weights in `prc_hicp_iw`, and first-published data in `prc_hicp_fpd`. The archived ECOICOP version 1 monthly index and item-weight datasets remain `prc_hicp_midx` and `prc_hicp_inw`. The protocol also requires the official ECOICOP v1/v2 correspondence and country compilation metadata before any bridge can be treated as evidence-backed.

The contract separates six effects that must not be conflated:

1. classification change;
2. index-reference-base change;
3. weight change;
4. product-coverage change;
5. retrospective reconstruction;
6. linking method.

It predeclares four candidate strategies:

- `T0`: frozen legacy classification as comparator;
- `T1`: full thirteen-division ECOICOP v2 adoption;
- `T2`: an evidence-backed bridge to the twelve Armilar categories;
- `T3`: parallel comparable and provider-native series.

It also predeclares fourteen metrics covering level discontinuity, monthly and annual inflation differences, contribution differences, errors by economy and category, world aggregation, link-period sensitivity, CP08, CP09 and CP13 effects, dependence on reconstructed back series, and comparable or unresolved weight shares.

The division-level candidate matrix contains thirteen replacement rows. Same-code persistence is never accepted as proof. CP07, CP08 and CP09 are treated as material reclassifications. Replacement CP12 and CP13 remain an evidence-dependent split of legacy CP12. Every row is fail-closed and `automatic_use_allowed=false`.

This release does not acquire live 2026 data, does not execute the empirical backtest, does not ratify a transition strategy, and does not extend ARM-O. It also does not amend the Research Core constitution, create 2026 targets, train models, open research release, or authorise monetary use.

The next milestone is v0.10.4: preservation and replay verification of the official dual-classification panel and its metadata.

## Official evidence registry

- Eurostat HICP information on data: `https://ec.europa.eu/eurostat/web/hicp/information-data`
- Eurostat HICP metadata: `https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm`
- Eurostat HICP improvements, Questions and Answers, 2026: `https://ec.europa.eu/eurostat/documents/272892/11336726/HICP%2Bimprovements%2B-%2BQuestions%2Band%2BAnswers-2026-EN.pdf`
- Eurostat information note on ECOICOP v2 database restructuring: `https://ec.europa.eu/eurostat/databrowser-backend/api/public/explanatory-notes/get/Info_note_HICP_COICOP18_20260128.pdf`
- Eurostat classifications and correspondence tables: `https://ec.europa.eu/eurostat/web/metadata/classifications`
