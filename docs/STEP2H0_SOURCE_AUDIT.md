# Step 2H0 official-source feasibility audit

## Purpose

The audit determines whether an official source can plausibly yield 2021 household final consumption expenditure by the twelve Armilar categories without modelled allocation.

A successful HTTP response is insufficient. The resource must be an actual dataset and must satisfy the economic concept, period, classification, price, currency and institutional-sector gates.

## Candidate classes

- `A_CANDIDATE`: an exact official S14/P31 dataset appears available;
- `B_CANDIDATE`: an exact official derivation may be possible without estimated shares;
- `C_ONLY`: the source requires survey shares, temporal interpolation, grouped-category allocation or another experimental transformation;
- `D_UNAVAILABLE`: provisional probe class only. It does not prove definitive unavailability.

## Methodological states

- `EXACT_OFFICIAL`
- `OFFICIAL_DERIVED_NO_ALLOCATION`
- `OFFICIAL_EXPERIMENTAL_ALLOCATION`
- `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`
- `ACCESS_BLOCKED`
- `SOURCE_NOT_MACHINE_READABLE`
- `CONCEPT_AMBIGUOUS`
- `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`

The final state is allowed only when all five core official-source families have documentary attempts and none remains blocked or uninvestigated.

## Registry scope

`config/source_probe_candidates.csv` contains 29 concrete official resources across ten economies. Two economies have a declared B candidate, India and Russia. The remaining eight have Class C evidence at best. There is no proven A candidate.

These declarations are hypotheses tied to named resources. Runtime acquisition may downgrade them. A landing page can locate a database but can never count as the database result.

## Family coverage

`source_probe_family_coverage.csv` emits one row per economy and family, including zero-candidate families. It distinguishes:

- `DATASET_ACQUIRED`;
- `DISCOVERY_ONLY`;
- `SOURCE_NOT_MACHINE_READABLE`;
- `ACCESS_BLOCKED`;
- `ATTEMPTED_NO_ADMISSIBLE_DATASET`;
- `NOT_INVESTIGATED`.

## Evidence controls

Each acquired candidate records the requested and final URL, timestamp, HTTP status, content type, bytes, signature, markers, file path and SHA-256. Each failed candidate records the attempt errors in a JSON receipt. No hash is emitted without content.

No source-probe row enters the weight matrix.
