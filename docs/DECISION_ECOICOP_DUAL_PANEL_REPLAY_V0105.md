# Decision: require external dual-panel replay before transition backtest

## Decision

ARMILAR v0.10.5 introduces a verifier for externally materialised ECOICOP v1/v2
panel artifacts and refuses to execute the economic transition backtest until a
panel artifact passes replay validation.

## Rationale

The v0.10.4 milestone defined the acquisition contract.  Executing a backtest
without first proving raw-byte provenance, coverage and lineage would create a
false empirical claim.  The replay verifier separates the code PR from the
non-PR live acquisition run and preserves the fail-closed boundary.

## Consequences

- the dual-panel verified gate remains closed;
- official bytes must be acquired outside code PRs;
- backtest execution remains blocked;
- transition strategy selection remains blocked;
- the next milestone is materialising and verifying the external panel artifact.
