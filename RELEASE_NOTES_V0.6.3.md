# Release notes v0.6.3

## Scope

This release closes the India conceptual audit without adding exact matrix cells.

## Changes

- MoSPI Statement 5.1 and Chapter 22 methodology are acquired as separate official sources.
- Raw files, acquisition metadata and SHA-256 hashes are preserved.
- The workbook is parsed and reconciled, including explicit narcotics exclusion.
- The exact-weight path is rejected because PFCE combines households and NPISH and the two are not separately available.
- Fiscal 2021-22 is explicitly contradicted as a calendar-2021 substitute.
- India gate outputs now carry evidence URLs, locations, timestamps, hashes and review mode.
- The source probe adds `ACQUIRED_DOCUMENTATION_EVIDENCE`, preventing methodology documents from being mistaken for datasets.
- `INDIA_METHOD_GATE_REPORT.md` is included in workflow artefacts and public outputs.

## Gates

- Exact cells added: 0
- `weights_final.csv`: empty
- `global_12_category_matrix_complete=false`
- `monetary_release_allowed=false`
- Step 2J: not started
