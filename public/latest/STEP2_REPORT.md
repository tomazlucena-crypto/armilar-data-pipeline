# Armilar Step 2 acquisition report

Generated: 2026-06-28T20:22:54Z

## Source identification

The pipeline uses World Bank DataBank source 90, ICP 2021, and preserves the source metadata,
dimension inventories, classification workbook, participation page, FAQ and every data response page.

## Discovered Source 90 dimensions

- Country: `Country`
- Heading: `Series`
- Measure: `Classification`
- Time: `Time` (`YR2021`)

## Selected measures

- PPP: `PPPGlob`
- Nominal expenditure: `CN`
- Real PPP-based expenditure: `PP.CD`

## Methodological gates

- Only headings in the 1100000 household-consumption branch are accepted.
- CP02 is built from 1102100 and 1102200; 1102300 and parent 1102000 are excluded.
- AIC headings, NPISH and government individual consumption are rejected.
- An economy enters candidate weights only with all twelve categories and the HFCE control aggregate.
- PPP, nominal and real expenditure are reconciled numerically.
- Additive hierarchy identities are tested in nominal local-currency expenditure, not across non-additive PPP real expenditures.
- PPP-based real expenditure is validated separately through nominal expenditure divided by PPP.
- Published AIC or households-plus-NPISH headings are preserved as evidence and rejected as HFCE substitutes.
- No population, GDP, income or model allocation is used.

## Result

- Status: `BLOCKED_SOURCE_PUBLICATION_SCOPE`
- Release allowed: `False`
- Complete participating economies: `0`
- Candidate cells: `0`
- Candidate weight sum: `0`

## Public publication scope audit

- HFCE_CONTROL: missing `1100000`; forbidden alternatives present `9100000`.
- CP04: missing `1104000`; forbidden alternatives present `9060000`.
- CP06: missing `1106000`; forbidden alternatives present `9080000`.
- CP09: missing `1109000`; forbidden alternatives present `9110000`.
- CP10: missing `1110000`; forbidden alternatives present `9120000`.
- CP12: missing `1112000`; forbidden alternatives present `9140000`.

Missing required headings in Source 90 inventory: 1100000, 1104000, 1106000, 1109000, 1110000, 1112000

## Blocking reasons

- PARTICIPATION_REGISTRY_NOT_FULLY_MAPPED:173/176
- PARTICIPATING_ECONOMIES_INCOMPLETE:0/176
- OFFICIAL_IMPUTATION_REGISTRY_COUNT_MISMATCH:20/19
- OFFICIALLY_IMPUTED_ECONOMIES_HAVE_NO_PUBLIC_12_CATEGORY_ALLOCATION:20
- WEIGHT_SUM_OUTSIDE_TOLERANCE:0
- MANDATORY_HEADINGS_ABSENT_FROM_SOURCE90_INVENTORY:1100000,1104000,1106000,1109000,1110000,1112000
- STRICT_HFCE_PUBLICATION_SCOPE_MISSING_REQUIRED_HEADINGS:1100000,1104000,1106000,1109000,1110000,1112000
- FORBIDDEN_ALTERNATIVES_AVAILABLE_BUT_NOT_USED:9060000,9080000,9100000,9110000,9120000,9140000
