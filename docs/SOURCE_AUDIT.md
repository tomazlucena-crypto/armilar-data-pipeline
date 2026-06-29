# Source audit

## Established international sources

World Bank ICP 2021 Source 90 provides the global PPP link, direct published HFCE headings, participation controls and aggregate-imputation evidence. OECD Table 5 T501, UNData SNA Table 3.2, Eurostat `nama_10_cp18` and OECD Table 5A T501 provide strict-household nominal expenditure under explicit concept and classification gates.

The international-source hierarchy selects one complete provider per economy. It does not splice incompatible concepts.

## National-source triage

The ten-economy registry in `config/source_probe_candidates.csv` is a feasibility inventory. It names actual official resources and classifies their evidence role. Homepages and catalogue pages are discovery-only. A download remains inadmissible when its concept, period or classification requires allocation.

The source probe preserves real acquisition receipts and emits full family coverage. It does not infer that an unavailable network path means the data do not exist.

## Option B evidence

`proxy_financing_exposure.csv` reports the nominal AIC/HFCE financing gap. It measures third-party financing exposure.

`proxy_ppp_comparison.csv` contains only matched official AIC and strict-HFCE PPP observations for the same economy, category and year. The corresponding error is:

`PPP_HFCE / PPP_AIC - 1`

`proxy_error_by_category.csv` and `proxy_error_by_economy.csv` summarise only those direct pairs. Without enough direct pairs, the status remains `INSUFFICIENT_DIRECT_EVIDENCE` regardless of the financing-gap sample size.

## Known scope limitation

Current national-accounts releases may contain revisions made after the ICP 2021 compilation vintage. The pipeline preserves the exact source vintage and quality flags rather than hiding this mismatch.
