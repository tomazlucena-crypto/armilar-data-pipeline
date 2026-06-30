# SDMX client spike v0.8.6

The v0.8.6 spike selects `sdmx1` for the v0.8.7 Eurostat/OECD pilot.

`pysdmx` is not installed or evaluated because no concrete requirement currently fails under the existing `armilar_prices.sdmx_adapter` contract. Pull-request CI remains deterministic and network-free.

Live smoke output, when run manually outside pull requests, is written outside `public/latest` and preserves request metadata, raw bytes and SHA-256 hashes. If network access is unavailable, the spike status is `NETWORK_BLOCKED`; no acquisition result is invented.
