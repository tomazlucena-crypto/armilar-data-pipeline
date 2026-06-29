# Next actions after v0.7.1

1. Implement v0.7.2 baseline methods for C, D and E cells with deterministic donor and fallback rules.
2. Add masked-cell validation using existing A/B evidence cells.
3. Connect country-audit partial evidence into `evidence_cells.csv` as C candidates without changing strict outputs.
4. Add duplicate-promotion guards across strict, country-audit and imputed evidence sources.
5. Continue live source acquisition reviews for audited countries, but do not let country-by-country exactness block the global contract layer.
6. Keep `weights_final.csv` empty and `monetary_release_allowed=false` until separate monetary ratification.

Experimental allocations are authorised only inside `ARM-WEIGHTS-GLOBAL` with explicit uncertainty and provenance; they remain prohibited in strict outputs.
