# Egypt method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `national_accounts_catalogue_acquired` | `CONFIRMED` | `EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG` | `80052547d52f3801cee5096592af5d6c800ecbb9f8cbf292e14fdb7a8198e535` | The official CAPMAS National Accounts collection was acquired and its study inventory reviewed. |
| `machine_readable_catalogue_inventory_acquired` | `CONFIRMED` | `EGY_CAPMAS_NATIONAL_ACCOUNTS_EXPORT_CSV` | `dd4c1a3bcf31154dbfaabe65b60eb6f5a3be76fd6d9a6e36727981df1ab01eb9` | The official catalogue CSV inventory was acquired as machine-readable source-family evidence. |
| `sut_reference_period_matches_2021` | `CONTRADICTED` | `EGY_CAPMAS_SUT_2017_2018_METHOD` | `7b1ef570ba116f1a85f9722653a39d44fb925fa656d3c82dd7f4c47f80c006cf` | The identified CAPMAS SUT benchmark is 2017/2018 rather than 2021. |
| `sut_is_exact_purpose_classification` | `CONTRADICTED` | `EGY_CAPMAS_SUT_2017_2018_METHOD` | `7b1ef570ba116f1a85f9722653a39d44fb925fa656d3c82dd7f4c47f80c006cf` | The SUT is organised around products and activities, not twelve household purposes. |
| `hiecs_is_national_accounts_s14_p31` | `NOT_FOUND` | `EGY_CAPMAS_HIECS_2021` | `` | HIECS 2021 is explicitly a sample survey and cannot be substituted for national-accounts S14/P31. |
| `hiecs_reference_period_matches_2021` | `NOT_FOUND` | `EGY_CAPMAS_HIECS_2021` | `` | HIECS is a 2021 survey, but the matching year does not cure the conceptual mismatch. |
| `exact_armilar_source_available` | `NOT_FOUND` | `EGY_CAPMAS_NATIONAL_ACCOUNTS_CATALOG` | `80052547d52f3801cee5096592af5d6c800ecbb9f8cbf292e14fdb7a8198e535` | The catalogues, historical product-based SUT and 2021 survey each fail at least one exact Armilar gate; none supplies current-price 2021 S14/P31 by twelve purposes. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
