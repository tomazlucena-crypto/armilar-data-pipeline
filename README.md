# Armilar data pipeline

Auditable acquisition and construction pipeline for Step 2 of the Armilar Index: the ICP 2021 research weight matrix.

## Version 0.8.8: minimum economic backtest

Version 0.8.8 runs a bounded rolling-origin stress test over the official v0.8.7 Eurostat category panel. It compares four deterministic missing-cell baselines on identical samples, decomposes errors by scenario, horizon, economy, category and evidence class, measures weight sensitivity and ranks the three largest observed B3 error sources.

The input is a single final provider vintage. Historical publication lags and revisions are unavailable, so the result is explicitly `FINAL_VINTAGE_PSEUDO_REAL_TIME` and `publication_aware=false`. Official headline, FX and imputed-economy sensitivities remain unavailable rather than estimated without evidence. `research_release_allowed=false` and `monetary_release_allowed=false`.

## Version 0.8.7: official Eurostat vertical series

Version 0.8.7 preserves and replays the first bounded official Eurostat HICP category panel for Germany, Spain, France, Italy and Portugal from 2021-01 through 2025-12. The fixed-universe output contains 3,600 observations and 60 monthly index values with complete manifests and no `public/latest` mutation.

## Version 0.8.6: development discipline and telemetry

Version 0.8.6 makes `pyproject.toml` the only authored project version, derives runtime version values from installed metadata, selects `sdmx1` for the v0.8.7 Eurostat/OECD pilot, adds bounded Hypothesis property tests and publishes deterministic development telemetry as a CI artefact. Live SDMX checks are manual and non-PR only; unavailable telemetry metrics are `null` with reasons. `research_release_allowed=false` and `monetary_release_allowed=false`.

## Version 0.8.5: validation gates and sensitivity audit

Version 0.8.5 verifies every v0.8.4 output and original input hash, publishes row-level validation, compares the selected completion model with headline-only and world-pattern baselines, runs predeclared donor sensitivity scenarios and evaluates overall plus worst-group gates. The gate policy is deliberately unratified and passing technical gates cannot authorise release. `research_release_allowed=false` and `monetary_release_allowed=false`.

## Version 0.8.4: experimental global price completion

Version 0.8.4 completes the canonical ARM01-ARM09 economy-category-month grid using P1/P2 official observations and headline-anchored P3/P4/P5 fallbacks. P4 and P5 estimate only the category deviation from each target economy's official headline inflation, select donors ex ante from declared profiles and availability, chain monthly indices, publish uncertainty and run leave-one-economy-out validation by category, region, horizon and fallback class. All inputs and outputs are hashed. The engine is experimental and does not claim a real global official data release. `research_release_allowed=false` and `monetary_release_allowed=false`.

## Version 0.8.3: ratified FX separation and ECB pilot

Version 0.8.3 formally separates the primary `PPP_WEIGHTED_LOCAL_PRICE_RELATIVES` index from the informational `COMMON_CURRENCY_BASKET_COST` layer. Current FX never enters the primary inflation index. The common-currency layer uses official ECB EXR monthly average rates quoted as currency units per EUR, preserves raw bytes and SHA-256 receipts, rejects inverse conventions and fails closed without renormalisation when FX is missing. Both layers remain research-only and do not inform monetary policy.

## Version 0.8.2: fixed-universe Eurostat category pilot engine

Version 0.8.2 adds `PriceUniverseSpec` and a deterministic engine for an explicit Eurostat HICP category pilot. It admits only complete P1 CP01-CP12 economies, fixes the universe for the whole common interval, normalises covered world weights once, publishes external coverage and rejects incomplete months. The engine is ready for a hash-preserved official Eurostat snapshot; this commit does not represent synthetic fixtures as live data. `research_release_allowed=false` and `monetary_release_allowed=false`.

### Canonical Armilar consumption classification

The v0.8.2 pilot now publishes nine stable Armilar macro-categories while preserving all twelve ECOICOP V1 source divisions. The total index is still calculated from source-category fixed weights; canonical categories are exact weighted merges and cannot alter the total. Mapping files, effective periods and SHA-256 hashes are published. The ECOICOP V2 bridge remains provisional until the official back series is validated. The HICP monetary-consumption scope versus Armilar HFCE weights remains an explicit release blocker.

## Version 0.8.1: SDMX pilot replay and provenance receipts

