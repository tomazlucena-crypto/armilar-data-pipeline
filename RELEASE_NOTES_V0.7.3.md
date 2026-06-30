# Release notes v0.7.3

## Conditional global research release

Version 0.7.3 adds a fail-closed global research release gate.

### Added

- `armilar_global_weights.release_gate`;
- `armilar-global-release` CLI;
- configurable validation and coverage gates;
- independent limits for total estimated share and Class E fallback share;
- conditional creation of `ARM-WEIGHTS-GLOBAL` only after all gates pass;
- explicit gate report in `global_release_gate.json`;
- tests proving failed gates do not produce a global release.

### Unchanged

- `weights_final.csv` remains empty;
- strict A/B evidence is preserved;
- C/D/E cells remain research estimates;
- `monetary_release_allowed=false` cannot be overridden by this module.
