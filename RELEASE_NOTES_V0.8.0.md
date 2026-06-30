# Armilar v0.8.0

## Added

- canonical monthly price-series registry;
- price evidence hierarchy P1 to P5;
- deterministic monthly rebasing and category expansion;
- source selection with audit trails and source-switch detection;
- monthly core and global research index engine;
- explicit incomplete-period handling without silent renormalisation;
- contribution and evidence-coverage outputs;
- optional `sdmx1` acquisition adapter contract;
- OECD and Eurostat live-pilot candidates, disabled pending network validation;
- CLI command `armilar-prices`.

## Safety state

- no real-world monthly Armilar index is released by this version alone;
- common-currency FX adjustment is blocked pending methodological ratification;
- `research_release_allowed=false`;
- `monetary_release_allowed=false`.
