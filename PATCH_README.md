# Armilar v0.7.0 corrected patch pack

This pack advances M1 and M2 of the revised plan and creates the isolated contract layer for M4.

## Required base

Apply only over repository version `0.6.13`, which is currently on:

```text
origin/codex/step2h0-remaining-country-audits
```

The public `main` branch is still `0.6.5`. Do not create the v0.7.0 branch from that older base.

## Apply

```powershell
py .\armilar_v070_patch_fixed\scripts\apply_v070_patch.py `
  "C:\Users\tomaz\Downloads\armilar\armilar-data-pipeline"

cd "C:\Users\tomaz\Downloads\armilar\armilar-data-pipeline"
py -m pip install -e .
py -m unittest discover -s tests -v
```

The script updates all runtime version declarations from `0.6.13` to `0.7.0` and adds the new CLI entry point.

## Smoke test

```powershell
armilar-global-weights build `
  --input examples\global_weight_cells.sample.csv `
  --output build\global-weight-sample `
  --release-id ARM-WEIGHTS-GLOBAL-SAMPLE
```

## Production warning

The example contains synthetic values. It exists only to test the contract and output machinery.
