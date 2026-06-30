# Russia method gate report

Pipeline version: `0.6.8`

This report records the strict Armilar admissibility decision for the official Rosstat and Fedstat source chain.
An aggregate national-accounts indicator, product-based SUT data and purpose-classified survey data are kept conceptually separate.

| Criterion | Status | Evidence source | Evidence |
|---|---|---|---|
| `aggregate_household_hfce_available` | `NOT_FOUND` | `RUT_FEDSTAT_HFCE_31414` | The aggregate Fedstat source was not acquired and structurally confirmed in this run. |
| `current_prices_2021_available_at_aggregate` | `NOT_FOUND` | `RUT_FEDSTAT_HFCE_31414` | Current-price 2021 aggregate evidence was not structurally confirmed in this run. |
| `twelve_purpose_categories_in_national_accounts` | `NOT_FOUND` | `RUT_FEDSTAT_HFCE_31414` | The existence of a twelve-purpose national-accounts dimension was not confirmed. |
| `sut_is_exact_purpose_classification` | `NOT_FOUND` | `RUT_ROSSTAT_SUT_2021_XLSX` | The SUT classification could not be conclusively assessed in this run. |
| `npish_excluded_at_required_category_level` | `NOT_FOUND` | `RUT_ROSSTAT_SUT_2021_XLSX` | No category-level NPISH exclusion was confirmed. |
| `purpose_detail_available_in_household_survey` | `NOT_FOUND` | `RUT_ROSSTAT_HBS_2021` | KIPC-DH survey detail was not structurally confirmed in this run. |
| `household_survey_is_national_accounts_p31dc` | `NOT_FOUND` | `RUT_ROSSTAT_HBS_2021` | The survey concept was not structurally confirmed in this run. |
| `exact_armilar_source_available` | `NOT_FOUND` | `RUT_FEDSTAT_HFCE_31414` | The complete critical source chain was not validated in this run. |

## Decision

No Russian source is admitted to the strict exact matrix in this probe.
Fedstat indicator 31414 is aggregate-only, the 2021 SUT workbook requires a product-to-purpose allocation, and KIPC-DH purpose detail comes from a household survey rather than S14/P31DC national accounts.
No product allocation, survey-share substitution or NPISH assumption is permitted.
