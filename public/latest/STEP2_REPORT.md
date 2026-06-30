# Armilar Step 2 hybrid ICP 2021 report

Generated: 2026-06-30T21:05:22Z

## Method

Seven categories use strict household ICP headings from World Bank Source 90.
CP02 is constructed from alcohol plus tobacco and excludes narcotics.
Five categories use strict household S14/P31DC nominal expenditure from OECD, UNSD or Eurostat,
divided by the ratified ICP actual-consumption PPP proxy for the matching category.
Government and NPISH expenditure never enters the numerator.

## Status

- Status: `RESEARCH_MATRIX_AVAILABLE_GLOBAL_SCOPE_INCOMPLETE`
- Research release allowed: `True`
- Monetary release allowed: `False`
- Participating economies mapped: `176` / `176`
- Complete participating economies: `62`
- Observed-universe weight cells: `744`
- Observed-universe weight sum: `1.000000000000000000000000`
- Officially imputed aggregate-only economies: `19`

## Supplemental source diagnostics

- `OECD_TABLE5_T501`: accepted=432, excluded=8312, status=OK
- `UNDATA_SNA_TABLE32`: accepted=675, excluded=12, status=OK
- `EUROSTAT_NAMA_10_CP18`: accepted=384, excluded=0, status=OK
- `OECD_TABLE5A_T501`: accepted=360, excluded=8582, status=OK

## Step 2H0 feasibility audit

- Priority economies probed: `15`
- A/B candidates accessible in this run: `0`
- C-only economies accessible in this run: `1`
- Unavailable economies in this run: `14`
- Complete-economy coverage in the seven-category priority indicator: `0.4971716160380331246617494915`
- Option B evidence status: `INSUFFICIENT_DIRECT_EVIDENCE`
- Direct strict-HFCE versus AIC PPP comparisons: `0`

The source probe classifies availability and conceptual suitability; it does not insert any national source into the matrix.
The priority indicator uses only seven direct ICP categories and is not a world-coverage estimate.

## Remaining global-scope blockers

- PARTICIPATING_ECONOMIES_WITH_INCOMPLETE_12_CATEGORY_DATA:114
- OFFICIALLY_IMPUTED_NONPARTICIPANTS_EXCLUDED_NO_CATEGORY_DETAIL:19
