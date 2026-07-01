# Armilar minimum economic backtest v0.8.8

## Purpose

The v0.8.8 block tests how the fixed v0.8.7 Eurostat category panel behaves when observations are deliberately hidden. It uses the complete category-price index as the target and compares four deterministic completion baselines on exactly the same cases.

The block adds no countries, no new source acquisition and no adaptive model.

## Models

| ID | Definition | Evidence interpretation |
|---|---|---|
| `B0_GLOBAL_EQUAL_HEADLINE` | A masked cell follows the simple mean price-change factor of all currently observed cells. | Global headline-style fallback, not official CP00. |
| `B1_ARMILAR_WEIGHTED_HEADLINE` | A masked cell follows the Armilar-weighted price-change factor of all currently observed cells. | Weighted global headline-style fallback. |
| `B2_CATEGORY_CARRY_FORWARD` | A masked cell retains its last observed level. | P3 persistence baseline. |
| `B3_HIERARCHICAL_COMPLETION` | A masked cell uses same-economy and same-category donor changes where available, then category, economy or global fallbacks. | P4/P5 deterministic completion. |

The terms “headline-style” describe the aggregation mechanism. The v0.8.7 snapshot does not contain an independent Eurostat CP00 series, so B0 and B1 must not be presented as official headline CPI.

## Missingness scenarios

- `SINGLE_CELL`: one economy-category cell disappears.
- `ECONOMY_OUTAGE`: all twelve categories of one economy disappear.
- `CATEGORY_OUTAGE`: one category disappears in all five economies.

The horizons are 1, 3, 6 and 12 months. Every origin precedes its target. All four models use the same scenario-origin-target sample.

## Vintage limitation

The v0.8.7 official snapshot is one final retrieval. It does not preserve the historical release calendar or pre-revision values that existed at each past date.

The v0.8.8 runner therefore uses `FINAL_VINTAGE_PSEUDO_REAL_TIME`:

- masked cells use only their value at the origin;
- target-period donor cells may use the values present in the final snapshot;
- historical provider publication lags and revisions are not reconstructed;
- `publication_aware=false` is mandatory;
- any attempt to set it to true fails closed.

This is a defensible stress test of completion behaviour. It is not a full real-time vintage backtest.

## Outputs

The runner writes:

- `backtest_cases.csv`;
- `model_metrics.csv`;
- errors by scenario, horizon, economy, category and evidence class;
- `construction_sensitivity.csv`;
- `sensitivity_summary.json`;
- `top_three_error_sources.json`;
- `backtest_summary.json`;
- `BACKTEST_REPORT.md`;
- `MANIFEST.sha256`.

## Sensitivity boundaries

The current input can measure the effect of changing economy-category weights. It cannot yet identify:

- improvement over independent official headline CPI, because CP00 is absent;
- current-FX methodology sensitivity, because the primary index excludes FX and no aligned FX panel is supplied;
- the effect of imputed economies, because the five-economy universe contains direct Eurostat observations only.

Unavailable quantities remain absent with explicit reasons.

## Local gate

After v0.8.7 official outputs exist:

```powershell
py scripts\validate_backtest_v088.py --repo-root .
```

The gate is offline, hashes the v0.8.7 input manifest, verifies the v0.8.8 manifest and proves that `public/latest` is unchanged.

`research_release_allowed=false`

`monetary_release_allowed=false`
