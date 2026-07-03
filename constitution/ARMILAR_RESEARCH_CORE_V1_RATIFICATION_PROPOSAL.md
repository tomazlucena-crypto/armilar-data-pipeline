# ARMILAR_RESEARCH_CORE_V1 Ratification Proposal

The canonical proposal is `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json`.

## Status

- Proposal version: `0.2.0`
- Status: `PROPOSED`
- Human approval: required
- Approval status: `NOT_APPROVED`
- Target constitution: `ARMILAR_RESEARCH_CORE_V1`, version `0.3.0-draft`
- Proposed ratified status: `RATIFIED_FOR_ENGINE_DEVELOPMENT`
- Proposed ratified version: `1.0.0-research`
- All release, model, shadow, monetary and world-claim gates remain `false`

This proposal closes the specification of seven methodological decisions. It does not amend the canonical constitution, approve itself, enable publication or start v0.9.6.

## Clarifications added in version 0.2.0

1. The official formula is a fixed-weight arithmetic Laspeyres-type index using 2021 real-expenditure weights converted to a common comparable unit through ICP PPPs.
2. The basket contains 25 AIC-PPP proxy cells, concentrated in CP04, CP06, CP09, CP10 and CP12 across all five economies. They represent `0.589731681350816432896035605` of fixed-universe weight.
3. An OOH sensitivity analysis is mandatory before external research release or shadow production. It is not represented as a complete measurement of the HFCE/HICP gap.
4. ARM-L requires an immutable information set, versioned per-cell source registry, explicit cutoffs, raw snapshots, model version, quality state and uncertainty.
5. The concrete ARM-L publication clock belongs to a separately approved operational schedule contract rather than the constitution.
6. Economies and categories are fixed within a basket version. Adding or removing either creates a new basket version and a new series.
7. Proxy-to-exact improvements are classified as evidence metadata patches, numerical weight patches or basket scope changes according to their numerical and scope effects.

## Proposed decisions

1. **Normalization base:** annual average of the twelve monthly 2021 official NSA index levels equals 100.
2. **Official formula:** fixed-weight arithmetic Laspeyres-type aggregation with PPP-adjusted 2021 expenditure weights, explicit proxy exceptions, no FX, no CP00 and no incomplete-period renormalization.
3. **Vintage and revisions:** immutable ARM-O vintages; later revisions appear in ARM-R and never overwrite original releases.
4. **Precision and rounding:** Decimal precision 28, `ROUND_HALF_EVEN`, no intermediate rounding and canonical decimal output scales.
5. **Series semantics:** ARM-O, ARM-R, ARM-H and ARM-L remain separate. ARM-L is reproducible from an immutable cutoff-bound information set.
6. **HFCE/HICP treatment:** the scope mismatch and proxy exposure are material research limitations, with mandatory disclosure and OOH sensitivity analysis.
7. **Amendment process:** every change is classified, versioned, hashed and approved, with prior outputs preserved.

## Approval boundary

A later, separate PR may ratify the proposal only after explicit human approval. That PR must update the canonical constitution, its schema, the human-readable rendering, manifests and tests.

The checker in this PR is intentionally fail-closed and has no approval or write mode, except for deterministic proposal-manifest regeneration.
