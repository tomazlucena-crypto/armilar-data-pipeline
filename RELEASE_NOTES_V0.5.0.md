# Release notes v0.5.0

## Step 2H1 and first Step 2H2 wave

This version adds the reusable national-adapter architecture without relaxing the economic gates.

### Added

- `armilar-country acquire` CLI;
- common adapter interface and registry;
- normalized country row schema with per-cell provenance;
- country status, source evidence, mapping audit, reconciliation audit and failure outputs;
- India MoSPI NAS 2024 Statement 5.1 parser for current-price PFCE item rows;
- exact India item bridge for Armilar categories, excluding narcotics and preserving 2021-22 as a fiscal year;
- audit-only records for Russia, China, Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam;
- stricter source-probe rejection of corrupted XLSX files;
- 6 additional tests, bringing the suite to 42 tests.

### Gate outcome

India is technically parseable and internally reconciled, but remains `UNAVAILABLE` for the exact matrix because Statement 5.1 is PFCE and the strict households-only S14/P31 boundary with NPISH excluded is not confirmed by that workbook.

China remains unavailable because the official NBS source verified in the audit is an eight-group household survey, not national-accounts HFCE/P31 with twelve Armilar categories.

Russia remains unavailable until a deterministic official Rosstat structured table for 2021 strict household COICOP-HH is acquired.

### No shortcut

No survey allocation, population/GDP/income allocation, many-to-many product bridge or AIC expenditure numerator was added. `weights_final.csv` remains empty until the global exact gates pass.
