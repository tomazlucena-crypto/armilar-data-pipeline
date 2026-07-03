# Decision proposal: Research Core official formula

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

ARM-O is a fixed-weight arithmetic Laspeyres-type research index:

\[
ARM\text{-}O_t=\sum_i\sum_c w_{i,c}R_{i,c,t}
\]

where the 60 `fixed_universe_weight` values sum exactly to one and each 2021 annual-average price relative equals 100.

CP00 and current FX are excluded. A period with any missing weighted cell receives no ARM-O value and status `INCOMPLETE`; weights are never silently renormalized.

Cell contribution to the monthly movement is:

\[
C_{i,c,t}=w_{i,c}(R_{i,c,t}-R_{i,c,t-1})
\]

## Consequences

The name ARM-O means official-source Research Core series. It is not an official statistic. The engine must preserve complete-grid and no-renormalization invariants.
