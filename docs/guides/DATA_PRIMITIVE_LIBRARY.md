# Reusable data primitive library

Taedri now has a small but real data-utility library, not a list of proposed names.
The checked-in registry evidence contains 13 active releases: two text primitives and
11 data-cleaning, data-engineering, and data-science primitives. Each can be
searched, downloaded as an immutable pack, inspected, independently executed, and wired
through exact typed ports.

## Current complete cohort

| Domain | Primitive | Reusable behavior |
|---|---|---|
| Data cleaning | `collapse-whitespace` | Collapse Unicode whitespace runs without changing other characters |
| Data cleaning | `normalize-column-name` | NFKC-normalize, case-fold, and delimit a human column header |
| Data cleaning | `stable-deduplicate` | Preserve first occurrence under finite canonical-JSON equality |
| Data cleaning | `normalize-null-marker` | Map a fixed, documented set of textual missing-value sentinels to null |
| Data engineering | `flatten-record` | Flatten nested JSON objects and reject key collisions |
| Data engineering | `chunk-sequence` | Split a list into strict, bounded contiguous batches |
| Data engineering | `normalize-iso-datetime` | Convert offset-aware ISO timestamps to canonical UTC and reject naïve times |
| Data science | `numeric-mean` | Validate finite values and calculate an accurate arithmetic mean |
| Data science | `numeric-median` | Calculate the conventional finite numeric median |
| Data science | `minmax-scale` | Scale a finite vector to `[0, 1]`, with defined constant-vector behavior |
| Data science | `zscore-standardize` | Apply population z-score scaling, with defined constant-vector behavior |

All 11 have explicit error behavior, limitations, positive/boundary/negative examples,
three additional test vectors, an exact Python 3.12 runtime, no network access, no
third-party dependency, license evidence, immutable Git provenance, six directional
interface/evidence edges, two typed ports, and searchable capability groups.

## What the measured run proves

`eval/results/data-primitive-cohort-2026-07-16` is a persistent evidence bundle. Its
SQLite database has 13 active releases and 129 content-addressed blobs. The run executed
78 cases, served 13 targeted searches with exactly one intended result each, and found
31 directional compatibility edges by schema-digest blocking before exact assessment.

It then downloaded the release packs and executed four routes without a model call or
generated glue:

1. `normalize-text → collapse-whitespace → casefold-text → normalize-column-name`
2. `minmax-scale → numeric-mean`
3. `normalize-text → normalize-iso-datetime`
4. `collapse-whitespace → normalize-null-marker`

`eval/results/primitive-retrieval-program-2026-07-17` separately checks how these
primitives are found. The versioned program runs exact/name, label, BM25, blocking, and
explicitly nonsemantic lexical-hash paths under a cost budget; a true semantic path is
optional and capability-gated. On its 31-case constructed fixture it retained all 26
positive targets at K=4, improved rank-1 selection from 25/26 to 26/26, improved
unsupported abstention from 3/5 to 5/5, and returned 34 candidates instead of 83. Every
path execution or skip is digest-bound in a retrieval receipt.

The run does not establish corpus-wide relevance, hosted throughput, or token/cost
savings. Those remain benchmark questions rather than documentation claims.

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

1. locale-independent numeric coercion with per-item failure receipts;
2. record projection and rename maps with collision rules;
3. deterministic sort/group/window operations with stability and memory contracts;
4. typed joins with null, key-cardinality, and duplicate-key policies;
5. quantiles, robust scaling, covariance, correlation, and evaluation metrics;
6. streaming and Arrow-native variants for inputs too large to materialize;
7. dependency-backed pandas, Polars, PyArrow, NumPy, and scikit-learn adapters after the
   isolated-lock gate exists.

Every admission should add real task evidence, adversarial cases, search receipts, and
at least one successful consumer or explain why it is a useful terminal primitive. A
large database of weak names is worse than a smaller registry of trustworthy reusable
code.
