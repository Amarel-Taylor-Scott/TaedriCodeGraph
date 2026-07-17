# Primitive route planner evidence

Status: **passed**

The checked benchmark translated 20 operation intents into
body-free retrieval shortlists, found and executed 7 of
7 expected compatible routes, and correctly abstained on all
3 of 3 negative cases.

| Task | Stages | Selected route | Other valid routes |
|---|---:|---|---:|
| `text_identifier` | 4 | `normalize-text → collapse-whitespace → casefold-text → normalize-column-name` | 0 |
| `numeric_mean` | 2 | `minmax-scale → numeric-mean` | 3 |
| `datetime_utc` | 2 | `normalize-text → normalize-iso-datetime` | 0 |
| `null_marker` | 2 | `collapse-whitespace → normalize-null-marker` | 0 |
| `json_flatten` | 5 | `parse-json-object → drop-null-fields → wrap-flatten-request → flatten-record → canonical-json-object` | 0 |
| `number_adapter` | 3 | `normalize-text → coerce-finite-number → format-compact-number` | 0 |
| `vector_normalized_sum` | 2 | `l2-normalize → numeric-sum` | 0 |

The first pass considered 24 candidates
and performed 16 authoritative adjacent-wire
assessments across a 23-release catalog. Every successful
route was executed from exact digest-bound packs with zero model calls and zero bytes of
generated glue code.

The resulting 7 exact recipes were then resolved again
under the same catalog and runtime environment. All
7 lookups were cache hits and required zero
candidate expansions and zero wire assessments. A changed catalog or environment digest
is a cache miss.

This fixture proves bounded ordered unary route discovery and reuse. It does not yet
prove multi-input hypergraph planning, corpus-scale relevance, hostile-code isolation,
or correctness beyond each capsule's tests and the recorded route executions.
