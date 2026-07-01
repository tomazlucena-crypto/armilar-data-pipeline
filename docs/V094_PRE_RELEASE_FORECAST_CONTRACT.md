# Armilar v0.9.4 pre-publication forecast contract

## Objective

Evaluate whether the five-economy Armilar panel can forecast the first-published target-month index before that target month is released.

## Inputs

- the verified v0.9.3 first-published panel;
- five economies: Germany, Spain, France, Italy and Portugal;
- CP00-CP12;
- January 2021 to December 2025;
- fixed Armilar cell and economy weights;
- official release dates attached by v0.9.3.

## Forecast timing

Each forecast is generated as of the official full-data release date of the origin month.

For a target month `t` and horizon `h`:

```text
origin = t - h months
as_of_date = official full-data release date of origin
```

The target release date is retained only for scoring after publication. It is never an input to a forecast.

## Hard information-set boundary

Every source value must satisfy:

```text
source_period <= origin_period < target_period
```

The following are prohibited:

- target-period CP00;
- target-period CP01-CP12;
- any target-period donor;
- any value from a period after the origin;
- use of 2024-2025 holdout results to choose a model or parameter.

## Models

### P0: equal headline carry-forward

Equal mean of the five origin-month CP00 values.

### P1: Armilar-weighted headline carry-forward

Origin-month CP00 values weighted by each economy's total Armilar weight.

### P2: category carry-forward

Every economy-category cell carries its origin-month value forward to the target.

### P3: seasonal year-on-year forecast

For each economy-category cell:

```text
forecast(target) = value(target-12) * value(origin) / value(origin-12)
```

All three source periods must be available by the origin.

### P4: fixed half ensemble

For each economy-category cell:

```text
forecast = 0.5 * P2 + 0.5 * P3
```

The weights are fixed before evaluation and are not trained.

## Truth

The global truth is the fixed-weight Armilar category index calculated from first-published CP01-CP12 target values.

CP00 is an independent headline benchmark and is not part of the category-weighted truth.

## Temporal split

- development reporting: January to December 2023;
- sealed holdout reporting: January 2024 to December 2025.

Neither period is used for model selection or parameter fitting. The split exists to expose stability.

## Historical-vintage limitation

Historical inputs are the values as first published. The pipeline does not reconstruct later revisions that may already have been known at each historical origin date.

The valid claim is therefore:

```text
FIRST_PUBLISHED_HISTORY_PRE_RELEASE_FORECAST
```

The valid claim is not a complete real-time-vintage reconstruction.

## Required outputs

- `forecast_cases.csv`;
- `economy_forecast_cases.csv`;
- `cell_forecast_cases.csv`;
- `model_metrics.csv`;
- `error_by_economy.csv`;
- `error_by_category.csv`;
- `paired_model_comparisons.csv`;
- `ranking_stability.json`;
- `focus_diagnostics.json`;
- `holdout_evaluation.json`;
- `run_summary.json`;
- `PRE_RELEASE_BACKTEST_REPORT.md`;
- `MANIFEST.sha256`.

## Invariants

- exactly five economies;
- exactly CP00-CP12;
- exactly 60 input months;
- horizons 1, 3, 6 and 12 months;
- identical global case-id sample across P0-P4;
- paired comparisons use exact matching cases;
- development and holdout rankings are reported separately;
- signed forecast bias is reported;
- maximum source period equals or precedes the origin;
- no target value enters prediction;
- all outputs are deterministic;
- `public/latest` is unchanged.

## Gates

```text
pre_release_forecast_comparison_allowed=true
model_promotion_allowed=false
research_release_allowed=false
monetary_release_allowed=false
```

## Out of scope

- new countries;
- external high-frequency predictors;
- model fitting;
- machine learning;
- nowcasting within the target month;
- API, dashboard or blockchain publication;
- promotion of any model.

## Diagnostic comparisons

The following directions are fixed before observing production results:

```text
P1 vs P0
P2 vs P1
P3 vs P1
P4 vs P1
P4 vs P2
P4 vs P3
```

Each comparison reports mean, median and p95 change in absolute error, win/loss/tie rates, worst regression, best improvement and change in signed bias. Negative absolute-error deltas indicate improvement.

The output also reports development-versus-holdout ranking stability and dedicated holdout rankings for Italy, Portugal, CP04 and the 12-month horizon. These diagnostics are descriptive and cannot be used to alter the fixed P4 weights after holdout inspection.
