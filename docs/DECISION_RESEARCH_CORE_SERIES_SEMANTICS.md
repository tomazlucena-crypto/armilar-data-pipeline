# Decision proposal: Exact Research Core series semantics

## Status

`PROPOSED`, awaiting explicit human approval.

## ARM-O

First-published, official-source Research Core index for a declared information cutoff and complete 60-cell grid. It contains no price proxies or carry-forward values and is not an official statistic.

## ARM-R

Latest-revised official-source reconstruction. It preserves all ARM-O vintages and may never replace or rewrite them.

## ARM-H

Independent CP00 headline benchmark. CP00 is outside the weighted CP01-CP12 basket. Economy weights equal the sum of the twelve Research Core category weights for each economy. A complete five-economy CP00 grid is required.

## ARM-L

ARM-L is a versioned live research estimate anchored to the latest valid ARM-O release.

Every ARM-L release must identify:

- the anchor ARM-O vintage;
- `information_cutoff`;
- `retrieval_cutoff`;
- source-registry version;
- model version;
- raw snapshot identifiers;
- publication and retrieval timestamps;
- quality state;
- uncertainty bounds.

Only an observation published on or before the information cutoff and retrieved on or before the retrieval cutoff is eligible. A late observation enters the next release only.

Source precedence is defined per cell in a versioned source registry. Two runs with the same information set, model, basket and code version must produce the same ARM-L output.

An ARM-L release is immutable. It is never retroactively edited to match ARM-O.

When official observations arrive for an estimated period:

1. the original ARM-L release is preserved;
2. ARM-O becomes the current official-source value for that period;
3. a reconciliation event records the error and its decomposition.

Until a model is approved, ARM-L may expose only an explicit carry-forward baseline with uncertainty and quality metadata.

The constitution does not hard-code a weekday or clock time. Before the first ARM-L release, a separately approved `ARM_L_RELEASE_SCHEDULE_V1` contract must define the cadence and cutoffs.

## Common rule

No series may silently substitute another.
