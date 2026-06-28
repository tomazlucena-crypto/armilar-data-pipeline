# Step 2 architecture

## 1. Acquisition

All network requests run in GitHub Actions. Responses are written under `run/raw/` before parsing. Each response receives a metadata sidecar with source URL, retrieval timestamp, byte count and SHA-256 hash. A last-known-good cache is marked `stale_cache` and never presented as fresh data.

## 2. Discovery

The World Bank Advanced Data API exposes Source 90 through multidimensional concepts. The pipeline downloads each concept and variable inventory, then identifies roles from content:

- the heading dimension contains ICP codes such as `1101000`;
- the time dimension contains `2021`;
- the country dimension contains economy codes;
- the remaining dimension contains statistical measures.

No DataBank interface layout is hard-coded.

## 3. Measure selection

The pipeline identifies:

- PPP;
- nominal expenditure in local currency;
- PPP-based real expenditure.

Semantic matching is checked through:

`nominal expenditure / PPP = PPP-based real expenditure`

Ambiguous measure triples are rejected.

## 4. Publication-scope audit

`config/publication_scope_rules.csv` defines every strict HFCE requirement and every forbidden public alternative. The live Source 90 inventory is compared against those rules.

The following never substitute for strict HFCE:

- actual-consumption headings `9060000`, `9080000`, `9110000`, `9120000`, `9140000`;
- households-plus-NPISH aggregate `9100000`;
- CP02 parent `1102000`.

The audit is written to `outputs/publication_scope_audit.csv`.

## 5. Scope enforcement

Only headings explicitly included by `config/icp_headings_to_armilar.csv` can enter the category matrix. CP02 is alcohol plus tobacco. Parent and child headings never enter simultaneously. AIC, NPISH, government consumption and narcotics remain outside weights.

## 6. Economy status

The registry separates:

- `PARTICIPATING`, matched to the official 176-economy list;
- `OFFICIALLY_IMPUTED_AGGREGATE_ONLY`, nonparticipants with aggregate Source 90 results but no category allocation;
- `AGGREGATE`, regional or analytical aggregates;
- `UNAVAILABLE_OR_NONPUBLISHED`.

The 19 aggregate-only cases are identified from the Source 90 release structure and accepted as an official-imputation register only when the detected count matches the official count of 19.

## 7. Economy eligibility

An economy enters candidate weights only when:

- it is in the official participation list;
- all twelve strict Armilar categories are available;
- nominal and real values exist for every included heading;
- strict HFCE control `1100000` is available;
- PPP, nominal and real identities pass;
- nominal parent-component hierarchy checks pass when their inputs are published.

Missing inputs remain explicit. No fallback fills them.

## 8. Nominal hierarchy audit

Additive reconciliation uses nominal local-currency expenditure:

- `1102000 = 1102100 + 1102200 + 1102300`;
- `1100000 = sum of published household categories including 1113000`;
- `1100000 - twelve Armilar categories = 1102300 + 1113000`.

PPP-based real expenditures are not required to add across headings. They are used for weight construction after the separate accounting identity passes.

## 9. Weight construction

Candidate weights use PPP-based real expenditure:

`w(i,c) = E(i,c) / sum(E(i,c))`

Weights are emitted to 24 decimal places. The final ordered cell absorbs the disclosed decimal closure residual. The emitted sum must equal exactly one within tolerance `1E-20`.

## 10. Release gate

`weights_candidate_observed_participants.csv` is diagnostic or candidate output for the observed participating universe. `weights_final_normalized.csv` remains header-only unless the worldwide Constitution-compliant matrix passes every gate.

A successful software run can therefore finish with economic status `BLOCKED_SOURCE_PUBLICATION_SCOPE`. This is an audited result, not a release.

## 11. Publication

GitHub Actions publishes concise diagnostics under `public/latest/`, uploads the complete run as an Actions artifact and replaces a rolling prerelease asset. Raw source files stay in the artifact rather than the Git history.
