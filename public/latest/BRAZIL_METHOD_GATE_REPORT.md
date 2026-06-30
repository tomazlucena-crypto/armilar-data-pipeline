# Brazil method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `sidra_national_accounts_family_identified` | `CONFIRMED` | `BRA_IBGE_SIDRA_CNT_TABLES` | `370363ce118cc4b4c563196665fd2e5e329c5751e820eddad103973aa80a410c` | The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only. |
| `scn_exact_twelve_purpose_table_identified` | `CONTRADICTED` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `eef5d5681b539d3b3a85d7b8a02dff889dc817eee5188c1f88085fa88fa4dd1d` | The SCN publication family does not pin a strict twelve-purpose S14 table in this probe. |
| `cei_is_purpose_classified_hfce` | `AMBIGUOUS` | `BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS` | `24107517b58a02b97d26a7bdf85acbf88b14274105fd324a568764465312c055` | CEI is institutional-account evidence rather than household consumption by purpose. |
| `tru_is_exact_purpose_source` | `CONTRADICTED` | `BRA_IBGE_TABELAS_RECURSOS_USOS` | `49b790fd65792c03c0106e03c4be3edca85c364dfe1479a4e7248e08c71f91e3` | TRU is product-based and cannot be mapped exactly to COICOP without allocation. |
| `pof_or_ipca_can_supply_exact_weights` | `AMBIGUOUS` | `BRA_IBGE_POF_IPCA_CLASS_C` | `a3cf65a6a3ed9494655570bdeebc580449d5c32300aec0b28e320c1dc6a0e8d3` | POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `AMBIGUOUS` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `eef5d5681b539d3b3a85d7b8a02dff889dc817eee5188c1f88085fa88fa4dd1d` | No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
