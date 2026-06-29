# Nigeria method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `gdp_expenditure_2021_source_acquired` | `CONFIRMED` | `NGA_NBS_ELIBRARY_REPORT_PAGE` | `3157770c626a24ba192c25d1529f5fefd11ca74a37e14074f493f0b2291ec4f6` | The official NBS 2021 expenditure-GDP release was acquired. |
| `household_consumption_is_purpose_classified` | `CONTRADICTED` | `NGA_NBS_ELIBRARY_REPORT_PAGE` | `3157770c626a24ba192c25d1529f5fefd11ca74a37e14074f493f0b2291ec4f6` | The report presents household consumption as an aggregate GDP-expenditure component, not twelve purposes. |
| `download_is_machine_readable_twelve_purpose_data` | `CONTRADICTED` | `NGA_NBS_GDP_EXPENDITURE_2021_PDF` | `ee31ba8f1ab7dbceabf7a23d4142317b8901a1cdd7ae82cf58c88e314b1fbaed` | The official download is a PDF report and does not expose a machine-readable purpose matrix. |
| `consumption_pattern_is_national_accounts_s14_p31` | `CONTRADICTED` | `NGA_NBS_CONSUMPTION_PATTERN_2019` | `60ae5c8db1046ef7d7b62942106c2f872095915af3b660274c0dbc1b9a4a86b2` | The consumption-pattern publication is household survey evidence, not national-accounts S14/P31. |
| `consumption_pattern_reference_period_matches_2021` | `CONTRADICTED` | `NGA_NBS_CONSUMPTION_PATTERN_2019` | `60ae5c8db1046ef7d7b62942106c2f872095915af3b660274c0dbc1b9a4a86b2` | The detailed consumption study refers to 2019 rather than 2021. |
| `exact_armilar_source_available` | `CONTRADICTED` | `NGA_NBS_ELIBRARY_REPORT_PAGE` | `3157770c626a24ba192c25d1529f5fefd11ca74a37e14074f493f0b2291ec4f6` | The reviewed official sources separate a 2021 aggregate national-accounts component from wrong-period household-survey detail; neither is an exact twelve-purpose matrix. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
