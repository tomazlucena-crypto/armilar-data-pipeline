# Armilar v0.8.5 validation gates and sensitivity audit

Version 0.8.5 adds a fail-closed audit layer over the experimental v0.8.4 price
completion engine.

It verifies manifests and original input hashes, publishes row-level validation,
compares the selected completion model against headline-only and world-pattern
baselines, tests predeclared donor-policy perturbations and evaluates overall,
worst-category, worst-region, evidence-coverage and sensitivity gates.

The gate policy remains explicitly unratified. Passing technical gates cannot
authorise research or monetary use. Both release flags remain false.
