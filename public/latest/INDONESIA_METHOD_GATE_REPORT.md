# Indonesia method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `official_grouped_hfce_publication_available` | `NOT_FOUND` | `IDN_BPS_GDP_EXPENDITURE_2020_2024` | `` | BPS publishes GDP by expenditure with grouped household-consumption categories. |
| `twelve_armilar_purposes_available` | `NOT_FOUND` | `IDN_BPS_GDP_EXPENDITURE_2020_2024` | `` | The reviewed publication is grouped and cannot be split into twelve purposes without allocation. |
| `sut_is_exact_purpose_source` | `NOT_FOUND` | `IDN_BPS_SUPPLY_USE_TABLES` | `` | The SUT family is product-based and does not prove an exact COICOP-purpose table. |
| `input_output_is_exact_purpose_source` | `NOT_FOUND` | `IDN_BPS_INPUT_OUTPUT_TABLES` | `` | Input-output tables are product-based and require prohibited allocation. |
| `survey_or_cpi_can_supply_exact_weights` | `NOT_FOUND` | `IDN_BPS_SURVEY_OR_CPI_CLASS_C` | `` | Survey or CPI data remains Class C and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `NOT_FOUND` | `IDN_BPS_GDP_EXPENDITURE_2020_2024` | `` | No reviewed source supplies strict S14/P31DC current-price 2021 values across twelve purposes without allocation. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
