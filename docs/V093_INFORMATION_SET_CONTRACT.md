# Armilar v0.9.3 first-published release-time contract

## Objective

Replace the final-vintage-only limitation of the v0.9.0-v0.9.2 experiments for Germany, Spain, France, Italy and Portugal with official Eurostat evidence for January 2021 to December 2025:

1. the exact day on which the complete monthly HICP release became available;
2. CP00-CP12 values preserved as first published on that release;
3. a B0-B4 missing-cell completion backtest evaluated as of the target month's complete-data release;
4. a sensitivity comparison against the previous current-final-vintage results.

## Official inputs

### Release timing

The monthly Eurostat release-calendar pages establish the day on which the complete HICP breakdown for each reference month was disseminated.

### First-published values

The Eurostat dataset `prc_hicp_fp` preserves old-ECOICOP HICP values as first published. The v0.9.3 panel uses:

- monthly frequency;
- the complete release labelled `Final`, distinct from the flash estimate;
- the unit labelled as the 2015=100 index;
- CP00 through CP12;
- DE, ES, FR, IT and PT;
- 2021-01 through 2025-12.

The unit and release codes are discovered from official JSON-stat metadata. They are not silently assumed.

## Two different information problems

### Release-time completion

At the complete-data release date of target month `t`, the unmasked first-published observations for month `t` are available. The Armilar backtest may therefore use those contemporaneous observations as donors to reconstruct deliberately masked cells from the same release.

The valid classification is:

```text
FIRST_PUBLISHED_TARGET_RELEASE_COMPLETION
```

This is publication-aware for a missing-cell completion problem.

### Pre-release forecasting

Before the target month's complete release, neither target CP00 nor target category donors are available. A pre-release forecast must use only information released before its forecast origin.

The v0.9.3 package does not implement that nowcast problem. It must never describe the release-time completion results as a pre-release forecast.

## B0-B4 contract

- B0-B3 use the existing v0.9.0 model code without modification.
- Their category panel, headline panel, truth and donors are rebuilt from first-published values.
- Every case is stamped with the official target-month full-release date.
- Target-period donors are allowed only because the as-of date is that same complete-data release.
- B4 retains the two v0.9.2 candidate rules.
- B4 activation is recalculated using first-published development cases from 2022-01 to 2023-12.
- B4 evaluation remains sealed to 2024-01 through 2025-12.
- Evaluation observations never affect rule activation.

## Vintage sensitivity

A separate comparison joins identical case IDs across:

- the v0.9.3 first-published release-time backtest;
- the v0.9.0 final-vintage B0-B3 backtest;
- the v0.9.2 final-vintage B4 evaluation.

It reports how first-published values alter:

- mean and p95 errors;
- model ranking;
- results by scenario;
- results by horizon;
- results by economy;
- results by category.

This comparison measures sensitivity to revisions and historical corrections. It does not establish pre-release forecasting performance.

## Required outputs

### Release timing and first-published panel

- `cp00_publication_availability.csv`;
- `first_published_observations.csv`;
- `first_published_monthly_indices.csv`;
- `revision_audit.csv`;
- input and output manifests.

### Release-time backtest

- `backtest_cases.csv` containing B0-B4;
- `model_metrics.csv`;
- `b4_rule_activation.json`;
- `holdout_evaluation.json`;
- `backtest_summary.json`;
- `RELEASE_TIME_BACKTEST_REPORT.md`;
- `MANIFEST.sha256`.

### Vintage sensitivity

- `vintage_sensitivity_cases.csv`;
- `vintage_sensitivity_by_dimension.csv`;
- `model_ranking_sensitivity.json`;
- `run_summary.json`;
- `VINTAGE_SENSITIVITY_REPORT.md`;
- `MANIFEST.sha256`.

## Invariants

- the economy universe is exactly DEU, ESP, FRA, ITA and PRT;
- the category universe is exactly CP00-CP12;
- all 60 months are present for every economy-category cell;
- release dates and first-published values remain separate hashed evidence chains;
- category weights sum exactly to one;
- economy headline weights equal the sum of their category weights;
- B0-B3 model code is unchanged;
- the rejected v0.8.9 experiment is not reused;
- `public/latest` is unchanged;
- `pre_release_forecast_comparison_allowed=false`;
- `model_promotion_allowed=false`;
- `research_release_allowed=false`;
- `monetary_release_allowed=false`.

## Completion gate

The milestone is complete when:

- 60 official release pages are acquired and sealed;
- 3,900 official first-published observations are acquired and replayed;
- B0-B4 are rerun on first-published values with identical case samples;
- B4 activation uses development data only;
- the 2024-2025 holdout is reported;
- first-published versus final-vintage sensitivity is reported;
- every manifest verifies;
- no model or release gate is promoted.

## Remaining boundary

The next modelling milestone may construct a genuine pre-release nowcast. Such a model must prohibit target-period CP00 and category donors and use only information whose release timestamp precedes the forecast origin.
