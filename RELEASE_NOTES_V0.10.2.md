# ARMILAR v0.10.2

## ECOICOP v2 transition audit

This release freezes the 2026 Eurostat HICP classification transition as an executable, fail-closed contract.

Eurostat replaced the legacy `prc_hicp_midx` dataset with `prc_hicp_minr`, adopted ECOICOP version 2, changed the common index reference period to `2025=100`, published thirteen divisions and made back series available for 1996-2025. Divisions 08 and 09 were materially revised, while the former division 12 no longer has a one-to-one division structure because the new classification publishes divisions 12 and 13 separately.

The existence of back series does not prove that the frozen twelve-category Research Core can be extended automatically. v0.10.2 therefore:

- preserves the v0.8.7 official source horizon at December 2025;
- records the replacement dataset and official evidence;
- produces a deterministic thirteen-row transition matrix;
- blocks automatic same-code equivalence;
- blocks dropping CP13;
- blocks silent expansion of the basket;
- blocks automatic substitution of ECOICOP v2 back series;
- keeps every release, training, ARM-L, shadow and monetary gate closed;
- requires an explicit constitutional transition decision and a point-in-time backtest before ARM-O can extend into 2026;
- validates the complete v0.10.1 predecessor at commit `43c3bf02216635d41624f56fa0f2951c3d0cfdae` in a detached worktree, avoiding version-checker misuse on the v0.10.2 tree.

This release does not acquire live data, alter the Research Core constitution, modify weights, extend ARM-O, generate 2026 targets or claim backtest execution.
