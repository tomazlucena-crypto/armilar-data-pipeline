# Incident report: GitHub Actions run 28336070795

## Finding

The ICP 2021 acquisition and Step 2 calculation completed successfully. The run produced:

- 176 of 176 participating economies mapped;
- 19 officially imputed aggregate-only economies identified;
- 62 participating economies with complete twelve-category matrices;
- 744 observed research-weight cells;
- exact research-weight sum of `1.000000000000000000000000`;
- no source acquisition failures;
- a complete 4.62 MB diagnostic artefact.

## Cause of the red GitHub Actions status

After `run_step2()` returned successfully, the CLI attempted to print the returned Python object with the standard `json.dumps()` encoder. The object contained `decimal.Decimal` values used to preserve exact weights and tolerances. The standard encoder cannot serialize `Decimal`, so the process exited with an unhandled `TypeError` after all outputs and the ZIP bundle had already been written.

This was an execution-wrapper defect. It was not a failure of the World Bank, OECD, UNData or Eurostat acquisition and did not invalidate the generated matrices.

## Correction in v0.3.1

The CLI now uses the same audited JSON serializer as the file-output layer. `Decimal` values are emitted as exact decimal strings and `Path` values as strings. Two regression tests reproduce the former failure and verify the strict-release exit code separately.

A normal research run now exits with code 0 and allows GitHub Actions to publish `public/latest`. Global-scope incompleteness remains visible in `step2_summary.json` and does not masquerade as a technical execution failure.
