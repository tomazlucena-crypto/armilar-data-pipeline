# Source audit

## World Bank ICP 2021 Source 90

Role:

- global PPP link;
- direct published HFCE headings;
- official participation and aggregate-imputation controls;
- nominal and PPP-based real expenditure checks.

The global public release contains 45 headings. It directly supports seven Armilar categories after CP02 is decomposed into alcohol and tobacco. It supplies actual-consumption PPPs for the five categories covered by ratified Option B.

It does not publicly supply a twelve-category allocation for the officially imputed non-participating economies.

## OECD Table 5 T501

Role:

- strict household sector S14;
- domestic HFCE transaction P31DC;
- current prices;
- national currency;
- COICOP 1999 twelve-division structure.

This is the preferred nominal source where a complete five-proxy-category set exists.

## UNData SNA Table 3.2

Role:

- official country national accounts;
- individual consumption expenditure of households;
- domestic-market twelve-division structure;
- current national-currency values.

The parser accepts either the standard ZIP/CSV download or a plain CSV response. Country-name variants are mapped explicitly. Non-household subgroups and non-2021 rows are rejected.

## Eurostat `nama_10_cp18`

Role:

- household domestic HFCE;
- current prices in national currency;
- COICOP 2018.

The Armilar CP12 bridge is CP12 plus CP13. The two components must both be present. No incomplete bridge is accepted.

## OECD Table 5A T501

Role:

- COICOP 2018 fallback;
- same household, domestic, current-price and national-currency restrictions.

The same CP12 plus CP13 bridge applies.

## Source hierarchy

1. OECD Table 5 T501
2. UNData SNA Table 3.2
3. Eurostat `nama_10_cp18`
4. OECD Table 5A T501

The hierarchy selects one complete provider per economy. It does not splice categories from multiple providers.

## Known scope limitation

Current national-accounts releases may include revisions made after the ICP 2021 compilation vintage. The pipeline does not conceal this. Proxy-category rows carry a vintage-mismatch quality flag and preserve exact source provenance.
