# Decision: v0.10.6 ECOICOP dual-panel materialization runner

## Decision

Create an offline materialization runner before attempting a live provider run.

## Reason

v0.10.5 defined the replay verifier, but did not define how a staged provider
acquisition should be converted into the exact replay artifact.  Running a live
acquisition before this contract exists would create an ambiguous artifact and
would make later backtests harder to audit.

## Consequences

The pipeline now has a deterministic boundary:

```text
staged official bytes and parsed rows
→ materialized external artifact
→ v0.10.5 replay verification
```

The repository still does not contain official bytes and still does not claim
that the dual panel is verified.

## Rejected alternatives

1. Commit a small real provider response in the PR.  Rejected because official
   bytes must be produced by an external non-PR acquisition run.
2. Open the dual-panel verification gate after a fixture replay.  Rejected
   because fixtures do not constitute the official panel.
3. Start the transition backtest immediately.  Rejected because the official
   dual panel has not yet been materialized and verified.

## Next milestone

```text
V0107_RUN_EXTERNAL_DUAL_PANEL_ACQUISITION_AND_ATTACH_VERIFIED_ARTIFACT
```
