# Armilar data pipeline

Auditable acquisition and construction pipeline for Step 2 of the Armilar Index: the ICP 2021 research weight matrix.

## Version 0.5.0: Step 2H1 / first Step 2H2 wave

Version 0.5.0 adds a reusable national-adapter layer while preserving the fail-closed economic gates.

The release adds:

1. `armilar-country acquire`, an isolated country-adapter CLI;
2. a typed adapter result contract with normalized rows, evidence, mapping audit, reconciliation audit and failures;
3. an India MoSPI Statement 5.1 parser that preserves the 2021-22 fiscal year, current-price `INR crore` unit, exact many-to-one item aggregation and narcotics exclusion;
4. audit-only adapters for Russia, China, Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam;
5. stronger source-probe validation for corrupted XLSX downloads.

The India parser proves that Statement 5.1 can be reconciled exactly at item level. It does not enter the exact matrix until the strict households-only S14/P31 boundary and NPISH exclusion are confirmed from an official source. China remains blocked because the official NBS evidence found is an eight-group household survey. Russia remains blocked until a deterministic official Rosstat structured table for 2021 strict household COICOP-HH is acquired.

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

The preliminary methodological audit identifies:

- 2 `B_CANDIDATE` economies: India and Russia;
- 7 `C_ONLY` economies: China, Indonesia, Brazil, Egypt, Pakistan, Bangladesh and Viet Nam;
- 1 `D_UNAVAILABLE` economy: Nigeria;
- 0 proven `A_CANDIDATE` economies.

These are candidate classifications. The live GitHub run may downgrade an inaccessible or invalid response to `D_UNAVAILABLE`. It never upgrades a conceptually unsuitable source merely because it downloads successfully.

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
- `outputs/source_probe_failures.csv`
- `outputs/source_probe_summary.json`
- `outputs/economy_gap_priority.csv`
- `outputs/gap_priority_summary.json`
- `outputs/proxy_financing_exposure.csv`
- `outputs/proxy_ppp_comparison.csv`
- `outputs/proxy_validation_summary.json`
- `outputs/country_adapter_status.csv`
- `outputs/country_source_evidence.csv`
- `outputs/country_normalized_rows.csv`
- `outputs/country_mapping_audit.csv`
- `outputs/country_reconciliation_audit.csv`
- `outputs/country_adapter_failures.csv`
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