Version 0.8.1 adds deterministic replay from canonical synthetic Eurostat/OECD contract fixtures. Normalized observations are parsed from the same raw bytes recorded in the SHA-256 receipts. The fixtures are not archived official provider responses. Live acquisition is disabled until official DSD snapshots and provider-specific parsers are implemented, and it remains outside pull-request checks.

## Version 0.8.0: monthly price registry and research index engine

Version 0.8.0 adds a canonical monthly CPI/HICP registry, the P1-P5 price-evidence hierarchy, deterministic rebasing, audited source selection and monthly core/global research index calculation. Incomplete months are never silently renormalised. The live OECD and Eurostat pilots remain disabled pending network validation, common-currency FX treatment is not yet ratified, and `monetary_release_allowed=false` remains mandatory.

## Version 0.7.3: conditional global research release

Version 0.7.3 adds a fail-closed gate between the completed research evidence grid and publication of `ARM-WEIGHTS-GLOBAL`. It evaluates validation coverage, MAPE, interval coverage, estimated expenditure share, Class E fallback share and per-cell validation metadata. A research release is created only when every configured gate passes. `weights_final.csv` remains untouched and `monetary_release_allowed=false` cannot be overridden.

## Version 0.7.2: baseline imputation and validation

Version 0.7.2 adds deterministic C, D and E research baselines, own-economy aggregate allocation, profile-based donor selection, regional/global fallback and leave-one-out validation. Outputs remain research-only until the v0.7.3 gate passes.

## Version 0.7.1: evidence-cell staging

Version 0.7.1 adds a canonical `evidence_cells.csv` staging layer between the strict Step 2 matrix and the experimental global-weight builder. The `armilar-global-weights stage-strict` command converts `economy_category_matrix_weight_eligible.csv` into per-cell evidence records with source state, evidence class, transformation method and core/global eligibility.

Strict rows are converted to A/B evidence without changing their real-expenditure values or uncertainty bounds. Experimental allocations are rejected rather than silently promoted, and C/D/E evidence can be marked global-eligible only outside `ARM-WEIGHTS-CORE`.

## Version 0.7.0: global weight contract layer

Version 0.7.0 keeps the strict observed matrix and national-source audits intact while adding a separate experimental complete-world weight contract. The new `armilar-global-weights` programme builds `ARM-WEIGHTS-GLOBAL` from a complete economy-category grid with per-cell evidence classes A to E, required uncertainty for estimated cells, method provenance and deterministic manifests.

`ARM-WEIGHTS-CORE` remains separate and accepts only official exact cells and official deterministic derivations. Estimated C/D/E cells can enter only the experimental global construction with explicit bounds, method IDs, model versions, source IDs and donors where applicable. They are never promoted to official exact values.

The release also adds Amendment 2, JSON schemas, a synthetic sample input, open-source reuse documentation and build-versus-reuse decisions. `monetary_release_allowed=false` remains unchanged.

## Version 0.6.13: cumulative second-wave and Step 2H exception audits

Version 0.6.13 is the cumulative staging release intended to replace the failed v0.6.7 pull-request contents. It includes the malformed Brazil registry-row repair, dedicated official-source-family audits for Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam, and executable Step 2H exception audits for Belarus CP02, Kuwait CP02, Saudi Arabia CP02, Bonaire and Liberia.

All new country adapters preserve real acquisition receipts and hashes, distinguish `ACCESS_BLOCKED` from source non-admissibility, require renewed review when structural markers change, and emit zero exact rows when a source fails a material Armilar gate. Survey and CPI detail remains Class C, product-based SUT/input-output evidence is not converted into exact purpose weights, and wrong-period evidence is not silently interpolated.

The source registry now covers fifteen economies and sixty-five concrete official resources or source-family entries. `weights_final.csv` remains header-only, `global_12_category_matrix_complete=false`, `monetary_release_allowed=false`, and direct AIC/HFCE PPP validation remains `INSUFFICIENT_DIRECT_EVIDENCE`.

## Versions 0.6.9 to 0.6.12: second-wave country audits

- **0.6.9 Pakistan:** separates aggregate fiscal-year national accounts from HIES survey detail and rejects fiscal 2021-22 as calendar 2021.
- **0.6.10 Nigeria:** separates the 2021 aggregate expenditure-GDP report from the 2019 household consumption survey.
- **0.6.11 Bangladesh:** separates the national-accounts publication inventory from HIES 2022 survey evidence.
- **0.6.12 Viet Nam:** separates the aggregate 2021 final-consumption release from VHLSS 2020/2022 survey publications.

