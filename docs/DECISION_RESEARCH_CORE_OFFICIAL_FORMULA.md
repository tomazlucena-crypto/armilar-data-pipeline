# Decision proposal: Research Core official formula

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

ARM-O is a fixed-weight arithmetic Laspeyres-type research index using PPP-adjusted 2021 expenditure weights:

\[
ARM	ext{-}O_t=\sum_i\sum_c w_{i,c}R_{i,c,t}
\]

The target weight concept is each economy-category cell's share of 2021 real HFCE expenditure converted to a common comparable unit through ICP PPPs. The weights are fixed within the basket version.

The current implementation contains explicit exceptions: 25 cells use an AIC PPP as the ratified Option B proxy for the HFCE numerator. These cells are listed in `constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json` and may not be described as exact HFCE-PPP observations.

The 60 `fixed_universe_weight` values sum exactly to one. CP00 and current FX are excluded.

A period with any missing weighted cell receives no ARM-O value and status `INCOMPLETE`; weights are never silently renormalized.

Cell contribution to the monthly movement is:

\[
C_{i,c,t}=w_{i,c}(R_{i,c,t}-R_{i,c,t-1})
\]

## Basket scope

The following are fixed within `ARMILAR_RESEARCH_CORE_V1`:

- economies: DEU, ESP, FRA, ITA and PRT;
- categories: CP01 to CP12.

Adding or removing an economy or category requires a new basket version, a new series, an impact analysis and preservation of the previous series.

A better source for an existing cell follows the patch rules in the amendment decision. It never changes scope silently.

## Consequences

The name ARM-O means official-source Research Core series. It is not an official statistic.

The engine must preserve:

- complete-grid operation;
- no-renormalization;
- fixed basket scope;
- explicit proxy exposure;
- exact reproducibility from the basket version and price vintage.
