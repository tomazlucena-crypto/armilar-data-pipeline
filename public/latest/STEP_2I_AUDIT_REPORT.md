# Step 2I corrective audit report

Generated: deterministic v0.6.5 Step 2I report

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

## Status

- Status: `Step 2I diagnostic infrastructure complete; source audit ongoing`
- No economy is marked `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.
- `weights_final.csv` remains empty.
- Step 2J has not been started.

## Step 2I decisions

- IND India: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: MoSPI Statement 5.1 is machine-readable and supports exact category aggregation plus an explicit narcotics exclusion. MoSPI methodology defines PFCE as expenditure of households and NPISH combined and states that the two are not separately available. The table reports fiscal year 2021-22 rather than calendar year 2021. It is therefore not admissible to the strict S14/P31DC Armilar 2021 exact matrix.
- RUT Russian Federation: decision `ACCESS_BLOCKED`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: The current run could not acquire or validate all critical official Russian source families: RUT_FEDSTAT_HFCE_31414, RUT_ROSSTAT_HBS_2021, RUT_ROSSTAT_SUT_2021_XLSX. The absence of an admissible exact table cannot be treated as proven while these attempts are blocked.
- CHN China: decision `CONCEPT_AMBIGUOUS`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Acquired official Chinese resources did not match the reviewed structural markers for: CHN_NBS_YEARBOOK_2022_INDEX. No source is admitted until the changed content is reviewed.
- IDN Indonesia: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Official source identified in probe regroups COICOP and cannot be bridged exactly to twelve Armilar categories.
- BRA Brazil: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Official product tables would require many-to-many product-to-COICOP allocation.

## Coverage

- Exact cells added: `0`
- Coverage change: `0` complete economies; all gates remain fail-closed.

## Source-family coverage

- IND `official_csv_xls_xlsx`: 5 attempt(s), best status `fresh`.
- IND `official_structured_publications`: 5 attempt(s), best status `fresh`.
- RUT `official_statistical_database`: 5 attempt(s), best status `ACCESS_BLOCKED`.
- RUT `official_supply_and_use_tables`: 5 attempt(s), best status `ACCESS_BLOCKED`.
- RUT `official_structured_publications`: 10 attempt(s), best status `ACCESS_BLOCKED`.
- RUT `survey_or_cpi_class_c_only`: 5 attempt(s), best status `ACCESS_BLOCKED`.
- CHN `official_supply_and_use_tables`: 10 attempt(s), best status `ACQUIRED_CLASS_C_SURVEY`.
- CHN `official_structured_publications`: 20 attempt(s), best status `ACQUIRED_AGGREGATE_ONLY`.
- IDN `official_supply_and_use_tables`: 5 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- IDN `official_structured_publications`: 10 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- BRA `official_national_accounts_api`: 5 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- BRA `official_structured_publications`: 10 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.

## Step 2H exceptions

- BLR CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - CP02 cannot be reconstructed without both alcohol and tobacco strict HFCE cells or an official narcotics-excluding aggregate.
- KWT CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No modelled alcohol/tobacco split is allowed.
- SAU CP02: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No modelled alcohol/tobacco split is allowed.
- BON *: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - No public official twelve-category allocation or proxy-numerator source accepted.
- LBR CP04|CP06|CP09|CP10|CP12: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` - Median supplemental-to-Source90 ratio is incompatible; using it would risk a unit or concept error.
