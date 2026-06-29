# Final report v0.6.1

## Scope

Implemented the Step 2I corrective audit release. The release preserves v0.6.0 infrastructure while correcting over-definitive terminology and keeping the audit state provisional unless full evidence exists.

## Files changed

- `.github/workflows/fetch-data.yml`
- `pyproject.toml`
- `config/step2_icp2021.json`
- `src/armilar_pipeline/__init__.py`
- `src/armilar_pipeline/country_adapters.py`
- `tests/test_config.py`
- `tests/test_country_adapters.py`
- `README.md`
- `NEXT_ACTIONS.md`
- `CHANGELOG.md`
- `RELEASE_NOTES_V0.6.1.md`
- `STEP2I_VERSION_REPORT_V0.6.1.md`
- `docs/STEP2I_AUDIT_STATES.md`

## Implemented outputs

The code now writes:

- `country_source_family_coverage.csv`
- `step2i_audit_summary.json`
- `STEP_2I_AUDIT_REPORT.md`

Existing Step 2I outputs are preserved.

## Tests

- Baseline before changes: 46 tests passed.
- Updated suite after changes: 48 tests passed.
- Isolated country-adapter run: completed for CHN, IND, RUT, IDN and BRA with 0 accepted rows and 1 access failure in this sandbox.
- Full Step 2 pipeline: not completed in this sandbox because DNS resolution failed before the World Bank metadata acquisition.

## Sources really acquired

No external source was freshly acquired in this sandbox because DNS resolution failed. The code records the India MoSPI workbook attempt as `ACCESS_BLOCKED` when acquisition fails.

## Sources blocked

- India MoSPI Statement 5.1 workbook: blocked locally by DNS failure.

## States changed

- India parseable-but-boundary-ambiguous path: `CONCEPT_AMBIGUOUS`.
- India acquisition-failure path: `ACCESS_BLOCKED`.
- China, Russia, Indonesia and Brazil: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` instead of definitive unavailability.
- Step 2H exception audit rows avoid final-unavailability wording.

## Cells and coverage

- Exact cells added: 0.
- Coverage change: 0 complete economies.
- `weights_final.csv`: remains empty.
- `monetary_release_allowed`: remains false.
- `global_12_category_matrix_complete`: remains false.

## Decisions still provisional

All Step 2I decisions remain provisional current-probe decisions. `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` is not used.

## Families still to investigate

The code records source-family coverage, but a real networked run is still needed to acquire or reject the official families with full HTTP metadata and hashes.

## Step 2J

Step 2J was not started.
