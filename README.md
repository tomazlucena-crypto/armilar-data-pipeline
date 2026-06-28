# armilar-data-pipeline

Automated data acquisition and validation pipeline for the Armilar global purchasing-power index.

## What version 0.1 does

- tests DNS resolution, TLS and HTTP reachability from GitHub Actions;
- downloads bounded pilot responses from official sources;
- retries temporary failures;
- restores a clearly labelled last-known-good response when a source is unavailable;
- records provenance, errors, timestamps and SHA-256 hashes;
- creates a reproducible ZIP bundle;
- publishes the latest bundle as a public pre-release named `data-latest`.

This infrastructure removes data acquisition from the local ChatGPT execution environment. It does not yet contain the final detailed ICP 2021 HFCE weight matrix.

## Run locally

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m armilar_pipeline run-all
```

Outputs are written to:

```text
run/diagnostics.json
run/manifest.json
run/raw/
run/SHA256SUMS
artifacts/armilar_data_<timestamp>.zip
```

## Run on GitHub

1. Open the **Actions** tab.
2. Select **Fetch Armilar data**.
3. Select **Run workflow**.
4. Open the completed run and inspect the manifest and diagnostics.
5. Open **Releases** and download **Latest Armilar data bundle**.

The workflow also runs every day at 05:17 UTC. The schedule can be changed later.

## Status interpretation

- `NORMAL`: required sources are fresh.
- `DEGRADED`: at least one response came from cache.
- `FAILED`: a required source has no fresh or cached response.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data flow and current limitations.
