# ARMILAR_RESEARCH_CORE_V1 Ratification Proposal

The canonical proposal is `constitution/ARMILAR_RESEARCH_CORE_V1_RATIFICATION_PROPOSAL.json`.

## Status

- Proposal version: `0.1.0`
- Status: `PROPOSED`
- Human approval: required
- Approval status: `NOT_APPROVED`
- Target constitution: `ARMILAR_RESEARCH_CORE_V1`, version `0.3.0-draft`
- Proposed ratified status: `RATIFIED_FOR_ENGINE_DEVELOPMENT`
- Proposed ratified version: `1.0.0-research`
- All release, model, shadow, monetary and world-claim gates remain `false`

This proposal closes the specification of seven methodological decisions. It does not amend the canonical constitution, approve itself, enable publication or start v0.9.6.

## Proposed decisions

1. **Normalization base:** annual average of the twelve monthly 2021 official NSA index levels equals 100.
2. **Official formula:** fixed-weight arithmetic Laspeyres-type aggregation over the complete 60-cell Research Core, with no FX, CP00 or incomplete-period renormalization.
3. **Vintage and revisions:** immutable ARM-O vintages; later revisions appear in ARM-R and never overwrite original releases.
4. **Precision and rounding:** Decimal precision 28, `ROUND_HALF_EVEN`, no intermediate rounding and canonical decimal output scales.
5. **Series semantics:** ARM-O, ARM-R, ARM-H and ARM-L remain separate and may never silently substitute one another.
6. **HFCE/HICP treatment:** the known scope mismatch is accepted only for engine development and internal research, with mandatory disclosure and closed release gates.
7. **Amendment process:** every constitutional change requires a versioned record, impact analysis, tests, canonical hashes and explicit human approval.

## Approval boundary

A later, separate PR may ratify the proposal only after explicit human approval. That PR must update the canonical constitution, its schema, the human-readable rendering, manifests and tests. The checker in this PR is intentionally fail-closed and has no approval or write mode.
