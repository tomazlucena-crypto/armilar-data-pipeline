# Armilar v0.7.0 patch pack

This pack advances M1 and M2 of the revised plan and creates the isolated contract layer for M4.

## Apply

From any directory:

```bash
python scripts/apply_v070_patch.py /path/to/armilar-data-pipeline
cd /path/to/armilar-data-pipeline
python -m pip install -e .
pytest -q
```

The script refuses to edit `pyproject.toml` unless it finds the reconciled version `0.6.13`, or an already-applied `0.7.0`.

## Smoke test

```bash
armilar-global-weights build \
  --input examples/global_weight_cells.sample.csv \
  --output build/global-weight-sample \
  --release-id ARM-WEIGHTS-GLOBAL-SAMPLE
```

## Production warning

The example contains synthetic values. It exists only to test the contract and output machinery.
