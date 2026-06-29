# Step 2I audit report

Generated: deterministic v0.6.1 Step 2I report

## Version mapping

| Version | Project step | Meaning |
|---|---|---|
| 0.4.0 | Step 2H | Gap resolver and source probe |
| 0.5.0 | Step 2I start | National adapter architecture and first audits |
| 0.6.0 | Step 2I infrastructure | Initial diagnostic closure, now treated as over-certain |
| 0.6.1 | Step 2I corrective audit | Diagnostic infrastructure complete; source audit ongoing |

## Status

- Status: `Step 2I diagnostic infrastructure complete; source audit ongoing`
- No economy is marked `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.
- `weights_final.csv` remains empty.
- Step 2J has not been started.

## Step 2I decisions

- IND India: decision `CONCEPT_AMBIGUOUS`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Statement 5.1 is PFCE by item. The workbook supports exact item aggregation, but the strict households-only S14/P31 boundary and NPISH exclusion are not confirmed in this source file.
- RUT Russian Federation: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: No deterministic official XLS/XLSX/CSV/SDMX/HTML Rosstat table with 2021 strict household COICOP-HH values has passed the gates.
- CHN China: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Official NBS table is a household survey with eight combined groups, not national-accounts S14/P31 with twelve Armilar categories.
- IDN Indonesia: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Official source identified in probe regroups COICOP and cannot be bridged exactly to twelve Armilar categories.
- BRA Brazil: decision `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`, accepted `none`, non-admissible `CP04|CP06|CP09|CP10|CP12`. Blocker: Official product tables would require many-to-many product-to-COICOP allocation.

## Coverage

- Exact cells added: `0`
- Coverage change: `0` complete economies; all gates remain fail-closed.

## Source-family coverage

- IND `official_csv_xls_xlsx`: 5 attempt(s), best status `fresh`.
- IND `official_structured_publications`: 5 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- RUT `official_national_accounts_api`: 5 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- RUT `official_structured_publications`: 10 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
- CHN `official_structured_publications`: 15 attempt(s), best status `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.
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
