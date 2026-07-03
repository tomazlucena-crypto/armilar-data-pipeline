# Decision proposal: Research Core vintage and revision policy

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

Each ARM-O release is tied to an information cutoff, raw source snapshot, retrieval timestamp and available publication/revision identifiers. Once released, that ARM-O vintage is immutable.

Later official revisions create a new data vintage. They may update ARM-R, the latest-revised reconstruction, but can never overwrite the original ARM-O value or its inputs.

Where historical first-publication evidence is incomplete, the limitation must be explicit. A latest-available API response may not be represented as a historical first-published vintage.

## Consequences

Storage in v0.9.6 must be append-only by release and data vintage. Original and revised histories remain queryable separately.
