# Next actions after v0.8.5

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

Build the first real, replayable Eurostat HICP vertical series for a fixed declared universe and common interval. No synthetic fixture may be described as an official live release.

## v0.8.8

Run the first minimum economic backtest and identify the three largest measured error sources before expanding coverage or model complexity.

`weights_final.csv` remains unused and monetary release remains separately gated.
