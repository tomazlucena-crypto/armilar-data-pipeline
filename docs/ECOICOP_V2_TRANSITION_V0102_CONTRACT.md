# ECOICOP v2 transition contract v0.10.2

## Objective

Convert the 2026 Eurostat HICP classification break into an executable gate before any extension of the official ARM-O series.

## Fixed predecessor

The existing official input remains:

- dataset: `prc_hicp_midx`;
- classification: `ECOICOP_V1_PRE_2026`;
- categories: `CP01` to `CP12`;
- last permitted period: `2025-12`;
- policy: `config/eurostat_vertical_v087.json`.

## Replacement evidence

Eurostat now disseminates HICP through `prc_hicp_minr` under ECOICOP version 2. The replacement series use the reference base `2025=100`, include thirteen divisions and have harmonised back series for 1996-2025. Eurostat identifies divisions 08 and 09 as extensively revised and introduces division 13.

Official references:

- https://ec.europa.eu/eurostat/documents/272892/11336726/HICP%2Bimprovements%2B-%2BQuestions%2Band%2BAnswers-2026-EN.pdf/dff14a89-9f65-8371-e143-488231305710?t=1766052045691
- https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm
- https://ec.europa.eu/eurostat/web/hicp/information-data
- https://ec.europa.eu/eurostat/databrowser/product/page/PRC_HICP_MIDX

## Invariants

1. Availability of a back series is not treated as proof of semantic equivalence with the frozen basket.
2. Matching division codes do not authorize direct substitution.
3. CP08 and CP09 remain blocked pending an empirical bridge audit.
4. Legacy CP12 cannot be mapped automatically to only one of replacement CP12 or CP13.
5. CP13 cannot be discarded, folded into another division or added to the basket silently.
6. The constitution, weights, historical v0.8.7 snapshot and existing ARM-O vintages remain immutable.
7. Every v0.10.2 gate remains false.
8. The v0.10.1 predecessor is validated at exact commit `43c3bf02216635d41624f56fa0f2951c3d0cfdae` in a detached worktree; its version-specific checker is never executed directly on a v0.10.2 tree.

## Outputs

The audit command writes:

- `ecoicop_v2_transition_matrix.csv`;
- `ecoicop_v2_transition_summary.json`;
- `official_evidence.json`;
- `MANIFEST.sha256`.

The matrix contains one row for each replacement division `CP01` to `CP13`. Every row has `automatic_use_allowed=false`.

## Commands

```text
python -m armilar_backtest.ecoicop_v2_transition_v0102 validate-policy   --policy config/ecoicop_v2_transition_v0102.json

python -m armilar_backtest.ecoicop_v2_transition_v0102 audit   --policy config/ecoicop_v2_transition_v0102.json   --root .   --output <temporary-directory>   --created-at 2026-07-06T00:00:00Z

python -m armilar_backtest.ecoicop_v2_transition_v0102 verify-audit   --policy config/ecoicop_v2_transition_v0102.json   --root .   --audit <temporary-directory>
```

## Success condition

The repository checker also requires:

- `v0101_status=ARM_O_MATERIALIZATION_BRIDGE_V0101_VALID`;
- `v0101_mode=DETACHED_WORKTREE`;
- `v0101_commit=43c3bf02216635d41624f56fa0f2951c3d0cfdae`.

The contract succeeds only with status:

`ECOICOP_V2_TRANSITION_BLOCKED_PENDING_EXPLICIT_DECISION`

and required next decision:

`EXPLICIT_CONSTITUTIONAL_TRANSITION_DECISION_AND_BACKTEST`

## Out of scope

- downloading `prc_hicp_minr`;
- selecting a constitutional transition method;
- modifying the twelve frozen weights;
- creating a thirteen-category basket;
- extending ARM-O or targets into 2026;
- activating research or monetary gates.
