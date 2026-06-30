# Release notes v0.6.7

Version 0.6.7 adds the Brazil Step 2H0 official source-family audit.

## Added

- `BrazilIbgeAuditAdapter` for the official IBGE source chain.
- Independent acquisition attempts for SIDRA/CNT discovery, Sistema de Contas Nacionais, Contas Economicas Integradas, Tabelas de Recursos e Usos, downloadable SCN tables, POF/IPCA and classification/methodology evidence.
- `brazil_methodology_gate_audit.csv`.
- `BRAZIL_METHOD_GATE_REPORT.md`.

## Decision

Brazil adds no exact cells.

SIDRA, SCN and CEI evidence is retained as official source-family evidence but is not admitted unless a strict 2021 current-price S14/P31DC twelve-purpose table is identified. TRU evidence remains product/resource-use based and would require product-to-purpose allocation. POF/IPCA remains Class C only.

`weights_final.csv` remains empty, `monetary_release_allowed=false`, and `global_12_category_matrix_complete=false`.
