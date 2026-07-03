# ARMILAR v0.9.7 proxy registry and acquisition contract

## OBJECTIVE

Create a versioned registry and a deterministic acquisition layer for research proxies relevant to energy, fuels, food, transport and owner-occupied-housing sensitivity analysis.

## INPUTS

- `config/proxy_source_registry_v097.json`.
- HTTPS responses from the exact registered official hosts.
- Explicit UTC `retrieved_at` and, where evidenced, `published_at`.

## OUTPUTS

Each acquisition creates an immutable snapshot bundle containing:

- the exact raw response;
- `normalized.csv` under the closed observation contract;
- `receipt.json` with transport and licensing metadata;
- `normalization_summary.json`;
- the exact registry entry used;
- `MANIFEST.sha256`;
- an append-only entry in `snapshot_ledger.jsonl`.

## INVARIANTS

- No proxy observation can enter ARM-O, ARM-R or ARM-H.
- ARM-L use, model training, shadow production and monetary use remain disabled.
- CI performs no live acquisition.
- Raw bytes are preserved and every normalized row points to a raw snapshot.
- Replay must reproduce identical normalized bytes.
- A dataset without demonstrable historical publication timing cannot enter a historical information set.
- No current source in this registry is information-set ready.
- Redirects outside the registered host allowlist are rejected.
- Future-dated, duplicate and out-of-domain observations are rejected.

## FAILURE STATES

Acquisition fails closed on registry drift, HTTP failure, host drift, excessive payloads, invalid file signatures, parser ambiguity, duplicate identities, future periods, manifest mismatch, ledger corruption or non-deterministic replay.

## SUCCESS CONDITION

The registry passes its checker, all four parsers pass fixture-based replay tests, every snapshot is manifested and all prohibited-use gates remain false.

## STOP CONDITION

A source is left unavailable when its official format cannot be parsed without guessing, its licence cannot be confirmed, or publication timing remains unresolved. The source does not block the rest of the milestone.

## FALLBACK CONDITION

There is no automatic data fallback in v0.9.7. A replacement source requires a new registered source ID, preserved evidence and a new registry version or reviewed amendment.

## ACCEPTANCE TESTS

- closed registry and schemas;
- fixture tests for FAO, World Bank, European Commission and Eurostat;
- raw-to-normalized deterministic replay;
- manifest and hash-chain verification;
- tamper rejection;
- no changes to the Research Core basket, constitution, official engine or `public/latest`.

## OUT OF SCOPE

- proxy selection for ARM-L;
- model fitting or backtesting;
- direct index calculation;
- source scheduling;
- publication API;
- release or monetary eligibility.
