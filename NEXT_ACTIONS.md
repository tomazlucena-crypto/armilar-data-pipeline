# Next actions after v0.8.1

1. Run the OECD and Eurostat live pilots in a network-enabled non-PR job and preserve the resulting raw responses outside Git.
2. Replace replay fixtures only when the raw hash, DSD snapshot and parser expectations are updated together.
3. Confirm the exact OECD and Eurostat data structures and categorical query keys before enabling candidate series in production.
4. Expand the price registry across the observed economies using official category CPI/HICP first and headline CPI only as an explicit fallback.
5. Ratify the exchange-rate treatment before enabling common-currency basket calculations.
6. Build the first real monthly core and global research series only for periods with complete declared coverage.
7. Start the v0.9.0 vintage-aware backtest and reconciliation layer.
8. Keep `weights_final.csv` empty and `monetary_release_allowed=false` until separate monetary ratification.
