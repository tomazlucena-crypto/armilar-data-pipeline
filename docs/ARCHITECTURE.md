# Architecture

## 1. Four independent programmes

The repository keeps one methodology and one set of schemas, exposed through four programmes:

1. `armilar-source-probe` performs source-family triage and preserves raw evidence;
2. `armilar-proxy-audit` tests the AIC PPP proxy using matched direct benchmarks;
3. `armilar-country` runs isolated national adapters for sources that survive triage;
4. `armilar-matrix` acquires the established international sources and constructs the research matrix.

The full pipeline composes these programmes. Each can also run independently.

## 2. Acquisition and evidence

Every real attempt records the exact URL, timestamp, HTTP result where available, content type, byte count, signature result, markers and SHA-256 when content exists. Failed attempts produce a receipt with the error chain and no content hash.

A landing page, catalogue page, documentation page or publication page is discovery evidence. It cannot qualify as a dataset. Dataset evidence is restricted to validated API responses, data files, database queries and machine-readable HTML tables.

A last-known-good cache may be used after fresh attempts fail and is labelled `stale_cache`.

## 3. Source-family triage

For each economy, the probe reports these ordered families:

1. official national-accounts API;
2. official CSV, XLS or XLSX;
3. official statistical database;
4. official supply-and-use tables;
5. official structured publications;
6. survey or CPI evidence, Class C only.

The first five are required before definitive unavailability can be considered. `NOT_INVESTIGATED`, `ACCESS_BLOCKED` and discovery-only results keep the decision provisional.

## 4. Economic construction

Seven categories use direct strict-household ICP cells. CP02 combines alcohol and tobacco while excluding narcotics. Five categories use strict-household nominal expenditure divided by an AIC PPP proxy under the ratified research amendment.

Government and NPISH expenditure never enters the numerator.

## 5. Proxy audit

The proxy audit keeps two diagnostics separate:

- financing exposure: nominal AIC minus reconstructed strict HFCE;
- direct proxy error: `PPP_HFCE / PPP_AIC - 1` for matched official economy-category-year pairs.

Financing exposure cannot validate the PPP proxy. Direct validation is blocked until the minimum total, economy and per-category comparison gates pass.

## 6. Country adapters

Only sources that remain A or B candidates after runtime and conceptual review should receive parsers. Every adapter emits a common result contract, and a failure in one economy cannot affect another.

Accepted exact data classes are `EXACT_OFFICIAL` and `OFFICIAL_DERIVED_NO_ALLOCATION`. Experimental allocations and incompatible concepts stay outside the exact matrix.

## 7. Weight namespaces

- `weights_observed_universe.csv`: internally normalised complete observed subset;
- `weights_experimental_universe.csv`: separately authorised experimental observations only;
- `weights_final.csv`: approved worldwide matrix only.

A sum of one in the observed universe proves internal normalisation only.
