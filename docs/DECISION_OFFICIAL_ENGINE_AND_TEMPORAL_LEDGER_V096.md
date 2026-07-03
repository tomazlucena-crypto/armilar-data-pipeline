# Decision: deterministic official engine and temporal ledger for v0.9.6

**Date:** 2026-07-03  
**Status:** Implemented for local validation  
**Constitutional scope:** Research Core engine development only

## Decision

Create a new, isolated `official_engine_v096` module instead of modifying the earlier experimental index engine. The module implements the ratified `ARM-O`, `ARM-R` and `ARM-H` semantics and writes immutable run bundles to a hash-chained temporal ledger.

## Reason

The existing experimental modules predate the canonical ratification and contain assumptions that should remain available for comparison. An isolated engine reduces regression risk and makes the constitutional boundary auditable.

## Storage decision

Canonical artefacts remain plain CSV and JSON with SHA-256 manifests. DuckDB is adopted only as an optional exporter of derived Parquet views. This keeps replay independent of a database engine while allowing efficient historical queries when the optional dependency is installed.

## Transaction decision

A run is built in a temporary sibling directory, verified, atomically moved to its final path and then appended to the ledger. If ledger insertion fails, the new output is removed. Existing runs are never overwritten.

## Vintage decision

Selection requires both `published_at <= cutoff_at` and `retrieved_at <= cutoff_at`. `ARM-O` selects the earliest official publication for a cell-period even under a later cutoff; `ARM-R` selects the latest official revision available by the cutoff. Each observation carries a raw snapshot ID and SHA-256. Both series preserve their own immutable run bundles.


## Numeric publication decision

Calculations retain full `Decimal` precision under the constitutional context. Canonical CSV display fields use fixed scales of 12 decimal places for index levels, price relatives and contributions, and 8 decimal places for percentage revisions. Each index row publishes the unrounded value and the residual required to reconcile independently rounded cell, economy and category contributions.

## Rejected alternatives

- Replacing the earlier engine in place: rejected because it would blur experimental and ratified semantics.
- Storing only in DuckDB: rejected because replay would depend on a mutable database file and an additional runtime dependency.
- Filling incomplete periods through carry-forward: rejected by the ratified `ARM-O` contract.
- Treating CP04 scenarios as OOH evidence: rejected because a multiplier scenario cannot establish imputed-rent equivalence. The v0.9.6 harness therefore declares `uses_official_oohpi=false` and cannot satisfy the constitutional OOH requirement.

## Consequences

- The code is larger than a thin calculation function because integrity, replay and temporal behaviour are part of the product.
- Canonical outputs are portable and independently hashable.
- Parquet can be regenerated and is never authoritative.
- A subsequent milestone can build orchestration or an API around the same run bundle without changing the formula.
