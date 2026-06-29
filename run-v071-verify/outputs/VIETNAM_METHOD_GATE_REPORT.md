# Viet Nam method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `official_statistical_data_portal_acquired` | `CONFIRMED` | `VNM_NSO_STATISTICAL_DATA_PORTAL` | `5e1462e0f33545426127aa1b1aa31a1e8ff76f6f5913733e80e034568141c5dd` | The official NSO statistical-data portal was acquired. |
| `2021_final_consumption_release_acquired` | `CONFIRMED` | `VNM_NSO_SOCIO_ECONOMIC_2021` | `2de1b5fd3d1980e44ce81aa3ddff64a6e9a780042dceaa99af5ebf3a22ae1ca4` | The official 2021 socio-economic release was acquired. |
| `2021_release_is_household_level_by_purpose` | `CONTRADICTED` | `VNM_NSO_SOCIO_ECONOMIC_2021` | `2de1b5fd3d1980e44ce81aa3ddff64a6e9a780042dceaa99af5ebf3a22ae1ca4` | The release reports aggregate final-consumption growth and no household-purpose levels. |
| `vhlss_is_national_accounts_s14_p31` | `CONTRADICTED` | `VNM_NSO_VHLSS_2022` | `bb4eb2cabf7bf56b575714d68556419fe7ba61655fb7f76d8a7a83086fd5b87a` | VHLSS is a living-standards household survey, not national-accounts S14/P31. |
| `vhlss_reference_period_matches_2021` | `CONTRADICTED` | `VNM_NSO_VHLSS_2022` | `bb4eb2cabf7bf56b575714d68556419fe7ba61655fb7f76d8a7a83086fd5b87a` | The located VHLSS rounds are 2020 and 2022 rather than 2021. |
| `exact_armilar_source_available` | `CONTRADICTED` | `VNM_NSO_STATISTICAL_DATA_PORTAL` | `5e1462e0f33545426127aa1b1aa31a1e8ff76f6f5913733e80e034568141c5dd` | No reviewed NSO source combines 2021, current prices, strict household national accounts and twelve-purpose coverage. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
