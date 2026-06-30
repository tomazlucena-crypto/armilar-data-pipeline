# Decision: Eurostat transport for v0.8.7

**Date:** 2026-06-30  
**Status:** ratified for the bounded v0.8.7 vertical slice

## Decision

Use the official Eurostat Statistics API JSON-stat response for the first fixed-universe vertical series. Preserve exact bytes and parse them with the Python standard library. Keep `sdmx1` selected as the general SDMX client for metadata, future provider integration and the later OECD milestone.

## Reason

The immediate risk is whether official category prices can travel through the full Armilar chain and produce a replayable economic series. A direct official JSON-stat snapshot supplies the necessary data without adding an optional dependency to deterministic replay. It also makes raw-byte preservation and hash verification explicit.

## Alternatives rejected

- **Use DBnomics as the data source:** rejected because discovery or convenience aggregation cannot replace the official provider bytes.
- **Install both `sdmx1` and `pysdmx`:** rejected because no concrete `sdmx1` capability gap has been demonstrated.
- **Make live network access part of PR CI:** rejected because it would make PRs slow and non-deterministic.

## Consequences

- Live acquisition remains manual and bounded.
- PR tests use deterministic fixtures and replay.
- The official snapshot is preserved as the v0.8.7 empirical gate evidence.
- The transport decision must be reviewed before generalising the connector or integrating OECD.
