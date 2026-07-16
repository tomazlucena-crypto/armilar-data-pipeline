# Decision: v0.10.7 ECOICOP dual-panel external artifact attachment

## Decision

The project will not commit official ECOICOP v1/v2 panel bytes to the code PR.
A future externally materialized artifact must instead be verified by the
v0.10.5 replay verifier and attached through a deterministic descriptor.

## Rationale

The previous milestones separated acquisition contracts, replay verification and
offline materialization.  The next safe step is to create an auditable attachment
handle so a future backtest can reference a verified artifact without silently
mixing data acquisition, code changes and economic interpretation.

## Consequences

- The repository gains the attachment protocol and checker.
- The actual official panel remains external until an explicit acquisition run.
- The verified-panel gate remains closed.
- No transition strategy is selected.
- The next milestone can execute the ECOICOP transition backtest only against a
  verified attached artifact.
