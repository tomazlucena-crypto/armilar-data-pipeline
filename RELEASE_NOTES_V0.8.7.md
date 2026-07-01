# Armilar v0.8.7

This release implements the first bounded Eurostat price-to-index vertical chain.

## Added

- official Eurostat JSON-stat acquisition with bounded requests;
- immutable raw snapshots, request receipts and SHA-256 verification;
- fixed universe of Germany, Spain, France, Italy and Portugal;
- complete CP01-CP12 monthly grid from 2021-01 through 2025-12;
- one-time normalization of the selected observed world weights;
- monthly PPP-weighted local-price index;
- contributions by economy, ECOICOP division and canonical Armilar category;
- explicit coverage and uncertainty disclosures;
- deterministic replay, manifest verification and economic report;
- fail-closed tests for incomplete grids, duplicate data, path traversal and hash changes;
- a single local official-data gate that avoids iterative GitHub Actions and proves `public/latest` is unchanged.

## Release status

The official Eurostat snapshot was acquired locally, preserved as exact raw bytes and replayed successfully through the deterministic vertical chain. No synthetic fixture is described as official evidence.

`research_release_allowed=false`

`monetary_release_allowed=false`
