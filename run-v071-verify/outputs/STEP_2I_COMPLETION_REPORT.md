# Step 2I audit report

Generated: deterministic v0.6.13 Step 2I report

## Version mapping

| Version | Project step | Meaning |
|---|---|---|
| 0.4.0 | Step 2H | Gap resolver and source probe |
| 0.5.0 | Step 2I start | National adapter architecture and first audits |
| 0.6.0 | Step 2I infrastructure | Initial diagnostic closure, now treated as over-certain |
| 0.6.1 | Step 2I corrective audit | Diagnostic infrastructure complete; source audit ongoing |
| 0.6.2 | Step 2H0 hardening | Dataset/discovery separation and direct PPP proxy audit |
| 0.6.3 | Step 2H0 India evidence closure | India documentary rejection and evidence-linked methodology gates |
| 0.6.4 | Step 2H0 Russia evidence closure | Fedstat aggregate, SUT product and HBS purpose concepts separated |
| 0.6.5 | Step 2H0 China evidence closure | Survey, yearbook, input-output and GDP aggregate concepts separated |
| 0.6.6 | Step 2H0 Indonesia audit | Grouped BPS, SUT, input-output and Class C concepts separated |
| 0.6.7 | Step 2H0 Brazil audit | SIDRA, SCN, CEI, TRU and Class C concepts separated |
| 0.6.8 | Step 2H0 Egypt audit | CAPMAS catalogue, historical SUT and HIECS concepts separated |
| 0.6.9 | Step 2H0 Pakistan audit | PBS aggregate national accounts, fiscal period and HIES survey concepts separated |
| 0.6.10 | Step 2H0 Nigeria audit | NBS aggregate expenditure reports and 2019 survey detail separated |
| 0.6.11 | Step 2H0 Bangladesh audit | BBS aggregate portals and HIES 2022 survey evidence separated |
| 0.6.12 | Step 2H0 Viet Nam audit | NSO aggregate final-consumption releases and VHLSS surveys separated |
| 0.6.13 | Step 2H exception audits | Belarus, Kuwait, Saudi Arabia, Bonaire and Liberia exceptions made executable |

## Status

- Status: `Step 2I diagnostic infrastructure complete; source audit ongoing`
- No economy is marked `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.
- `weights_final.csv` remains empty.
- Step 2J has not been started.

## Step 2I decisions

- IND India: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: MoSPI Statement 5.1 is machine-readable and supports exact category aggregation plus an explicit narcotics exclusion. MoSPI methodology defines PFCE as expenditure of households and NPISH combined and states that the two are not separately available. The table reports fiscal year 2021-22 rather than calendar year 2021. It is therefore not admissible to the strict S14/P31DC Armilar 2021 exact matrix.
- RUT Russian Federation: decision `ACCESS_BLOCKED`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: The current run could not acquire or validate all critical official Russian source families: RUT_FEDSTAT_HFCE_31414, RUT_ROSSTAT_HBS_2021, RUT_ROSSTAT_SUT_2021_XLSX. The absence of an admissible exact table cannot be treated as proven while these attempts are blocked.
- CHN China: decision `CONCEPT_AMBIGUOUS`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Acquired official Chinese resources did not match the reviewed structural markers for: CHN_NBS_YEARBOOK_2022_INDEX. No source is admitted until the changed content is reviewed.
- IDN Indonesia: decision `ACCESS_BLOCKED`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: The current run could not acquire or validate all critical official Indonesia source families: IDN_BPS_GDP_EXPENDITURE_2020_2024, IDN_BPS_INPUT_OUTPUT_TABLES, IDN_BPS_STATISTICS_TABLES_EXPENDITURE, IDN_BPS_SUPPLY_USE_TABLES. A closed source decision is not permitted while these attempts remain blocked.
- BRA Brazil: decision `ACCESS_BLOCKED`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: The current run could not acquire or validate all critical official Brazil source families: BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS. A closed source decision is not permitted while these attempts remain blocked.

## Coverage

- Exact cells added: `0`
- Coverage change: `0` complete economies; all gates remain fail-closed.

## Source-family coverage

- IND `official_structured_publications`: 10 attempt(s), best status `fresh`.
- RUT `official_structured_publications`: 25 attempt(s), best status `ACCESS_BLOCKED`.
- CHN `official_structured_publications`: 30 attempt(s), best status `ACQUIRED_AGGREGATE_ONLY`.
- IDN `official_csv_xls_xlsx`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `official_statistical_database`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `official_supply_and_use_tables`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `official_input_output_tables`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `official_structured_publications`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `survey_or_cpi_class_c_only`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- IDN `official_classifications_methodology`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- BRA `official_national_accounts_api`: 1 attempt(s), best status `ACQUIRED_REJECTED`.
- BRA `official_csv_xls_xlsx`: 1 attempt(s), best status `ACQUIRED_REJECTED`.
- BRA `official_statistical_database`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- BRA `official_supply_and_use_tables`: 1 attempt(s), best status `ACQUIRED_REJECTED`.
- BRA `official_structured_publications`: 1 attempt(s), best status `ACQUIRED_REJECTED`.
- BRA `survey_or_cpi_class_c_only`: 1 attempt(s), best status `ACCESS_BLOCKED`.
- BRA `official_classifications_methodology`: 1 attempt(s), best status `SOURCE_CONTENT_REVIEW_REQUIRED`.

## Step 2H exceptions

- BLR CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - CP02 cannot be reconstructed without both alcohol and tobacco strict HFCE cells or an official narcotics-excluding aggregate.
- KWT CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No modelled alcohol/tobacco split is allowed.
- SAU CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No modelled alcohol/tobacco split is allowed.
- BON *: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No public official twelve-category allocation or proxy-numerator source accepted.
- LBR CP04|CP06|CP09|CP10|CP12: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - Median supplemental-to-Source90 ratio is incompatible; using it would risk a unit or concept error.
