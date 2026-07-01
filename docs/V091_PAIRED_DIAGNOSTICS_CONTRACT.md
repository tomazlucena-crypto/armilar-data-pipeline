# v0.9.1 paired economic diagnostics contract

## Objective

Turn the v0.9.0 B0-B3 backtest into an actionable, paired economic diagnosis without changing any model, source, country, weight, release gate or published output.

## Inputs

- A completed v0.9.0 backtest directory with a valid `MANIFEST.sha256`.
- `backtest_cases.csv` containing the same case sample for B0-B3.
- `backtest_summary.json` proving independent CP00, final-vintage mode and closed release gates.

## Outputs

- Case-level signed error deltas for declared model pairs.
- Paired summaries overall and by scenario/horizon, economy and category.
- A ranked B3-versus-B2 priority list based on excess absolute index error.
- A deterministic report, run summary and SHA-256 manifest.

## Invariants

- B0-B3 code and predictions are not recalculated or altered.
- Every comparison is paired by the exact same `case_id`.
- Negative `mean_delta_absolute_bps` means the challenger improves on the baseline.
- Positive `mean_delta_absolute_bps` means the challenger regresses.
- Priority sources are diagnostic only and cannot promote a model.
- `vintage_mode=FINAL_VINTAGE_PSEUDO_REAL_TIME` remains explicit.
- `publication_aware=false` remains explicit.
- `research_release_allowed=false`.
- `monetary_release_allowed=false`.
- No command writes to `public/latest`.

## Failure states

- Invalid or tampered input manifest.
- Missing models or unequal case samples.
- Case metadata mismatch across models.
- Unsupported vintage or policy version.
- Headline independence not proven.
- Release gate weakened.
- Non-finite or negative absolute errors.
- Non-empty output directory.

## Success condition

The same B0-B3 case sample is paired deterministically, B3 regressions and improvements are quantified by economically relevant strata, and the report identifies measured mean regressions without padding the priority list with improvements or neutral groups.

## Out of scope

- New countries or sources.
- A new completion model.
- Publication-vintage reconstruction.
- FX, nowcast, API, dashboard or `public/latest` work.
