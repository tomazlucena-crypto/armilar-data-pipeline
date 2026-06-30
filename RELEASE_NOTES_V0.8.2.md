# Armilar v0.8.2: Eurostat category pilot engine

## Scope

Version 0.8.2 adds the deterministic engine for the first fixed-universe
Eurostat HICP category pilot.

The pilot:

- accepts only Eurostat P1 official category observations;
- requires CP01 to CP12 for every admitted economy;
- fixes the economy and category universe for the whole published interval;
- starts at 2021-01 by default;
- normalises covered world weights once, when the universe is resolved;
- publishes covered and external world weight before normalisation;
- rejects incomplete months instead of renormalising them;
- keeps current FX outside the inflation index;
- remains experimental and blocked from monetary use.

## Outputs

- `price_universe.json`
- `monthly_index.csv`
- `index_contributions.csv`
- `price_evidence_coverage.csv`
- `monthly_index_summary.json`
- `rejected_periods.csv`
- `MANIFEST.sha256`

## Important limitation

This commit implements and tests the production engine. It does not claim that
a real official Eurostat snapshot has already been captured. The v0.8.1 live
path remains disabled pending an official response parser and DSD snapshot.

A real v0.8.2 pilot release therefore requires a separately acquired,
hash-preserved Eurostat P1 dataset and a compatible `world_weight` input. Pull
request checks remain deterministic and network-free.

`research_release_allowed=false` and `monetary_release_allowed=false`.

## Canonical consumption classification

The pilot output layer now uses `ARMILAR_CONSUMPTION_CLASSIFICATION` version `1.0.0`. Nine Armilar categories are exact weighted aggregates of the twelve ECOICOP V1 source divisions. Source-level observations and contributions remain available, and the canonical aggregation is tested to leave the total index unchanged. ECOICOP V2 remains provisional until overlap validation is completed.
