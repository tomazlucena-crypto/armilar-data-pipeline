# ARMILAR v0.9.7

## Proxy registry and acquisition

This milestone adds:

- a closed, versioned registry for four official research-proxy sources;
- adapters for World Bank Pink Sheet, FAO FFPI, EC Weekly Oil Bulletin and Eurostat OOHPI;
- raw snapshot preservation, receipts and SHA-256 manifests;
- normalized observations with explicit publication and retrieval times;
- append-only hash-chained snapshot ledger;
- deterministic replay and tamper detection;
- closed JSON schemas and a repository checker;
- fixture-based tests with no live acquisition in CI.

All direct-index, ARM-L, model-training, shadow-production and monetary gates remain false. No proxy is information-set ready in this version.
