# Armilar Data Pipeline v0.6.13 final report

## Scope

Cumulative package built from the v0.6.5 delivery and the reconstructed v0.6.6-v0.6.7 Codex branch changes. It repairs the GitHub Actions registry failure and completes the configured second-wave and Step 2H exception audits.

## Completed audits

- Indonesia
- Brazil
- Egypt
- Pakistan
- Nigeria
- Bangladesh
- Viet Nam
- Belarus CP02
- Kuwait CP02
- Saudi Arabia CP02
- Bonaire
- Liberia

Previously completed India, Russia and China audits are preserved.

## Validation

- pytest: 110 passed, 5 subtests passed
- unittest: 110 passed
- Python compilation: passed
- workflow YAML parsing: passed
- source registry schema: 65 complete rows across 15 economies
- extracted ZIP test: 110 passed, 5 subtests passed
- deterministic fixture run: 72 files matched byte for byte across two executions
- fixture adapters run: 10
- fixture exact rows accepted: 0
- fixture failures: 0

## Economic gates

- exact cells added: 0
- `weights_final.csv`: header-only
- `global_12_category_matrix_complete=false`
- `monetary_release_allowed=false`
- direct proxy validation: `INSUFFICIENT_DIRECT_EVIDENCE`
- `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT`: not used

## External acquisition limitation

The local real-source exception run did not complete within the network timeout. No successful acquisition, source hash or HTTP result was fabricated. GitHub Actions should perform the next real network-backed validation.

## GitHub status

This build did not modify GitHub. It is ready to replace the files on the existing branch `codex/step2h0-remaining-country-audits`.
