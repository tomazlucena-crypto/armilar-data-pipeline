# Upload instructions

Use GitHub Desktop for this complete replacement.

1. Extract the ZIP.
2. Open the local clone of `tomazlucena-crypto/armilar-data-pipeline`.
3. Delete the repository contents except the hidden `.git` directory.
4. Copy the contents inside the extracted v0.3.1 folder into the repository root.
5. Confirm that `.github`, `config`, `constitution`, `docs`, `schemas`, `src` and `tests` are at root level.
6. Commit with a message such as `Fix Step 2 CLI publication pipeline v0.3.1`.
7. Push to `main`.

The push starts GitHub Actions automatically. Do not manually start a second run unless the automatic run fails to appear.

After completion inspect:

- `public/latest/step2_summary.json`
- `public/latest/STEP2_REPORT.md`
- `public/latest/coverage_report.csv`
- `public/latest/weights_research_observed_normalized.csv`
- `public/latest/weights_final_normalized.csv`
- the `armilar-step2-*` workflow artifact.

Do not treat the research matrix as the worldwide final matrix unless `global_12_category_matrix_complete=true`.
