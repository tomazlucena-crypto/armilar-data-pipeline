# Pakistan method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `annual_national_accounts_source_acquired` | `CONFIRMED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `9f3ab3c0ea59a50e49dc3f45ac5068a4e8aa56af6d99affaa9efc1f2e50565ca` | The official PBS annual national-accounts page was acquired and confirms demand-side aggregate series. |
| `machine_readable_2021_22_hfce_aggregate_acquired` | `CONFIRMED` | `PAK_PBS_NATIONAL_ACCOUNTS_XLSX` | `dd77cb5858080e06a565cee5521593ccfccf9eebd164e040bba3f2cb10e240ef` | The official annual-tables workbook contains aggregate household final consumption for fiscal 2021-22. |
| `reference_period_matches_calendar_2021` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_XLSX` | `dd77cb5858080e06a565cee5521593ccfccf9eebd164e040bba3f2cb10e240ef` | The relevant official period is fiscal 2021-22 rather than calendar year 2021. |
| `twelve_armilar_purposes_available_in_national_accounts` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `9f3ab3c0ea59a50e49dc3f45ac5068a4e8aa56af6d99affaa9efc1f2e50565ca` | The reviewed annual national-accounts source family exposes HFCE as an aggregate GDP component, not twelve purposes. |
| `hies_is_national_accounts_s14_p31` | `CONTRADICTED` | `PAK_PBS_HIES_2018_19` | `9b3208dcdec336df39e334f92f5db02238a44e4d1112fc1ba7c1c49e7aa589a7` | HIES is a household survey and cannot replace national-accounts S14/P31 expenditure. |
| `hies_reference_period_matches_2021` | `CONTRADICTED` | `PAK_PBS_HIES_2018_19` | `9b3208dcdec336df39e334f92f5db02238a44e4d1112fc1ba7c1c49e7aa589a7` | The located detailed HIES tables refer to 2018-19, not 2021. |
| `exact_armilar_source_available` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `9f3ab3c0ea59a50e49dc3f45ac5068a4e8aa56af6d99affaa9efc1f2e50565ca` | No reviewed PBS source combines calendar 2021, current prices, strict household national accounts and twelve-purpose coverage. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
