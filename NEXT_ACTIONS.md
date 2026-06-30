# Next actions after v0.7.3

1. Run v0.7.2 validation on the real staged A/B evidence and review errors by category and method.
2. Calibrate `config/global_release_gates.json` from observed validation performance rather than assumptions.
3. Connect country-audit partial evidence into the C-candidate staging layer without changing strict outputs.
4. Add explicit duplicate-promotion guards across strict, country-audit and imputed evidence sources.
5. Build the first monthly price-series registry and adapters after the world-weight research gate is empirically evaluated.
6. Keep `weights_final.csv` empty and `monetary_release_allowed=false` until separate monetary ratification.

Experimental allocations remain authorised only inside `ARM-WEIGHTS-GLOBAL` with explicit uncertainty and provenance.
