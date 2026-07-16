# Decision — ECOICOP transition backtest runner v0.10.8

## Decision

Create a fail-closed transition backtest runner before executing the empirical ECOICOP v1/v2 transition backtest.

## Reason

The project has contracts for acquisition, replay, materialization and attachment. The next safe step is to define the execution boundary: a backtest may only proceed from a verified external attachment and the declared v0.10.3 strategy/metric set.

## Consequences

The PR adds code, schemas, configuration and tests for the runner, but still forbids empirical execution and strategy selection. The next milestone may run the empirical transition backtest only with a verified external panel artifact.
