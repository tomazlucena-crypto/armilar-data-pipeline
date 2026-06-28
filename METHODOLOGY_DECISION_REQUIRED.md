# Methodological and source-data gates after the next GitHub Actions run

The next external run must answer two separate questions from the live Source 90 inventory.

## Gate 1: strict HFCE publication scope

The current official 45-heading table omits or substitutes:

- strict HFCE control `1100000` with households-plus-NPISH `9100000`;
- CP04 `1104000` with actual housing `9060000`;
- CP06 `1106000` with actual health `9080000`;
- CP09 `1109000` with actual recreation and culture `9110000`;
- CP10 `1110000` with actual education `9120000`;
- CP12 `1112000` with actual miscellaneous goods and services `9140000`.

If the Advanced Data API inventory confirms these omissions, Source 90 alone cannot produce the Constitution-compliant matrix. The next data action is then a targeted request for the unpublished strict-HFCE national-accounts results or another official publication with equivalent scope. AIC and NPISH substitutes remain prohibited.

## Gate 2: officially imputed economies

The official release identifies 19 nonparticipating economies with aggregate imputed results. It provides no public twelve-category allocation for them.

After the external run:

1. verify that the registry detects exactly 19 aggregate-only nonparticipants;
2. preserve them outside category weights;
3. decide later whether the research universe can be limited to benchmark participants or whether an independently governed allocation method is acceptable.

No model-based allocation enters `weights_final_normalized.csv` automatically.
