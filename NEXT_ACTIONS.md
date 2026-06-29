# Next actions

1. Do not start Step 2J until the v0.6.1 corrective audit has been reviewed and the Step 2I current-probe states are accepted as provisional, reproducible gates.
2. India: obtain an official MoSPI methodological source confirming whether Statement 5.1 PFCE is strict households-only S14/P31DC with NPISH excluded. This remains the highest expected coverage gain, but the cell state must stay `CONCEPT_AMBIGUOUS` until confirmed.
3. Russia: locate an official Rosstat XLS/XLSX/CSV/SDMX/HTML 2021 household consumption by purpose table. Do not use OCR.
4. Eurostat PPP detail: acquire a directly comparable official PPP dataset with both `PPP_HFCE` and `PPP_AIC` for the same category/economy pairs, or keep `INSUFFICIENT_DIRECT_EVIDENCE`.
5. China: continue only through official NBS national-accounts tables; the eight-group household survey remains excluded from exact weights.
6. Indonesia and Brazil: search for exact official COICOP-HH national-accounts tables before considering any product or regrouped source.
7. Pakistan, Nigeria, Bangladesh and Viet Nam: revisit in Step 2J because current public official sources are aggregate or survey-only.

8. Re-run the full pipeline in GitHub Actions or another environment with DNS/network access; this sandbox could not acquire World Bank source metadata because DNS resolution failed.
