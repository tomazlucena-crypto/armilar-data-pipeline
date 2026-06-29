# Release notes v0.7.1

## Evidence-cell staging

Version 0.7.1 adds the canonical `evidence_cells.csv` staging layer between the strict Step 2 matrix and the experimental global-weight builder.

### Added

- `armilar_global_weights.staging` for strict matrix to evidence-cell conversion.
- `armilar-global-weights stage-strict`.
- `evidence_class_coverage.csv` summaries by global scope, economy and category.
- Tests proving strict A/B conversion preserves values, rejects experimental allocation, and keeps C evidence out of core eligibility.

### Unchanged

- Strict matrix values and weights are not changed.
- C/D/E evidence remains excluded from `ARM-WEIGHTS-CORE`.
- `weights_final.csv` remains empty until the complete exact global gate is separately satisfied.
- `monetary_release_allowed=false`.
