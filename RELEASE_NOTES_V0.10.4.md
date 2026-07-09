# ARMILAR v0.10.4

## ECOICOP v1/v2 official dual-panel acquisition contract

This release defines the acquisition and replay surface for the official ECOICOP v1/v2 dual panel required by the transition backtest.

It does not commit official provider bytes, execute the empirical transition backtest, select a transition strategy, ratify the classification transition, or extend ARM-O into 2026.

## Included

- `config/ecoicop_dual_panel_v0104.json`
- JSON Schemas for the policy and scaffold summary
- executable dual-panel scaffold builder and verifier
- repository checker for v0.10.4
- directed tests for the acquisition contract
- documentation and decision record

## Gate

The checker validates:

```text
ECOICOP_V1_V2_DUAL_PANEL_ACQUISITION_CONTRACT_V0104_VALID
```

The empirical dual-panel verification gate remains closed until official bytes are acquired and replayed outside a pull request:

```text
ecoicop_v1_v2_dual_panel_verified=false
```

All research, model, ARM-O extension and monetary gates remain closed.
