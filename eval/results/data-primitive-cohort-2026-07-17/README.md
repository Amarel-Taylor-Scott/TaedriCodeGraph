# Data primitive cohort evidence

Status: **passed**

Taedri released and independently executed 23 complete primitives,
including 21 new data-cleaning, data-engineering, and
data-science utilities. Every primitive has 13 payloads covering all 12 required roles,
six executable cases, six evidence-bound interface edges, two typed ports, searchable
capability labels, exact runtime/dependency metadata, license evidence, and immutable
source provenance.

| Domain | Active releases |
|---|---:|
| data-cleaning | 7 |
| data-engineering | 8 |
| data-science | 6 |
| text-core | 2 |

The persistent SQLite artifact contains 23 active releases and
serves all 23 targeted queries with exactly one intended result.
The bounded client digester decoded and safely materialized all
23 packs (276 selected files),
omitting verifier code according to its default policy.
Schema-digest blocking followed by exact typed assessment produced
111 directional composition edges without an unbounded
global all-pairs operation.

Six downloaded-pack routes executed without an LLM or generated glue code:

- Text: `normalize-text → collapse-whitespace → casefold-text → normalize-column-name` transformed
  `'  Customer\t Straße  '` to `'customer_strasse'`.
- Numeric: `minmax-scale → numeric-mean` transformed
  `[10, 20, 30]` to `0.5`.
- Datetime: `normalize-text → normalize-iso-datetime` transformed
  `' 2026-07-17T08:30:00-04:00 '` to `'2026-07-17T12:30:00Z'`.
- Null marker: `collapse-whitespace → normalize-null-marker` transformed
  `'  N/A  '` to `None`.
- JSON adapters: `parse-json-object → drop-null-fields → wrap-flatten-request → flatten-record → canonical-json-object` transformed
  `'{"user":{"name":"Ada","age":37},"unused":null}'` to `'{"user.age":37,"user.name":"Ada"}'`.
- Number adapters: `normalize-text → coerce-finite-number → format-compact-number` transformed
  `' 1.25 '` to `'1.25'`.

| SQLite record type | Records |
|---|---:|
| `audit_event` | 47 |
| `job_payload` | 23 |
| `primitive_blob` | 225 |
| `primitive_handle` | 23 |
| `primitive_ref` | 23 |
| `primitive_ref_update` | 23 |
| `primitive_release` | 23 |
| `primitive_release_revocation` | 0 |
| `primitive_revision` | 23 |
| `primitive_tree` | 23 |

This proves a larger, queryable, reusable local database and six deterministic data
routes. It does not yet prove corpus-wide ranking quality, dependency-backed pandas or
scikit-learn execution, distributed scale, or task-level token/cost savings.
