# Decision: ECOICOP transition backtest execution engine v0.10.9

## Decision

Adopt a fail-closed execution-result contract for the ECOICOP v1/v2 transition backtest before running it on a real verified external panel.

## Reason

The previous milestones established the protocol, replay verifier, materializer, attachment protocol and readiness runner. The project still must avoid claiming empirical results without a real external verified panel. This version therefore validates the computation and reporting contract with a fixture and keeps all gates closed.

## Consequences

- The system can validate the shape of a transition backtest result before any real run.
- A result must cover all candidate strategies and all declared metrics.
- Fixture results cannot be interpreted economically.
- A later milestone must run the real empirical backtest on a verified external panel before any strategy can be selected.
