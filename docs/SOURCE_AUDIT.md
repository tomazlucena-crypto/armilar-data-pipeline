# ICP 2021 source audit

Audit date: 2026-06-28

## Repository state before this release

The public repository was a connectivity bootstrap. Its latest published run confirmed normal access to the World Bank and Eurostat. The OECD probe reached DNS and TLS but returned HTTP 416 because the bootstrap sent a bounded byte-range request to an endpoint that did not accept that range. OECD is not part of the ICP 2021 weight-matrix path in this release.

## Definitive statistical database

The machine-readable ICP source is the World Bank DataBank database:

- database: International Comparison Program 2021;
- Advanced Data API source ID: `90`;
- expected source code when returned by metadata: `IC2`;
- research reference year: `2021`;
- access mechanism: World Bank Advanced Data API V2.

The pipeline downloads and validates the source descriptor before accepting any observation.

## Exact official resources

The full registry is in `config/source_registry.csv`.

1. Source metadata
   - `https://api.worldbank.org/v2/sources/90?format=json`
   - Validates the exact database identity and availability metadata.

2. Source concepts
   - `https://api.worldbank.org/v2/sources/90/concepts/data?format=json&per_page=1000`
   - Discovers the dimensions and their order.

3. Concept-variable inventories
   - `https://api.worldbank.org/v2/sources/90/{concept}/data?format=json&per_page=1000`
   - Discovers economies, published expenditure headings, measures and time identifiers.

4. Multidimensional observations
   - `https://api.worldbank.org/v2/sources/90/{concept}/{selector}/.../data`
   - Supplies PPPs, nominal expenditure and PPP-based real expenditure for requested economy-heading combinations.
   - Query paths are generated from the concept order returned by the API.

5. ICP 2021 classification workbook
   - `ICPClassificationwithNonH-2021.xlsx`
   - Confirms the economic classification and the existence of strict HFCE codes in the full ICP taxonomy.
   - It does not prove that every code is published in Source 90.

6. ICP 2021 published table
   - `https://databank.worldbank.org/ICP-2021-Cycle/id/3a11040d`
   - Documents the actual 45-heading public release and the available measures.

7. ICP 2021 governance page
   - Provides the official regional list of 176 participating economies.
   - The parser deduplicates dual-participation economies and requires 176 unique names.

8. ICP data page and FAQ
   - Document 176 participating economies and 19 additional nonparticipating economies with official imputations.
   - Official imputations are published only at GDP, household-consumption and AIC aggregate levels.

## Public publication scope

The public 45-heading table contains strict household headings for:

- `1101000`, CP01;
- `1102100` and `1102200`, CP02 without narcotics;
- `1103000`, CP03;
- `1105000`, CP05;
- `1107000`, CP07;
- `1108000`, CP08;
- `1111000`, CP11.

For five Armilar divisions, the published table uses actual-consumption headings instead of strict HFCE headings:

| Armilar category | Required strict HFCE | Public alternative | Why rejected |
|---|---:|---:|---|
| CP04 | `1104000` | `9060000` | Actual housing can include non-household financing |
| CP06 | `1106000` | `9080000` | Actual health can include government-financed consumption |
| CP09 | `1109000` | `9110000` | Actual recreation and culture is AIC scope |
| CP10 | `1110000` | `9120000` | Actual education is AIC scope |
| CP12 | `1112000` | `9140000` | Actual miscellaneous goods and services is AIC scope |

The published aggregate `9100000` combines households and NPISHs. It cannot replace strict HFCE control `1100000` under the Armilar Constitution.

The pipeline preserves these alternatives as evidence and rejects them as category inputs. `publication_scope_audit.csv` records the result directly from the live Source 90 inventory.

## Narcotics and net purchases abroad

CP02 is constructed as:

`1102100 alcohol + 1102200 tobacco`

The parent `1102000` is excluded because it contains narcotics. A narcotics value is not inferred. `1102300`, when published, is preserved only for nominal hierarchy audit.

`1113000` net purchases abroad is an HFCE adjustment outside the twelve-category basket. It may be positive or negative. It is preserved when published and excluded from category weights.

## Additivity rule

Nominal expenditures in local currency are used for hierarchy reconciliation because they are additive across headings. PPP-based real expenditures from different headings are not assumed to be additive. The pipeline tests the separate accounting identity:

`nominal expenditure / PPP = PPP-based real expenditure`

This distinction prevents valid ICP data from being rejected through an invalid real-expenditure sum.

## Sufficiency conclusion

The public ICP 2021 release is sufficient to acquire:

- source identity and dimension inventories;
- the 176-economy participation universe;
- PPP, nominal and real expenditure measures for published headings;
- exact CP02 components without narcotics;
- aggregate-only official imputations for the additional 19 economies.

The public release is not sufficient, on the evidence currently published, to construct the Constitution-compliant worldwide economy-by-twelve-category matrix. Five strict HFCE divisions and the strict HFCE control are replaced or omitted at the public 45-heading level. The 19 officially imputed economies also have no public twelve-category allocation.

The GitHub Actions run will verify the live Source 90 inventory rather than relying only on the curated table. If the strict codes are absent, the pipeline emits diagnostics and no final weights. AIC, NPISH and modelled allocations remain excluded.
