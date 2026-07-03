# ARMILAR_RESEARCH_CORE_V1 Proxy Exposure Annex

The canonical annex is `constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json`.

## Scope

The current basket has 60 economy-category cells. Exactly 25 cells use `EXPERIMENTAL_RESEARCH` evidence because an actual-consumption PPP is used as the ratified Option B proxy for an HFCE numerator.

The affected categories are:

- CP04
- CP06
- CP09
- CP10
- CP12

They occur in every Research Core economy:

- DEU
- ESP
- FRA
- ITA
- PRT

## Weight exposure

Total fixed-universe proxy weight:

`0.589731681350816432896035605`

This is approximately `58.9731681350816432896035605%` of the Research Core basket.

### By category

| Category | Fixed-universe weight |
|---|---:|
| CP04 | `0.296410647375223307593806250` |
| CP06 | `0.074232235762010281782517264` |
| CP09 | `0.067940846492056712430431078` |
| CP10 | `0.016283152249515748557712695` |
| CP12 | `0.134864799472010382531568318` |

### By economy

| Economy | Fixed-universe proxy weight |
|---|---:|
| DEU | `0.213560166141047201153062839` |
| ESP | `0.083129678840141230844116839` |
| FRA | `0.152800211310763518545092201` |
| ITA | `0.121540337414705457551044175` |
| PRT | `0.018701287644159024802719551` |

## Interpretation

The exposure is systematic by category and shared across all five economies. It must not be described as exact HFCE-PPP coverage.

Every coverage or quality report must disclose:

- the total proxy weight share;
- the affected categories;
- the evidence class;
- the current basket and annex versions.

A later source improvement follows the amendment classes defined in `docs/DECISION_RESEARCH_CORE_AMENDMENT_PROCESS.md`. No proxy cell may be silently promoted.
