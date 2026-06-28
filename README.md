# Armilar data pipeline

Auditable acquisition and construction pipeline for Step 2 of the Armilar Index: the ICP 2021 research weight matrix.

## What version 0.3.0 changes

Version 0.2.0 attempted to obtain all twelve household-consumption divisions from the World Bank's global 45-heading ICP 2021 release. That release does not publish five strict HFCE divisions globally. Version 0.3.0 implements the ratified research methodology instead:

- **CP01, CP03, CP05, CP07, CP08 and CP11:** strict household nominal expenditure and PPP from World Bank ICP 2021 Source 90.
- **CP02:** alcohol plus tobacco from Source 90; narcotics are excluded explicitly.
- **CP04, CP06, CP09, CP10 and CP12:** strict household domestic nominal expenditure from official national-accounts sources, divided by the corresponding ICP actual-consumption PPP as a deflator only.
- Government and NPISH expenditure never enters a category numerator.
- No population, GDP or income allocation is permitted.
- The 19 non-participating economies with official aggregate ICP imputations remain separate because no official twelve-category allocation is published for them.

The methodology is fixed in `constitution/AMENDMENT_1_1_ICP_ACTUAL_CONSUMPTION_PROXY_RATIFIED.md` and `config/methodology_policy.json`.

## Official sources

The workflow acquires and preserves:

1. World Bank ICP 2021 Source 90 metadata, concepts, variables and observations.
2. The official ICP 2021 classification workbook.
3. The official ICP 2021 participation page, data page and FAQ.
4. OECD Table 5 T501, household domestic consumption by COICOP 1999, requested through the proven annual SDMX key and SDMX-CSV 2.0 content type.
5. UNData SNA Table 3.2, household consumption in the domestic market.
6. Eurostat `nama_10_cp18`, household domestic HFCE by COICOP 2018.
7. OECD Table 5A T501 as a COICOP 2018 fallback, using the same annual SDMX request pattern.

All downloaded files are retained in the run bundle with URL, retrieval time, byte count and SHA-256 hash.

## Run locally

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m armilar_pipeline run-step2 \
  --config config/step2_icp2021.json \
  --run-dir run \
  --cache-dir .cache/armilar \
  --output-dir artifacts
```

The intended acquisition environment is GitHub Actions. A push to `main` starts the workflow automatically, except when a commit changes only `public/latest/**`.

## Main outputs

The complete run bundle contains:

- `outputs/normalized_icp2021.csv`
- `outputs/raw_economy_heading_matrix.csv`
- `outputs/supplemental_nominal_all_sources.csv`
- `outputs/nominal_source_selection_audit.csv`
- `outputs/measure_identity_audit.csv`
- `outputs/unit_reconciliation.csv`
- `outputs/economy_category_matrix.csv`
- `outputs/economy_category_matrix_weight_eligible.csv`
- `outputs/economy_registry.csv`
- `outputs/coverage_report.csv`
- `outputs/exclusions_report.csv`
- `outputs/missing_data_report.csv`
- `outputs/weights_research_observed_normalized.csv`
- `outputs/weights_final_normalized.csv`
- `outputs/weights_by_economy.csv`
- `outputs/weights_by_category.csv`
- `manifest.json`
- `diagnostics.json`
- `SHA256SUMS`
- `STEP2_REPORT.md`

`economy_category_matrix.csv` preserves every admissible cell, including cells belonging to incomplete economies. Only economies with all twelve categories enter `economy_category_matrix_weight_eligible.csv` and the research weights.

## Status fields

- `research_release_allowed=true` means a non-empty, internally valid observed-participant research matrix exists, at least 30 participating economies are complete, all 176 participants are mapped and exactly 19 aggregate-only official imputations are identified.
- `global_12_category_matrix_complete=true` means every participating economy is complete and no unresolved aggregate-only economy remains. This is the gate for `weights_final_normalized.csv`.
- `monetary_release_allowed` is hard-coded to `false` in Step 2.

A research matrix is not the definitive worldwide Armilar matrix. The final file remains empty until the global scope passes every gate.

## Fail-closed controls

The pipeline rejects or isolates:

- duplicate economy-heading-measure observations;
- duplicate supplemental economy-category observations;
- category-level mixing of different nominal-data providers within one economy;
- non-household, non-domestic or non-current-price national-accounts rows;
- use of actual-consumption expenditure in the numerator;
- narcotics;
- missing proxy categories;
- incompatible unit scales;
- a Source 90 measure triple whose median `nominal / PPP = real` identity fails;
- invalid or empty weight matrices;
- silent allocation of the 19 aggregate-only imputations.

Weights are written with 24 decimal places and a deterministic residual adjustment. Their sum must equal exactly 1; the formal tolerance is `1E-20`.
