# Architecture

The acquisition subsystem is deliberately separate from the future index engine.

```text
Official sources
      |
      v
DNS / TLS / HTTP diagnostics
      |
      v
Bounded downloads with retries
      |
      +---- failure ----> last-known-good cache
      |
      v
Raw immutable response files
      |
      v
Manifest + SHA-256 checksums
      |
      v
Versioned ZIP bundle and public rolling release
```

## Operational states

- `NORMAL`: all required sources are freshly downloaded and no cached response is used.
- `DEGRADED`: at least one source uses the last-known-good cache, with the condition recorded.
- `FAILED`: a required source has neither a fresh response nor a cached response.

A failed source does not erase a valid prior response. The pipeline never presents cached data as fresh.

## Scope of version 0.1

This version proves external execution, diagnostics, provenance and cache behaviour. The World Bank PPP query is an initial connectivity and economy-coverage input. It is not the detailed ICP 2021 HFCE matrix required to complete Step 2.
