# ARMILAR v0.9.7 proxy source audit

Audit date: 2026-07-03.

## Registered sources

### World Bank Pink Sheet

Official monthly historical commodity-price workbook. Admitted for upstream global energy, food and crude-oil research signals. It is not a household retail-price source and the current workbook does not preserve the first-published vintage of each historical row.

Licence position: World Bank-produced open datasets generally use CC BY 4.0 unless a dataset-specific exception is stated. The registry remains fail-closed if such an exception is found.

### FAO Food Price Index

Official monthly international food commodity index and five commodity-group subindices. Admitted as a global food research signal. It does not measure national household retail prices. A current release date does not prove the publication date of every historical row.

Licence position: FAO statistical database terms identify CC BY 4.0 reuse with attribution and modification notices.

### European Commission Weekly Oil Bulletin

Official weekly consumer petroleum-price history for EU Member States. Admitted for fuels and transport research. Its coverage is geographically and categorically incomplete, so it cannot substitute for CP07 or CP04 price cells.

Licence position: Commission reuse policy applies subject to attribution and dataset-specific exceptions.

### Eurostat owner-occupied housing price index

Official quarterly OOHPI dataset `prc_hpi_ooq`. Admitted solely for the constitutionally required OOH sensitivity analysis. Its net-acquisitions framework is conceptually distinct from HFCE imputed rent.

Licence position: Eurostat reuse is allowed with acknowledgement unless an identified third-party exception applies.

## Publication-time conclusion

None of the four registered sources currently proves a complete historical sequence of first-published vintages and exact availability timestamps. Consequently, all have `historical_vintage_support=false`, and every v0.9.7 snapshot has `information_set_ready=false`.

## Source status

| Source | Status | Direct index | ARM-L | Model training |
|---|---|---:|---:|---:|
| World Bank Pink Sheet | Active research proxy | No | No | No |
| FAO Food Price Index | Active research proxy | No | No | No |
| EC Weekly Oil Bulletin | Active research proxy | No | No | No |
| Eurostat OOHPI | Active sensitivity only | No | No | No |
