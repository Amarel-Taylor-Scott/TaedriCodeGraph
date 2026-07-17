# Data primitive cohort evidence

Status: **passed**

Taedri released and independently executed 13 complete primitives,
including 11 new data-cleaning, data-engineering, and
data-science utilities. Every primitive has 13 payloads covering all 12 required roles,
six executable cases, six evidence-bound interface edges, two typed ports, searchable
capability labels, exact runtime/dependency metadata, license evidence, and immutable
source provenance.

| Domain | Active releases |
|---|---:|
| data-cleaning | 4 |
| data-engineering | 3 |
| data-science | 4 |
| text-core | 2 |

The persistent SQLite artifact contains 13 active releases and
serves all 13 targeted queries with exactly one intended result.
The bounded client digester decoded and safely materialized all
13 packs (156 selected files),
omitting verifier code according to its default policy.
Schema-digest blocking followed by exact typed assessment produced
31 directional composition edges without an unbounded
global all-pairs operation.

Four downloaded-pack routes executed without an LLM or generated glue code:

- Text: `normalize-text → collapse-whitespace → casefold-text → normalize-column-name` transformed
  `'  Customer\t Straße  '` to `'customer_strasse'`.
- Numeric: `minmax-scale → numeric-mean` transformed
  `[10, 20, 30]` to `0.5`.
- Datetime: `normalize-text → normalize-iso-datetime` transformed
  `' 2026-07-17T08:30:00-04:00 '` to `'2026-07-17T12:30:00Z'`.
- Null marker: `collapse-whitespace → normalize-null-marker` transformed
  `'  N/A  '` to `None`.

| SQLite record type | Records |
|---|---:|
| `audit_event` | 27 |
| `job_payload` | 13 |
| `primitive_blob` | 129 |
| `primitive_handle` | 13 |
| `primitive_ref` | 13 |
| `primitive_ref_update` | 13 |
| `primitive_release` | 13 |
| `primitive_release_revocation` | 0 |
| `primitive_revision` | 13 |
| `primitive_tree` | 13 |

This proves a larger, queryable, reusable local database and four deterministic data
routes. It does not yet prove corpus-wide ranking quality, dependency-backed pandas or
scikit-learn execution, distributed scale, or task-level token/cost savings.
