# ARMILAR v0.10.1 ARM-O Materialization Bridge Contract

## Objective

Create a verified and replayable bridge from the official Eurostat v0.8.7 vertical snapshot to:

1. the canonical v0.9.6 observation contract;
2. one immutable ARM-O run;
3. one append-only ledger entry;
4. one v0.10.0 target archive.

## Availability semantics

The Eurostat v0.8.7 snapshot records the time at which Armilar retrieved the official provider bytes. It does not prove a row-level official publication timestamp for every historical observation.

Accordingly, every converted observation uses:

`FIRST_VERIFIED_ARMILAR_RETRIEVAL_NOT_OFFICIAL_PUBLICATION_TIME`

The bridge places the verified retrieval timestamp in the legacy v0.9.6 `published_at` field only as a conservative availability bound. This does not authorise any claim about the provider's original publication time.

## Inputs

- official Eurostat v0.8.7 snapshot with exact raw bytes and hashes;
- deterministic v0.8.7 vertical output replayed from that snapshot;
- ratified Research Core weights;
- v0.9.6 official engine policy;
- v0.10.0 target protocol.

## Invariants

- provider is Eurostat;
- dataset is `prc_hicp_midx`;
- unit and universe are inherited from the validated v0.8.7 vertical contract;
- interval is January 2021 through December 2025;
- grid is exactly five economies by twelve categories by sixty months;
- every row has direct official category evidence;
- raw request hashes reconcile with the official snapshot;
- no proxy, synthetic or model evidence enters ARM-O;
- replay, ledger and target archive verification are mandatory;
- all release, model, ARM-L, shadow and monetary gates remain closed.

## Outputs

### Observation bridge

- `category_observations_v096.csv`
- `observation_bridge_summary.json`
- `MANIFEST.sha256`

### Materialization bundle

- `arm_o_run/`
- `temporal_ledger.jsonl`
- `target_archive/`
- `materialization_summary.json`
- `MANIFEST.sha256`

## Current structural limitation

The v0.9.6 engine policy ends in December 2025. The point-in-time feature archive begins in 2026. A real ARM-O run can therefore be materialized and verified, but it cannot yet create future targets after the feature cutoffs. The materialization bundle must report:

`NO_FUTURE_TARGETS_AFTER_2025_UNTIL_OFFICIAL_ENGINE_PERIOD_IS_EXTENDED`

No period extension may be inferred or fabricated in v0.10.1.

## Historical manifest grammar

Verified v0.8.7 artefacts exist with either of these line grammars:

```text
<SHA256><SPACE><RELATIVE_PATH>
<SHA256><SPACE><SPACE><RELATIVE_PATH>
```

The bridge accepts exactly those two forms. This is a compatibility rule for
verified historical v0.8.7 inputs, not a relaxation of the current canonical
manifest grammar. Tabs, three or more separator spaces and paths beginning
with whitespace are invalid.
