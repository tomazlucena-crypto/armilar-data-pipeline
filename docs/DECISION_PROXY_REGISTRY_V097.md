# Decision: registry and acquisition before ARM-L

Date: 2026-07-03

## Decision

Build a closed source registry, immutable snapshots and deterministic replay before evaluating any proxy for ARM-L.

## Reason

Proxy acquisition, information-set eligibility and model usefulness are separate questions. Combining them would allow revised histories or poorly timestamped datasets to leak into a release-time backtest.

## Alternatives rejected

- Feeding current proxy histories directly into the index.
- Treating the retrieval timestamp as the historical publication timestamp.
- Enabling model training merely because a source is official.
- Scraping commercial prices before official-source coverage is exhausted.

## Consequences

v0.9.7 can collect research evidence, but all use gates remain closed. A later milestone must preserve release-time archives, define mappings, run out-of-sample tests and obtain separate promotion approval.

## Evidence

The four registered providers publish official datasets relevant to the selected domains, while their current downloadable histories do not by themselves establish a complete first-published information set.

## Code version

0.9.7
