# Decision: point-in-time availability begins at verified first retrieval

**Version:** 0.9.8
**Status:** ACCEPTED_FOR_ENGINE_DEVELOPMENT
**Date:** 2026-07-03

## Decision

For sources without preserved historical vintages, ARMILAR will use the first verified retrieval containing an exact value as the earliest defensible availability time for that value. Dataset-level publication dates do not prove the availability of each historical row and cannot backdate the information set.

## Consequences

- future archives can support rigorous point-in-time research;
- pre-archive backtests remain unavailable for these proxies;
- later revisions are visible only from their first verified retrieval;
- current revised histories remain useful after retrieval but cannot be represented as historically first-published;
- no proxy is admitted to ARM-L or model training by this decision.

## Operational extension within v0.9.8

The same decision also requires explicit lineage between published archive bundles. A successor archive must preserve every predecessor snapshot observation, identify the predecessor by manifest and summary hash, and add at least one new verified snapshot.

Consecutive source snapshots are compared to expose added, revised, unchanged and missing rows. Cutoff bundles report source freshness using the closed continuity window. These are quality and integrity diagnostics only and do not alter any use gate.
