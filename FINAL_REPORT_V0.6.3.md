# Final report v0.6.3

## Result

Version 0.6.3 closes the India source-methodology audit while preserving every exact-matrix and monetary gate.

## Implemented

- The India adapter now acquires two separate official sources:
  - MoSPI National Accounts Statistics 2024, Statement 5.1;
  - MoSPI Chapter 22 methodology for Private Final Consumption Expenditure.
- Both raw files, acquisition records, sizes and SHA-256 hashes are preserved.
- Statement 5.1 is parsed and reconciled at item level.
- Alcohol, tobacco and narcotics remain separately identifiable; narcotics are excluded without estimation.
- The methodology gate records source URL, evidence location, retrieval timestamp, hash and review mode for every criterion.
- The reviewed methodology PDF is pinned to its audited SHA-256. A changed document returns `METHODOLOGY_REVIEW_REQUIRED` and `CONCEPT_AMBIGUOUS`.
- Official methodology is represented by `ACQUIRED_DOCUMENTATION_EVIDENCE`, separately from datasets and discovery pages.
- Added `INDIA_METHOD_GATE_REPORT.md` to run outputs, workflow artefacts and publication lists.
- India is removed from the static B-candidate set.

## India decision

The source is rejected from the strict exact matrix for two independent reasons:

1. MoSPI PFCE combines resident households and NPISH, and the components are not available separately.
2. Statement 5.1 reports fiscal 2021-22, not calendar 2021.

No NPISH allocation, proportional split or calendar-year interpolation was performed.

Decision: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.

## Local source evidence

- Statement 5.1: 77,568 bytes, SHA-256 `651c981f4d65697a3c03750ae3a62e21f197d039b4fc68061b334ecdb84eb729`.
- Chapter 22 methodology: 270,951 bytes, SHA-256 `8439d936cea6a451ed0f60c964feaf3c3635ec62c398cc952f1e0ec148f6da62`.

These hashes describe the exact official files reviewed in this development run. The methodology hash is pinned in code so a publisher-side change cannot inherit the old conclusion silently.

## Source-probe outcome

The static registry contains 30 official resources across ten economies:

- A candidates: 0;
- B candidates: 1, Russia only and still provisional;
- C-only resources: 9;
- D resources: 20.

The local India probe acquired one dataset and one documentation file, recorded two blocked ancillary candidates, classified India `D_UNAVAILABLE` provisionally and kept `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` unused.

## Proxy audit

The direct HFCE/AIC PPP benchmark registry remains empty. Two executions produced byte-identical outputs and the status remains `INSUFFICIENT_DIRECT_EVIDENCE`.

## Validation

- `python -m unittest discover -s tests -v`: 64 tests passed.
- `pytest -q`: 64 tests passed.
- Python compilation: passed.
- GitHub Actions YAML parse: passed.
- India adapter cached-official-file run: 1 adapter, 0 accepted rows, 0 failures.
- India reviewed-hash path: `REJECTED_BY_CONFIRMED_METHOD_GATE`.
- India changed-hash path: `METHODOLOGY_REVIEW_REQUIRED`.
- Proxy determinism: passed byte for byte.
- Full pipeline attempt: failed closed at World Bank metadata acquisition because the local Python runtime could not resolve DNS.

## Gates

- Exact cells added: 0.
- Complete economies added: 0.
- `weights_final.csv`: remains empty.
- `global_12_category_matrix_complete=false`.
- `monetary_release_allowed=false`.
- Step 2J: not started.
