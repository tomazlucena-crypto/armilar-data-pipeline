# ARMILAR v0.10.1

Adds a fail-closed materialization bridge from the verified Eurostat v0.8.7 official vertical snapshot to the canonical v0.9.6 ARM-O engine and v0.10.0 target archive.

The bridge validates raw official bytes, exact grid coverage, replay, ledger integrity and target archive integrity. Historical availability is conservatively anchored to the first verified Armilar retrieval and is never represented as a proven official publication timestamp.

All gates remain closed. The v0.9.6 period still ends in December 2025, so no future target overlap with 2026 feature cutoffs is claimed.

## Compatibility correction: historical v0.8.7 manifests

The verified real Eurostat v0.8.7 bundle uses two ASCII spaces between the
SHA-256 digest and the relative path. Earlier synthetic validation exercised
the one-space form only. The bridge now accepts exactly one or two ASCII
separator spaces for v0.8.7 snapshot and vertical manifests. Tabs, three or
more spaces, empty paths, leading-path spaces, duplicates, traversal and hash
mismatches remain rejected.
