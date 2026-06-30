# Amendment 3: Armilar Canonical Consumption Classification

## Status

Experimental research amendment. It does not authorise research release or monetary use.

## Purpose

The Armilar Index shall use a stable canonical consumption classification between
source classifications and the published index. Source codes such as COICOP,
ECOICOP, ICP and national classifications remain evidence inputs rather than the
constitutional category system of the index.

## Canonical classification

`ARMILAR_CONSUMPTION_CLASSIFICATION` version `1.0.0` contains nine categories:

1. ARM01 Food and non-alcoholic beverages;
2. ARM02 Alcoholic beverages and tobacco;
3. ARM03 Clothing and footwear;
4. ARM04 Housing and household operation;
5. ARM05 Health;
6. ARM06 Mobility and connectivity;
7. ARM07 Recreation, culture and education;
8. ARM08 Hospitality;
9. ARM09 Personal, social and financial services.

Narcotics remain excluded. This amendment does not alter any other constitutional
scope decision.

## Mapping rules

Every source-classification mapping shall publish:

- source provider;
- source classification and version;
- source code and label;
- target Armilar category;
- mapping type;
- effective interval;
- strict-pilot admissibility;
- bridge status;
- mapping and classification hashes.

The strict pilot may use only:

- `EXACT_ONE_TO_ONE`;
- `EXACT_MERGE`.

A split is admissible only when official lower-level weights make it deterministic.
An estimated split must be identified as estimated and is excluded from the strict
pilot. Unmapped source content fails closed.

## Preservation of detail

Raw and normalised source categories shall be preserved. Canonical aggregation is
an additional layer. It shall never overwrite source codes, receipts, hashes or
source-level contributions.

## Index invariance

For exact merges, the total index shall be calculated from source-category fixed
weights and price relatives. Canonical category results are weighted sums of those
source contributions. The canonical aggregation must not change the total index.

## Classification revisions

A new source-classification version requires a new mapping version and a bridge
audit. A historical back series may be used for validation, but no revised
classification may be spliced into the active series without:

1. complete source-code coverage;
2. explicit mapping status;
3. overlap comparison against the previous source version;
4. published divergence metrics;
5. a ratified effective date;
6. new hashes and manifests.

The ECOICOP version 2 mapping is provisional. It is not admissible in the strict
v0.8.2 pilot until the official back series has been validated.

## Scope limitation

Eurostat HICP prices represent household final monetary consumption expenditure,
while the Armilar 2021 weight target is HFCE in PPP terms. This mismatch, including
imputed-rent coverage, must remain explicit in pilot outputs and prevents release.

## Release flags

`research_release_allowed=false`

`monetary_release_allowed=false`
