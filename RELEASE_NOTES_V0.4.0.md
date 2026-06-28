# Release notes v0.4.0

## Step 2H0 feasibility audit

This version separates source discovery from country-data integration.

### Added

- official-source probe for the ten highest-priority incomplete economies;
- independent `armilar-source-probe` executable;
- preserved raw responses, metadata and SHA-256 hashes for every candidate source;
- validation of HTTP result, content type, file signature and expected source markers;
- methodological and runtime classifications A/B/C/D;
- economy-level source summary and failure register;
- economic-gap ranking based on the seven direct ICP categories;
- source-adjusted development priority score;
- Option B financing-exposure diagnostic;
- explicit empty direct comparison between strict-HFCE PPP and AIC PPP where the public benchmark does not exist;
- 6 new automated tests, bringing the suite to 36 tests.

### Corrected

- partial weights are renamed `weights_observed_universe.csv`;
- `weights_final.csv` remains empty while worldwide scope is incomplete;
- the AIC/HFCE financing comparison now reconstructs HFCE by adding narcotics and net purchases abroad to the Armilar twelve-category numerator;
- configuration, package and output schema versions are advanced to 0.4.0 / 4.0.

### No methodological shortcut

The probe does not populate the matrix. Survey sources remain experimental, grouped classifications remain blocked and sources without a strict 2021 household-purpose table remain unavailable. Ratified Option B remains research-only because no matched strict-HFCE PPP benchmark has yet been acquired for the five proxy categories.