## Version 0.6.8: Egypt source-family audit and registry repair

Version 0.6.8 repairs the malformed Brazil classification/methodology registry row that caused the v0.6.7 pull-request workflow to fail. The CSV schema test now also rejects missing values, not only surplus fields.

Egypt now uses a dedicated `EgyptCapmasAuditAdapter`. It acquires the CAPMAS National Accounts catalogue, the machine-readable catalogue CSV export, the 2017/2018 Supply and Use Tables study description and HIECS 2021 separately. The catalogue evidence identifies historical SUT and input-output studies, the relevant SUT benchmark is 2017/2018 and product/activity based, and HIECS 2021 is a sample survey rather than national-accounts S14/P31. No exact cells are added.

Network failures remain `ACCESS_BLOCKED`; changed structural markers require review. `weights_final.csv` remains empty, `global_12_category_matrix_complete=false` and `monetary_release_allowed=false`.

## Version 0.6.7: Brazil source-family audit

Version 0.6.7 replaces the static Brazil decision with a dedicated `BrazilIbgeAuditAdapter`. It records IBGE official source-family attempts for SIDRA national-accounts table discovery, Sistema de Contas Nacionais, Contas Economicas Integradas, Tabelas de Recursos e Usos, downloadable SCN tables, POF/IPCA Class C evidence and classification/methodology discovery.

The decision remains `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` when the critical IBGE source-family chain is acquired and structurally reviewed. SIDRA and SCN evidence remains discovery or publication-family evidence, CEI remains institutional-accounts evidence, TRU remains product/resource-use evidence requiring product-to-purpose allocation, and POF/IPCA remains Class C only. No exact cells are added.

## Version 0.6.6: Indonesia source-family audit

Version 0.6.6 replaces the static Indonesia decision with a dedicated `IndonesiaBpsAuditAdapter`. It records BPS official source-family attempts for the GDP-by-expenditure publication, BPS statistics-table family, downloadable national-accounts publication search, Supply and Use Tables, input-output tables, survey/CPI Class C evidence and classification/methodology discovery.

The decision remains `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` when the critical BPS source-family chain is acquired and structurally reviewed. The known BPS expenditure publication is rejected because it is grouped rather than a twelve-Armilar-purpose strict S14/P31DC current-price dataset. BPS SUT and input-output evidence remains product/source-family evidence and cannot be transformed into exact COICOP weights through many-to-many allocation. Survey or CPI evidence remains Class C only. No exact cells are added.

## Version 0.6.5: China source-chain closure

Version 0.6.5 replaces the static China decision with a dedicated `ChinaNbsAuditAdapter`. It acquires six exact official NBS resources independently, preserves raw evidence and hashes, and separates the eight-group household survey, the statistical-yearbook inventory, the 2020 product-based input-output family and the aggregate 2021 GDP verification.

The current decision is `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` only when all four critical sources are acquired and their reviewed structural markers are confirmed. Network failures produce `ACCESS_BLOCKED`; changed source content produces `CONCEPT_AMBIGUOUS`. No exact cells are added.

## Version 0.6.3: India evidence closure

Version 0.6.3 converts the India method gate from an unresolved hypothesis into an evidence-linked rejection for the strict exact matrix. The adapter acquires both MoSPI Statement 5.1 and the official PFCE methodology, preserves each raw file and hash, reconciles the item table, and then fails closed.

The official methodology defines PFCE as final consumption of resident households and NPISH estimated together and states that the two components are not available separately. Statement 5.1 is also reported for fiscal 2021-22 rather than calendar 2021. The source therefore remains useful research evidence but cannot supply strict S14/P31DC calendar-2021 weights without prohibited NPISH allocation and temporal interpolation.

A new `INDIA_METHOD_GATE_REPORT.md` exposes every criterion, status, evidence source, retrieval timestamp and SHA-256 hash. Official methodology PDFs are now classified as documentary evidence, not as datasets and not merely as machine-unreadable files.

## Version 0.6.2: Step 2H0 source-triage hardening

Version 0.6.2 separates discovery evidence from acquired datasets and expands the official-source registry across the ten priority incomplete economies. An accessible homepage or publication page can locate a source family, but it can no longer qualify as a dataset or preserve an A/B runtime class. Network failures are recorded as `ACCESS_BLOCKED`, with failure receipts, rather than being treated as proof of unavailability.

