# Decision: v0.10.4 ECOICOP dual-panel acquisition contract

## Decision

v0.10.4 creates the executable acquisition and replay contract for the official ECOICOP v1/v2 dual panel.

The release deliberately avoids committing live official bytes in the pull request. Official acquisition must run outside PR code review and must be replayed against this contract before any empirical transition backtest can be claimed.

## Reason

v0.10.3 defined the backtest protocol but did not acquire observations. The next safe step is to specify the exact evidence surface for official data while preserving the existing rule that pull requests do not publish live outputs.

## Consequences

The following remain false:

```text
ecoicop_v1_v2_dual_panel_verified=false
classification_transition_ratified=false
arm_o_2026_extension_allowed=false
backtest_execution_claim_allowed=false
model_training_allowed=false
research_release_allowed=false
monetary_use_allowed=false
```

The next milestone is to run official acquisition and replay, then promote the dual-panel verification gate only if every receipt, normalised observation and coverage row is reproducible.
