# ECOICOP v1/v2 backtest protocol v0.10.3

## OBJECTIVE

Define, validate and materialise the complete protocol required to compare the frozen ECOICOP v1 Armilar history with the ECOICOP v2 reconstruction and future current series. The protocol must be fixed before data acquisition in v0.10.4 and before empirical execution in v0.10.5.

## INPUTS

### Normative predecessor

- `config/ecoicop_v2_transition_v0102.json`
- SHA-256: `8ae44a982a2ae88fa6e33c23bb95437dc4f91e0f17896190d2bbbfbaa6ff5557`
- historical commit: `215bba966f2a376d2cd4370297512d440b0dbb7d`
- required checker status: `ECOICOP_V2_TRANSITION_V0102_VALID`

### Executable contracts

- `config/ecoicop_v2_backtest_protocol_v0103.json`
- `config/ecoicop_v1_v2_mapping_candidates_v0103.json`

### Official source roles registered for later acquisition

| Role | Official code or register | Time meaning |
|---|---|---|
| Legacy monthly index | `prc_hicp_midx` | archived or originally published ECOICOP v1 series, 1996-2025 |
| Legacy item weights | `prc_hicp_inw` | ECOICOP v1 weights through 2025 |
| Replacement index and rates | `prc_hicp_minr` | reconstructed ECOICOP v2 back series and current series |
| Replacement item weights | `prc_hicp_iw` | ECOICOP v2 item weights |
| First-published replacement data | `prc_hicp_fpd` | first releases from the ECOICOP v2 regime |
| Classification bridge | Eurostat ShowVoc correspondence | normative item-level mapping evidence |
| Country compilation metadata | `prc_hicp_esms` country files | methods used to construct back series and links |

Registration is metadata only in v0.10.3. No response bytes or observations are acquired by this module.

## OUTPUTS

A deterministic audit contains:

```text
protocol_summary.json
mapping_matrix.csv
strategy_register.csv
metric_register.csv
dataset_register.csv
transformation_dimension_register.csv
completion_gate_register.csv
MANIFEST.sha256
```

Given identical contracts and an explicit `created_at` timestamp, two executions must produce byte-identical outputs.

## INVARIANTS

1. The legacy Armilar panel remains frozen at `2025-12`.
2. The declared empirical universe remains Germany, Spain, France, Italy and Portugal until a later explicit scope decision.
3. The legacy classification has twelve divisions and ECOICOP v2 has thirteen.
4. A matching division code is not proof of unchanged economic content.
5. Every mapping row has `automatic_use_allowed=false`.
6. CP07, CP08 and CP09 remain `MATERIAL_RECLASSIFICATION` until detailed evidence proves a valid bridge.
7. Replacement CP12 and CP13 remain `SPLIT_REQUIRES_EVIDENCE` from legacy CP12.
8. CP13 cannot be dropped, zeroed or silently folded into another category.
9. Classification, reference base, weights, product coverage, retrospective reconstruction and linking method are isolated before combined scenarios are run.
10. Reconstructed back series are never labelled as information available at the historical publication date.
11. All strategies use a common sample for comparisons. Missing cells are reported and cannot be silently renormalised.
12. No metric threshold or code path automatically selects a constitutional strategy.
13. Every release, training, ARM-L, shadow and monetary gate remains false.

## MAPPING STATE MACHINE

### `EXACT_EQUIVALENCE`

Permitted only when the official item-level correspondence proves identical scope and both weight and price-relative reconciliation pass. The v0.10.3 candidate table makes no such automatic claim.

### `DETERMINISTIC_AGGREGATION`

A documented item-level relation may produce the replacement aggregate without discretionary allocation. It still requires weight preservation and price-relative reconciliation.

### `SPLIT_REQUIRES_EVIDENCE`

A legacy division feeds more than one replacement division. Observed item-level weights or a separately ratified constitutional allocation rule are required.

### `MATERIAL_RECLASSIFICATION`

