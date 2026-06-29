# Next actions after v0.7.0

1. Integrate the strict matrix outputs into a canonical evidence-cell staging file for v0.7.1.
2. Convert existing strict official cells into A/B evidence without changing their values or strict outputs.
3. Allow country audits to emit partial C evidence per category while keeping C evidence out of `ARM-WEIGHTS-CORE`.
4. Add class/economy/category coverage reports and duplicate-promotion guards.
5. Continue live source acquisition reviews for audited countries, but do not let country-by-country exactness block the global contract layer.
6. Keep `weights_final.csv` empty and `monetary_release_allowed=false` until separate monetary ratification.

Experimental allocations are authorised only inside `ARM-WEIGHTS-GLOBAL` with explicit uncertainty and provenance; they remain prohibited in strict outputs.
