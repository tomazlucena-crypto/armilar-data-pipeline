# Decision: repair the Research Core executable contracts

## Problem

The v0.9.5-03 implementation materialized the correct 60-cell numerical grid but left four contract defects:

1. the constitution schema required fields absent from the constitution JSON;
2. the basket schema constrained only `economy_code`;
3. evidence classes were inferred from category codes rather than preserved source provenance;
4. the SHA-256 file covered only the basket CSV.

The materializer also generated authored policy documents and schemas, which allowed a mechanical run to overwrite reviewed contract text.

## Decision

Version `0.3.0-draft` separates authored contracts from generated artefacts.

The materializer now generates only:

- `basket/ARMILAR_RESEARCH_CORE_V1.csv`;
- `constitution/ARMILAR_RESEARCH_CORE_V1.sha256`.

The constitution, schemas and decision records are authored and reviewed. The materializer validates them before generating outputs.

The constitutional weight input is an immutable snapshot checked into `constitution/inputs/ARMILAR_RESEARCH_CORE_V1_WEIGHTS_OBSERVED_UNIVERSE_V094.csv`. `public/latest/weights_observed_universe.csv` is a mutable operational pointer and is not a constitutional input.

The basket restores per-cell source files, hashes, PPP headings, PPP scope, derivation, quality flags and rounding-residual state. Evidence classification is based only on `ppp_scope` and `derivation`.

The manifest covers the basket, source, constitution, schemas, script, normalization configuration and decision records. It excludes itself.

Text inputs covered by the manifest are hashed from a canonical UTF-8 representation without BOM, with CRLF and isolated CR normalized to LF. The source weights CSV retains its raw-byte SHA-256 invariant. This removes Windows/Linux checkout differences without changing visible or economic content.

The manifest explicitly includes the immutable snapshot and excludes `public/latest/weights_observed_universe.csv`.

## Consequences

The Research Core remains `DRAFT` and `RESEARCH_ONLY`. All seven methodological decisions and all release gates remain unchanged. Ratification is postponed until these repaired contracts pass the complete repository suite.
