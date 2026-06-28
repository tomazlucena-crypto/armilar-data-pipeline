# Architecture

## 1. Independent programmes

The repository now contains separable programmes sharing one schema and one methodology:

- ICP and international-source acquisition;
- `armilar-source-probe` for national-source feasibility;
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

## 5. Proxy audit

The financing-exposure calculation reconstructs strict HFCE from:

- the twelve Armilar nominal categories;
- derived narcotics expenditure;
- net purchases abroad.

It compares that result with nominal AIC. A separate table is reserved for matched strict-HFCE versus AIC PPP comparisons. The two diagnostics are never conflated.

## 6. Weight namespaces

- `weights_observed_universe.csv`: internally normalised complete observed subset;
- `weights_experimental_universe.csv`: separately authorised experimental observations only;
- `weights_final.csv`: approved worldwide matrix only.

Incomplete economies are excluded whole. The 19 official aggregate-only imputations remain separately reported.
