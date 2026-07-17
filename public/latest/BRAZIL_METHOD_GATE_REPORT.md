# Brazil method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `sidra_national_accounts_family_identified` | `CONFIRMED` | `BRA_IBGE_SIDRA_CNT_TABLES` | `370363ce118cc4b4c563196665fd2e5e329c5751e820eddad103973aa80a410c` | The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only. |
| `scn_exact_twelve_purpose_table_identified` | `CONTRADICTED` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `8451b2ee0e990409d6b4b95e14330c0c8ed5cc8eadf0233a4718001a5fd0967a` | The SCN publication family does not pin a strict twelve-purpose S14 table in this probe. |
| `cei_is_purpose_classified_hfce` | `AMBIGUOUS` | `BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS` | `15d20d1d397557db2fb09a6ca735d46fdf546b56145194538cc1dfa9e05ac7c4` | CEI is institutional-account evidence rather than household consumption by purpose. |
| `tru_is_exact_purpose_source` | `CONTRADICTED` | `BRA_IBGE_TABELAS_RECURSOS_USOS` | `2c542581fb4b3ba73bb77482b172f08b7d5124f2a0d9c2e5a3ddf2066fe9168f` | TRU is product-based and cannot be mapped exactly to COICOP without allocation. |
| `pof_or_ipca_can_supply_exact_weights` | `AMBIGUOUS` | `BRA_IBGE_POF_IPCA_CLASS_C` | `70d8f04b39a495138cf01416af2efa09d350471c7295ff94d2daf2966d18e67b` | POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `AMBIGUOUS` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `8451b2ee0e990409d6b4b95e14330c0c8ed5cc8eadf0233a4718001a5fd0967a` | No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
