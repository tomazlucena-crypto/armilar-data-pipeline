# Pakistan method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `annual_national_accounts_source_acquired` | `CONFIRMED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `1baea0f4ea4a8587bcb727e808f02aadfe1a4e679357751ea28acbb7ad2ec308` | The official PBS annual national-accounts page was acquired and confirms demand-side aggregate series. |
| `machine_readable_2021_22_hfce_aggregate_acquired` | `CONFIRMED` | `PAK_PBS_NATIONAL_ACCOUNTS_XLSX` | `dd77cb5858080e06a565cee5521593ccfccf9eebd164e040bba3f2cb10e240ef` | The official annual-tables workbook contains aggregate household final consumption for fiscal 2021-22. |
| `reference_period_matches_calendar_2021` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_XLSX` | `dd77cb5858080e06a565cee5521593ccfccf9eebd164e040bba3f2cb10e240ef` | The relevant official period is fiscal 2021-22 rather than calendar year 2021. |
| `twelve_armilar_purposes_available_in_national_accounts` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `1baea0f4ea4a8587bcb727e808f02aadfe1a4e679357751ea28acbb7ad2ec308` | The reviewed annual national-accounts source family exposes HFCE as an aggregate GDP component, not twelve purposes. |
| `hies_is_national_accounts_s14_p31` | `CONTRADICTED` | `PAK_PBS_HIES_2018_19` | `424f607f39737a0b2e956857649a4faa93c60f0f77f4ebf4d1f816fc9a32383b` | HIES is a household survey and cannot replace national-accounts S14/P31 expenditure. |
| `hies_reference_period_matches_2021` | `CONTRADICTED` | `PAK_PBS_HIES_2018_19` | `424f607f39737a0b2e956857649a4faa93c60f0f77f4ebf4d1f816fc9a32383b` | The located detailed HIES tables refer to 2018-19, not 2021. |
| `exact_armilar_source_available` | `CONTRADICTED` | `PAK_PBS_NATIONAL_ACCOUNTS_PAGE` | `1baea0f4ea4a8587bcb727e808f02aadfe1a4e679357751ea28acbb7ad2ec308` | No reviewed PBS source combines calendar 2021, current prices, strict household national accounts and twelve-purpose coverage. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
