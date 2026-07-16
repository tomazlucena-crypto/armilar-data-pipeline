# ECOICOP dual-panel materialization contract v0.10.6

## Objective

v0.10.6 converts the v0.10.5 replay verifier into an offline materialization
runner.  The runner accepts a staging directory containing already acquired
provider bytes and parsed rows.  It materializes the external replay artifact
required by v0.10.5 and immediately verifies that artifact through the v0.10.5
replay verifier.

## Inputs

The input is a staging directory outside the repository with:

```text
STAGING_MANIFEST.sha256
staged_receipts.csv
staged_observations.csv
staged_coverage.csv
provider raw files referenced by staged_receipts.csv
```

Every raw file must be addressed by a safe path relative to the staging root.
The raw SHA-256 and byte count must match the bytes on disk.

## Outputs

The materialized external artifact contains:

```text
PANEL_MANIFEST.sha256
raw_receipts.csv
normalised_observations.csv
dual_panel_coverage.csv
dual_panel_lineage.csv
panel_summary.json
raw/<copied provider bytes>
```

The artifact must pass:

```text
ECOICOP_V1_V2_DUAL_PANEL_EXTERNAL_ARTIFACT_REPLAY_VALID
```

from the v0.10.5 replay verifier.

## Invariants

- No network acquisition is performed by this code PR.
- No official provider bytes are committed to the repository.
- `public/latest` is not modified.
- 2026 observations remain refused before a constitutional transition.
- No transition strategy is selected.
- No empirical transition backtest is executed.
- No gate is opened.
- Lineage may not rewrite history.

## Failure states

- staging manifest mismatch;
- raw receipt hash mismatch;
- observation without receipt;
- observed coverage without observation;
- non-observed coverage pointing to an observation;
- live 2026 observation before ratification;
- replay artifact rejected by the v0.10.5 verifier;
- premature backtest or strategy selection.

## Success condition

The v0.10.6 checker validates the policy, the v0.10.5 predecessor, a staged
fixture, the deterministic materialized artifact and the replay verification.

## Stop condition

Stop before live acquisition, real official byte verification, backtest
execution, constitutional ratification or ARM-O 2026 extension.
