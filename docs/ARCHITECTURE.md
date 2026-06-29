# Architecture

## 1. Independent programmes

The repository now contains separable programmes sharing one schema and one methodology:

- ICP and international-source acquisition;
- `armilar-source-probe` for national-source feasibility;
- `armilar-country` for isolated country adapters;
- Option B evidence audit;
- matrix builder and weight gates.

The full workflow runs them together, while the source probe can run independently.

## 2. Acquisition

Every source is downloaded with retries, size limits and a project user-agent. Fresh responses are preserved under `run/raw`. A last-known-good cache may be used only after fresh attempts fail and is labelled `stale_cache`.

World Bank Source 90 is mandatory. OECD, UNData and Eurostat are independent supplemental routes. Country probes are diagnostic and cannot block the established matrix.

## 3. Economic construction

Seven categories use direct strict-household ICP cells. CP02 is alcohol plus tobacco, excluding narcotics. Five categories use strict household nominal expenditure divided by an AIC PPP proxy under the ratified research amendment.

Government and NPISH expenditure never enters the numerator.

## 4. Step 2H0 source feasibility

Candidate sources are declared in `config/source_probe_candidates.csv`. Each is classified conceptually before runtime. GitHub Actions then verifies accessibility and file content.

Country-specific adapters will only be written for sources that remain A or B candidates after runtime validation. C sources are retained for a future experimental universe. D sources remain unavailable.

## 5. Country adapters

Country adapters expose one common result shape:

- `country_adapter_status.csv`;
- `country_source_evidence.csv`;
- `country_normalized_rows.csv`;
- `country_mapping_audit.csv`;
- `country_reconciliation_audit.csv`;
- `country_adapter_failures.csv`.

Each normalized cell carries economy, period, Armilar category, original item, value, currency, unit, sector, transaction, classification, source authority, file, URL, retrieval time, hash, derivation method, data class and quality flags.

Adapter failures are isolated by country. A blocked Russia or China audit does not prevent India evidence, and a blocked country adapter does not delete the established ICP matrix outputs.

Data classes remain separated:

- `EXACT_OFFICIAL`;
- `OFFICIAL_EXACT_DERIVATION`;
- `EXPERIMENTAL_ALLOCATION`;
- `UNAVAILABLE`.

Only the first two may enter the exact matrix. The current India adapter parses and reconciles MoSPI Statement 5.1, but keeps India `UNAVAILABLE` until the PFCE institutional boundary is officially confirmed as strict households-only with NPISH excluded.

Version 0.6.0 adds per-cell Step 2I decisions. A country can mix official providers by category only when every accepted cell is S14/P31DC, current-price, same accepted reference period, same currency/unit basis, NPISH and government excluded, exact COICOP/Armilar mapping, full provenance and reconciliation. Mixed providers are rejected on duplicate categories, incompatible periods, units, concepts or missing provenance.

## 6. Proxy audit

The financing-exposure calculation reconstructs strict HFCE from:

- the twelve Armilar nominal categories;
- derived narcotics expenditure;
- net purchases abroad.

It compares that result with nominal AIC. A separate table is reserved for matched strict-HFCE versus AIC PPP comparisons. The two diagnostics are never conflated.

## 7. Weight namespaces

- `weights_observed_universe.csv`: internally normalised complete observed subset;
- `weights_experimental_universe.csv`: separately authorised experimental observations only;
- `weights_final.csv`: approved worldwide matrix only.

Incomplete economies are excluded whole. The 19 official aggregate-only imputations remain separately reported.
