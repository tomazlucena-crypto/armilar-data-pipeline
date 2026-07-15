# ARMILAR v0.10.6

## ECOICOP dual-panel offline materialization runner

This release defines the deterministic offline runner that materializes a
v0.10.5-compatible external ECOICOP v1/v2 dual-panel artifact from a staged
set of already acquired official bytes and parsed rows.

## Included

- `config/ecoicop_dual_panel_materialization_v0106.json`
- staged input contract with `STAGING_MANIFEST.sha256`
- deterministic raw-byte copy into a replay artifact
- deterministic `raw_receipts.csv`, `normalised_observations.csv`,
  `dual_panel_coverage.csv`, `dual_panel_lineage.csv` and `panel_summary.json`
- immediate replay verification through the v0.10.5 verifier
- v0.10.6 checker and directed tests

## Out of scope

- no live provider acquisition in the code PR
- no official bytes committed in the repository
- no modification to `public/latest`
- no panel verification gate opened
- no transition backtest execution
- no T0/T1/T2/T3 strategy selected
- no constitutional ratification
- no ARM-O 2026 extension

## Status

```text
ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZATION_RUNNER_V0106_VALID
```

The materializer can produce an external artifact with status:

```text
ECOICOP_V1_V2_DUAL_PANEL_MATERIALIZED_ARTIFACT_REPLAY_VALID
```

That artifact still does not open the committed repository gate.  The real
external provider run remains a separate non-PR operation.

## Gates

All gates remain closed:

```text
ecoicop_v1_v2_dual_panel_verified=false
classification_transition_ratified=false
arm_o_2026_extension_allowed=false
backtest_execution_claim_allowed=false
model_training_allowed=false
research_release_allowed=false
monetary_use_allowed=false
```