The repository now exposes four independent programmes sharing one methodology and schema:

- `armilar-source-probe`;
- `armilar-proxy-audit`;
- `armilar-country`;
- `armilar-matrix`.

The proxy audit emits separate diagnostics for `aic_hfce_financing_gap` and `aic_ppp_proxy_error`. Direct proxy validation requires matched official HFCE and AIC PPP values for the same economy, category and year. The benchmark registry is empty until such evidence is acquired, so the result remains `INSUFFICIENT_DIRECT_EVIDENCE`.

No new exact cells are admitted. The observed-universe coverage is unchanged, `weights_final.csv` remains empty, `monetary_release_allowed=false`, and Step 2J country parsers have not started.

## Version 0.6.1: Step 2I corrective audit

Version 0.6.1 corrects the certainty level of v0.6.0. Step 2I is no longer described as diagnostically closed. The correct status is: `Step 2I diagnostic infrastructure complete; source audit ongoing`.

This release adds explicit states for ambiguous concepts, blocked access, non-machine-readable sources and current-probe non-admissibility. It also prevents `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` from being used without complete documented source-family coverage.

New outputs are `country_source_family_coverage.csv`, `step2i_audit_summary.json` and `STEP_2I_AUDIT_REPORT.md`. GitHub Actions now validates pull requests while preventing PRs and non-main manual runs from publishing `public/latest`, committing or replacing releases.

No new exact cells are admitted. `weights_final.csv` remains empty, `monetary_release_allowed=false`, `global_12_category_matrix_complete=false`, and Step 2J is not started.

## Version 0.5.0: Step 2H1 / first Step 2H2 wave

Version 0.5.0 adds a reusable national-adapter layer while preserving the fail-closed economic gates.

The release adds:

1. `armilar-country acquire`, an isolated country-adapter CLI;
2. a typed adapter result contract with normalized rows, evidence, mapping audit, reconciliation audit and failures;
3. an India MoSPI Statement 5.1 parser that preserves the 2021-22 fiscal year, current-price `INR crore` unit, exact many-to-one item aggregation and narcotics exclusion;
4. audit-only adapters for Russia, China, Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam;
5. stronger source-probe validation for corrupted XLSX downloads.

The India parser proves that Statement 5.1 can be reconciled exactly at item level. Official MoSPI methodology now confirms that PFCE combines households and NPISH and that the components are not separately available, so the source is rejected from the strict S14 exact matrix. China remains blocked because the official NBS evidence found is an eight-group household survey. Russia remains blocked until a deterministic official Rosstat structured table for 2021 strict household COICOP-HH is acquired.

## Version 0.6.0: Step 2I diagnostic closure

Version 0.6.0 completes Step 2I diagnostically for China, India, Russia, Indonesia and Brazil. It adds per-cell decisions for CP04, CP06, CP09, CP10 and CP12, a source-attempt audit, India methodology gate audit, Step 2H exception audit and a Step 2I completion report.

No new exact cells are admitted in this version. Each of the five Step 2I economies remains non-admissible for the five proxy categories because at least one material gate remains unresolved: strict S14/P31DC household scope, NPISH exclusion, exact COICOP purpose classification, current-price unit/currency confirmation, or no-allocation reconciliation.

### Step nomenclature

