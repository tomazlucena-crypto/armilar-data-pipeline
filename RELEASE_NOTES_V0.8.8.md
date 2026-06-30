# Armilar v0.8.8

Version 0.8.8 adds the first bounded economic backtest of the official v0.8.7 Eurostat category panel.

## Added

- rolling-origin scenario generation with 1, 3, 6 and 12 month horizons;
- identical comparison samples for B0 through B3;
- single-cell, whole-economy and whole-category outage simulations;
- deterministic P3, P4 and P5 completion baselines;
- errors by model, scenario, horizon, economy, category and evidence class;
- construction-weight sensitivity;
- a ranked quantitative top-three error report;
- deterministic manifests and an offline local gate;
- explicit final-vintage limitation and rejection of unsupported publication-aware claims.

## Boundaries

The v0.8.7 snapshot has no independent CP00 headline series, historical publication vintages, aligned FX panel or imputed economies. Version 0.8.8 reports those tests as unavailable instead of fabricating results.

`research_release_allowed=false`

`monetary_release_allowed=false`
