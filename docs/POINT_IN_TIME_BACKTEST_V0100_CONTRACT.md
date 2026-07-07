# ARMILAR v0.10.0 point-in-time target alignment contract

## Objective

Create a deterministic research bridge between verified v0.9.9 proxy feature bundles and first-published ARM-O cell targets. The milestone freezes the target definitions, forecast horizons and no-training baselines before any feature selection or model fitting is permitted.

## Inputs

- one verified ARM-O v0.9.6 run;
- one or more verified v0.9.9 feature bundles with distinct UTC cutoffs;
- the frozen v0.10.0 protocol;
- the ratified Research Core constitution and basket, unchanged.

## Target definitions

For every economy-category cell:

- `MONTHLY_CHANGE_PCT`: exact percentage change in the ARM-O normalised price relative from month `t-1` to month `t`;
- `YEAR_OVER_YEAR_CHANGE_PCT`: exact percentage change from `t-12` to `t`.

The target becomes available at the later publication timestamp of the two ARM-O observations needed to calculate it. Targets are evaluation artefacts only.

## Forecast case clock

Each feature bundle cutoff creates a decision origin equal to the cutoff calendar month. Horizons are fixed at 0, 1 and 3 months. A case is created only when:

- the target exists in the target archive;
- the target was not available at the decision cutoff;
- the feature bundle is verified and all its use gates are closed.

Features must be complete-period observations, available no later than the cutoff, and refer to an economic period no later than the origin month. The latest available observation is retained per deterministic stream variant.

## Baselines

- `ZERO_CHANGE`;
- `LAST_OBSERVED_TARGET`, using only targets available by the cutoff;
- `SEASONAL_12M`, using the same target metric twelve months earlier only when that target was available by the cutoff.

Baseline metrics are descriptive diagnostics. They cannot select features, choose models, open a backtest claim or inform ARM-L.

## Outputs

### Target archive

- `cell_targets.csv`;
- `target_archive_summary.json`;
- `MANIFEST.sha256`.

### Alignment bundle

- `forecast_cases.csv`;
- `aligned_features.csv`;
- `leakage_audit.csv`;
- `case_candidate_audit.csv`, including missing and already-known targets;
- `cutoff_inventory.csv`;
- `alignment_summary.json`;
- `MANIFEST.sha256`.

### Baseline diagnostic bundle

- `baseline_predictions.csv`;
- `baseline_metrics.csv`;
- `cell_protocol_readiness.csv`;
- `baseline_summary.json`;
- `MANIFEST.sha256`.

## Invariants

- no target known at the cutoff may be used as a forecast target;
- absence of future ARM-O targets must produce an explicit `NO_ELIGIBLE_FUTURE_TARGETS` result, not synthetic cases;
- no feature observed after the cutoff may be aligned;
- no feature period after the decision origin may be aligned;
- no revised ARM-R value may be used as a target;
- no proxy price evidence may enter the ARM-O target archive;
- no imputation, carry-forward, feature selection, quality weighting or model fitting is permitted;
- threshold satisfaction never opens a gate automatically;
- all bundles are immutable, deterministic and manifest-verified.

## Gates

All remain `false`:

- target archive claim;
- backtest execution claim;
- out-of-sample claim;
- feature selection;
- model training;
- model selection;
- ARM-L use;
- shadow production;
- monetary use.
