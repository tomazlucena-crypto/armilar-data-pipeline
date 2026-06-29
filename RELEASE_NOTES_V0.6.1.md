# Release notes v0.6.1

## Step 2I corrective audit

Version 0.6.1 corrects the over-definitive language introduced in v0.6.0. Step 2I is now described as diagnostic infrastructure complete, with the source audit still ongoing.

### Added

- explicit methodological states:
  - `EXACT_OFFICIAL`;
  - `OFFICIAL_DERIVED_NO_ALLOCATION`;
  - `OFFICIAL_EXPERIMENTAL_ALLOCATION`;
  - `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`;
  - `ACCESS_BLOCKED`;
  - `SOURCE_NOT_MACHINE_READABLE`;
  - `CONCEPT_AMBIGUOUS`;
  - `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`;
- guard preventing `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` without complete documented family coverage;
- `country_source_family_coverage.csv`;
- `step2i_audit_summary.json`;
- `STEP_2I_AUDIT_REPORT.md`;
- pull request validation in GitHub Actions;
- publication guards preventing PRs or non-main manual runs from modifying `public/latest`, committing or replacing releases;
- tests for the new states, final-unavailability gate and workflow protection.

### Changed

- India now remains `CONCEPT_AMBIGUOUS` when the workbook is parseable but the strict S14/P31DC household boundary and NPISH exclusion are not confirmed.
- India becomes `ACCESS_BLOCKED` when the official MoSPI workbook cannot be acquired in the current run.
- China, Russia, Indonesia and Brazil use `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` instead of a definitive unavailability state.
- Step 2H exceptions also avoid definitive unavailability wording unless an exhaustive audit is documented.
- The Step 2I summary status is now `DIAGNOSTIC_INFRASTRUCTURE_COMPLETE_SOURCE_AUDIT_ONGOING`.

### Gates preserved

No new exact cells are admitted. `weights_final.csv` remains empty, `monetary_release_allowed=false`, `global_12_category_matrix_complete=false`, the AIC proxy audit remains `INSUFFICIENT_DIRECT_EVIDENCE`, and Step 2J is not started.
