# Decision proposal: Research Core precision and rounding

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

Use Python `Decimal` arithmetic with precision `28` and `ROUND_HALF_EVEN`. Preserve source-weight precision and perform no intermediate rounding.

Canonical persisted scales:

| Field | Decimal places |
|---|---:|
| price relative | 12 |
| index level | 12 |
| contribution points | 12 |
| percentage rate | 8 |
| coverage share | 12 |

Canonical values use plain decimal strings without scientific notation. Display rounding is non-canonical.

Contribution reconciliation is checked before rounding. Any difference produced solely by output quantization is published separately as a rounding residual and is never hidden inside a cell.

## Consequences

The v0.9.6 engine must replace binary-float arithmetic at the constitutional calculation boundary.
