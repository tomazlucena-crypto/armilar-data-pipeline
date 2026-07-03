# Decision proposal: Research Core constitutional amendment process

## Status

`PROPOSED`, awaiting explicit human approval.

## Fixed basket scope

Economies and categories are fixed within a basket version. Adding or removing either is a scope change and cannot be implemented as a source update.

## Change classes

### `EDITORIAL_PATCH`

No numerical, semantic or eligibility change. Requires a new manifest and preserved prior text.

### `EVIDENCE_METADATA_PATCH`

Used when a better source or provenance changes the evidence classification but leaves every numerical weight unchanged.

Requirements:

- basket version may remain unchanged;
- unique `patch_id`;
- before-and-after evidence record;
- new manifest;
- no historical numerical recalculation.

### `NUMERICAL_WEIGHT_PATCH`

Used when a better source changes one or more weights while the economies, categories, formula and base remain unchanged.

Requirements:

- new basket revision;
- prior weights and manifests preserved;
- ARM-O releases never rewritten;
- ARM-R may reconstruct history under the new revision;
- impact report;
- backtest;
- explicit human approval;
- gates remain false by default.

### `BASKET_SCOPE_CHANGE`

Used when an economy or category is added or removed.

Requirements:

- new basket version;
- new series;
- full backtest;
- constitutional amendment;
- preservation of the prior series.

### `CONSTITUTIONAL_METHOD_CHANGE`

Used for changes to the base, formula, conceptual treatment or series semantics.

Requirements:

- new constitution version;
- full impact analysis and backtest;
- new series where comparability breaks;
- preservation of prior versions.

## Proxy-to-exact transition

A proxy cell may improve through one of three routes:

- same numerical weight, better evidence: `EVIDENCE_METADATA_PATCH`;
- changed numerical weight, same scope: `NUMERICAL_WEIGHT_PATCH`;
- new economy or category: `BASKET_SCOPE_CHANGE`.

Silent promotion from proxy to exact is forbidden.

## Mandatory process

Every applicable amendment requires:

1. a dated decision record;
2. affected versions and files;
3. alternatives and rationale;
4. impact analysis;
5. backtest for numerical changes;
6. updated schemas and tests;
7. canonical hashes;
8. explicit human approval;
9. preservation of all previous versions.

Release gates default to false after an amendment and must be approved separately. Emergency authority is limited to freezing publication or operation. It cannot rewrite history or change the formula.
