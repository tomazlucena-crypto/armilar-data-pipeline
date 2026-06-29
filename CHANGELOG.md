# Changelog

## 0.7.0 - Global weight contract layer

- Adds constitutional Amendment 2 for a separate experimental complete-world construction.
- Adds the isolated `armilar_global_weights` package and `armilar-global-weights` CLI.
- Adds per-cell evidence classes A to E, complete-grid validation, uncertainty bounds, provenance and donor requirements.
- Emits separate `weights_core.csv`, `weights_global.csv`, `weights_uncertainty.csv`, `weights_method_audit.csv`, summaries and non-self-referential manifests.
- Adds JSON schemas, synthetic sample input, release notes and open-source reuse documentation.
- Keeps strict Step 2 outputs unchanged, `weights_final.csv` empty and `monetary_release_allowed=false`.

## 0.6.13 - Cumulative second-wave and Step 2H exception audits

- fixed the malformed Brazil classification/methodology registry row that caused the GitHub Actions failure;
- strengthened registry validation so missing CSV values fail explicitly;
- added dedicated official-source-family adapters for Pakistan, Nigeria, Bangladesh and Viet Nam;
- added executable exception adapters for Belarus CP02, Kuwait CP02, Saudi Arabia CP02, Bonaire and Liberia;
- expanded the source registry from ten to fifteen economies and to 65 official resources or source-family entries;
- added blocked-access, content-change, deterministic-output and zero-exact-row tests for the new audits;
- admitted zero exact cells and preserved all global and monetary gates as closed.

## 0.6.12 - Viet Nam source-family audit

- separated the aggregate 2021 final-consumption release from VHLSS 2020 and 2022 household-survey evidence;
- rejected survey detail as exact national-accounts weights and added zero exact rows.

## 0.6.11 - Bangladesh source-family audit

- separated BBS national-accounts publication inventories from HIES 2022 household-survey evidence;
- rejected wrong-period and non-SNA detail without interpolation.

## 0.6.10 - Nigeria source-family audit

- separated the official 2021 GDP-expenditure report from the 2019 consumption-pattern survey;
- rejected aggregate and wrong-period survey sources from exact weights.

## 0.6.9 - Pakistan source-family audit

- separated annual aggregate national accounts from HIES survey detail;
- rejected fiscal 2021-22 as a silent substitute for calendar 2021;
- preserved NPISH and government boundaries at aggregate level without allocation.

## 0.6.8 - Egypt source-family audit and registry repair

- repaired the malformed `BRA_IBGE_CLASSIFICACOES_METODOLOGIA` CSV row;
- strengthened CSV schema tests to detect missing values;
- added dedicated Indonesia and Brazil source-family adapter outputs to the cumulative package;
- replaced the static Egypt decision with a CAPMAS source-family adapter;
- added CAPMAS National Accounts catalogue and CSV inventory resources;
- separated historical product-based SUT evidence from HIECS 2021 survey evidence;
- added Egypt gate CSV/report, failure-mode tests and deterministic fixture tests;
- admitted zero exact cells and kept all monetary gates closed.

## 0.6.7

- Replaced the static Brazil decision with `BrazilIbgeAuditAdapter`.
- Added independent IBGE source-family acquisition for SIDRA/CNT discovery, Sistema de Contas Nacionais, Contas Economicas Integradas, Tabelas de Recursos e Usos, downloadable SCN tables, POF/IPCA and classification/methodology evidence.
- Added `brazil_methodology_gate_audit.csv` and `BRAZIL_METHOD_GATE_REPORT.md`.
- Rejects SIDRA, SCN and CEI source-family evidence as exact weights unless a strict 2021 S14/P31DC twelve-purpose table is identified.
- Rejects IBGE TRU evidence as exact weights because product-to-purpose allocation would be required.
- Keeps POF/IPCA material as Class C only.
- Preserves `weights_final.csv` as empty and adds zero exact cells.

## 0.6.6

