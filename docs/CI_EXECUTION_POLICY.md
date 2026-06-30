# CI execution policy

## Pull requests

Pull requests execute deterministic validation only:

- package installation;
- the complete unit-test suite;
- Python compilation;
- release-safety checks.

They do not contact live statistical sources. A remote API outage must not block
review or merging of code whose deterministic tests pass.

## Main, schedule and manual runs

Live acquisition runs only after a push to `main`, on the weekly schedule, or
through `workflow_dispatch`.

The live refresh remains fail-closed:

- acquisition failures remain recorded;
- `monetary_release_allowed` must remain false;
- the observed-universe weights must sum exactly to one when a research release
  is allowed;
- `weights_final.csv` must remain empty until the full global matrix passes its
  constitutional gates.

## Reason

The source-probe layer already runs network requests concurrently, but the
country-adapter registry currently executes national adapters sequentially.
With fifteen adapters and multiple retries per source, a pull-request run can
exceed the former 75-minute job limit despite all deterministic tests passing.

Country-adapter concurrency should be implemented and tested in a later
increment. It is not required to make pull-request validation reliable.
