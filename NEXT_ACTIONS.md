# Next actions

1. Let the v0.6.1 GitHub workflow finish and use its raw receipts to review the v0.6.2 source registry. Do not copy runtime results into source declarations by hand.
2. Run `armilar-source-probe` for all ten priority economies. Resolve exact dataset queries only for source families currently marked `NOT_INVESTIGATED`, `DISCOVERY_ONLY` or `ACCESS_BLOCKED`.
3. India: settle the strict S14/P31DC and NPISH boundary for Statement 5.1 from official MoSPI documentation. Keep every India cell `CONCEPT_AMBIGUOUS` until the boundary is confirmed.
4. Russia: obtain a deterministic Rosstat API, XLS/XLSX, CSV or database query for 2021 household consumption by purpose. A BRICS publication or a Rosstat landing page is discovery evidence only.
5. China: search official NBS national-accounts, supply-and-use and input-output tables. The eight-group household survey remains Class C and cannot be allocated into twelve exact categories.
6. Indonesia and Brazil: locate exact national 2021 household-purpose tables. Regrouped expenditure components and product-to-purpose many-to-many bridges remain experimental.
7. Egypt, Pakistan, Nigeria, Bangladesh and Viet Nam: complete the same source-family triage. This is still Step 2H0 triage, not Step 2J adapter development.
8. Populate `config/proxy_ppp_benchmarks.csv` only with matched official AIC and strict-HFCE PPP pairs for the same economy, Armilar category and reference year. Financing gaps cannot fill this registry.
9. Keep `INSUFFICIENT_DIRECT_EVIDENCE` until the minimum total, economy and per-category direct-comparison gates pass.
10. Re-run the full pipeline in GitHub Actions or another environment with network access. The local sandbox cannot establish DNS access to the official sources.
