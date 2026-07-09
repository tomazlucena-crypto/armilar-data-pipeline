# ECOICOP v1/v2 dual-panel acquisition contract v0.10.4

## Objective

Define the exact official evidence required to build a replayable ECOICOP v1/v2 dual panel for the future transition backtest.

## Inputs

- v0.10.3 protocol and mapping candidates;
- the five-economy Eurostat HICP universe already used by the ARM-O materialisation bridge;
- Eurostat legacy HICP index and weight datasets;
- Eurostat replacement ECOICOP v2 index and weight datasets;
- classification correspondence and country compilation metadata.

## Outputs

The executable scaffold emits:

- acquisition request register;
- raw receipt contract;
- normalised observation contract;
- coverage contract;
- lineage contract;
- deterministic summary;
- SHA-256 manifest.

## Invariants

- no provider bytes are committed by this release;
- no empirical observation is treated as already acquired;
- live 2026 observations cannot create ARM-O targets;
- no transition strategy is selected;
- no constitutional decision is taken;
- all release, model and monetary gates remain closed;
- every future observation must trace to an immutable raw receipt.

## Stop condition

Stop after the acquisition and replay contract is executable and tested. Do not execute the economic transition backtest until a verified dual panel exists.
