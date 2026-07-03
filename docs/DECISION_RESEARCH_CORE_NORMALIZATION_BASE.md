# Decision proposal: Research Core normalization base

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

For every economy-category cell, define the Research Core base as the arithmetic mean of the twelve official non-seasonally-adjusted monthly price-index levels for January to December 2021. The resulting annual average is re-referenced to `100`.

\[
R_{i,c,t}=100\times\frac{P_{i,c,t}}{\frac{1}{12}\sum_{m=1}^{12}P_{i,c,2021,m}}
\]

All twelve base-year months are mandatory. Missing, zero or negative base observations cause a fail-closed result. No substitution, interpolation or renormalization is allowed.

## Reason

The basket weights represent 2021 annual expenditure. An annual-average price base aligns the time reference with those annual weights and avoids assigning constitutional importance to one arbitrary month.

## Consequences

The v0.9.6 engine must add annual-average normalization. Existing single-month research outputs remain historical experiments and must not be silently relabelled as ARM-O.
