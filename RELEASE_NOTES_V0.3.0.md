# Release notes v0.3.0

## Corrected blockers

- Fixed Russian Federation mapping from `RUS` to Source 90 code `RUT`.
- Fixed Bonaire mapping from `BES` to Source 90 code `BON`.
- Prevented the “Dual-participation economies” footer from becoming a false country.
- Reconciled the expected universe to 176 participants, 12 explicit benchmark aggregates and 19 aggregate-only official imputations.
- Prevented `North America (Benchmark)` from being counted as a twentieth imputed economy.

## New construction method

- Replaced the impossible strict-Source-90-only design with the previously ratified Option B.
- Added OECD, UNData and Eurostat official national-accounts acquisition.
- Replaced the OECD partial diagnostic request with the full annual SDMX key previously proven to return HTTP 200, using the SDMX-CSV 2.0 content type.
- Added direct ICP construction for seven categories.
- Added strict household nominal numerators with actual-consumption PPP deflators for five categories.
- Preserved the exclusion of government, NPISH and narcotics from numerators.

## New controls

- One complete supplemental provider per economy; provider mixing is blocked.
- Source 90 `nominal / PPP = real` identity audit.
- Supplemental-to-Source-90 unit-scale reconciliation.
- Complete-economy eligibility gate.
- Exact weight sum with 24 decimal places.
- Unified normalised provenance table.
- Separate research and global-final weight files.
- Automatic workflow trigger on pushes to `main` without bot-commit loops.

## Outputs

Version 0.3.0 publishes raw, normalised, category, coverage, exclusion, missing-data, source-selection, identity, unit-reconciliation and weight reports under `public/latest`.

## Validation

The package contains 28 automated tests. It has also been checked against preserved real OECD Table 5, OECD Table 5A and Eurostat 2021 responses from earlier successful acquisitions. The detailed result is preserved in `REAL_SOURCE_PARSER_VALIDATION_V0.3.0.txt`.
