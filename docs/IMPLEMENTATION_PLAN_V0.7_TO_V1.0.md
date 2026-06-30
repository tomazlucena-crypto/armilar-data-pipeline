# Implementation plan from v0.7 to v1.0

## v0.7.0: contracts and isolation

- ratify global experimental construction;
- enforce evidence classes per cell;
- require complete grids and uncertainty;
- register open-source reuse decisions.

## v0.7.1: integration

- connect strict outputs to classes A and B;
- create a canonical evidence-cell staging file;
- ensure country audits can emit partial C evidence without changing strict outputs.

## v0.7.2: imputation baselines

- implement own-economy allocation baseline;
- implement donor selection independent of desired results;
- implement regional and global fallback;
- use leave-one-out validation on observed cells.

## v0.7.3: world weight release

- fill the full economy-category grid;
- publish central and uncertainty weights;
- compare core and global results;
- preserve all methods and sources.

## v0.8.0: monthly price registry

- establish canonical price-series and observation contracts;
- adopt optional `sdmx1` acquisition adapter;
- establish the P1-P5 categorical CPI hierarchy;
- produce deterministic monthly core/global research series from validated inputs;
- keep OECD/Eurostat live pilots and real-world release gated pending network validation.

## v0.9.0: backtest and reconciliation

- compare headline, HFCE and category-level baselines;
- measure imputation error;
- establish release-quality gates from observed performance.

## v1.0.0: research index release

- reproducible world weights;
- validated monthly series;
- documented uncertainty and coverage;
- public API contract prepared;
- still no monetary use without a separate gate.
