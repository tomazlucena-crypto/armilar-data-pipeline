# Delivery report v0.4.0

## Scope

This package implements Step 2H0 of the Armilar Index: source feasibility triage and preliminary validation of the actual-consumption PPP proxy.

## Delivered programmes

### Full Step 2 pipeline

`python -m armilar_pipeline run-step2`

Acquires ICP and supplemental international data, builds the current observed-universe matrix, runs Step 2H0 and publishes all reports.

### Independent source probe

`armilar-source-probe`

Runs only the national-source feasibility audit. It can be scheduled independently later without recalculating the ICP matrix.

## Configured ten-economy audit

The preliminary evidence registry contains official sources for China, India, Russia, Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam.

Before online runtime validation, the methodological distribution is:

| Class | Economies | Meaning |
|---|---:|---|
| A candidate | 0 | Exact source already demonstrated |
| B candidate | 2 | Official derivation may be exact after mapping and boundary checks |
| C only | 7 | Survey, grouped classification or temporal allocation required |
| D unavailable | 1 | No adequate category source located |

The GitHub run records actual accessibility separately and may downgrade any failed source.

## Proxy audit result encoded by design

The programme reconstructs HFCE nominal expenditure for the complete observed economies and reports the AIC/HFCE financing gap. It does not mislabel that gap as PPP error.

The direct PPP benchmark count remains zero until a source publishes comparable strict-HFCE and AIC PPPs for the same category and economy. The expected status is therefore `INSUFFICIENT_DIRECT_EVIDENCE`.

## Validation

- 36 automated tests passed;
- editable installation tested;
- Python compilation tested;
- exact observed-universe weight sum retained;
- final and experimental weight files remain empty unless their specific gates authorise data;
- workflow publication list updated for all Step 2H0 outputs.

## Expected first GitHub result

The first online run will establish which of the eleven configured candidate URLs are accessible from GitHub Actions and will publish the raw evidence. It will not yet add China, India, Russia or any other probed economy to the matrix.
