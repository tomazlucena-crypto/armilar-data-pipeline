# Release notes v0.6.4

## Scope

This release closes the Russian source-chain design and method gates without adding exact matrix cells.

## Changes

- Adds a dedicated Russian adapter covering five exact official Rosstat/Fedstat resources.
- Replaces generic landing pages and the unsupported BRICS table hypothesis.
- Preserves each acquired raw resource, HTTP metadata and SHA-256 hash.
- Validates HTML markers, all XML text inside XLSX/DOCX containers and PDF signatures without OCR.
- Keeps the Fedstat aggregate, Rosstat SUT product tables and KIPC-DH household survey as distinct concepts.
- Adds `russia_methodology_gate_audit.csv` and `RUSSIA_METHOD_GATE_REPORT.md`.
- Adds failure states for blocked critical sources and changed source content.
- Extends the publication workflow to include the Russian audit outputs.

## Russia decision

No exact 2021 current-price S14/P31DC twelve-purpose source passed the gates:

1. Fedstat indicator 31414 is aggregate-only.
2. The 2021 SUT workbook is product-based and requires an allocation bridge; category-level NPISH exclusion is not proven.
3. KIPC-DH purpose detail is a household-budget survey and remains Class C.

Decision after successful acquisition: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.

## Gates

- Exact cells added: 0
- `weights_final.csv`: empty
- `global_12_category_matrix_complete=false`
- `monetary_release_allowed=false`
- Step 2J: not started
