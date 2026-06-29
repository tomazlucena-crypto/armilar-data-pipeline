# Step 2I audit states

Version 0.6.1 uses explicit methodological states rather than generic unavailability wording.

| State | Meaning | Admissible to exact matrix |
|---|---|---:|
| `EXACT_OFFICIAL` | Official exact cell with no derivation. | yes |
| `OFFICIAL_DERIVED_NO_ALLOCATION` | Official values summed or transformed without allocation. | yes |
| `OFFICIAL_EXPERIMENTAL_ALLOCATION` | Official source exists but exact Armilar category requires allocation. | no |
| `NO_ADMISSIBLE_SOURCE_FOUND_IN_CURRENT_PROBE` | Current probe found no source passing all gates, but the source audit is not exhaustive. | no |
| `ACCESS_BLOCKED` | Acquisition failed in the current run. | no |
| `SOURCE_NOT_MACHINE_READABLE` | Official evidence exists but cannot be acquired as structured data. | no |
| `CONCEPT_AMBIGUOUS` | Source is accessible but a material economic boundary is unresolved. | no |
| `UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` | Exhaustive official-source audit proves unavailability. | no |

`UNAVAILABLE_AFTER_EXHAUSTIVE_AUDIT` is intentionally gated. The code rejects it unless the audit record proves that all official source families were examined.

## Source-family order

1. official national-accounts API;
2. official CSV, XLS or XLSX;
3. official statistical database;
4. official Supply and Use Tables;
5. official structured publications;
6. survey or CPI evidence, class C only;
7. final exhaustive-unavailability documentation.

A homepage is not a dataset. It can only be an attempt record if the status remains non-admissible and the remaining gap is explicit.
