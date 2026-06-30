# Release notes v0.6.6

## Indonesia source-family audit

This release replaces the static Indonesia source decision with a dedicated BPS audit adapter.

The adapter records official BPS attempts across:

- GDP by expenditure publication evidence;
- BPS statistics-table family;
- downloadable national-accounts publication search;
- Supply and Use Tables;
- input-output tables;
- household survey or CPI Class C evidence;
- classification and methodology discovery.

## Decision

No Indonesian cells are admitted to the exact matrix.

The acquired BPS expenditure publication evidence is rejected because it is grouped and cannot provide twelve strict Armilar purpose categories without artificial splitting. SUT and input-output families are rejected from exact weights because product-to-purpose allocation would be required. Survey and CPI evidence remains Class C only.

## Gates

- Exact cells added: `0`
- `weights_final.csv`: remains empty
- `monetary_release_allowed=false`
- `global_12_category_matrix_complete=false`
- Step 2J: not started
