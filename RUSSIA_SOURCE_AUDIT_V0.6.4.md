# Russia source audit v0.6.4

## Scope

Official 2021 current-price strict household S14/P31DC expenditure by twelve Armilar purposes.

## Official source chain

### 1. Household final consumption expenditure indicator 31414

- Source ID: `RUT_FEDSTAT_HFCE_31414`
- URL: https://www.fedstat.ru/indicator/31414
- Family: `official_statistical_database`
- Evidence role: `DATASET_CANDIDATE`
- Preliminary class: `D_UNAVAILABLE`
- Gate: Official current-price household HFCE is aggregate and has no KIPC-DH or COICOP purpose dimension.

### 2. Base input-output and supply-use tables for 2021

- Source ID: `RUT_ROSSTAT_SUT_2021_XLSX`
- URL: https://rosstat.gov.ru/storage/mediabank/Rezultaty_RB_2021.xlsx
- Family: `official_supply_and_use_tables`
- Evidence role: `DATASET_CANDIDATE`
- Preliminary class: `C_ONLY`
- Gate: Product-to-COICOP mapping would require a many-to-many allocation and strict S14 scope is not proven at the required category level.

### 3. KIPC-DH classification

- Source ID: `RUT_ROSSTAT_KIPC_DH_CLASSIFICATION`
- URL: https://rosstat.gov.ru/storage/mediabank/KIPC_DX.docx
- Family: `official_structured_publications`
- Evidence role: `DOCUMENTATION`
- Preliminary class: `D_UNAVAILABLE`
- Gate: Classification documentation contains no expenditure values.

### 4. National Accounts of Russia in 2015-2022

- Source ID: `RUT_ROSSTAT_NATIONAL_ACCOUNTS_2015_2022`
- URL: https://rosstat.gov.ru/storage/mediabank/Nac-sch_2015-2022.pdf
- Family: `official_structured_publications`
- Evidence role: `DOCUMENTATION`
- Preliminary class: `D_UNAVAILABLE`
- Gate: Official PDF is preserved as documentary evidence; no OCR or unverified table extraction is allowed.

### 5. Income expenditure and consumption of households in 2021

- Source ID: `RUT_ROSSTAT_HBS_2021`
- URL: https://rosstat.gov.ru/bgd/regl/b21_102/
- Family: `survey_or_cpi_class_c_only`
- Evidence role: `CLASS_C_DATASET`
- Preliminary class: `C_ONLY`
- Gate: Purpose detail comes from a household budget survey and cannot substitute for national-accounts S14/P31DC expenditure.

## Methodological conclusion

The official source families establish aggregate household HFCE, product-based supply-use information and purpose-classified household-survey expenditure. They do not establish one exact 2021 current-price S14/P31DC table by twelve purposes without allocation.

Decision after successful acquisition and structural validation: `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE`.

The local runtime could not resolve Rosstat/Fedstat DNS and therefore correctly returned `ACCESS_BLOCKED`; it did not fabricate acquisitions or hashes.

## Gates

- Exact cells added: `0`
- `weights_final.csv` remains empty.
- `global_12_category_matrix_complete=false`.
- `monetary_release_allowed=false`.
- Step 2J has not started.
