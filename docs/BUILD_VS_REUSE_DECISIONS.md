# Build versus reuse decisions

| Capability | Decision | Armilar responsibility |
|---|---|---|
| SDMX transport and parsing | Pilot `sdmx1` | Dataset selection, source policy and Armilar normalisation |
| Provider discovery | Adapt DBnomics knowledge | Official receipts, licence checks and source priority |
| Storage | Defer DuckDB/Parquet | Current release remains file-based |
| Tabular validation | Defer Pandera | Maintain JSON Schema and semantic validators |
| Property tests | Adopt Hypothesis next | Define economic and mathematical invariants |
| API | Defer FastAPI | Define public response contract first |
| Orchestration | Defer Prefect | Stabilise connector functions first |
| Model registry | Defer MLflow | Establish nowcast baselines first |

## Code that remains custom

- evidence-class semantics;
- strict and global matrix separation;
- complete-grid requirement;
- donor and fallback policy;
- uncertainty propagation;
- replacement and release rules;
- Armilar outputs and manifests.
