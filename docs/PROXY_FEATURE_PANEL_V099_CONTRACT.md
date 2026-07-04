# ARMILAR v0.9.9 Proxy Feature Panel Contract

## Status

Research infrastructure only. This contract does not authorise direct index use, ARM-L use, model training, backtest eligibility, shadow production, monetary use, price-coverage claims, concordance approval, stability approval or model-readiness claims.

## Objective

Transform a verified v0.9.8 point-in-time proxy information set into a deterministic monthly feature panel mapped to the 60 cells of `ARMILAR_RESEARCH_CORE_V1`. Preserve the information cutoff, expose missingness, age, first-seen lag and provenance concentration, and compare successive feature panels without promoting any feature to operational use.

## Main bundle outputs

- `feature_values.csv`;
- `cell_coverage.csv`;
- `mapping_audit.csv`;
- `unmapped_observations.csv`;
- `feature_stream_history.csv`;
- `cell_period_coverage.csv`;
- `feature_concordance.csv`;
- `cell_research_diagnostics.csv`;
- `feature_availability_profile.csv`;
- `cell_provenance_concentration.csv`;
- `cell_research_risk_flags.csv`;
- `feature_summary.json`;
- `MANIFEST.sha256`.

## Comparison bundle outputs

- `feature_deltas.csv`;
- `cell_coverage_deltas.csv`;
- `stream_revision_stability.csv`;
- `cell_revision_stability.csv`;
- `comparison_summary.json`;
- `MANIFEST.sha256`.

## Invariants

1. Every source-series mapping is explicit and versioned.
2. Global drivers are broadcast only to Research Core economies.
3. Economy-specific drivers require an explicit geography alias.
4. Weekly observations are averaged by calendar month.
5. Monthly observations remain unchanged.
6. Quarterly observations are assigned only to the quarter-end month.
7. Only exact calendar lags generate period and year-over-year changes.
8. No missing value is imputed or carried forward.
9. No observation available after the cutoff may enter the panel.
10. OOHPI remains sensitivity-only.
11. Coverage counts distinct feature streams, not historical rows.
12. Every feature exposes target-period end, age and completeness.
13. Acquisition freshness and economic observation age remain separate.
14. First-seen lag is measured from period end to the verified Armilar availability timestamp and cannot be treated as an official publication lag.
15. Provenance concentration is descriptive and cannot become a quality weight.
16. Risk flags remain separate booleans; no aggregate risk score is permitted.
17. History diagnostics respect native monthly or quarterly spacing.
18. Cell-period coverage emits explicit `NO_FEATURE` rows over the observed monthly span.
19. Concordance compares only overlapping completed percentage-change observations and remains descriptive.
20. Feature-panel comparison requires ordered cutoffs, an unchanged policy hash and an unchanged basket hash.
21. Revision stability is reported separately by stream variant and Research Core cell.
22. Comparison diagnostics cannot approve, reject, rank or weight features.
23. All release, use and approval gates remain closed.

## Failure states

The build aborts on an invalid upstream bundle, changed policy, overlapping mappings, unknown frequency, duplicate feature identity, unresolved Research Core target, future observation, malformed basket, invalid freshness state, existing output directory or manifest mismatch.

The comparison aborts on invalid feature bundles, reversed or equal cutoffs, changed policy or basket hashes, changed Research Core metadata, duplicate comparison identities, existing output directory or manifest mismatch.

## Acceptance tests

- deterministic replay;
- exact 60-cell coverage grid and weights summing to one;
- exact weekly, monthly and quarterly transformations;
- explicit unmapped audit;
- frequency-aware stream history and gap counts;
- complete cell-month grid over the observed span;
- deterministic cross-source concordance metrics;
- deterministic first-seen lag and provenance-concentration metrics;
- 60-cell descriptive risk flags with no aggregate score;
- deterministic feature-panel comparison and revision-stability reports;
- semantic tamper rejection for every output family;
- all gates false;
- v0.9.8 contract remains independently valid.

## Out of scope

Feature selection, quality weighting, aggregate risk scoring, predictive modelling, automated backtest approval, ARM-L, proxy imputation, price completion, model training, release promotion, API publication and monetary use.
