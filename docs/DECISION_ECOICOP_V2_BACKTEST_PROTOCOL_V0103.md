# Decision: ECOICOP v1/v2 backtest protocol v0.10.3

## Decision

Adopt the executable comparability and backtest protocol defined by:

- `config/ecoicop_v2_backtest_protocol_v0103.json`;
- `config/ecoicop_v1_v2_mapping_candidates_v0103.json`.

This decision authorises only the design of the evidence panel and future empirical comparison. It does not choose a classification transition.

## Evidence established before this decision

Eurostat applies ECOICOP version 2 from January 2026, publishes thirteen divisions, reconstructs back series for 1996-2025, and re-references the index to `2025=100`. Eurostat also warns that classification and compilation changes can produce breaks, and records monthly or annual linking plus possible documented level-shift treatment. The official correspondence and country compilation metadata are therefore required inputs, rather than optional explanatory material.

The official database restructuring identifies:

- `prc_hicp_midx` to `prc_hicp_minr` for monthly indices and rates;
- `prc_hicp_inw` to `prc_hicp_iw` for item weights;
- `prc_hicp_fp` to `prc_hicp_fpd` for first-released data.

## Alternatives rejected

### Treat same division codes as equivalent

Rejected because codes alone do not prove identical economic scope. CP07 changed boundary, CP08 and CP09 were extensively revised, and old CP12 is distributed across new CP12 and CP13.

### Drop CP13

Rejected because this would remove an official consumption division and silently alter coverage.

### Adopt the reconstructed ECOICOP v2 back series as the historical Armilar record

Rejected because a reconstruction published later is not equivalent to the information available at each historical date.

### Select a strategy by a single numerical threshold

Rejected because the constitutional choice involves comparability, dimensionality, historical integrity and operational cost. The empirical report must expose trade-offs and unresolved uncertainty.

## Consequences

The next version may acquire and preserve the official dual-classification evidence under the v0.10.3 contract. The subsequent backtest must evaluate all four candidate strategies on a common sample and publish every predeclared metric.

No transition follows automatically from protocol validation or from completion of the future backtest.

## Gate state

```text
classification_transition_ratified=false
arm_o_2026_extension_allowed=false
backtest_execution_claim_allowed=false
model_training_allowed=false
arm_l_use_allowed=false
shadow_production_allowed=false
research_release_allowed=false
monetary_use_allowed=false
```

## Next authorised milestone

```text
V0104_DUAL_PANEL_ACQUISITION_AND_VERIFICATION
```
