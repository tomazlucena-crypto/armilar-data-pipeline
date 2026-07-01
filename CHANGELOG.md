# Changelog

## 0.8.8 - Minimum economic backtest

- adds a bounded rolling-origin completion backtest over the official v0.8.7 Eurostat category panel;
- compares B0 through B3 on identical single-cell, economy-outage and category-outage cases;
- reports errors by model, scenario, horizon, economy, category and evidence class;
- measures construction-weight sensitivity and ranks the three largest measured B3 error sources;
- labels the run final-vintage pseudo-real-time because historical publication vintages are unavailable;
- leaves headline, FX and imputed-economy sensitivities explicitly unavailable where inputs do not support them;
- keeps `research_release_allowed=false` and `monetary_release_allowed=false`.

## 0.8.7 - Eurostat vertical series

- adds the first bounded Eurostat HICP price-to-index vertical chain over official preserved bytes;
- acquires one bounded JSON-stat response per ECOICOP division and stores raw bytes with SHA-256 receipts;
- replays a fixed Germany, Spain, France, Italy and Portugal universe from 2021-01 through 2025-12;
- publishes monthly index rows, category/economy contributions, coverage disclosures and the economic report outside `public/latest`;
- keeps `research_release_allowed=false` and `monetary_release_allowed=false`.

## 0.8.6 - Version source, SDMX spike, properties and telemetry

- makes `pyproject.toml` the sole authored project version;
- derives runtime and generated report versions from installed package metadata;
- adds a CI gate and negative test for version divergence;
- selects `sdmx1` for the v0.8.7 Eurostat/OECD SDMX pilot and records `pysdmx` as unevaluated absent a concrete gap;
- keeps live SDMX smoke checks manual and outside pull-request CI;
- adds Hypothesis as a test-only optional dependency for bounded invariant properties;
- generates deterministic `development_metrics.json` as a CI artefact with null-plus-reason unavailable metrics;
- marks v0.8.6 contracts V086-C02 through V086-C05 complete while keeping release flags false.

## 0.8.5 - Validation gates and sensitivity audit

- verifies completion manifests and every original input hash;
- publishes row-level validation on a common comparison sample;
- compares selected, headline-only and world-pattern baselines;
- tests predeclared donor-policy sensitivity scenarios;
- evaluates overall, worst-category, worst-region and evidence gates;
- keeps the gate policy unratified and both release flags false.

## 0.8.4 - Experimental global price completion

- completes the fixed ARM01-ARM09 economy-category-month grid;
- preserves direct P1/P2 observations without promotion or alteration;
- implements headline-anchored P3, P4 regional and P5 world fallbacks;
- selects donors from declared profiles and availability without target values;
- chains monthly estimates and publishes cell and global uncertainty;
- adds leave-one-economy-out validation by category, region, horizon and class;
- hashes every input contract and generated output;
- keeps research and monetary release flags false.

## 0.8.3 - Ratified FX separation and ECB pilot

- separates local-price inflation from common-currency basket cost;
- adds official ECB EXR monthly-average acquisition and deterministic replay;
- discovers the ECB CSV structure and preserves raw bytes, receipts and hashes;
- rejects inverted FX conventions and double conversion;
- handles EUR monetary-union cells and explicit redenomination factors;
- fails closed on missing FX and unratified currency transitions;
- keeps both research and monetary release flags false.

## 0.8.2 - Fixed-universe Eurostat category pilot engine

- added the versioned nine-category Armilar canonical consumption classification;
- maps ECOICOP V1 CP01-CP12 through exact one-to-one relations and exact weighted merges;
- preserves source-category contributions separately from canonical contributions;
- publishes classification and mapping SHA-256 hashes in every pilot universe;
- stores the ECOICOP V2 bridge as provisional and blocks strict use pending back-series validation;
- exposes the HFMCE versus HFCE concept mismatch and keeps all release flags false;

- added `PriceUniverseSpec` with explicit covered and external world weight;
- added a deterministic CP01-CP12 P1 Eurostat pilot builder;
- fixes the universe and weights for the entire common complete interval;
- rejects incomplete periods without monthly renormalisation;
- emits the six required outputs plus `MANIFEST.sha256`;
- keeps the official live snapshot pending and all release flags false.

## 0.8.1 - SDMX pilot replay and provenance receipts

- added deterministic Eurostat/OECD price acquisition replay;
- added provider structure snapshots, request receipts and raw SHA-256 hashes;
- added `armilar-prices acquire` with replay and isolated live modes;
- emits source health, resolved registry, normalized observations and manifests;
- keeps live acquisition out of pull-request checks and `monetary_release_allowed=false`.
- corrected replay provenance so normalized observations are parsed from the exact hashed raw fixture bytes;
- disabled live acquisition before network access until real Eurostat and OECD response parsers and DSD snapshots exist.

## 0.8.0 - Monthly price registry and research index engine

- added P1-P5 price evidence classes;
- added deterministic rebasing and source selection;
- added monthly core/global research index calculation;
- blocked silent renormalisation and unratified FX aggregation;
- added optional `sdmx1` acquisition adapter;
- preserved `monetary_release_allowed=false`.

## 0.7.3 - Conditional global research release

- Adds a fail-closed release gate for the completed research evidence grid.
- Evaluates validation sample size, MAPE, interval coverage and estimated evidence shares.
- Builds `ARM-WEIGHTS-GLOBAL` only when every research gate passes.
- Keeps `weights_final.csv` absent and `monetary_release_allowed=false`.

## 0.7.2 - Imputation baselines and validation

- Adds deterministic C, D and E research baselines.
- Adds own-economy constrained allocation, profile-based donor selection and regional/global fallback.
- Adds leave-one-out validation and attaches available validation metrics to estimated cells.
- Does not publish global or monetary weights.

## 0.7.1 - Evidence-cell staging

- Adds `armilar_global_weights.staging`.
- Adds `armilar-global-weights stage-strict`.
- Converts strict Step 2 matrix rows into canonical evidence cells without changing values.
- Emits `evidence_cells.csv` and `evidence_class_coverage.csv`.
- Rejects experimental allocations during strict staging and prevents C/D/E evidence from being core-eligible.
- Keeps strict outputs and monetary gates unchanged.

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
