# Brazil method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `sidra_national_accounts_family_identified` | `CONFIRMED` | `BRA_IBGE_SIDRA_CNT_TABLES` | `370363ce118cc4b4c563196665fd2e5e329c5751e820eddad103973aa80a410c` | The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only. |
| `scn_exact_twelve_purpose_table_identified` | `CONTRADICTED` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `db2ea3a2abc2aca309e5438d12d2794a7dd4217e5a004f6525ad9efec85e85ae` | The SCN publication family does not pin a strict twelve-purpose S14 table in this probe. |
| `cei_is_purpose_classified_hfce` | `NOT_FOUND` | `BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS` | `` | CEI is institutional-account evidence rather than household consumption by purpose. |
| `tru_is_exact_purpose_source` | `CONTRADICTED` | `BRA_IBGE_TABELAS_RECURSOS_USOS` | `2beacdcaeb15322e86a33e27dade90a190f32694ca33b3e1233b9a7435e54348` | TRU is product-based and cannot be mapped exactly to COICOP without allocation. |
| `pof_or_ipca_can_supply_exact_weights` | `NOT_FOUND` | `BRA_IBGE_POF_IPCA_CLASS_C` | `` | POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `NOT_FOUND` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `db2ea3a2abc2aca309e5438d12d2794a7dd4217e5a004f6525ad9efec85e85ae` | No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
