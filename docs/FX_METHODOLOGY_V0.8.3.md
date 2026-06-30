# Armilar FX Methodology v0.8.3

## Ratified separation

The Armilar price system publishes two distinct constructions.

### Primary inflation index

`PPP_WEIGHTED_LOCAL_PRICE_RELATIVES`

This index uses fixed PPP expenditure weights and local-currency price relatives.
Current exchange-rate movements do not enter the calculation. It measures the
weighted evolution of local consumption baskets.

### Informational common-currency layer

`COMMON_CURRENCY_BASKET_COST`

This layer converts each local price relative into an EUR-relative basket cost
using official ECB monthly-average exchange rates. It has its own identifier and
does not replace the primary inflation index.

For an ECB quote expressed as currency units per euro:

`common_relative = local_price_relative * fx_reference / fx_current`

A local-currency depreciation therefore reduces the EUR cost when local prices
are unchanged. The convention is recorded as `CURRENCY_UNITS_PER_EUR` and any
inverse convention is rejected.

## Source contract

The pilot uses the ECB `EXR` dataset with:

- frequency `M`;
- currency denominator `EUR`;
- exchange-rate type `SP00`;
- series variation `A`.

CSV columns are discovered from the response header. Raw bytes, final URL,
retrieval time, query, byte count and SHA-256 are preserved in receipts.

## Failure rules

- Missing FX never changes the primary index.
- The common-currency layer is marked incomplete when any fixed weight lacks FX.
- Missing cells are not renormalised away.
- EUR economies use an implicit rate of one.
- Redenominations require an explicit factor to canonical currency units.
- Currency transitions require a separately ratified bridge.
- Inputs already converted into a common currency are rejected to prevent double
  conversion.

Both constructions remain research-only and are barred from monetary use.
