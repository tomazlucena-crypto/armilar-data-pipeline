# Final report v0.6.4

## Result

Version 0.6.4 replaces the provisional Russian source hypothesis with an exact, executable Rosstat/Fedstat source-chain audit. No exact cells are added.

## Implemented

- Dedicated `RussiaRosstatAuditAdapter`.
- Five exact official resources instead of generic homepages:
  - Fedstat indicator 31414;
  - Rosstat 2021 supply-use workbook;
  - Rosstat 2021 household income, expenditure and consumption publication;
  - official KIPC-DH classification DOCX;
  - National Accounts of Russia 2015-2022 PDF.
- Independent acquisition, raw preservation, status code, content type, size and SHA-256 recording.
- Structured HTML marker checks.
- XLSX and DOCX XML text-inventory checks without office automation.
- PDF signature preservation without OCR.
- Cross-source methodology gates and fail-closed changed-content handling.
- `russia_methodology_gate_audit.csv` and `RUSSIA_METHOD_GATE_REPORT.md`.
- Workflow publication list updated for both Russian outputs.

## Russia decision

After successful acquisition of the three critical data families:

- Fedstat confirms aggregate household HFCE and current-price 2021 availability, but no purpose dimension.
- The SUT workbook is product-based, contains a household-and-NPISH combined marker in the tested structure, and requires a prohibited product-to-purpose allocation.
- KIPC-DH purpose detail is household-budget survey evidence, not national-accounts S14/P31DC.

Decision: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.

The local network run returned `ACCESS_BLOCKED` for all five sources because DNS resolution was unavailable. This is retained as runtime evidence and does not override the official-source methodological audit.

## Validation

- `pytest -q`: 71 tests passed.
- Source-chain fixture run: five acquired sources, zero exact rows, zero failures, confirmed method-gate rejection.
- Blocked-source test: a missing critical source prevents closed rejection.
- Changed-content test: an altered critical page returns `CONCEPT_AMBIGUOUS`.
- Deterministic output checks remain green.
- Local real-network run: one adapter, zero accepted rows, five acquisition failures, `ACCESS_BLOCKED`.

## Registry state

- Official resources: 32 across ten economies.
- A candidates: 0.
- B candidates: 0.
- C-only resources: 11.
- D resources: 21.

## Gates

- Exact cells added: 0.
- Complete economies added: 0.
- `weights_final.csv`: remains empty.
- `global_12_category_matrix_complete=false`.
- `monetary_release_allowed=false`.
- Step 2J: not started.
- GitHub update: deliberately deferred until all priority-country audits are complete.
