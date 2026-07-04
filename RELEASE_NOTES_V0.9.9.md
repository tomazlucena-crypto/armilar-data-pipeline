# ARMILAR v0.9.9

## Mapped Point-in-Time Proxy Feature Panel, Risk Diagnostics and Cutoff Stability

This release adds a deterministic research layer between the v0.9.8 point-in-time proxy archive and future empirical model work.

### Added

- 15 explicit, versioned proxy-to-category mapping rules;
- weekly-to-monthly, monthly and quarter-end transformations;
- exact period and year-over-year changes;
- feature age, period completeness and first-seen availability-lag profiles;
- 60-cell weighted coverage audit;
- mapping and unmapped-series audits;
- frequency-aware history and gap diagnostics by feature stream;
- complete cell-month coverage grid over the observed span;
- descriptive cross-source concordance metrics;
- source and stream provenance-concentration diagnostics;
- descriptive research risk flags for all 60 cells, without an aggregate risk score;
- deterministic comparison of successive v0.9.9 feature bundles;
- explicit addition, removal, value, provenance and metadata deltas;
- stream-variant and cell-level revision-stability reports;
- eighteen closed schemas, manifests, checker and CLI;
- adversarial tests for look-ahead, overlap, semantic tampering and gate opening.

### Deliberate limitations

- no carry-forward or imputation;
- no claim that a proxy is a direct category price;
- no automatic backtest or model eligibility;
- no feature selection, quality weighting or aggregate risk score;
- no ARM-L integration;
- no model training;
- OOHPI remains sensitivity-only;
- all release, approval and monetary gates remain false.
