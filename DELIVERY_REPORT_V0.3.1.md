# Delivery report v0.3.1

## Purpose

Correct the false GitHub Actions failure that occurred after the v0.3.0 ICP acquisition had already completed successfully.

## Root cause

`run_step2()` returned a result containing exact `decimal.Decimal` values. The CLI printed that result using the standard `json.dumps()` encoder without the pipeline's custom serializer. The resulting `TypeError` set exit code 1 after the run bundle and diagnostic outputs had already been generated.

## Correction

- `src/armilar_pipeline/cli.py` now uses `armilar_pipeline.util.json_default`.
- Decimal values remain exact and are printed as strings.
- Path objects are printed as strings.
- Two CLI regression tests cover the former crash and strict-release behaviour.
- Package version and executable configuration are bumped to `0.3.1`.

## Evidence from run 28336070795

The downloaded artefact confirmed:

- no acquisition failures;
- 176 of 176 participating economies mapped;
- 19 officially imputed aggregate-only economies;
- 62 complete participating economies;
- 744 research-weight cells;
- exact weight sum `1.000000000000000000000000`;
- `research_release_allowed=true`;
- global coverage still incomplete.

The next GitHub Actions run should therefore finish successfully and publish the research outputs to `public/latest`. It must continue to leave `weights_final_normalized.csv` empty because the global twelve-category matrix has not yet passed its economic coverage gate.

## Validation

- 30 automated tests passed.
- Clean editable installation passed.
- Python compilation passed.
- Dedicated CLI Decimal regression passed.
- Internal manifest and extracted-ZIP verification are included in the package audit.
