# Delivery report v0.3.0

## Purpose

This release corrects the Step 2 architecture so the pipeline can produce a non-empty, auditable observed-participant research weight matrix instead of remaining blocked by the limited global 45-heading publication.

## Corrections completed

1. **Participation universe**
   - Russian Federation mapped to Source 90 code `RUT`.
   - Bonaire mapped to Source 90 code `BON`.
   - The governance-page footer is no longer parsed as a country.
   - The preserved official participation section maps 176/176 economies against the live Source 90 inventory.

2. **Aggregate and imputation universe**
   - The twelve Source 90 benchmark aggregates are identified explicitly by code.
   - `North America (Benchmark)` can no longer be misclassified as a twentieth imputed economy.
   - The remaining non-participant, non-aggregate Source 90 economy universe contains 19 economies, matching the official aggregate-imputation count.

3. **Economic construction**
   - Seven categories use direct ICP household headings.
   - CP02 is alcohol plus tobacco; narcotics are excluded.
   - Five categories use strict household domestic nominal expenditure and the previously ratified actual-consumption PPP proxy.
   - Government and NPISH expenditure are excluded from all numerators.

4. **Official supplemental acquisition**
   - OECD Table 5 T501 through the proven annual SDMX key and SDMX-CSV 2.0 response format.
   - UNData SNA Table 3.2.
   - Eurostat `nama_10_cp18`.
   - OECD Table 5A T501 fallback.

5. **Fail-closed controls**
   - One complete nominal provider per economy.
   - No category-level provider mixing.
   - Source 90 measure identity audit.
   - Supplemental unit-scale reconciliation.
   - Whole-economy exclusion when any category is missing.
   - Exact weight sum.
   - Separate observed research and worldwide-final files.

## Validation performed before delivery

- 28/28 automated tests passed in a clean virtual environment.
- Package installation and console command were verified.
- Workflow YAML and all JSON configuration/schema files were parsed successfully.
- The official 176-name participation fixture maps 176/176 against the current published Source 90 country inventory.
- The current Source 90 inventory separates into 176 participants, 12 benchmark aggregates and 19 other economies.
- Preserved real 2021 files from earlier successful acquisitions were parsed again:
  - OECD Table 5 T501: 36 economies with twelve divisions.
  - Eurostat: 32 economies with twelve Armilar divisions after the CP12 bridge.
  - OECD Table 5A T501: 30 economies with twelve divisions after the CP12 bridge.
  - Applying the one-provider-per-economy rule yields 45 complete economies before UNData is added.
- The complete preserved-file validation transcript is included as `REAL_SOURCE_PARSER_VALIDATION_V0.3.0.txt`.

## Expected GitHub Actions result

The next live run should:

- map 176/176 participating economies;
- identify 19 aggregate-only official imputations;
- publish a non-empty `weights_research_observed_normalized.csv` if at least 30 economies pass all twelve-category and unit gates;
- keep `weights_final_normalized.csv` empty unless the worldwide scope becomes complete;
- keep `monetary_release_allowed=false`.

The exact number of complete economies cannot be asserted before the GitHub Actions run because current source availability, revisions and the UNData response are evaluated live.

## Upload

Replace the repository contents with the contents of the release ZIP and push to `main`. The workflow now starts automatically on that push.
