# Development contract standard

A material capability must have a contract before implementation. The machine-readable registry is `config/development_contracts.json` and is checked by `scripts/validate_development_contracts.py`.

## Required fields

```text
OBJECTIVE
INPUTS
OUTPUTS
INVARIANTS
FAILURE STATES
SUCCESS CONDITION
STOP CONDITION
FALLBACK CONDITION
ACCEPTANCE TESTS
OUT OF SCOPE
```

## Interpretation

### Objective

A single result that can be evaluated. Avoid broad descriptions such as "improve the pipeline".

### Inputs and outputs

List concrete files, commands, schemas or provider responses. Outputs must distinguish research artefacts from production or monetary artefacts.

### Invariants

Rules that remain true under every valid execution. Economic invariants take precedence over convenience.

### Failure states

Named outcomes that fail closed. A network failure must not be reclassified as source non-admissibility, and incomplete data must not trigger silent renormalisation.

### Success condition

The evidence required to declare the capability complete.

### Stop condition

The point at which further work in the current unit must stop. This prevents agents from spending a session on an unbounded source or refactor.

### Fallback condition

The declared alternative when the success condition cannot be reached within scope.

### Acceptance tests

Commands and assertions that a reviewer can reproduce. Live acquisition checks must run outside pull-request CI.

### Out of scope

Explicitly excluded work. An agent must not continue into the next milestone merely because time remains.

## Pull-request rule

A pull request should implement one capability or one tightly coupled gate. It must not combine source expansion, methodological change, workflow redesign and publication outputs.

## Version rule

`pyproject.toml` is the sole authored version value. Generated artefacts may repeat the version, but CI must derive or verify those values rather than maintain independent constants.

## Test-baseline rule

CI records the test count and suite result on the current `main`. A lower count fails unless the pull request documents intentional consolidation and preserves equivalent coverage. The previously reported 221 tests are a historical reference only.