| Version | Original step | Repository wording |
|---|---|---|
| 0.4.0 | Step 2H | Gap resolver / source probe |
| 0.5.0 | Step 2I start | National adapter architecture and first audits |
| 0.6.0 | Step 2I infrastructure | Initial diagnostic closure, corrected by v0.6.1 |
| 0.6.1 | Step 2I corrective audit | Diagnostic infrastructure complete; source audit ongoing |
| 0.6.2 | Step 2H0 hardening alongside Step 2I audit | Dataset/discovery separation and direct proxy-error audit |
| 0.6.3 | Step 2H0 India evidence closure | Evidence-linked S14/NPISH and calendar-year rejection |
| 0.6.4 | Step 2H0 Russia evidence closure | Aggregate, SUT-product and survey-purpose concepts separated |
| 0.6.5 | Step 2H0 China evidence closure | Survey, yearbook, 2020 input-output and 2021 GDP aggregate concepts separated |
| 0.6.6 | Step 2H0 Indonesia source-family audit | BPS grouped, database, SUT, input-output and Class C concepts separated |
| 0.6.7 | Step 2H0 Brazil source-family audit | IBGE SIDRA, SCN, CEI, TRU and Class C concepts separated |
| 0.6.8 | Step 2H0 Egypt source-family audit | CAPMAS catalogue, historical SUT and HIECS concepts separated |
| 0.6.9 | Step 2H0 Pakistan source-family audit | Fiscal-year aggregate accounts and HIES survey concepts separated |
| 0.6.10 | Step 2H0 Nigeria source-family audit | 2021 aggregate GDP-expenditure and 2019 survey concepts separated |
| 0.6.11 | Step 2H0 Bangladesh source-family audit | Publication inventory and HIES 2022 concepts separated |
| 0.6.12 | Step 2H0 Viet Nam source-family audit | Aggregate 2021 release and VHLSS concepts separated |
| 0.6.13 | Step 2H exception audits | CP02, territory-scope and unit/concept exceptions made executable |
| 0.7.0 | Global weight contract layer | Separate core/global constructions with per-cell evidence classes and uncertainty |
| 0.7.1 | Evidence-cell staging | Strict A/B conversion and class coverage reports |

## Version 0.4.0: Step 2H0

Version 0.4.0 adds a feasibility layer before country-specific parsers are developed. It does not fill missing cells or change the ratified economic construction.

The release adds four separable components:

1. `armilar-source-probe`, which downloads and preserves official candidate sources for the ten highest-priority incomplete economies;
2. a source classifier with the states `A_CANDIDATE`, `B_CANDIDATE`, `C_ONLY` and `D_UNAVAILABLE`;
3. a gap-priority engine based on the seven directly published ICP categories, explicitly labelled as a development indicator rather than a world weight;
4. an evidence audit for the five actual-consumption PPP proxies used under ratified Option B.

The existing matrix builder remains fail-closed. No source found by the probe enters a weight until a country adapter and all economic controls pass.

## Current economic construction

- **CP01, CP03, CP05, CP07, CP08 and CP11:** strict household nominal expenditure and PPP from World Bank ICP 2021 Source 90.
- **CP02:** alcohol plus tobacco from Source 90, with narcotics excluded.
- **CP04, CP06, CP09, CP10 and CP12:** strict household domestic nominal expenditure from official national-accounts sources divided by the matching ICP actual-consumption PPP proxy.
- Government and NPISH expenditure never enters the numerator.
- The 19 non-participating economies with aggregate ICP imputations remain outside the twelve-category matrix.

The methodology is fixed in `constitution/AMENDMENT_1_1_ICP_ACTUAL_CONSUMPTION_PROXY_RATIFIED.md` and `config/methodology_policy.json`.

## Step 2H0 source probe

The configured first wave covers:

- China;
- India;
- Russia;
- Indonesia;
- Brazil;
- Egypt;
- Pakistan;
- Nigeria;
- Bangladesh;
- Viet Nam.

The registry in `config/source_probe_candidates.csv` records authority, URL, reference period, conceptual scope, category coverage, expected file type, validation markers, preliminary class and blocking reason. GitHub Actions then verifies actual accessibility, response type, file signature and content markers. Every raw response is preserved and hashed.

The declared registry no longer treats India or Russia as B candidates. The Russian exact-source audit shows that the available official resources are aggregate, product-based, documentary, or survey-based. There are currently no `A_CANDIDATE` or `B_CANDIDATE` resources in the ten-economy registry. Runtime acquisition may still downgrade access or require review, and discovery pages never count as datasets.

These are candidate classifications. The live GitHub run may downgrade an inaccessible or invalid response to a blocked or current-probe non-admissible state. It never upgrades a conceptually unsuitable source merely because it downloads successfully.

## Option B evidence audit

`proxy_financing_exposure.csv` reconstructs strict HFCE nominal expenditure for complete economies by adding the derived narcotics residual and net purchases abroad to the twelve Armilar categories. It then compares that reconstructed HFCE with AIC nominal expenditure.

This financing gap measures exposure to consumption financed by government and NPISH. It is not treated as the error of the PPP proxy.

`proxy_ppp_comparison.csv` keeps the actual error test explicit:

`PPP_HFCE / PPP_AIC - 1`

The public global ICP release does not provide the matched strict-HFCE PPPs for the five proxy categories. The audit therefore returns `INSUFFICIENT_DIRECT_EVIDENCE` and keeps monetary use disabled.

