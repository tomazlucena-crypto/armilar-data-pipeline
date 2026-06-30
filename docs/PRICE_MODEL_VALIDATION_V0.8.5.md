# Armilar price-model validation gates v0.8.5

## Status

This policy is a draft audit contract. Its numerical thresholds are provisional
engineering defaults and are not release criteria until calibrated on real,
hash-preserved data and formally ratified.

Both release flags remain false. Passing every empirical gate cannot by itself
authorise a research or monetary release.

## Audit sequence

1. Verify every v0.8.4 output against `MANIFEST.sha256`.
2. Verify the original weights, observations, profiles, completion policy and
   classification mapping against the hashes recorded by v0.8.4.
3. Re-run leave-one-economy-out validation on a common comparison sample.
4. Compare the selected P3/P4/P5 method with:
   - `B0_TARGET_HEADLINE_ONLY`;
   - `B1_WORLD_PATTERN`.
5. Re-run the model under predeclared donor-policy perturbations.
6. Evaluate overall and worst-group validation, evidence coverage and
   sensitivity gates.
7. Publish a technical result while keeping release disabled.

## Anti-leakage rules

Baseline and sensitivity comparisons use the intersection of validation keys
available under every compared method. A method cannot improve its score merely
by dropping difficult observations. Hidden target values remain unavailable to
donor selection, future observations remain prohibited and monthly weights are
never renormalised.

## Outputs

- `price_validation_detail.csv`
- `price_baseline_comparison.csv`
- `price_sensitivity_audit.csv`
- `price_model_gate_results.csv`
- `price_model_audit_summary.json`
- `MANIFEST.sha256`
