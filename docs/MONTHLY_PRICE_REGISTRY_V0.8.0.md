# Armilar monthly price registry v0.8.0

## Status

This release establishes the deterministic monthly-price contract and research index engine. It does not yet publish a validated real-world Armilar index.

The live OECD and Eurostat pilot remains disabled until the provider data structures, query keys and retrieved observations are preserved and tested in GitHub Actions or another network-enabled environment.

## Evidence hierarchy

Every economy-category-period observation is assigned one price-evidence class:

1. `P1_OFFICIAL_CATEGORY`: direct official CPI or HICP for one Armilar category;
2. `P2_OFFICIAL_AGGREGATE`: official broader group mapped to one or more categories;
3. `P3_OFFICIAL_HEADLINE`: official national headline CPI used as a temporary category fallback;
4. `P4_REGIONAL_PROXY`: regional category proxy;
5. `P5_GLOBAL_PROXY`: global category proxy.

The selector always chooses the lowest evidence rank first, then the declared source priority, then the stable series identifier. A headline series cannot displace a direct category series merely because it has a lower numeric source priority.

## No silent renormalisation

The index engine does not renormalise the available price cells when a period is incomplete. An incomplete month is written with:

- `status=INCOMPLETE`;
- a blank index value;
- the covered weight;
- the missing cells.

This prevents a changing observed universe from being presented as a stable world index.

## Reference-period rebasing

Each source series must contain the declared reference month. The normaliser rebases that series to 100 in the reference month before expanding it to its target Armilar categories.

Series without the reference month are reported and excluded. They are not backfilled automatically in v0.8.0.

## Aggregation

The implemented research baseline is:

`PPP_WEIGHTED_LOCAL_PRICE_RELATIVES`

It combines local CPI/HICP relatives with the fixed PPP expenditure weights. It is useful as a global inflation baseline.

The alternative `COMMON_CURRENCY_FX_ADJUSTED` mode is explicitly blocked. The treatment of exchange rates must be ratified methodologically before code is allowed to calculate a common-currency basket value.

## Open-source SDMX reuse

The optional acquisition adapter delegates SDMX retrieval to `sdmx1`. The dependency is optional because deterministic tests and local fixtures must remain runnable without network access.

The first candidate providers are:

- OECD `DSD_PRICES@DF_PRICES_ALL`;
- Eurostat `prc_hicp_midx`.

Their pilot definitions remain disabled until a live run confirms the exact structures and query keys.

## Release controls

This release always reports:

- `research_release_allowed=false`;
- `monetary_release_allowed=false`;
- `fx_treatment=NOT_INCLUDED_RESEARCH_BASELINE`.

A real monthly series can only be promoted after provider receipts, data vintages, coverage and backtests have been audited.
