# Data primitive cohort evidence

Status: **passed**

Taedri released and independently executed 11 complete primitives,
including 9 new data-cleaning, data-engineering, and
data-science utilities. Every primitive has 13 payloads covering all 12 required roles,
six executable cases, six evidence-bound interface edges, two typed ports, searchable
capability labels, exact runtime/dependency metadata, license evidence, and immutable
source provenance.

| Domain | Active releases |
|---|---:|
| data-cleaning | 3 |
| data-engineering | 2 |
| data-science | 4 |
| text-core | 2 |

The persistent SQLite artifact contains 11 active releases and
serves all 11 targeted queries with exactly one intended result.
The bounded client digester decoded and safely materialized all
11 packs (132 selected files),
omitting verifier code according to its default policy.
Schema-digest blocking followed by exact typed assessment produced
18 directional composition edges without an unbounded
global all-pairs operation.

Two downloaded-pack routes executed without an LLM or generated glue code:

- Text: `normalize-text → collapse-whitespace → casefold-text → normalize-column-name` transformed
  `'  Customer\t Straße  '` to `'customer_strasse'`.
- Numeric: `minmax-scale → numeric-mean` transformed
  `[10, 20, 30]` to `0.5`.

| SQLite record type | Records |
|---|---:|
| `audit_event` | 23 |
| `job_payload` | 11 |
| `primitive_blob` | 109 |
| `primitive_handle` | 11 |
| `primitive_ref` | 11 |
| `primitive_ref_update` | 11 |
| `primitive_release` | 11 |
| `primitive_release_revocation` | 0 |
| `primitive_revision` | 11 |
| `primitive_tree` | 11 |

This proves a larger, queryable, reusable local database and two deterministic data
routes. It does not yet prove corpus-wide ranking quality, dependency-backed pandas or
scikit-learn execution, distributed scale, or task-level token/cost savings.
