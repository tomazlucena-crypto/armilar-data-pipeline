# Brazil method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `sidra_national_accounts_family_identified` | `CONFIRMED` | `BRA_IBGE_SIDRA_CNT_TABLES` | `370363ce118cc4b4c563196665fd2e5e329c5751e820eddad103973aa80a410c` | The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only. |
| `scn_exact_twelve_purpose_table_identified` | `CONTRADICTED` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `77b16e0ad941d02fb89b36bc2b71cfbdf1fd3df2c327b3deedf35c894e20e6b1` | The SCN publication family does not pin a strict twelve-purpose S14 table in this probe. |
| `cei_is_purpose_classified_hfce` | `AMBIGUOUS` | `BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS` | `d74d8dc899b28b8120117ed194497e206f013e554f6737112b8c32e5e390a9c0` | CEI is institutional-account evidence rather than household consumption by purpose. |
| `tru_is_exact_purpose_source` | `CONTRADICTED` | `BRA_IBGE_TABELAS_RECURSOS_USOS` | `990a51db7ca76c630e2342f6404ab41f76c1c98d721634c0a203021825525123` | TRU is product-based and cannot be mapped exactly to COICOP without allocation. |
| `pof_or_ipca_can_supply_exact_weights` | `AMBIGUOUS` | `BRA_IBGE_POF_IPCA_CLASS_C` | `70d8f04b39a495138cf01416af2efa09d350471c7295ff94d2daf2966d18e67b` | POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `AMBIGUOUS` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `77b16e0ad941d02fb89b36bc2b71cfbdf1fd3df2c327b3deedf35c894e20e6b1` | No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
