# China method gate report

Pipeline version: `0.6.5`

This report records the strict Armilar admissibility decision for the official NBS source chain.
Household-survey detail, national-accounts aggregates and input-output product tables remain conceptually separate.

| Criterion | Status | Evidence source | Evidence |
|---|---|---|---|
| `official_2021_household_survey_available` | `CONFIRMED` | `CHN_NBS_2021_HOUSEHOLD_CONSUMPTION` | The NBS release reports 2021 household consumption from a national household sample survey. |
| `survey_has_twelve_armilar_categories` | `CONTRADICTED` | `CHN_NBS_2021_HOUSEHOLD_CONSUMPTION` | The survey publishes eight groups, combining food with tobacco and alcohol and combining education with culture and recreation. |
| `survey_is_national_accounts_s14_p31` | `CONTRADICTED` | `CHN_NBS_2021_HOUSEHOLD_CONSUMPTION` | The values are collected through a household income and expenditure survey and cannot be substituted for national-accounts S14/P31 expenditure. |
| `yearbook_relevant_table_families_identified` | `AMBIGUOUS` | `CHN_NBS_YEARBOOK_2022_INDEX` | The yearbook table inventory was not structurally confirmed. |
| `input_output_reference_year_matches_2021` | `CONTRADICTED` | `CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF` | The input-output benchmark described in the 2022 yearbook is 2020, not 2021. |
| `input_output_is_exact_purpose_classification` | `CONTRADICTED` | `CHN_NBS_YEARBOOK_2022_NATIONAL_ACCOUNTS_BRIEF` | The input-output source is product-oriented and does not expose a COICOP purpose dimension; conversion would require allocation. |
| `current_price_2021_national_accounts_aggregate_available` | `CONFIRMED` | `CHN_NBS_2021_GDP_FINAL_VERIFICATION` | The final 2021 GDP verification publishes official current-price national-accounts aggregates. |
| `twelve_purpose_categories_in_2021_national_accounts` | `AMBIGUOUS` | `CHN_NBS_2021_GDP_FINAL_VERIFICATION` | A 2021 twelve-purpose national-accounts table was not conclusively assessed in this run. |
| `narcotics_excludable_without_allocation` | `CONTRADICTED` | `CHN_NBS_2021_HOUSEHOLD_CONSUMPTION` | The survey combines food, tobacco and alcohol, so CP02 and narcotics cannot be isolated without an allocation. |
| `exact_armilar_source_available` | `AMBIGUOUS` | `CHN_NBS_2021_GDP_FINAL_VERIFICATION` | The complete critical Chinese source chain was not validated in this run. |

## Decision

No Chinese source is admitted to the strict exact matrix in this probe.
The eight-group household survey is not national-accounts S14/P31 and combines Armilar categories; the yearbook input-output benchmark is 2020 and product-based; the acquired 2021 national-accounts publication is aggregate.
No survey-share split, product allocation, narcotics estimate or temporal substitution is permitted.
