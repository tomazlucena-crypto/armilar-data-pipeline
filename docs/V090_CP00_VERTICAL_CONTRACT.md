# v0.9.0 CP00 vertical contract

## Objective

Complete the existing five-economy Eurostat vertical chain with an independently acquired official CP00 headline panel and use it to make B0 and B1 genuine headline baselines.

## Inputs

- v0.8.7 official CP01-CP12 replay output for DEU, ESP, FRA, ITA and PRT.
- A separate Eurostat `prc_hicp_midx`, `M`, `I15`, `CP00` snapshot for the same five economies and 2021-01 to 2025-12.
- The v0.8.8 backtest contract and cases.

## Outputs

- Immutable CP00 raw snapshot and SHA-256 manifest.
- 300 normalized official headline observations.
- B0 equal-country official CP00 index.
- B1 Armilar-economy-weighted official CP00 index.
- B0-B3 backtest on an identical common sample.
- Construction comparison and economic report.

## Invariants

- CP01-CP12 prices never construct B0 or B1.
- B2 and B3 definitions remain unchanged from v0.8.8.
- The v0.8.9 rejected challenger is not imported, copied or promoted.
- Vintage mode remains `FINAL_VINTAGE_PSEUDO_REAL_TIME`.
- `publication_aware=false`.
- `research_release_allowed=false`.
- `monetary_release_allowed=false`.
- No command writes to `public/latest`.

## Failure states

- Missing or duplicate CP00 observations.
- Snapshot or output hash mismatch.
- Economy, period or universe mismatch between headline and category panels.
- Headline evidence not official.
- Category prices used in headline construction.
- Release gate weakened.
- Rejected v0.8.9 code or output reused.

## Success condition

The separate official CP00 snapshot replays deterministically, B0 and B1 are computed exclusively from CP00, all B0-B3 cases share the same sample, and the report states the final-vintage limitation and keeps both release gates false.

## Stop condition

Do not add countries, a new completion model, publication-lag simulation, FX, API or dashboard work in this milestone.
