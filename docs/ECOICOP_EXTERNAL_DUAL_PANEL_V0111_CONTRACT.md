# ECOICOP external dual-panel intake contract v0.11.1

The v0.11.1 contract defines how an external verified ECOICOP v1/v2 dual-panel
artifact is admitted as input for a later empirical transition backtest.

## Inputs

- v0.11.0 empirical backtest gatekeeper policy;
- v0.10.7 external attachment descriptor;
- v0.10.6 materialized panel artifact verified through v0.10.5 replay.

## Outputs

- `external_dual_panel_intake_report.json`;
- `EXTERNAL_DUAL_PANEL_INTAKE_MANIFEST.sha256`.

## Invariants

- official provider bytes remain external to the repository;
- `public/latest` is not modified;
- no empirical transition backtest is executed;
- no transition strategy is selected;
- all research and monetary gates remain closed.
