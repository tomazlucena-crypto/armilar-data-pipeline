# Canonical consumption classification method

## Why the layer exists

Official classifications change over time and do not change in exactly the same way
across providers. Armilar therefore stores source classifications unchanged and maps
them into a stable nine-category analytical layer.

## Reliability effect

An exact merge does not change the total index. Each source-category contribution is
calculated first using its fixed Armilar world weight. Contributions are then summed
into the canonical category. A macro-category price relative is the weighted average
of the source relatives, never a simple average.

The classification layer can still introduce risk when a source category must be
split. Strict v0.8.2 rejects such mappings. Future estimated splits require separate
uncertainty and validation.

## Current bridges

- ECOICOP V1 to Armilar V1: ratified for the experimental 1996-2025 Eurostat source
  structure using CP01-CP12 exact one-to-one mappings and exact merges.
- ECOICOP V2 to Armilar V1: provisional. The division-level mapping is stored for
  audit, but cross-division reclassifications require comparison with Eurostat's
  official historical back series before activation.

## Preserved outputs

`index_contributions.csv` reports the nine canonical categories.

`source_category_contributions.csv` retains CP01-CP12 detail.

`classification_mapping_audit.csv` binds every source code to the active mapping,
classification version and SHA-256 hashes.
