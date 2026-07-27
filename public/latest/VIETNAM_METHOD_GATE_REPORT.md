# Viet Nam method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `official_statistical_data_portal_acquired` | `CONFIRMED` | `VNM_NSO_STATISTICAL_DATA_PORTAL` | `de493867f59d3b41228ed59f20ce034a4ae808846b7f4615b310841c76abe315` | The official NSO statistical-data portal was acquired. |
| `2021_final_consumption_release_acquired` | `CONFIRMED` | `VNM_NSO_SOCIO_ECONOMIC_2021` | `dc8c75ef1fdc9f1e3cbb303180a41fc178ad2de5b196cf51710a1d5c165fa7ec` | The official 2021 socio-economic release was acquired. |
| `2021_release_is_household_level_by_purpose` | `CONTRADICTED` | `VNM_NSO_SOCIO_ECONOMIC_2021` | `dc8c75ef1fdc9f1e3cbb303180a41fc178ad2de5b196cf51710a1d5c165fa7ec` | The release reports aggregate final-consumption growth and no household-purpose levels. |
| `vhlss_is_national_accounts_s14_p31` | `CONTRADICTED` | `VNM_NSO_VHLSS_2022` | `6c362adcf4f6bad8ef4ad67d04a29815b1f8b92f58aa69f442e47e77bebcb8b0` | VHLSS is a living-standards household survey, not national-accounts S14/P31. |
| `vhlss_reference_period_matches_2021` | `CONTRADICTED` | `VNM_NSO_VHLSS_2022` | `6c362adcf4f6bad8ef4ad67d04a29815b1f8b92f58aa69f442e47e77bebcb8b0` | The located VHLSS rounds are 2020 and 2022 rather than 2021. |
| `exact_armilar_source_available` | `CONTRADICTED` | `VNM_NSO_STATISTICAL_DATA_PORTAL` | `de493867f59d3b41228ed59f20ce034a4ae808846b7f4615b310841c76abe315` | No reviewed NSO source combines 2021, current prices, strict household national accounts and twelve-purpose coverage. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
