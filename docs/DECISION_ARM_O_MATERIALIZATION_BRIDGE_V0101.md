# Decision: v0.10.1 ARM-O Materialization Bridge

- **Decision:** reuse the verified Eurostat v0.8.7 official vertical snapshot as the first real price input for the ratified v0.9.6 engine.
- **Availability rule:** use first verified Armilar retrieval as a conservative availability bound where historical row-level official publication timestamps are unavailable.
- **Reason:** this preserves raw official evidence and prevents look-ahead without fabricating release dates.
- **Rejected:** treating retrieval time as proven official publication time.
- **Rejected:** using the synthetic validation panel from the v0.9.6 package.
- **Rejected:** extending the engine beyond December 2025 inside this milestone.
- **Consequence:** a real ARM-O run and target archive become materializable, while the backtest remains blocked for lack of future target overlap.

## Compatibility decision: v0.8.7 manifest separators

A real official v0.8.7 Eurostat bundle demonstrated that historical Armilar
manifests were emitted with two separator spaces, while the initial v0.10.1
fixture used one. The verifier therefore recognises exactly one or two ASCII
spaces. Normalising or rewriting the source manifests was rejected because it
would alter the evidence bundle being verified.
