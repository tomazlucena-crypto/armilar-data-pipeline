# Eurostat vertical series v0.8.7

## Purpose

This component closes the first bounded price-to-index chain over real official Eurostat HICP bytes:

```text
official JSON-stat bytes
→ immutable snapshot and SHA-256 receipts
→ normalized P1 observations
→ fixed five-economy, twelve-division universe
→ PPP-weighted local price relatives
→ monthly index and contributions
→ coverage, uncertainty disclosure and economic report
```

The declared universe is Germany, Spain, France, Italy and Portugal from January 2021 through December 2025. It uses the twelve ECOICOP V1 divisions and publishes nine canonical Armilar macro-categories. The source divisions remain preserved in every normalized row.

Each cell is divided by its arithmetic mean over the twelve months of 2021. This aligns the price reference period with the annual ICP 2021 expenditure weights. Consequently, the arithmetic mean of the twelve monthly aggregate index values in 2021 is 100; January 2021 is not forced to 100.

## Transport decision

The v0.8.6 architecture keeps `sdmx1` as the selected general SDMX client for structure and metadata work, particularly for later multi-provider expansion. This bounded Eurostat slice deliberately retrieves the official Statistics API JSON-stat representation with the Python standard library. The decision avoids adding a second parser layer to a single-provider vertical test, preserves the exact official response bytes and keeps deterministic replay independent of an optional runtime dependency. It does not reverse the `sdmx1` selection.

The transport choice must be reviewed before OECD integration or before the Eurostat slice is generalised beyond this fixed contract.

Runtime version values and the acquisition user agent are derived from the repository's `armilar_pipeline.version` helper. The new module does not maintain an independent software-version constant. In an overlay-only checkout, it reports the permitted diagnostic value `0+unknown`.

## Invariants

- The universe is fixed before calculation.
- All five economies, twelve source categories and sixty months must be complete.
- Covered world weights are normalized once, before any monthly calculation.
- No missing cell can be silently dropped or renormalized.
- Current FX never enters the primary index.
- Every observation points to exact raw bytes and a SHA-256 receipt.
- `research_release_allowed=false`.
- `monetary_release_allowed=false`.

## Acquisition

Live acquisition is an explicit local operation and is excluded from pull-request checks:

```powershell
py scripts/run_eurostat_vertical_v087.py acquire `
  --policy config/eurostat_vertical_v087.json `
  --snapshot-dir artifacts/v087/eurostat_snapshot
```

The acquisition makes one bounded official request per source division. It has no open-ended retry loop. Provider bytes are written before parsing and are never silently replaced.

## Single local empirical gate

The normal closure path uses one local command and no GitHub Action:

```powershell
py scripts\validate_official_v087.py --repo-root .
```

It acquires the twelve official responses, verifies the snapshot, performs deterministic replay, checks the 2021 annual-average identity, verifies both manifests and compares a complete hash tree of `public/latest` before and after execution. It writes `artifacts/v087/OFFICIAL_GATE_REPORT.json`. A simulated test run can never emit the status `OFFICIAL_EMPIRICAL_GATE_PASSED`.

## Replay

```powershell
py scripts/run_eurostat_vertical_v087.py replay `
  --policy config/eurostat_vertical_v087.json `
  --snapshot-dir artifacts/v087/eurostat_snapshot `
  --weights public/latest/weights_observed_universe.csv `
  --output-dir artifacts/v087/eurostat_vertical
```

Replay verifies every raw hash and then requires the complete declared grid. It writes:

- `normalized_price_observations.csv`
- `fixed_universe_weights.csv`
- `monthly_index.csv`
- contributions by economy, source category and Armilar category
- `uncertainty_summary.json`
- `run_summary.json`
- `ECONOMIC_REPORT.md`
- `MANIFEST.sha256`

## Uncertainty

The component does not publish a fabricated zero-width confidence interval. Eurostat prices are direct P1 observations, but HICP measures household final monetary consumption while the Armilar weights target HFCE. The scope difference and current weight uncertainty are explicit and not yet calibrated. Bounds therefore remain absent and both release flags stay false.

## Release status and empirical gate

The official snapshot has been acquired and the full series has been rebuilt from those exact bytes. Synthetic JSON-stat fixtures remain tests only. The empirical gate writes `artifacts/v087/OFFICIAL_GATE_REPORT.json` and the economic report under `artifacts/v087/eurostat_vertical/ECONOMIC_REPORT.md`.

## Stop condition

This milestone stops before OECD expansion, additional countries, model backtesting, nowcasting, API publication or monetary use.
