# ECOICOP transition empirical backtest gate contract v0.11.0

## Objective

Define the boundary conditions for a future real empirical ECOICOP v1/v2 transition backtest.

## Inputs

- v0.10.9 execution engine policy and fixture result.
- v0.10.3 strategy and metric protocol through the predecessor chain.
- No live data in this PR.

## Outputs

- `empirical_transition_backtest_preflight_report.json`
- `EMPIRICAL_TRANSITION_BACKTEST_PREFLIGHT_MANIFEST.sha256`

## Invariants

- No empirical transition backtest is claimed.
- No strategy is selected.
- No official bytes are committed.
- `public/latest` is not modified.
- All research and monetary gates remain closed.

## Success condition

The checker emits `ECOICOP_V2_TRANSITION_BACKTEST_EMPIRICAL_GATE_V0110_VALID`.

## Out of scope

Real data acquisition, interpretation, constitutional ratification, ARM-O 2026 extension, and monetary release.
