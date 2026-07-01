# Validation report: Armilar v0.8.8

## Package validation

The isolated v0.8.8 implementation passed:

- policy and release-gate validation;
- rejection of unsupported publication-aware claims;
- complete-grid and exact-weight checks;
- duplicate and missing-cell rejection;
- rolling-origin temporal-order tests;
- common-sample tests across all four models;
- deterministic replay tests;
- independent metric reproduction from case rows;
- output manifest tamper detection;
- explicit absence tests for headline, FX and imputed-economy sensitivities.

The dedicated suite contains 15 tests. A full synthetic 2021-2025 run produced 53,592 model-case rows, or 13,398 common cases per model, and a valid deterministic manifest.

## Required repository-local gate

The official local gate must use the preserved v0.8.7 outputs at `artifacts/v087/eurostat_vertical`. It writes:

- `artifacts/v088/minimum_backtest/`;
- `artifacts/v088/BACKTEST_GATE_REPORT.json`.

The gate performs no network calls and does not alter `public/latest`.

## Release status

The software block can be promoted to v0.8.8 only after the repository-local gate passes against the official v0.8.7 output and the complete repository test suite remains green.
