# ARMILAR v0.10.0

## Point-in-time target alignment and frozen baseline protocol

This release adds a research-only bridge from verified v0.9.9 features to first-published ARM-O targets.

### Added

- deterministic ARM-O cell target archive;
- monthly and year-over-year target definitions;
- explicit target availability timestamps;
- 0, 1 and 3 month forecast cases;
- long-format aligned features;
- row-level leakage audit;
- candidate audit that distinguishes missing, already-known and eligible targets;
- valid zero-case result when the ARM-O horizon does not overlap the feature cutoffs;
- cutoff inventory;
- zero-change, last-observed and seasonal baselines;
- MAE, RMSE, mean error and prediction-coverage diagnostics;
- cell-level protocol-readiness report;
- thirteen closed schemas;
- CLI and fail-closed repository checker.

### Deliberately excluded

- model training or selection;
- feature selection or quality weighting;
- ARM-L;
- imputation or carry-forward;
- any out-of-sample, production or monetary claim.

All release and use gates remain closed.