## Weight file names

Version 0.4.0 removes ambiguous filenames:

- `weights_observed_universe.csv` contains weights normalised only across complete observed economies;
- `weights_experimental_universe.csv` is reserved for separately authorised experimental allocations and is empty in this release;
- `weights_final.csv` remains empty until the approved worldwide scope passes all gates.

A sum of 1 in `weights_observed_universe.csv` proves internal normalisation only. It does not prove worldwide coverage.

## Run

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m armilar_pipeline run-step2 \
  --config config/step2_icp2021.json \
  --run-dir run \
  --cache-dir .cache/armilar \
  --output-dir artifacts
```

Run only the source feasibility programme:

```bash
armilar-source-probe \
  --config config/step2_icp2021.json \
  --run-dir run-source-probe \
  --cache-dir .cache/armilar
```

Limit a diagnostic run without changing the registry:

```bash
armilar-source-probe --economy CHN --economy IND \
  --config config/step2_icp2021.json \
  --run-dir run-source-probe \
  --cache-dir .cache/armilar
```

Run the proxy audit independently:

```bash
armilar-proxy-audit \
  --comparison-file config/proxy_ppp_benchmarks.csv \
  --output-dir run-proxy-audit/outputs
```

Run the matrix builder independently:

```bash
armilar-matrix \
  --config config/step2_icp2021.json \
  --run-dir run \
  --cache-dir .cache/armilar \
  --output-dir artifacts
```

Run national adapters independently:

```bash
armilar-country acquire IND RUT CHN \
  --config config/step2_icp2021.json \
  --run-dir run-country \
  --cache-dir .cache/armilar
```

The intended acquisition environment is GitHub Actions. A push to `main` starts the full workflow automatically, except when only `public/latest/**` changes.

## Main Step 2H0 outputs

- `outputs/source_probe_candidate_results.csv`
- `outputs/source_probe_economy_summary.csv`
- `outputs/source_probe_family_coverage.csv`
- `outputs/source_probe_failures.csv`
- `outputs/source_probe_summary.json`
- `outputs/economy_gap_priority.csv`
- `outputs/gap_priority_summary.json`
- `outputs/proxy_financing_exposure.csv`
- `outputs/proxy_ppp_comparison.csv`
- `outputs/proxy_error_by_category.csv`
- `outputs/proxy_error_by_economy.csv`
- `outputs/proxy_validation_summary.json`
- `outputs/country_adapter_status.csv`
- `outputs/country_source_evidence.csv`
- `outputs/country_normalized_rows.csv`
- `outputs/country_mapping_audit.csv`
- `outputs/country_reconciliation_audit.csv`
- `outputs/country_adapter_failures.csv`
- `outputs/country_cell_status.csv`
- `outputs/country_source_attempts.csv`
- `outputs/step2i_economy_summary.csv`
- `outputs/india_methodology_gate_audit.csv`
- `outputs/russia_methodology_gate_audit.csv`
- `outputs/china_methodology_gate_audit.csv`
- `outputs/indonesia_methodology_gate_audit.csv`
- `outputs/step2h_exception_audit.csv`
- `outputs/step2i_completion_summary.json`
- `outputs/step2i_audit_summary.json`
- `outputs/INDIA_METHOD_GATE_REPORT.md`
- `outputs/RUSSIA_METHOD_GATE_REPORT.md`
- `outputs/CHINA_METHOD_GATE_REPORT.md`
- `outputs/INDONESIA_METHOD_GATE_REPORT.md`
- `outputs/STEP_2I_AUDIT_REPORT.md`
- `outputs/STEP_2I_COMPLETION_REPORT.md`
- `outputs/weights_observed_universe.csv`
- `outputs/weights_experimental_universe.csv`
- `outputs/weights_final.csv`

The existing normalised data, matrices, coverage reports, manifests and hashes continue to be produced.

## Release gates

- `research_release_allowed=true` means an internally valid observed-universe research matrix exists and the mapping and imputation-count controls pass.
- `global_12_category_matrix_complete=true` is the gate for `weights_final.csv`.
- `monetary_release_allowed` is hard-coded to `false` throughout Step 2.
- source-probe results alone can never release weights.

Weights use 24 decimal places and a deterministic residual adjustment. The emitted observed-universe sum must equal exactly 1, with formal tolerance `1E-20`.
