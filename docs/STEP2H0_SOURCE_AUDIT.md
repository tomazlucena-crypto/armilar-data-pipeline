# Step 2H0 official-source feasibility audit

## Purpose

The audit asks a narrow question before any country parser is written:

> Does an official, accessible source exist that can plausibly yield calendar-2021 household final consumption expenditure by the twelve Armilar categories without allocating by population, GDP or income?

A successful download is insufficient. The source must also satisfy the conceptual and classification gates.

## Classes

- `A_CANDIDATE`: exact official S14/P31 data by the required categories appears available.
- `B_CANDIDATE`: an exact official derivation may be possible through item aggregation or an explicit classification bridge, without estimated shares.
- `C_ONLY`: the source is official but requires survey shares, temporal interpolation, grouped-category allocation or another experimental transformation.
- `D_UNAVAILABLE`: no adequate public source has been located or the source fails runtime validation.

## Initial registry

| Economy | Preliminary class | Official source | Principal blocker |
|---|---|---|---|
| China | C only | National Bureau of Statistics household-consumption release | Eight survey groups; food combines tobacco and alcohol; education combines culture and recreation |
| India | B candidate | MOSPI National Accounts Statistics, Statement 5.1 | Fiscal-year reference and exact item-to-Armilar bridge require validation |
| Russia | B candidate | Rosstat BRICS household consumption by purpose table | Exact cells and structured Rosstat export still require extraction |
| Indonesia | C only | BPS GDP by expenditure | Twelve COICOP divisions are regrouped into seven categories |
| Brazil | C only | IBGE System of National Accounts | Product tables require a many-to-many purpose allocation unless an exact bridge is found |
| Egypt | C only | CAPMAS HIECS 2021 | Household survey rather than S14/P31; imputed-rent treatment requires validation |
| Pakistan | C only | PBS HIES fallback | Survey is not 2021 and is not S14/P31; national accounts page has no confirmed twelve-category table |
| Nigeria | D unavailable | NBS expenditure-GDP report | Aggregate household consumption only |
| Bangladesh | C only | BBS HIES 2022 | Wrong reference year and survey concept |
| Viet Nam | C only | NSO VHLSS 2022 | Wrong reference year and survey concept |

The CSV registry is authoritative for machine execution. The runtime result may be weaker than the preliminary class when the response cannot be validated.

## Runtime controls

For every candidate the programme preserves:

- requested and final URL;
- retrieval status and HTTP status;
- content type and byte count;
- file signature result;
- required content-marker result;
- SHA-256 hash;
- retrieval timestamp;
- raw source file;
- blocking reason.

No probe result is imported into weights.

## Priority rule

The development order is based on:

`direct ICP expenditure share × assumed class success probability ÷ integration-cost divisor`

The seven-category direct-expenditure share is an engineering priority indicator. It does not estimate final Armilar coverage.
