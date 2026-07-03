# ARMILAR v0.9.8 Point-in-Time Proxy Archive Contract

## Objective

Convert the immutable v0.9.7 proxy snapshots into a deterministic point-in-time archive without inventing historical vintages, while preserving operational lineage between successive archive releases.

## Inputs

- the closed v0.9.7 source registry;
- one or more v0.9.7 snapshot bundles;
- the v0.9.7 append-only snapshot ledger;
- the v0.9.8 information-set policy;
- optionally, one verified predecessor v0.9.8 archive when building a successor.

## Outputs

### Archive bundle

- every verified snapshot observation;
- every distinct value version first observed by ARMILAR;
- revision events;
- per-snapshot change diagnostics;
- source continuity diagnostics;
- explicit root or successor lineage;
- manifests and a closed archive summary.

### Cutoff bundle

- one value version per observation key available by an explicit UTC cutoff;
- source-level freshness diagnostics at that cutoff;
- manifests and a closed information-set summary.

## Availability rule

An observation version becomes available at the first verified ARMILAR retrieval containing that exact value. A dataset-level release date cannot move a historical row backwards in time. A later revised history cannot be used before the retrieval in which the revision was first observed.

This creates a valid archive from the start of ARMILAR preservation. It does not reconstruct first-published history before that date.

## Archive succession rule

A root archive has no parent. A successor archive must:

1. verify the predecessor bundle;
2. contain every predecessor snapshot;
3. preserve every predecessor snapshot row byte-semantically;
4. contain at least one new snapshot;
5. record the predecessor manifest and summary hashes;
6. remain immutable after publication.

A successor is rebuilt deterministically from the complete verified snapshot root. The predecessor archive is never modified.

## Snapshot delta rule

Each source snapshot is compared with the immediately preceding snapshot from the same source. The diagnostic records:

- new observation keys;
- unchanged reobservations;
- changed values;
- keys missing from the new snapshot.

A missing key is recorded as a source-history change. It does not delete the earlier observation or its value version.

## Cutoff freshness rule

For every source present in the archive, the cutoff bundle records the most recent verified snapshot at or before the cutoff. The diagnostic status is:

- `NO_SNAPSHOT_BY_CUTOFF`;
- `CURRENT_WITHIN_EXPECTED_WINDOW`;
- `STALE_BEYOND_EXPECTED_WINDOW`.

The expected window reuses the closed continuity threshold derived from source frequency, expected publication lag and the policy multiplier. Freshness is a quality diagnostic only. It does not authorise proxy use.

## Invariants

1. Every input snapshot passes its v0.9.7 manifest and deterministic replay.
2. Every snapshot is anchored in the verified v0.9.7 ledger.
3. Retrieval clocks never regress within a source.
4. Duplicate keys inside one snapshot are rejected.
5. Equal values in later snapshots are reobservations, not revisions.
6. Changed values produce an immutable revision event.
7. Disappearing rows are reported but never erase history.
8. A cutoff panel contains only versions with `available_at <= cutoff`.
9. A successor preserves the complete predecessor archive content and records its hashes.
10. All direct-index, ARM-L, training, shadow-production and monetary gates remain closed.
11. Historical first-published claims remain forbidden.

## Success condition

The same verified inputs, policy and predecessor produce byte-identical archive and cutoff bundles. A later revision never appears in an earlier cutoff, and no successor can omit or alter predecessor observations.

## Stop condition

Any missing ledger anchor, manifest failure, replay mismatch, clock regression, duplicate row, unknown source, predecessor mismatch, missing predecessor snapshot or policy divergence aborts the build.

## Out of scope

- proxy mapping to CP01-CP12;
- model fitting;
- ARM-L construction;
- historical release-calendar reconstruction;
- API, dashboard, oracle or monetary use.
