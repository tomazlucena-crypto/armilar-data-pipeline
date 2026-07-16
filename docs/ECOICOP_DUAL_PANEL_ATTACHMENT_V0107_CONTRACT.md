# ECOICOP dual-panel external attachment contract v0.10.7

## Objective

Define how an external materialized ECOICOP v1/v2 dual-panel artifact is
attached to the repository through a deterministic descriptor without committing
official provider bytes.

## Inputs

- `config/ecoicop_dual_panel_attachment_v0107.json`
- v0.10.6 materialization runner
- v0.10.5 replay verifier
- externally stored materialized panel artifact containing `PANEL_MANIFEST.sha256`

## Outputs

- `panel_attachment_descriptor.json`
- `ATTACHMENT_MANIFEST.sha256`
- checker output `ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ATTACHMENT_PROTOCOL_V0107_VALID`

## Invariants

- Official provider bytes remain external to the repository.
- `public/latest` is not modified.
- The descriptor cannot claim transition backtest execution.
- The descriptor cannot select T0, T1, T2 or T3.
- The descriptor cannot open the verified-panel gate.
- All research and monetary gates remain false.

## Failure states

- attachment manifest mismatch;
- materialized artifact manifest mismatch;
- artifact fails v0.10.5 replay verification;
- descriptor claims official byte commit;
- descriptor claims `public/latest` modification;
- descriptor claims backtest execution;
- descriptor selects a transition strategy;
- descriptor opens a gate.

## Out of scope

- live data acquisition;
- committing official bytes;
- executing transition backtest;
- constitutional ratification;
- ARM-O extension to 2026;
- monetary use.
