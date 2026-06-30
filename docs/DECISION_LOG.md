# Decision log

## 2026-06-30: vertical delivery before further expansion

**Decision:** Complete a real weights-to-report chain before adding countries or complex models.

**Reason:** Horizontal expansion has increased infrastructure without yet forcing an early economic demonstration.

**Rejected alternatives:** Continue country-by-country integration; begin API or nowcast work immediately.

**Consequence:** New national adapters remain frozen through the v0.8.7 vertical-series gate.

## 2026-06-30: executable contracts before material code

**Decision:** Every material capability requires objective, inputs, outputs, invariants, failure states, success, stop, fallback, acceptance tests and out-of-scope declarations.

**Reason:** Bounded contracts reduce redesign and agent drift.

**Consequence:** `config/development_contracts.json` becomes a CI-validated planning input.

## 2026-06-30: pyproject as the sole authored version

**Decision:** The project version is authored only in `pyproject.toml`; code reads installed metadata and CI checks generated repetitions.

**Reason:** Prior releases duplicated version values across config, reports and branch names.

**Consequence:** v0.8.6 must remove or generate independent version constants.

## 2026-06-30: sdmx1 first, pysdmx only as a challenger

**Decision:** Select `sdmx1` for the v0.8.7 Eurostat and OECD pilot. Evaluate `pysdmx` only against a recorded gap.

**Reason:** Installing parallel SDMX stacks without a concrete need increases maintenance cost.

**Consequence:** `pysdmx` is not installed in v0.8.6. If live network is blocked, the spike records `NETWORK_BLOCKED` rather than inventing acquisition evidence.

## 2026-06-30: deterministic development telemetry

**Decision:** Generate `development_metrics.json` with standard-library code and publish it as a CI artefact outside `public/latest`.

**Reason:** Development metrics are useful for review but must not become economic progress gates.

**Consequence:** Unknown metrics are represented as `null` with reasons, and test-count regression is measured against the current `main` baseline rather than a hard-coded historical value.

## 2026-06-30: property-based testing is test-only infrastructure

**Decision:** Add Hypothesis in a test extra, not as a runtime dependency.

**Reason:** It is useful for mathematical and malformed-grid invariants and does not belong in production execution.

**Consequence:** The full deterministic unit suite remains mandatory.

## 2026-06-30: measured test baseline

**Decision:** Do not hard-code the historical count of 221 tests as a permanent gate.

**Reason:** The current `main` may already contain a different number. A fixed stale count can pass a regression or block valid additions.

**Consequence:** CI records the current-main baseline and rejects unexplained reductions.
