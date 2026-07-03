# ARMILAR v0.9.6 Official Engine and Temporal Ledger Contract

## OBJECTIVE

Implement the ratified `ARMILAR_RESEARCH_CORE_V1` as a deterministic research engine for `ARM-O`, `ARM-R` and `ARM-H`, while preserving every release gate in the closed state.

## INPUTS

1. Ratified constitution `ARMILAR_RESEARCH_CORE_V1`, version `1.0.0-research`.
2. Canonical 60-cell basket with `fixed_universe_weight` summing exactly to one.
3. Category price observations with economy, category, month, value, publication timestamp, retrieval timestamp, vintage, revision sequence, raw snapshot ID, raw snapshot SHA-256 and evidence class.
4. CP00 observations for `ARM-H` only.
5. A versioned engine policy with the ratified constitution and ratification-record hashes.
6. A build request declaring run ID, series kind, vintage ID, information cutoff and creation timestamp.

## OUTPUTS

Every accepted run is an immutable directory containing:

- copied canonical inputs;
- selected as-of-cutoff observations;
- 2021-normalised price observations;
- monthly index series;
- cell, economy and category contributions;
- a machine-readable run summary;
- an economic report;
- a complete SHA-256 manifest.

The run is appended to a hash-chained JSONL temporal ledger only after all files and the manifest validate.

## INVARIANTS

- Decimal precision is 28 with `ROUND_HALF_EVEN`.
- Intermediate rounding is forbidden. Canonical index levels, price relatives and contributions are published with 12 decimal places; percentage revisions use 8 decimal places. Unrounded values and explicit aggregation residuals remain in the artefact.
- The arithmetic mean of all twelve 2021 monthly levels equals 100 for every required source series.
- All twelve base months are mandatory.
- Every requested month requires a complete cell grid.
- `ARM-O` uses the earliest official publication that was both published and retrieved by the declared cutoff, even when later revisions are already visible.
- `ARM-R` uses the latest official revision that was both published and retrieved by the declared cutoff and never overwrites `ARM-O`.
- `ARM-H` is a separate first-published CP00 benchmark and never enters the weighted category basket.
- Every observation must identify the preserved raw snapshot and its SHA-256.
- Proxy, imputed, model, forecast, nowcast, carry-forward and synthetic price evidence is rejected.
- Weights remain fixed within the basket version and are never silently renormalised.
- The current exchange rate is excluded from the primary calculation.
- A run ID is content-addressed within the ledger: the same ID may be replayed only with exactly the same payload.
- All release, promotion, shadow-production, monetary and world-claim gates remain false.
- OOH sensitivity is explicitly a scenario exercise and cannot be represented as evidence or imputed-rent equivalence.
- Canonical run storage is CSV and JSON. Parquet is a derived, non-canonical view.

## FAILURE STATES

The engine fails closed for:

- an unratified or altered policy;
- an open release gate;
- a missing or duplicate weight cell;
- a weight sum different from one beyond the declared decimal tolerance;
- an incomplete 2021 base;
- a missing current-period observation;
- an observation published or retrieved after the information cutoff;
- an invalid UTC timestamp, month or SHA-256 value;
- a float supplied where an exact decimal is required;
- an existing non-empty output directory;
- manifest or ledger tampering;
- a reused run ID with different content;
- path traversal in a manifest;
- an unavailable optional storage dependency when Parquet export is requested.

No partial run is retained after a rejected transaction.

## SUCCESS CONDITION

A build succeeds only when:

1. every policy and input invariant passes;
2. the complete declared time grid is calculated;
3. contributions reconcile exactly before display rounding;
4. the run bundle verifies from its manifest;
5. the ledger append succeeds and the full chain verifies;
6. deterministic replay reproduces the same canonical outputs.

## STOP CONDITION

Development of this milestone stops when the engine, ledger, replay, reconciliation, OOH sensitivity and optional Parquet export pass the targeted suite and the repository-wide suite without altering protected paths.

## FALLBACK CONDITION

There is no numerical fallback for missing official observations. The run is rejected. Optional Parquet export may be omitted while canonical CSV and JSON artefacts remain available. OOH analysis uses only declared mechanical scenarios and cannot fill data gaps.

## ACCEPTANCE TESTS

- exact 2021 annual normalisation;
- invariance to input row ordering;
- exact unrounded index and contribution reconciliation, plus canonical fixed-scale residual reconciliation;
- cutoff exclusion of later publications and later retrievals;
- preservation of first-published ARM-O under a later cutoff;
- rejection of proxy or model price evidence;
- separation of `ARM-O`, `ARM-R` and `ARM-H`;
- immutable run directories;
- append-only hash-chain verification;
- deterministic replay;
- reconciliation between original and revised runs;
- detection of input, manifest and ledger tampering;
- rejection of missing cells and duplicate cells;
- rejection of any opened gate;
- real canonical basket validation;
- OOH scenario outputs labelled `SCENARIO_NOT_EVIDENCE`, `uses_official_oohpi=false` and `constitutional_ooh_requirement_satisfied=false`;
- explicit failure when DuckDB is absent and successful five-table Parquet export when the temporal extra is installed.

## OUT OF SCOPE

- `ARM-L` nowcasting;
- model training or promotion;
- live acquisition and scheduling;
- API and dashboard;
- oracle or blockchain integration;
- external research release;
- shadow production;
- monetary use;
- a world-index claim;
- changing the basket, weights, price concept or constitutional methodology.
