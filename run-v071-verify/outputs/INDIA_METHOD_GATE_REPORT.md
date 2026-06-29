# India method gate report

Pipeline version: `0.6.8`

This report records the strict Armilar admissibility decision for MoSPI PFCE Statement 5.1.
The source remains outside the exact matrix whenever a material criterion is contradicted or unresolved.

| Criterion | Status | Evidence source | Evidence |
|---|---|---|---|
| `represents_households_S14` | `CONTRADICTED` | `IND_MOSPI_PFCE_CHAPTER_22` | MoSPI defines PFCE as expenditure of resident households and NPISH and says the two are estimated together and are not available separately. |
| `corresponds_to_P31_HFCE` | `CONTRADICTED` | `IND_MOSPI_PFCE_CHAPTER_22` | The source is a P31-type final-consumption measure for households and NPISH combined, not strict household S14 HFCE/P31DC. |
| `excludes_NPISH` | `CONTRADICTED` | `IND_MOSPI_PFCE_CHAPTER_22` | Official methodology explicitly includes NPISH and states that household and NPISH final consumption are not separately available. |
| `excludes_government_consumption` | `CONFIRMED` | `IND_MOSPI_PFCE_CHAPTER_22` | The commodity-flow method deducts consumption on government account and other final uses outside households and NPISH. |
| `includes_imputed_rent` | `CONFIRMED` | `IND_MOSPI_PFCE_CHAPTER_22` | Official methodology includes imputed gross rent of owner-occupied dwellings. |
| `narcotics_separable` | `CONFIRMED` | `IND_MOSPI_NAS2024_STATEMENT_5_1` | Statement 5.1 exposes alcohol, tobacco and narcotics as separate item codes 2.1, 2.2 and 2.3. |
| `current_prices` | `CONFIRMED` | `IND_MOSPI_NAS2024_STATEMENT_5_1` | The workbook has an explicit current-price block in INR crore. |
| `reference_period_2021_22_available` | `CONFIRMED` | `IND_MOSPI_NAS2024_STATEMENT_5_1` | The workbook exposes fiscal year 2021-22 and the adapter preserves that label. |
| `compatible_with_armilar_calendar_2021` | `CONTRADICTED` | `IND_MOSPI_NAS2024_STATEMENT_5_1` | Fiscal year 2021-22 is not calendar year 2021; no interpolation or silent temporal conversion is permitted. |

## Decision

MoSPI PFCE cannot enter the strict exact matrix because the official methodology combines resident households and NPISH, while Statement 5.1 reports fiscal 2021-22 rather than calendar 2021.
No NPISH allocation or calendar-year interpolation is permitted.
