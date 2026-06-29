# Release notes v0.6.0

## Step 2I diagnostic closure

This version closes Step 2I for China, India, Russia, Indonesia and Brazil without admitting unsupported cells.

### Added

- per-cell Step 2I classifications for CP04, CP06, CP09, CP10 and CP12;
- source-attempt audit with official source family, concept, period, sector, transaction, unit and rejection reason fields;
- India methodology gate audit with `CONFIRMED`, `CONTRADICTED`, `AMBIGUOUS` and `NOT_FOUND` states;
- Step 2H exception audit for Belarus CP02, Kuwait CP02, Saudi Arabia CP02, Bonaire and Liberia;
- `step2i_completion_summary.json`;
- `STEP_2I_COMPLETION_REPORT.md`;
- validator support for admissible mixed-provider cells when all concepts, periods, units and provenance match;
- tests for per-cell classification, mixed-provider admissibility, concept/year/unit rejection, deterministic Step 2I summary and fail-closed output.

### Decisions

- China: unavailable for CP04, CP06, CP09, CP10 and CP12. Official NBS evidence remains survey/grouped or not exact S14/P31DC COICOP-HH.
- India: unavailable for CP04, CP06, CP09, CP10 and CP12. MoSPI Statement 5.1 parses and reconciles, but strict S14/P31DC household scope and NPISH exclusion remain unconfirmed.
- Russia: unavailable for CP04, CP06, CP09, CP10 and CP12. No deterministic official structured 2021 Rosstat COICOP-HH table has passed the gates.
- Indonesia: unavailable for CP04, CP06, CP09, CP10 and CP12. Current BPS source families are grouped and cannot be disaggregated without allocation.
- Brazil: unavailable for CP04, CP06, CP09, CP10 and CP12. IBGE product/resource-use sources cannot be converted to exact Armilar categories without many-to-many allocation.

### Gates preserved

`weights_final.csv` remains empty, `monetary_release_allowed=false`, `global_12_category_matrix_complete=false`, and the AIC proxy audit remains `INSUFFICIENT_DIRECT_EVIDENCE`.
