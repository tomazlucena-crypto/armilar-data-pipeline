# Armilar data pipeline v0.6.2

## Scope

This release hardens Step 2H0 source triage while the Step 2I audit remains open. It does not start Step 2J country parsers and does not add any exact matrix cells.

## Source-probe correction

An accessible homepage, catalogue entry or publication page is now discovery evidence only. A source qualifies as dataset evidence only when the configured resource is an API response, data file, database query or machine-readable HTML table and its signature and markers pass.

The probe records six ordered official-source families. Missing families are emitted as `NOT_INVESTIGATED`. A network or access failure is emitted as `ACCESS_BLOCKED` and preserved in a JSON receipt. Neither condition can support `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`.

The registry now contains 29 official candidate resources across China, India, Russia, Indonesia, Brazil, Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam.

## Option B correction

The release treats two quantities separately:

- `aic_hfce_financing_gap`, which measures the nominal exposure to consumption financed by government or NPISH;
- `aic_ppp_proxy_error`, calculated from matched PPPs as `PPP_HFCE / PPP_AIC - 1`.

The direct benchmark registry is empty because no matched official observations have yet passed the evidence gates. The validation status therefore remains `INSUFFICIENT_DIRECT_EVIDENCE`.

## Programmes

- `armilar-source-probe`
- `armilar-proxy-audit`
- `armilar-country`
- `armilar-matrix`

## New outputs

- `source_probe_family_coverage.csv`
- `proxy_error_by_category.csv`
- `proxy_error_by_economy.csv`

## Gates

- exact cells added: 0
- observed-universe coverage change: 0
- `weights_final.csv`: empty
- `global_12_category_matrix_complete=false`
- `monetary_release_allowed=false`
- Step 2J parsers: not started
