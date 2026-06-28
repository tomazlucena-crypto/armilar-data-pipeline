# Codex overnight report

## Result

Implemented version 0.5.0 with a national-adapter layer and the first Step 2H2 audits.

## Adapter coverage

- India: MoSPI NAS 2024 Statement 5.1 is machine-readable, current-price, `INR crore`, fiscal year 2021-22. The adapter parses items, maps exact many-to-one categories, excludes narcotics and reconciles to the official total. It remains blocked from the exact matrix because PFCE strict households-only S14/P31 and NPISH exclusion are not confirmed in the workbook.
- Russia: blocked. No deterministic official Rosstat structured 2021 strict household COICOP-HH table has passed the gates.
- China: blocked. The verified NBS source is an eight-group household survey and combines categories.
- Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam: retained as audit evidence only; no Class A/B exact adapter was created.

## Outputs

Added:

- `country_adapter_status.csv`
- `country_source_evidence.csv`
- `country_normalized_rows.csv`
- `country_mapping_audit.csv`
- `country_reconciliation_audit.csv`
- `country_adapter_failures.csv`

## Tests

Local test command:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Result: 42 tests passed.

## Workflow synchronization

Run #6 completed successfully and was pulled before using `public/latest` as the v0.4.0 baseline.

Confirmed `public/latest/step2_summary.json`:

- `pipeline_version`: `0.4.0`
- `status`: `RESEARCH_MATRIX_AVAILABLE_GLOBAL_SCOPE_INCOMPLETE`
- `research_release_allowed`: `true`
- `global_12_category_matrix_complete`: `false`
- `weights_final.csv`: header only

Confirmed `public/latest/source_probe_summary.json`:

- economies probed: 10
- source candidates probed: 11
- accessible candidates: 5
- failed candidates: 5
- runtime classes: 1 B candidate, 3 C-only, 6 unavailable

No commit or push was made while run #6 was active.
