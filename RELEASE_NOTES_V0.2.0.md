# Armilar data pipeline v0.2.0

## Purpose

This release replaces the connectivity bootstrap with the effective ICP 2021 Step 2 acquisition and audit pipeline.

## Source audit result

World Bank Source 90 is the authoritative machine-readable ICP 2021 database. The public release provides 45 expenditure headings, PPPs, nominal expenditure and PPP-based real expenditure.

The published heading set does not currently provide a complete strict-HFCE twelve-category matrix. Five divisions are represented by actual-consumption headings, and the public household aggregate combines households with NPISHs. The pipeline records these as forbidden alternatives and does not use them.

The 19 official nonparticipant imputations are available only at aggregate levels and remain separate.

## Acquisitions

The workflow now preserves:

- Source 90 metadata;
- concept and variable inventories;
- strict HFCE and imputation-control data pages;
- the classification workbook;
- participation, data and FAQ pages;
- the official published table.

Every file receives a metadata sidecar, retrieval timestamp and SHA-256 hash.

## Matrix rules

- Source: ICP 2021, Source 90.
- Scope: strict HFCE only.
- CP02: alcohol plus tobacco.
- Narcotics: excluded without estimation.
- AIC, NPISH and government consumption: rejected.
- Net purchases abroad: adjustment outside the twelve categories.
- Additive checks: nominal local-currency expenditure.
- PPP-based real expenditure: used for weights and checked through `nominal / PPP = real`.
- Missing values: reported and never silently filled.
- Experimental allocation: none.
- Weight precision: 24 decimal places.
- Weight-sum tolerance: `1E-20`.

## New audit outputs

- `publication_scope_audit.csv` identifies missing strict headings and visible forbidden alternatives.
- `economy_registry.csv` records the evidence used for participation and official-imputation status.
- `hierarchy_reconciliation.csv` now states its nominal measure basis.
- `source90_variable_inventory.csv` preserves the live heading and measure inventory.

## Automated tests

Twenty-two tests cover configuration, source identity, publication-scope blocking, workbook validation, participation parsing, measure selection, duplicate rejection, official aggregate-only imputation detection, category construction, nominal hierarchy reconciliation, non-additive PPP real expenditures, exact weight closure and the global release gate.

The complete synthetic test contains 176 participants and 19 aggregate-only official imputations. It verifies 2,112 participant-category cells, exact weight closure and a blocked worldwide release.
