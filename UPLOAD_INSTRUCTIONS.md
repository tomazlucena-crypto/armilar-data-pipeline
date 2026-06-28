# Upload instructions

1. Extract the ZIP locally.
2. In the GitHub repository, upload the contents of the extracted folder, preserving directories.
3. Replace files with the same names.
4. Commit directly to `main`.
5. Open **Actions**, select **Build ICP 2021 Armilar matrix**, then choose **Run workflow**.
6. After completion, inspect:
   - `public/latest/manifest.json`
   - `public/latest/diagnostics.json`
   - `public/latest/STEP2_REPORT.md`
   - the `armilar-step2-*` workflow artifact.

Do not copy the extracted parent folder itself into the repository. Upload its contents so that `.github`, `config`, `src` and `tests` remain at repository root.
