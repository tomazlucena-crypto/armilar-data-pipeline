# Decision: freeze point-in-time targets and baseline protocol before modelling

**Version:** 0.10.0
**Status:** development contract only

## Decision

ARMILAR will not begin model training immediately after constructing proxy features. It first creates a verifiable bridge between the information actually available at each cutoff and future first-published ARM-O targets.

The bridge freezes:

- two target metrics;
- horizons of 0, 1 and 3 months;
- three no-training baselines;
- exact temporal leakage rules;
- minimum diagnostic thresholds of 24 distinct cutoffs and 24 cases per cell-metric-horizon.

## Reasons

A feature panel can look historically rich while containing data first observed only recently. A conventional random split would therefore overstate performance. Separating decision time, economic target period and target publication time is necessary before any predictive claim can be evaluated.

## Rejected alternatives

- training immediately on the full historical proxy backfill;
- treating ARM-R revised history as the evaluation target;
- allowing the current cutoff to predict a target already published;
- selecting whichever baseline or horizon looks best after seeing the results;
- promoting diagnostic thresholds directly into release gates.

## Consequences

The first real v0.10.0 build may contain very few eligible cases because the point-in-time archive is young. That is an honest result. More cutoffs must accumulate before an out-of-sample claim can be considered.