- Replaced the static Indonesia decision with `IndonesiaBpsAuditAdapter`.
- Added independent BPS source-family acquisition for the expenditure publication, statistics-table family, downloadable national-accounts publication search, SUT, input-output, survey/CPI and classification/methodology evidence.
- Added `indonesia_methodology_gate_audit.csv` and `INDONESIA_METHOD_GATE_REPORT.md`.
- Rejects grouped BPS national-accounts publication evidence without artificial category splitting.
- Rejects BPS SUT and input-output source families as exact weights because product-to-purpose allocation would be required.
- Keeps survey/CPI material as Class C only.
- Preserves `weights_final.csv` as empty and adds zero exact cells.

## 0.6.5

- Replaced the static China decision with `ChinaNbsAuditAdapter`.
- Added independent acquisition and hashing for six official NBS resources.
- Separated the 2021 eight-group household survey, yearbook inventory, 2020 input-output tables and aggregate 2021 GDP verification.
- Added `china_methodology_gate_audit.csv` and `CHINA_METHOD_GATE_REPORT.md`.
- Added fail-closed tests for blocked sources, changed content and inconsistent gate conclusions.
- Preserved `weights_final.csv` as empty and added zero exact cells.

## 0.6.4

- Replaces the Russian Fedstat homepage and incorrect BRICS publication hypothesis with five exact official resources.
- Adds `RussiaRosstatAuditAdapter` with independent acquisition, hashing and structural validation for Fedstat, SUT, HBS, KIPC-DH documentation and the national-accounts publication.
- Confirms that Fedstat indicator 31414 is aggregate-only and cannot supply twelve Armilar purposes.
- Rejects the 2021 supply-use workbook as an exact source because it is product-based, requires allocation and does not prove strict S14 exclusion at purpose level.
- Keeps KIPC-DH household-budget purpose detail as Class C survey evidence.
- Adds `russia_methodology_gate_audit.csv` and `RUSSIA_METHOD_GATE_REPORT.md`.
- Fails closed as `ACCESS_BLOCKED` when a critical source cannot be acquired and as `CONCEPT_AMBIGUOUS` when structural markers change.
- Removes the final provisional B candidate from the ten-economy registry.
- Keeps exact coverage unchanged and all global and monetary gates closed.

## 0.6.3

- Acquires and hashes the official MoSPI PFCE methodology alongside Statement 5.1.
- Confirms that Indian PFCE combines resident households and NPISH and that the components are unavailable separately.
- Rejects fiscal 2021-22 as a silent substitute for calendar 2021.
- Adds evidence source, location, retrieval timestamp and SHA-256 fields to every India methodology gate.
- Adds `INDIA_METHOD_GATE_REPORT.md`.
- Distinguishes acquired official documentation from datasets and generic discovery evidence in the source probe.
- Removes India from the provisional B-candidate set for strict exact weights.
- Keeps exact coverage unchanged and all monetary gates closed.

## 0.6.2

- Separates official-source discovery pages from qualifying acquired datasets.
- Adds ordered source-family coverage and explicit `NOT_INVESTIGATED`, `DISCOVERY_ONLY`, `ACCESS_BLOCKED` and non-machine-readable outcomes.
- Preserves structured failure receipts and attempt errors without fabricating hashes.
- Expands the official-source registry to 29 concrete candidates across ten priority economies.
- Adds independent `armilar-proxy-audit` and `armilar-matrix` programmes alongside the source probe and country adapters.
- Separates AIC/HFCE financing exposure from direct HFCE/AIC PPP proxy error.
- Adds `proxy_error_by_category.csv`, `proxy_error_by_economy.csv` and `source_probe_family_coverage.csv`.
- Keeps exact coverage unchanged and all global and monetary gates closed.

## 0.6.1

- Corrects Step 2I certainty language: diagnostic infrastructure is complete, source audit remains ongoing.
- Adds explicit methodological states for current-probe non-admissibility, access blocking, non-machine-readable sources and concept ambiguity.
- Prevents `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` unless final audit evidence exists.
- Adds `country_source_family_coverage.csv`, `step2i_audit_summary.json` and `STEP_2I_AUDIT_REPORT.md`.
- Adds pull-request validation and guards all publication steps to main non-PR runs.
- Keeps all monetary and global-scope gates closed.
