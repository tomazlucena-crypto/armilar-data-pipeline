# Next actions after v0.8.7

The immediate objective is a validated vertical chain, not further horizontal expansion:

```text
weights
-> official prices
-> normalisation
-> monthly index
-> historical series
-> backtest
-> economic report
```

## v0.8.6: contracts, reuse and development discipline

Status: complete for contracts V086-C01 through V086-C05.

Deliver v0.8.6 through three small pull requests.

1. **Contracts and roadmap**
   - ratify `docs/ROADMAP_V0.8.6_TO_V1.0.md`;
   - adopt the contract format in `docs/DEVELOPMENT_CONTRACT_STANDARD.md`;
   - validate `config/development_contracts.json`;
   - update the reuse registry and decision log.
2. **Version and SDMX spike** - complete
   - make `pyproject.toml` the only authored version value;
   - expose the installed version through `importlib.metadata`;
   - block divergent config, report and manifest versions in CI;
   - run a narrow `sdmx1` spike against Eurostat and OECD in a network-enabled non-PR job;
   - evaluate `pysdmx` only for requirements that `sdmx1` demonstrably fails.
3. **Property tests and telemetry** - complete
   - add Hypothesis as a test-only dependency;
   - cover mathematical and data-contract invariants;
   - publish development telemetry without treating lines of code as a progress gate.

## Freeze during v0.8.6

Do not add countries, new imputation models, public API work, dashboard work or blockchain work.
Do not modify `public/latest` in pull-request workflows.
Keep `research_release_allowed=false` and `monetary_release_allowed=false`.

## v0.8.7

Status: complete.

The first real, replayable Eurostat HICP vertical series has been built for the fixed declared universe and common interval. The official bytes are preserved under `artifacts/v087/eurostat_snapshot`, the replayed economic outputs are under `artifacts/v087/eurostat_vertical`, and `public/latest` remains unchanged. The release remains research-blocked and monetary-blocked.

## v0.8.8

Status: complete under the declared final-vintage fallback.

The first bounded economic backtest now compares B0 through B3 on a common rolling-origin sample and publishes a quantitative top-three error report. Historical publication vintages, independent CP00 headline data, vintage-aligned FX and imputed economies remain unavailable and are not reconstructed.

## v0.9.0

Use the measured v0.8.8 errors to prioritise the next source and coverage expansion. Preserve repeated provider snapshots so later tests can become genuinely publication-aware. Do not begin nowcast, API or monetary work. Keep both release gates false.
