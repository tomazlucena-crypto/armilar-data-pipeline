# Decision: v0.8.8 final-vintage limitation

**Date:** 2026-06-30

## Decision

Run the first bounded completion backtest against the complete v0.8.7 official Eurostat panel, while labelling it `FINAL_VINTAGE_PSEUDO_REAL_TIME` and prohibiting publication-aware claims.

## Reason

The preserved v0.8.7 snapshot proves the exact values retrieved on one date. It does not contain historical provider vintages, original release dates for every observation or pre-revision values. Reconstructing those values would create evidence that was not preserved.

## Alternatives rejected

1. Treat the final snapshot as if it were known historically. Rejected because it would conceal look-ahead from revisions and publication lags.
2. Invent publication dates from generic monthly schedules. Rejected because schedules do not prove the availability of each observation.
3. Delay all testing until a multi-vintage archive exists. Rejected because missing-cell completion and weight sensitivity can already be tested honestly within declared limits.

## Consequences

- origin periods always precede target periods;
- masked cells cannot use target values;
- same-period donor values come from the final vintage and this assumption is explicit;
- the official headline, FX and imputed-economy comparisons remain unavailable;
- the next expansion must preserve repeated provider snapshots if full publication-aware testing is required;
- both release gates remain false.
