# ECOICOP transition backtest runner v0.10.8

This contract defines the runner that will execute the ECOICOP v1/v2 transition backtest only after an external dual-panel artefact has been materialized and attached through the v0.10.6 and v0.10.7 contracts.

The version validates three layers:

1. the v0.10.7 attachment protocol;
2. the v0.10.3 candidate strategies and backtest metrics;
3. the v0.10.8 readiness report invariants.

It does not claim that an empirical backtest has been executed. The generated readiness report is an audit precondition for a later external run.

## Invariants

- No strategy T0/T1/T2/T3 is selected.
- `backtest_execution_claim_allowed=false`.
- `transition_backtest_executed=false`.
- No official provider bytes are committed.
- `public/latest` is not modified.
- All research and monetary gates remain closed.
