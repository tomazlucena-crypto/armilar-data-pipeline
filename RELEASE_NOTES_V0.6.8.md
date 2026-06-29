# Armilar Data Pipeline v0.6.8

## Scope

This release repairs the v0.6.7 source-registry schema error and completes the Step 2H0 Egypt source-family audit.

## Egypt

The dedicated CAPMAS adapter preserves and evaluates the National Accounts catalogue, its CSV export, the 2017/2018 Supply and Use Tables study description and HIECS 2021. The evidence does not provide a current-price calendar-2021 strict S14/P31 household-final-consumption matrix by the twelve Armilar purposes. HIECS remains Class C survey evidence and the SUT source is historical and product/activity based.

## Safety

Blocked critical sources produce `ACCESS_BLOCKED`. Changed content produces `CONCEPT_AMBIGUOUS`. No product allocation, survey-share substitution or temporal interpolation is allowed. Zero exact cells are added and `weights_final.csv` remains empty.
