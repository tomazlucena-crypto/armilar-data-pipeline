# Architecture

## 1. Acquisition

Every source is downloaded by GitHub Actions with retries, size limits and a project user-agent. The fresh response is preserved under `run/raw`. A last-known-good cache may be used only after all fresh attempts fail; the manifest labels it `stale_cache`.

World Bank Source 90 is mandatory. OECD, UNData and Eurostat are independent official supplemental routes. Failure of one supplemental route does not erase the others and is reported in `source_acquisition_failures.csv`.

## 2. Source discovery

The pipeline discovers Source 90 concept order, variables and the 2021 time identifier from the API. It does not hard-code the multidimensional query order. It validates:

- Source ID 90 and ICP 2021 identity;
- the official classification workbook;
- presence of every Source 90 heading required by the selected methodology;
- the official list of 176 participating economies.

## 3. Economic construction

### Direct categories

For CP01, CP03, CP05, CP07, CP08 and CP11:

`real expenditure = ICP nominal household expenditure / ICP category PPP`

For CP02:

`real expenditure = alcohol nominal / alcohol PPP + tobacco nominal / tobacco PPP`

The composite CP02 PPP is retained as `total nominal / total real`. The parent containing narcotics is never used.

### Proxy-PPP categories

For CP04, CP06, CP09, CP10 and CP12:

`real expenditure = strict household domestic nominal expenditure / ICP actual-consumption PPP proxy`

Only the deflator has the broader actual-consumption scope. The numerator is restricted to household domestic consumption.

## 4. Supplemental provider selection

A provider is eligible for an economy only when it supplies all five proxy categories. One provider is selected for the whole economy according to the configured priority. Category-level provider mixing is prohibited.

Alternative official providers are retained in the audit. Divergences are reported and never rescaled away.

## 5. Unit and identity controls

The selected Source 90 measures must satisfy the median identity:

`nominal expenditure / PPP = published PPP-based real expenditure`

Supplemental nominal values are compared with overlapping direct Source 90 categories. Obvious unit-scale mismatches invalidate that source for that economy. No automatic scale correction is applied.

## 6. Economy eligibility

Every admissible category cell is preserved. An economy enters weights only when all twelve categories exist. Incomplete economies are excluded whole, rather than implicitly renormalising their available categories.

The 19 officially imputed non-participants are tagged `OFFICIALLY_IMPUTED_AGGREGATE_ONLY` and excluded because the public ICP release does not provide a twelve-category allocation.

## 7. Weights

For the complete observed-participant universe:

`w(i,c) = real_expenditure(i,c) / sum(real_expenditure)`

Weights are quantised to 24 decimal places. A deterministic residual is applied to the final sorted row so the emitted sum is exactly 1.

## 8. Release layers

- `weights_research_observed_normalized.csv`: complete observed participants only.
- `weights_final_normalized.csv`: populated only after the full global scope passes.
- `monetary_release_allowed`: always false in Step 2.

## 9. Provenance

Every normalised row records source file, URL, retrieval timestamp, SHA-256 and quality flags. `manifest.json` lists acquisition metadata. `SHA256SUMS` covers the entire run directory.
