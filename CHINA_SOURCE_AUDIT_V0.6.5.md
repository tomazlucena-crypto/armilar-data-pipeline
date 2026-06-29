# China source audit v0.6.5

## Decision

`NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`

This decision is provisional and source-chain-specific. It is not `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.

## Findings

- The official 2021 household release is a sample survey and reports eight groups. Food is combined with tobacco and alcohol; education is combined with culture and recreation.
- The China Statistical Yearbook 2022 inventory identifies a household-consumption table and input-output tables for 2020.
- The input-output source is product-oriented and has the wrong reference year for the 2021 benchmark.
- The official final verification of 2021 GDP provides current-price national-accounts aggregates but no household-purpose dimension.
- The two explanatory-note PDFs are preserved and hashed without OCR.

## Gates

No survey split, product-to-purpose allocation, narcotics estimate or temporal substitution is permitted. Exact cells added: `0`.
