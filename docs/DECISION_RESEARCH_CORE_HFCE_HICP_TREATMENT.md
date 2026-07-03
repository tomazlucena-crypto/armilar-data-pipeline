# Decision proposal: HFCE and HICP conceptual treatment

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

The Research Core combines Armilar 2021 HFCE-PPP weights with Eurostat HICP price observations. These concepts have a known partial scope mismatch because HICP covers household final monetary consumption while HFCE weights can contain items outside that price boundary.

The mismatch is accepted only for engine development and internal research. It is not treated as resolved.

Mandatory rules:

- every Research Core release reports `KNOWN_PARTIAL_SCOPE_MISMATCH`;
- no complete-HFCE or world-index claim is allowed;
- current basket weights are not automatically adjusted;
- imputed rent is not silently substituted;
- research release remains blocked until a quantitative alignment report and separate approval;
- monetary eligibility requires a separate constitutional amendment.

## Consequences

The v0.9.6 engine must carry concept-alignment metadata in every output.
