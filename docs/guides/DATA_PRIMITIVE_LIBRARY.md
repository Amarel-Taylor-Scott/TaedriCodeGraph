# Reusable data primitive library

Taedri now has a small but real data-utility library, not a list of proposed names.
The expanded checked-in registry evidence contains 23 active releases: two text
primitives and 21 data-cleaning, data-engineering, and data-science primitives. Each can be
searched, downloaded as an immutable pack, inspected, independently executed, and wired
through exact typed ports.

## Current complete cohort

| Domain | Primitive | Reusable behavior |
|---|---|---|
| Data cleaning | `collapse-whitespace` | Collapse Unicode whitespace runs without changing other characters |
| Data cleaning | `normalize-column-name` | NFKC-normalize, case-fold, and delimit a human column header |
| Data cleaning | `stable-deduplicate` | Preserve first occurrence under finite canonical-JSON equality |
| Data cleaning | `normalize-null-marker` | Map a fixed, documented set of textual missing-value sentinels to null |
| Data cleaning | `normalize-unicode-nfkc` | Apply Unicode NFKC compatibility normalization without changing case |
| Data cleaning | `remove-control-characters` | Remove Unicode Cc control characters |
| Data cleaning | `drop-null-fields` | Omit top-level null fields from one JSON object |
| Data engineering | `flatten-record` | Flatten nested JSON objects and reject key collisions |
| Data engineering | `chunk-sequence` | Split a list into strict, bounded contiguous batches |
| Data engineering | `normalize-iso-datetime` | Convert offset-aware ISO timestamps to canonical UTC and reject naïve times |
| Data engineering | `parse-json-object` | Strictly parse a top-level JSON object and reject duplicate keys |
| Data engineering | `canonical-json-object` | Serialize an object with stable recursive key order and compact spacing |
| Data engineering | `coerce-finite-number` | Convert decimal or exponent text to a finite number |
| Data engineering | `format-compact-number` | Convert one finite number to compact JSON number text |
| Data engineering | `wrap-flatten-request` | Adapt a generic object to `flatten-record`'s exact request schema |
| Data science | `numeric-mean` | Validate finite values and calculate an accurate arithmetic mean |
| Data science | `numeric-median` | Calculate the conventional finite numeric median |
| Data science | `numeric-sum` | Accurately total a finite vector with `math.fsum` |
| Data science | `minmax-scale` | Scale a finite vector to `[0, 1]`, with defined constant-vector behavior |
| Data science | `zscore-standardize` | Apply population z-score scaling, with defined constant-vector behavior |
| Data science | `l2-normalize` | Normalize a vector to unit Euclidean length with defined zero behavior |

All 21 have explicit error behavior, limitations, positive/boundary/negative examples,
three additional test vectors, an exact Python 3.12 runtime, no network access, no
third-party dependency, license evidence, immutable Git provenance, six directional
interface/evidence edges, two typed ports, and searchable capability groups.

## What the measured run proves

`eval/results/data-primitive-cohort-2026-07-17` is the expanded persistent evidence
bundle. Its SQLite database has 23 active releases and 225 content-addressed blobs. The
run executed 138 cases, served 23 targeted searches with exactly one intended result
each, and found 111 directional compatibility edges by schema-digest blocking before
exact assessment.

It then downloaded the release packs and executed six routes without a model call or
generated glue:

1. `normalize-text → collapse-whitespace → casefold-text → normalize-column-name`
2. `minmax-scale → numeric-mean`
3. `normalize-text → normalize-iso-datetime`
4. `collapse-whitespace → normalize-null-marker`
5. `parse-json-object → drop-null-fields → wrap-flatten-request → flatten-record → canonical-json-object`
6. `normalize-text → coerce-finite-number → format-compact-number`

The fifth route is deliberately important: `wrap-flatten-request` is a normal tested
adapter whose output schema exactly matches `flatten-record`'s input. The planner does
not silently reinterpret a generic object as that request contract.

`eval/results/primitive-retrieval-program-2026-07-17` separately checks how these
primitives are found. The versioned program runs exact/name, label, BM25, blocking, and
explicitly nonsemantic lexical-hash paths under a cost budget; a true semantic path is
optional and capability-gated. On its 31-case constructed fixture it retained all 26
positive targets at K=4, improved rank-1 selection from 25/26 to 26/26, improved
unsupported abstention from 3/5 to 5/5, and returned 34 candidates instead of 83. Every
path execution or skip is digest-bound in a retrieval receipt.

The run does not establish corpus-wide relevance, hosted throughput, or token/cost
savings. Those remain benchmark questions rather than documentation claims.

`eval/results/primitive-route-planner-2026-07-17` checks retrieval and use together on
the expanded catalog. It ran 20 body-free retrieval executions for seven structured
routes, considered 24 route candidates, performed 16 exact adjacent-wire assessments,
executed all seven intended routes, and abstained on three invalid contracts. All seven
verified routes were then reused under the same catalog/runtime identity with zero
candidate expansion and zero wire assessment.

## Why these semantics

The cohort follows well-established public interfaces while keeping the first release
dependency-free. Python's `statistics` documentation defines the descriptive-statistics
baseline. pandas documents duplicate removal, JSON normalization, text operations, and
the broader cleaning workflow. scikit-learn documents min/max and standard scaling,
including their sensitivity and constant-feature behavior.

- [Python 3.12 statistics](https://docs.python.org/3.12/library/statistics.html)
- [pandas user guide](https://pandas.pydata.org/docs/user_guide/)
- [pandas `drop_duplicates`](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html)
- [pandas `json_normalize`](https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html)
- [scikit-learn `MinMaxScaler`](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.MinMaxScaler.html)
- [scikit-learn `StandardScaler`](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html)

These are semantic references, not claims that Taedri embeds or substitutes for those
libraries. A future pandas/scikit-learn-backed primitive must carry an exact dependency
closure and pass an isolated verifier that installs, scans, executes, and attests that
lock. The current local verifier intentionally does not pretend to provide that boundary.

## One-at-a-time growth queue

Add the next primitive only for a real reuse gap and only after its complete capsule
passes. High-value candidates are:

1. record projection and rename maps with collision rules;
2. deterministic sort/group/window operations with stability and memory contracts;
3. typed joins with null, key-cardinality, and duplicate-key policies;
4. quantiles, robust scaling, covariance, correlation, and evaluation metrics;
5. multi-input aggregation and lookup primitives once set-valued route state exists;
6. streaming and Arrow-native variants for inputs too large to materialize;
7. dependency-backed pandas, Polars, PyArrow, NumPy, and scikit-learn adapters after the
   isolated-lock gate exists.

Every admission should add real task evidence, adversarial cases, search receipts, and
at least one successful consumer or explain why it is a useful terminal primitive. A
large database of weak names is worse than a smaller registry of trustworthy reusable
code.
