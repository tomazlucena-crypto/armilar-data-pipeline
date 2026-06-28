# Release notes v0.3.1

## Fixed

- Corrected the CLI JSON serialization failure exposed by GitHub Actions run `28336070795`.
- Exact `Decimal` values and filesystem `Path` values can now be printed as valid JSON.
- A successful acquisition with a valid research matrix now returns exit code 0 even when global coverage remains incomplete.
- `--strict-release` continues to return a non-zero code only when `research_release_allowed=false`.

## Regression protection

Added tests that reproduce the former post-build crash with exact 24-decimal weights and verify that terminal output remains parseable JSON.

## Validated real-run state

The failed-status artefact from v0.3.0 proves that the underlying pipeline completed and generated a valid research matrix for 62 participating economies, 744 cells and an exact weight sum of 1. The remaining 114 participating economies and 19 officially imputed economies remain explicit global-scope blockers. No synthetic allocations are introduced by this release.
