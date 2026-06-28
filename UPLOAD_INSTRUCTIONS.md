# Upload instructions

Use GitHub Desktop for the complete v0.4.0 replacement.

1. Extract the ZIP.
2. Open the local clone of `tomazlucena-crypto/armilar-data-pipeline`.
3. Delete the repository contents except the hidden `.git` directory.
4. Copy the contents inside the extracted `armilar-data-pipeline-v0.4.0` folder into the repository root.
5. Confirm that `.github`, `config`, `constitution`, `docs`, `schemas`, `src` and `tests` are at root level.
6. Commit with `Implement Step 2H0 source feasibility audit v0.4.0`.
7. Push to `main`.

The push starts GitHub Actions automatically.

After completion inspect:

- `public/latest/source_probe_economy_summary.csv`;
- `public/latest/source_probe_candidate_results.csv`;
- `public/latest/economy_gap_priority.csv`;
- `public/latest/proxy_validation_summary.json`;
- `public/latest/step2_summary.json`;
- the `armilar-step2-*` workflow artefact.

`weights_observed_universe.csv` is normalised only inside the complete observed subset. `weights_final.csv` remains the sole worldwide final-output file and must remain empty until its gate passes.
