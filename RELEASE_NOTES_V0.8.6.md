# Armilar v0.8.6 development discipline

Version 0.8.6 completes the bounded development-discipline milestone. It makes `pyproject.toml` the only authored project version, derives runtime version strings from installed package metadata, and adds an explicit consistency gate.

The release selects `sdmx1` for the v0.8.7 Eurostat/OECD pilot, with live acquisition limited to a manual non-PR spike and deterministic `NETWORK_BLOCKED` reporting when network access is unavailable. `pysdmx` remains unevaluated because no concrete `sdmx1` gap has been documented.

Hypothesis is added only as a test extra and covers core invariants for weight sums, ordering, duplicate and incomplete grids, no silent renormalisation, no future-observation leakage and FX convention rejection.

Development telemetry is generated as `development_metrics.json` outside `public/latest`, with unavailable metrics represented as `null` plus reasons. CI measures the current `main` test baseline dynamically and uploads telemetry as an artefact.

`research_release_allowed=false` and `monetary_release_allowed=false` remain unchanged.
