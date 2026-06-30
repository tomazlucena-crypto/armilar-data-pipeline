# Next actions after v0.8.0

1. Complete the v0.7.2 validation on the real A/B evidence grid and calibrate the world-weight release gates.
2. Run the OECD and Eurostat SDMX pilots in a network-enabled CI environment.
3. Preserve raw provider responses, retrieval timestamps and SHA-256 receipts.
4. Confirm the exact OECD and Eurostat data structures and categorical query keys before enabling candidate series.
5. Expand the price registry across the observed economies using official category CPI/HICP first and headline CPI only as an explicit fallback.
6. Ratify the exchange-rate treatment before enabling common-currency basket calculations.
7. Build the first real monthly core and global research series only for periods with complete declared coverage.
8. Start the v0.9.0 vintage-aware backtest and reconciliation layer.
9. Keep `weights_final.csv` empty and `monetary_release_allowed=false` until separate monetary ratification.
