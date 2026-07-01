# Armilar v0.9.5 to v1.1.0 Roadmap

## v0.9.5 Constitution and contracts

- Objective: declare Research Core scope and road rules.
- Main outputs: scope document, decisions log, roadmap.
- Dependencies: validated v0.9.4 baseline.
- Completion: scope, gates and pending decisions are explicit.
- Out of scope: engine changes, live work, new countries.

## v0.9.6 Official engine and temporal storage

- Objective: build the official Research Core engine.
- Main outputs: deterministic engine, temporal storage contract, initial historical store.
- Dependencies: v0.9.5 constitution.
- Completion: engine and storage are reproducible on the fixed universe.
- Out of scope: public API, dashboard, proxy expansion.

## v0.9.7 Proxy registry and acquisition

- Objective: register and acquire proxy evidence.
- Main outputs: proxy registry, acquisition receipts, validation notes.
- Dependencies: v0.9.6 engine and storage.
- Completion: proxies are classified and traceable.
- Out of scope: live estimator, production shadow.

## v0.9.8 Minimum live estimator and uncertainty

- Objective: add a minimal live estimator.
- Main outputs: live estimate, uncertainty summaries, anchor logic.
- Dependencies: v0.9.7 proxies.
- Completion: live estimate works without replacing the official series.
- Out of scope: reconciliation machine, public API.

## v0.9.9 Reconciliation, quality and state machine

- Objective: reconcile live and official series with explicit states.
- Main outputs: reconciliation rules, quality checks, state machine.
- Dependencies: v0.9.8 estimator.
- Completion: states are explicit and fail closed.
- Out of scope: operational UI and broad optimisation.

## v0.10.0 Continuous operation

- Objective: run the system continuously in a controlled mode.
- Main outputs: scheduled operation, monitoring reports.
- Dependencies: v0.9.9 state machine.
- Completion: continuous runs remain deterministic and auditable.
- Out of scope: external API, shadow dashboard.

## v0.10.1 Internal API

- Objective: expose an internal interface for controlled use.
- Main outputs: internal API contract and handlers.
- Dependencies: v0.10.0 operation.
- Completion: internal consumers can query without side effects.
- Out of scope: public API, open access.

## v0.10.2 Shadow dashboard

- Objective: provide a read-only shadow dashboard.
- Main outputs: visual diagnostics and summary views.
- Dependencies: v0.10.1 API.
- Completion: dashboard reflects the same audited data.
- Out of scope: publication, promotion.

## v0.11.0 Shadow production candidate

- Objective: harden the system for shadow production.
- Main outputs: candidate release, operational checks, readiness report.
- Dependencies: v0.10.2 dashboard.
- Completion: shadow production readiness is demonstrated.
- Out of scope: production claims, policy claims.

## v0.12.0+ Methodological optimisation

- Objective: improve methodology after shadow production exists.
- Main outputs: optimisation proposals, backtests, revised decisions.
- Dependencies: v0.11.0 candidate.
- Completion: any methodological change is separately justified and tested.
- Out of scope: ad hoc tuning without evidence.
