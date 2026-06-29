# Step 2I version report v0.6.1

Version 0.6.1 is a corrective audit release.

It preserves the useful v0.6.0 infrastructure, but removes language implying that China, India, Russia, Indonesia and Brazil were definitively closed. The correct status is:

`Step 2I diagnostic infrastructure complete; source audit ongoing`

## Methodological correction

The release distinguishes three different situations:

1. a source was acquired but remains conceptually ambiguous;
2. a source family was checked in the current probe but no admissible source was found;
3. an exhaustive official-source audit has been completed.

Only the third can ever justify `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`. The code now rejects that state unless explicit final-audit evidence exists.

## Economic gates

The release keeps every monetary and global-completion gate closed:

- no exact cells added;
- no experimental allocation admitted;
- no modelled weights;
- no CPI or household-budget shares used as exact weights;
- no Step 2J work started;
- `weights_final.csv` remains empty.

## Local validation

The updated unit suite passed locally with 48 tests.

A full Step 2 pipeline run could not be completed in this sandbox because DNS resolution failed before the World Bank source metadata acquisition. The country-adapter isolated run completed and recorded India as `ACCESS_BLOCKED` in this environment.