The boundary or content changed materially. Same-code matching is invalid and both a detailed bridge and empirical comparison are required.

### `NO_VALID_AUTOMATIC_MAPPING`

No evidence-backed automatic relation exists. The row remains unresolved.

## CANDIDATE STRATEGIES

### T0: legacy classification without transition

Purpose: comparator preserving the information and classification used through December 2025.

Constraint: cannot extend ARM-O into 2026.

### T1: full ECOICOP v2 adoption

Purpose: preserve the provider-native thirteen-division structure.

Constraint: changes constitutional dimensionality and uses retrospectively reconstructed history.

### T2: constitutional bridge to twelve Armilar categories

Purpose: preserve the twelve-category Armilar interface through an item-level, deterministic bridge.

Constraint: CP07, CP08, CP09, CP12 and CP13 require explicit evidence and potentially a constitutional choice.

### T3: parallel comparable and provider-native series

Purpose: retain a twelve-category comparable Armilar series and a thirteen-division provider-native series with separate lineage.

Constraint: both outputs and their relationship must remain explicit. One cannot silently replace the other.

## METRICS

The protocol predeclares the following required metrics:

- level discontinuity at each link period;
- monthly inflation difference;
- annual inflation difference;
- L1 difference in category contributions;
- RMSE by economy;
- RMSE by category;
- RMSE of the declared world aggregate;
- sensitivity to the link period;
- separate impacts of CP08, CP09 and CP13;
- dependence on later reconstructed back series;
- directly comparable weight share;
- excluded or unresolved weight share.

No numerical acceptance threshold is invented in v0.10.3. Completion means that the metric is calculated on the predeclared common sample, or that a precise ineligibility reason is published. The constitutional decision remains human and evidence-based.

## FAILURE STATES

The implementation fails closed if any of the following occurs:

- a contract contains unknown or missing keys;
- a required dataset role or official code changes;
- the mapping does not cover all thirteen replacement divisions exactly once;
- a legacy division disappears from the candidate relationship;
- a mapping row authorises automatic use;
- CP07, CP08 or CP09 loses its material-reclassification status;
- CP12 or CP13 ceases to be an evidence-dependent split from legacy CP12;
- any release, training or monetary gate becomes true;
- a strategy can be selected automatically;
- an audit output or manifest is altered;
- audit reproduction is not byte-identical;
- live acquisition or an empirical observation enters v0.10.3.

## SUCCESS CONDITION

```text
ECOICOP_V2_BACKTEST_PROTOCOL_V0103_VALID
```

Success proves only that the protocol is complete, deterministic and fail-closed. It does not prove that any transition strategy is economically acceptable.

## STOP CONDITION

Stop v0.10.3 development once:

- the contracts and schemas validate;
- the thirteen-row mapping state machine validates;
- all four strategies and all metrics are materialised deterministically;
- the v0.10.2 checker passes at its historical commit in a detached worktree;
- directed tests and the complete test suite pass;
- CI is green.

Do not acquire the panel or implement transition calculations inside this version.

## FALLBACK CONDITION

If an official classification relation, weight series, country metadata file or time-semantics distinction cannot be preserved in v0.10.4, mark the affected row or comparison ineligible. Do not replace it with a guessed allocation, same-code assumption, later vintage, or silent renormalisation.

## ACCEPTANCE TESTS

- exact strategy set `T0` to `T3`;
- exact replacement coverage `CP01` to `CP13`;
- all automatic mapping flags false;
- all gates false;
- exact registered Eurostat dataset codes;
- zero empirical observations;
- zero live 2026 observations;
- deterministic files and manifest;
- tamper detection;
- detached-worktree verification of v0.10.2;
- no network or process access in the runtime module.

## OUT OF SCOPE

- downloading official observations;
- constructing the dual-classification panel;
- calculating empirical transition results;
- choosing a preferred strategy;
- amending the constitution;
- extending ARM-O into 2026;
- creating 2026 point-in-time targets;
- model training;
- ARM-L, shadow production or monetary use.
