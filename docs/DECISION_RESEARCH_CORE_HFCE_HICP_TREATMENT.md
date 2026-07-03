# Decision proposal: HFCE and HICP conceptual treatment

## Status

`PROPOSED`, awaiting explicit human approval.

## Decision

The Research Core combines Armilar 2021 HFCE-oriented PPP-adjusted weights with Eurostat HICP price observations. These concepts have a known material partial scope mismatch because HICP covers household final monetary consumption while HFCE can contain items outside that price boundary.

The mismatch is tolerated exclusively for engine development and internal research. It is not treated as resolved.

The target weight concept is real HFCE expenditure in 2021 converted through ICP PPPs. The current basket nevertheless contains 25 experimental cells that use an AIC PPP proxy. They represent:

`0.589731681350816432896035605`

of fixed-universe weight and are detailed in `constitution/ARMILAR_RESEARCH_CORE_V1_PROXY_EXPOSURE.json`.

## Mandatory rules

- every Research Core output reports `KNOWN_MATERIAL_PARTIAL_SCOPE_MISMATCH`;
- every coverage output reports the proxy weight share and affected categories;
- no complete-HFCE, exact-HFCE-PPP or world-index claim is allowed;
- current basket weights are not automatically adjusted;
- imputed rent is not silently substituted;
- research release remains blocked until a quantitative alignment report and separate approval;
- monetary eligibility requires a separate constitutional amendment.

## OOH sensitivity analysis

Before any external research release or shadow production, the project must compare:

- the standard HICP-based Research Core;
- a documented sensitivity variant incorporating available Eurostat OOHPI evidence.

The report must document:

- economies and periods covered;
- the OOH approach used;
- frequency alignment;
- weights;
- publication lag;
- missing-data treatment;
- effect on levels and changes.

This sensitivity analysis is not a complete measure of the HFCE/HICP mismatch and may not be presented as equivalent to HFCE imputed rent.

## Consequences

The v0.9.6 engine must carry concept-alignment and evidence-exposure metadata in every output. External or shadow release remains fail-closed until the sensitivity and alignment reports exist.
