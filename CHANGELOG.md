# Changelog

## 0.6.5

- Replaced the static China decision with `ChinaNbsAuditAdapter`.
- Added independent acquisition and hashing for six official NBS resources.
- Separated the 2021 eight-group household survey, yearbook inventory, 2020 input-output tables and aggregate 2021 GDP verification.
- Added `china_methodology_gate_audit.csv` and `CHINA_METHOD_GATE_REPORT.md`.
- Added fail-closed tests for blocked sources, changed content and inconsistent gate conclusions.
- Preserved `weights_final.csv` as empty and added zero exact cells.

## 0.6.4

- Replaces the Russian Fedstat homepage and incorrect BRICS publication hypothesis with five exact official resources.
- Adds `RussiaRosstatAuditAdapter` with independent acquisition, hashing and structural validation for Fedstat, SUT, HBS, KIPC-DH documentation and the national-accounts publication.
- Confirms that Fedstat indicator 31414 is aggregate-only and cannot supply twelve Armilar purposes.
- Rejects the 2021 supply-use workbook as an exact source because it is product-based, requires allocation and does not prove strict S14 exclusion at purpose level.
- Keeps KIPC-DH household-budget purpose detail as Class C survey evidence.
- Adds `russia_methodology_gate_audit.csv` and `RUSSIA_METHOD_GATE_REPORT.md`.
- Fails closed as `ACCESS_BLOCKED` when a critical source cannot be acquired and as `CONCEPT_AMBIGUOUS` when structural markers change.
- Removes the final provisional B candidate from the ten-economy registry.
- Keeps exact coverage unchanged and all global and monetary gates closed.

## 0.6.3

- Acquires and hashes the official MoSPI PFCE methodology alongside Statement 5.1.
- Confirms that Indian PFCE combines resident households and NPISH and that the components are unavailable separately.
- Rejects fiscal 2021-22 as a silent substitute for calendar 2021.
- Adds evidence source, location, retrieval timestamp and SHA-256 fields to every India methodology gate.
- Adds `INDIA_METHOD_GATE_REPORT.md`.
- Distinguishes acquired official documentation from datasets and generic discovery evidence in the source probe.
- Removes India from the provisional B-candidate set for strict exact weights.
- Keeps exact coverage unchanged and all monetary gates closed.

## 0.6.2

- Separates official-source discovery pages from qualifying acquired datasets.
- Adds ordered source-family coverage and explicit `NOT_INVESTIGATED`, `DISCOVERY_ONLY`, `ACCESS_BLOCKED` and non-machine-readable outcomes.
- Preserves structured failure receipts and attempt errors without fabricating hashes.
- Expands the official-source registry to 29 concrete candidates across ten priority economies.
- Adds independent `armilar-proxy-audit` and `armilar-matrix` programmes alongside the source probe and country adapters.
- Separates AIC/HFCE financing exposure from direct HFCE/AIC PPP proxy error.
- Adds `proxy_error_by_category.csv`, `proxy_error_by_economy.csv` and `source_probe_family_coverage.csv`.
- Keeps exact coverage unchanged and all global and monetary gates closed.

## 0.6.1

- Corrects Step 2I certainty language: diagnostic infrastructure is complete, source audit remains ongoing.
- Adds explicit methodological states for current-probe non-admissibility, access blocking, non-machine-readable sources and concept ambiguity.
- Prevents `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` unless final audit evidence exists.
- Adds `country_source_family_coverage.csv`, `step2i_audit_summary.json` and `STEP_2I_AUDIT_REPORT.md`.
- Adds pull-request validation and guards all publication steps to main non-PR runs.
- Keeps all monetary and global-scope gates closed.
