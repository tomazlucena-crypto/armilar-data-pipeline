# ECOICOP transition backtest execution engine v0.10.9

This contract defines the execution-result artefact that will later be used for an empirical ECOICOP v1/v2 transition backtest.

The version validates:

1. the v0.10.8 readiness report;
2. the v0.10.3 candidate strategies and metrics;
3. a complete strategy × metric result matrix;
4. the result manifest and fail-closed invariants.

The PR only runs a deterministic fixture execution. The fixture output is not an empirical result and cannot be interpreted economically.

## Invariants

- `empirical_transition_backtest_executed=false`.
- `backtest_execution_claim_allowed=false`.
- `selected_strategy=NONE`.
- `result_interpretation_allowed=false`.
- No official provider bytes are committed.
- `public/latest` is not modified.
- All research and monetary gates remain closed.

## Required artefacts

A future real run must produce:

```text
transition_backtest_result_report.json
transition_backtest_metrics.csv
TRANSITION_BACKTEST_RESULT_MANIFEST.sha256
```

The result matrix must contain every declared T0-T3 strategy crossed with every metric declared in the v0.10.3 protocol.
