# ARMILAR v0.9.8

Introduces the first-seen point-in-time proxy archive and cutoff information-set builder.

The release preserves every v0.9.7 snapshot row, derives distinct value versions and revision events, audits source continuity, records changes between consecutive snapshots and builds deterministic cutoff panels using only values actually observed by ARMILAR by the requested UTC timestamp.

Successive archives form an explicit immutable chain. A successor records its predecessor hashes, must preserve every predecessor snapshot observation and must add at least one new snapshot.

Each cutoff now includes source-level freshness diagnostics distinguishing current sources, stale sources and sources not yet observed by the cutoff.

It does not reconstruct pre-archive vintages, map proxies into the index, train models, build ARM-L, publish a research release or open any monetary gate.
