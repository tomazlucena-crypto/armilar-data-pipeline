# Decision: freeze the ECOICOP v2 transition

## Decision

ARMILAR v0.10.2 records the Eurostat ECOICOP version 2 migration as a classification break that requires an explicit constitutional decision and a backtest. No automatic extension of ARM-O beyond December 2025 is authorised.

## Reason

The source family remains official Eurostat HICP, but the published structure changed materially:

- `prc_hicp_midx` was discontinued and replaced by `prc_hicp_minr`;
- the index reference period changed to `2025=100`;
- the division grid changed from twelve to thirteen;
- divisions 08 and 09 were extensively revised;
- the old miscellaneous division no longer has a one-to-one successor because replacement divisions 12 and 13 are separate;
- harmonised ECOICOP v2 back series exist for 1996-2025.

The back series make a future bridge testable. They do not by themselves authorise a silent change to the frozen Research Core.

## Alternatives rejected

### Append 2026 values by matching the old division codes

Rejected because matching labels or codes do not prove unchanged item content.

### Drop CP13 and retain twelve divisions

Rejected because it would remove published consumption scope without a constitutional rule or impact analysis.

### Combine replacement CP12 and CP13 automatically

Rejected because the frozen weights were constructed for the legacy category system. Summing price indices without compatible weights would not preserve the original economic object.

### Replace the complete history immediately with the ECOICOP v2 back series

Rejected as an automatic action. This is a candidate transition method that must be evaluated against the preserved v0.8.7 history and the point-in-time protocol.

## Consequences

The next development block must acquire and preserve a versioned `prc_hicp_minr` snapshot, then compare candidate transition methods over the overlapping 2021-2025 period. Any selected method must pass an explicit constitutional amendment, impact analysis and point-in-time backtest before it may extend ARM-O.

All gates remain closed. The v0.10.1 bridge remains a frozen predecessor and is validated in a detached worktree at commit `43c3bf02216635d41624f56fa0f2951c3d0cfdae`; its checker is not run against the v0.10.2 versioned tree.
