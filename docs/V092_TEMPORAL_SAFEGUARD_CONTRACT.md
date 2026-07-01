# Armilar v0.9.2 temporal safeguard contract

## Objective

Test two pre-declared, minimal safeguards for the B3 completion model without changing B0-B3:

1. fall back from B3 to B2 for `CP08` cases;
2. fall back from B3 to B2 for `CATEGORY_OUTAGE` cases at a one-month horizon.

The safeguards form a research-only selector named `B4_TEMPORAL_SAFEGUARD`. B4 is not a new estimator. It selects an existing B2 or B3 result for each already-defined v0.9.0 backtest case.

## Temporal contract

- Development targets: January 2022 to December 2023.
- Sealed evaluation targets: January 2024 to December 2025.
- Rule activation uses development cases only.
- Evaluation cases never affect activation, thresholds or rule selection.
- The two periods are non-overlapping and every input case must belong to exactly one period.

## Activation contract

Each candidate rule is activated only when its development subset:

- has at least the configured minimum number of cases;
- has a strictly positive mean `B3 absolute error minus B2 absolute error`;
- has a B3-versus-B2 regression rate at or above the configured threshold.

An inactive rule is not applied to development or evaluation cases. Overlapping active rules select B2 once and retain all matching rule identifiers for audit.

## Inputs

A verified v0.9.0 backtest directory containing:

- `backtest_cases.csv`;
- `backtest_summary.json`;
- `MANIFEST.sha256`.

The input must retain:

- `FINAL_VINTAGE_PSEUDO_REAL_TIME`;
- `publication_aware=false`;
- independent Eurostat CP00 headlines;
- all four B0-B3 results on an identical sample;
- both release gates closed;
- no reuse of the rejected v0.8.9 experiment.

## Outputs

- `rule_activation.json`;
- `safeguard_case_results.csv`;
- `safeguard_metrics.csv`;
- `evaluation_summary.json`;
- `run_summary.json`;
- `TEMPORAL_SAFEGUARD_REPORT.md`;
- `MANIFEST.sha256`.

## Invariants

- B0-B3 code and results remain unchanged.
- B4 uses only B2 or B3 values already present in the same `case_id`.
- Evaluation data do not influence activation.
- Outputs are deterministic and manifest-verified.
- `public/latest` is not read or written.
- `research_release_allowed=false`.
- `monetary_release_allowed=false`.
- `model_promotion_allowed=false` regardless of the result.

## Decision boundary

This experiment may show whether the two safeguards survive a temporal holdout. It cannot promote B4, authorise publication, change the methodology or establish real-time performance because the source backtest remains final-vintage and not publication-aware.
