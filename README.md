# Armilar data pipeline

Auditable acquisition and construction pipeline for Step 2 of the Armilar Index: the ICP 2021 research weight matrix.

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
- `outputs/step2h_exception_audit.csv`
- `outputs/step2i_completion_summary.json`
- `outputs/RUSSIA_METHOD_GATE_REPORT.md`
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
