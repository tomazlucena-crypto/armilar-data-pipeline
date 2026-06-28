# Armilar Step 2 delivery report

Version: 0.2.0  
Audit date: 2026-06-28

## Purpose

This release replaces the connectivity bootstrap with an auditable ICP 2021 acquisition and weight-matrix pipeline designed for GitHub Actions.

## Repository audit

The previous public run established working Internet access to the World Bank and Eurostat. The OECD HTTP 416 result belonged to an optional bounded-range connectivity probe. OECD is not used in the ICP 2021 weight-matrix path in this release.

## Exact ICP 2021 source path

The pipeline is pinned to World Bank Advanced Data API Source 90 and preserves:

- source metadata;
- concept and variable inventories;
- multidimensional 2021 observation pages;
- the ICP 2021 classification workbook;
- the official participation page;
- the ICP data page and FAQ;
- the official DataBank published table.

The observation parser normalizes PPPs, nominal expenditure and PPP-based real expenditure with source URL, retrieval timestamp and SHA-256 provenance.

## Economic finding

The public 45-heading release provides strict HFCE headings for CP01, CP03, CP05, CP07, CP08 and CP11, together with alcohol and tobacco components for a narcotics-free CP02.

It publishes actual-consumption alternatives rather than strict HFCE divisions for CP04, CP06, CP09, CP10 and CP12. It also publishes a households-plus-NPISH aggregate rather than the strict HFCE control. These alternatives are preserved for evidence and prohibited from entering Armilar weights.

The additional 19 officially imputed nonparticipating economies have aggregate PPP results only. No twelve-category allocation is created by the pipeline.

## Statistical rules implemented

- Candidate weights use PPP-based real expenditure.
- Nominal local-currency expenditure is used for additive hierarchy checks.
- PPP-based real expenditures are checked through nominal expenditure divided by PPP.
- Real expenditures are not required to add to a published parent aggregate.
- CP02 is represented by the two published atomic components alcohol and tobacco, with narcotics excluded.
- Net purchases abroad is preserved as an excluded HFCE adjustment and may be negative.
- Duplicate economy-heading-measure records are fatal.
- AIC, NPISH, government consumption and modelled allocations are prohibited.
- Final weights are written only when every release gate passes.
- Candidate weights close exactly to 1 by a deterministic final-cell rounding adjustment. The explicit acceptance tolerance is 1E-20.

## Expected live result

If the live Source 90 inventory matches the official 45-heading table, the run status will be `BLOCKED_SOURCE_PUBLICATION_SCOPE`. It will still publish the complete acquisition bundle, normalized data, coverage, exclusions, missing-data records and candidate diagnostics. `weights_final_normalized.csv` will contain only its header.

Step 2 is therefore not declared complete by this package. Completion requires an official publication or authorized release containing the missing strict-HFCE divisions and a methodologically accepted treatment of the 19 aggregate-only imputed economies.

## Validation

- Python unit tests: 22 passed, 0 failed.
- JSON configuration and schemas parsed successfully.
- GitHub Actions YAML parsed successfully.
- All Python source files compiled successfully.
- Package manifest verified after extraction from the delivery ZIP.
