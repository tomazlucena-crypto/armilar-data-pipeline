# Global research release gates v0.7.3

Version 0.7.3 adds a fail-closed gate between the research imputation grid and publication of `ARM-WEIGHTS-GLOBAL`.

The gate evaluates:

- completeness of the economy-category grid;
- leave-one-out validation coverage;
- prediction count;
- MAPE;
- interval coverage;
- estimated expenditure share;
- Class E fallback share;
- validation metrics attached to estimated cells;
- prohibition of result-driven donor selection;
- preservation of `monetary_release_allowed=false`.

Passing the gate may authorise a research release and invoke the existing global-weight builder. It never creates or populates `weights_final.csv`, and it cannot authorise monetary use.

Thresholds are defined in `config/global_release_gates.json`. They are initial research gates and must later be calibrated from real validation results rather than treated as constitutional constants.
