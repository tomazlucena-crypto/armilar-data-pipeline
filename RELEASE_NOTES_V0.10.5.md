# ARMILAR v0.10.5

## ECOICOP dual-panel replay verifier

This release defines the offline replay verifier that an externally materialised
ECOICOP v1/v2 dual-panel artifact must satisfy before any empirical transition
backtest can be executed.

## Included

- replay policy for external dual-panel artifacts;
- required artifact file register;
- raw receipt, normalised observation, coverage and lineage contracts;
- deterministic contract scaffold;
- external artifact verifier;
- checker and targeted tests;
- JSON schemas;
- development contract update.

## Explicitly out of scope

- committing official provider bytes;
- modifying `public/latest`;
- verifying a real official panel;
- executing the transition backtest;
- selecting T0, T1, T2 or T3;
- ratifying the classification transition;
- extending ARM-O to 2026;
- opening research, model or monetary gates.

## Gate

```text
ECOICOP_V1_V2_DUAL_PANEL_REPLAY_VERIFIER_V0105_VALID
```

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
