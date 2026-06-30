# Release notes v0.7.0

## Global coverage contract

Version 0.7.0 introduces a separate experimental complete-world construction without changing the strict observed matrix.

### Added

- constitutional Amendment 2 for complete-world coverage and uncertainty;
- per-cell evidence classes A to E;
- complete-grid validator for every economy across CP01 to CP12;
- separate `weights_core.csv` and `weights_global.csv` outputs;
- compositional lower and upper weight bounds;
- method and provenance audit output;
- deterministic manifests;
- open-source component registry and build-versus-reuse gate;
- independent CLI `armilar-global-weights`;
- tests for completeness, uncertainty, class semantics and deterministic output.

### Unchanged

- the existing strict matrix and Option B audit;
- historic public outputs;
- `monetary_release_allowed=false`;
- the requirement to preserve original evidence and hashes.

### Explicit limitation

This release defines and tests the global construction contract. It does not yet impute the real production universe or calculate a live price index.

## Packaging correction

- Uses the repository's existing `unittest` test runner, without adding an undeclared `pytest` dependency.
- Updates `pyproject.toml`, `armilar_pipeline.__version__`, runtime configuration and version assertions together.
- Refuses to apply over the obsolete public `main` version 0.6.5.
