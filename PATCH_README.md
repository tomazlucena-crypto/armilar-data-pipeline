# Armilar v0.7.0 patch provenance

This file records the origin of the candidate v0.7.0 patch pack. The candidate has been reconciled into the repository through normal review, edits and tests.

Do not execute `scripts/apply_v070_patch.py` blindly against the current repository. It is retained only as provenance for the original candidate patch and must be reconciled with the real remote state before any reuse.

## Smoke test

```powershell
python -m armilar_global_weights.cli build `
  --input examples\global_weight_cells.sample.csv `
  --output build\global-weight-sample `
  --release-id ARM-WEIGHTS-GLOBAL-SAMPLE
```

The example contains synthetic values. It exists only to test the contract and output machinery.
