# Build versus reuse decisions

| Capability | Decision | Trigger or phase | Armilar responsibility |
|---|---|---|---|
| SDMX transport and parsing | `ADOPT_PILOT` sdmx1 | v0.8.6 | Dataset selection, source policy, receipts and normalisation |
| SDMX challenger | `EVALUATE_CHALLENGER` pysdmx | Only if the sdmx1 spike records an unmet requirement | Same contracts and provider evidence |
| Provider discovery | `ADAPT_REFERENCE_ONLY` DBnomics | Source discovery | Official receipts, licence checks and source priority |
| Property tests | `ADOPT` Hypothesis | v0.8.6 test extra | Economic and mathematical invariants |
| Analytical storage | `DEFER` DuckDB/Parquet | First material multi-vintage bottleneck | Public output contracts and deterministic manifests |
| Tabular validation | `DEFER` Pandera | Stable real price panel | Armilar semantic checks |
| Backtest utilities | `ADOPT` scikit-learn | v0.8.8 | Publication-aware vintages and economic comparisons |
| State-space models | `DEFER_TO_V0.10` statsmodels | Validated monthly baseline | Model restrictions and reconciliation |
| Forecast framework | `EVALUATE_CHALLENGER` sktime | Several comparable models | Acceptance gates and no-look-ahead logic |
| Service contracts | `DEFER` Pydantic | Stable public API schema | Economic response semantics |
| Public API | `DEFER` FastAPI | Validated research series | Versioning, quality and provenance fields |
| Orchestration | `DEFER` Prefect | Several production connectors | Fail-closed states and publication policy |
| Model registry | `DEFER` MLflow | Multiple promoted models | Monetary separation and approval gates |
| Standard lineage | `DEFER` OpenLineage | Existing provenance becomes insufficient | Hashes and economic lineage |
| Structured logging | `DEFER` structlog | Public operation | Event taxonomy and redaction policy |

## Code that remains custom

- economic basket and classification semantics;
- strict core and experimental global separation;
- P1-P5 evidence hierarchy;
- donor, fallback and uncertainty policy;
- price and FX methodology;
- release, freeze and recovery rules;
- manifests and revision preservation;
- research and monetary gates.
