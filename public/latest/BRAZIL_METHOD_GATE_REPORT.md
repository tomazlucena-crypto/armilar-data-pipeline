# Brazil method gate report

Pipeline version: `0.6.13`

This report preserves the official source-family evidence and the strict Armilar admissibility decision.
A blocked source or changed structural marker prevents a closed rejection.

| Criterion | Status | Evidence source | SHA-256 | Evidence |
|---|---|---|---|---|
| `sidra_national_accounts_family_identified` | `CONFIRMED` | `BRA_IBGE_SIDRA_CNT_TABLES` | `370363ce118cc4b4c563196665fd2e5e329c5751e820eddad103973aa80a410c` | The official SIDRA national-accounts family is identified, but the landing page is discovery evidence only. |
| `scn_exact_twelve_purpose_table_identified` | `CONTRADICTED` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `502b9b44901ee53b9584b715b59cabe26b8dd41a77f2c68e7647ea6234ec32f0` | The SCN publication family does not pin a strict twelve-purpose S14 table in this probe. |
| `cei_is_purpose_classified_hfce` | `AMBIGUOUS` | `BRA_IBGE_CONTAS_ECONOMICAS_INTEGRADAS` | `a1d307f086be09a6a120e6d51a426e68050172dd84d2c5f0c6aebaf533e3f8a8` | CEI is institutional-account evidence rather than household consumption by purpose. |
| `tru_is_exact_purpose_source` | `NOT_FOUND` | `BRA_IBGE_TABELAS_RECURSOS_USOS` | `` | TRU is product-based and cannot be mapped exactly to COICOP without allocation. |
| `pof_or_ipca_can_supply_exact_weights` | `AMBIGUOUS` | `BRA_IBGE_POF_IPCA_CLASS_C` | `8d31ea08b6f63579e5a12fe67d6ce13b54d51b967d79a559f61b261191aaad0c` | POF/IPCA remains survey or price-index evidence and cannot supply exact national-accounts weights. |
| `exact_armilar_source_available` | `NOT_FOUND` | `BRA_IBGE_SISTEMA_CONTAS_NACIONAIS` | `502b9b44901ee53b9584b715b59cabe26b8dd41a77f2c68e7647ea6234ec32f0` | No reviewed IBGE source provides current-price 2021 S14/P31DC by twelve Armilar purposes without product allocation or survey substitution. |

## Decision

No exact rows are admitted by this audit. `weights_final.csv` remains empty and monetary release remains disabled.
