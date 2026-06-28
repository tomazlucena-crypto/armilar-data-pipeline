# Armilar data pipeline

Auditable acquisition and construction pipeline for the **ICP 2021 Armilar weight matrix**.

Version 0.2.0 replaces the connectivity bootstrap with an effective Step 2 pipeline. It uses World Bank DataBank Source 90, preserves every acquired response, audits the actual public publication scope and constructs weights only from strict household final consumption expenditure inputs.

## What it acquires

The GitHub Actions workflow downloads and preserves:

- Source 90 metadata;
- all Source 90 concepts and dimension-variable inventories;
- 2021 observations for strict HFCE headings and aggregate imputation controls;
- the official ICP 2021 classification workbook;
- the official participation page;
- the ICP data page and FAQ;
- the official 45-heading published table.

The pipeline discovers the Source 90 dimensions from their content. It does not assume that the DataBank layout is stable.

## Current source conclusion

The official public table publishes exact alcohol and tobacco components, so CP02 can exclude narcotics without an arbitrary percentage. It also publishes five actual-consumption headings where Armilar requires strict HFCE:

- CP04: `9060000` instead of `1104000`;
- CP06: `9080000` instead of `1106000`;
- CP09: `9110000` instead of `1109000`;
- CP10: `9120000` instead of `1110000`;
- CP12: `9140000` instead of `1112000`.

The public household aggregate `9100000` includes NPISHs and cannot replace strict HFCE `1100000`. The pipeline detects these cases from the live API inventory, preserves them for audit and refuses to use them as substitutes.

The 19 officially imputed nonparticipating economies are also aggregate-only. They remain outside category weights.

## Economic scope

Included when published:

- strict household consumption headings;
- twelve Armilar categories;
- owner-occupied imputed rent inside strict CP04;
- CP02 as `1102100 + 1102200`;
- PPP-based real expenditure for weights;
- nominal expenditure for additive hierarchy audit.

Excluded:

- parent `1102000`;
- narcotics `1102300`;
- net purchases abroad `1113000` from the twelve categories;
- actual-consumption substitutes;
- NPISH and government consumption;
- population, GDP, income or model-based category allocations.

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

`run-step2` returns successfully when acquisition and audit outputs are produced, including a blocked economic result. Add `--strict-release` to return a non-zero exit code when `release_allowed=false`.

## Main outputs

- `outputs/normalized_icp2021.csv`
- `outputs/raw_economy_heading_matrix.csv`
- `outputs/economy_category_matrix.csv`
- `outputs/economy_registry.csv`
- `outputs/observed_participating_economies.csv`
- `outputs/officially_imputed_aggregate_only_economies.csv`
- `outputs/unavailable_or_nonpublished_economies.csv`
- `outputs/publication_scope_audit.csv`
- `outputs/coverage_report.csv`
- `outputs/exclusions_report.csv`
- `outputs/missing_data_report.csv`
- `outputs/ppp_identity_reconciliation.csv`
- `outputs/hierarchy_reconciliation.csv`
- `outputs/weights_candidate_observed_participants.csv`
- `outputs/weights_final_normalized.csv`
- `outputs/weights_by_economy.csv`
- `outputs/weights_by_category.csv`
- `outputs/participation_mapping_audit.csv`
- `outputs/measure_selection_audit.csv`
- `outputs/source90_concepts.csv`
- `outputs/source90_variable_inventory.csv`
- `manifest.json`
- `diagnostics.json`
- `SHA256SUMS`
- `STEP2_REPORT.md`

## Release gate

A weight file is final only when every strict HFCE heading, every required economy, provenance, identity and coverage gate passes. A pipeline status of `BLOCKED_SOURCE_PUBLICATION_SCOPE` is expected when the live public inventory matches the current official 45-heading table.
