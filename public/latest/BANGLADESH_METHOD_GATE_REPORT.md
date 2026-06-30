# Bangladesh method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `official_national_statistics_portal_acquired` | `NOT_FOUND` | `BGD_BBS_NSDS_PORTAL` | `` | The official BBS dissemination portal was acquired. |
| `national_accounts_release_family_identified` | `NOT_FOUND` | `BGD_BBS_RELEASE_CALENDAR_NATIONAL_ACCOUNTS` | `` | The official release calendar identifies national-accounts publications. |
| `twelve_armilar_purposes_available_in_national_accounts` | `NOT_FOUND` | `BGD_BBS_NSDS_PORTAL` | `` | The reviewed portal evidence remains aggregate and does not expose twelve-purpose household expenditure. |
| `hies_is_national_accounts_s14_p31` | `NOT_FOUND` | `BGD_BBS_HIES_DOCUMENTATION` | `` | HIES is explicitly a household survey rather than national-accounts S14/P31. |
| `hies_reference_period_matches_2021` | `NOT_FOUND` | `BGD_BBS_HIES_2022_FINAL_REPORT_PAGE` | `` | The located final HIES report refers to 2022 rather than 2021. |
| `exact_armilar_source_available` | `NOT_FOUND` | `BGD_BBS_NSDS_PORTAL` | `` | No reviewed BBS source combines 2021, current prices, strict household national accounts and twelve-purpose coverage. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
