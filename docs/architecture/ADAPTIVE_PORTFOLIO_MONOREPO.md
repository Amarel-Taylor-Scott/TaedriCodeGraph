# Adaptive portfolio and monorepo architecture

Status: accepted direction with executable POC components
Atlas: [Taedri Code Entity Description Atlas](../spec/TAEDRI_CODE_ENTITY_DESCRIPTION_ATLAS.md)
Interactive view: [architecture explorer](../visuals/architecture-explorer.html)

## Decision

Taedri should use an open descriptor registry over typed long tables, not a wide
entity table and not an untyped entity-attribute-value dump. The logical model may
retain any number of independently versioned representations. Physical generation
and indexing remain budgeted, measured, and replaceable.

The complete descriptor identity is:

```text
subject + facet + production event + representation + scope
        + evidence + lineage + validity + cost
```

Adding licensing, lineage, hierarchy, a new scalar, an embedding space, or another
model output normally adds a descriptor definition and assertion rows. It does not
add a nullable column to every entity and does not rewrite canonical identity.

## Typed long-table model

The canonical ledger separates concerns that a conventional EAV table would mix:

| Logical relation | One row represents | Key properties |
|---|---|---|
| `descriptor_definition` | one immutable descriptor version | namespace, schema, applicability, missing semantics, index recipes |
| `representation_content` | one content-addressed typed payload | deduplicated independently of subject and run |
| `generation_run` | one actual attempt | producer, version, inputs, config, environment, status, cost |
| `representation_assertion` | one claim that content describes a subject | scope, modality, polarity, confidence, validity, lifecycle |
| `lineage_assertion` | one ordered or role-labeled DAG input | many-to-many derivation, evidence, producer, run |
| `materialization_state` | one explicit descriptor state for one subject | present, failed, stale, unknown, withheld, and other non-empty states |
| `preferred_view` | one reversible role-scoped selection | retrieval, solving, execution, verification, or human scope |
| `projection_epoch` | one disposable physical build | model/index versions, calibration, policy partition, measured recall |

Values retain a wire kind such as text, keyword, integer, decimal string, timestamp,
URI, digest, JSON, sparse vector, dense vector, distribution, or content reference.
Serving stores may promote frequently queried descriptors into typed projection
tables and specialist indexes. The canonical ledger remains source of truth.

This avoids two opposite failures:

- wide tables force migrations, sparse nulls, and model-specific columns;
- untyped EAV loses schema validation, units, vector-space identity, index intent,
  and missing-state semantics.

## Physical database split

No single database should own every workload.

| Plane | Recommended initial system | Why |
|---|---|---|
| Payload and artifact bytes | content-addressed object storage | immutable dedupe, integrity, cheap large objects |
| Canonical analytical facts | compressed Parquet/Arrow partitions | scan efficiency, compact storage, reproducible epochs |
| Registry and operational control | PostgreSQL typed long tables | transactions, constraints, bitemporal and provenance queries |
| Lexical and facet serving | PostgreSQL FTS first; replaceable search service later | simple POC, independent scale-out path |
| Vector candidates | pgvector first; replaceable ANN service by vector space | avoids one universal vector table while preserving receipts |
| Graph serving | compact adjacency first; graph service only for justified paths | canonical edges stay outside vendor-specific storage |
| Local analysis and ablation | DuckDB over Parquet | direct reproducible research without serving duplication |

Every physical index is a disposable projection from immutable facts. An index
manifest names its input epoch, descriptor versions, model space, parameters, policy
partition, calibration, counts, measured recall, and invalidation state.

## Independent usefulness below package level

A package description is context, not a semantic ceiling. A private helper in an
address parser can be independently useful for normalization, tokenization, error
handling, caching, or another domain. Taedri therefore scores each subject from its
own evidence:

- observed query demand and successful reuse;
- collision or candidate-confusion pressure;
- local and ecosystem reuse potential;
- graph centrality and boundary position;
- evidence and verification gaps;
- staleness and change pressure.

Package-purpose alignment is not a negative gate. Package, module, class, function,
method, relation, group, and route representations coexist and can disagree in scope.

## Adaptive enrichment depth

`portfolio.py` implements a deterministic selector with integer parts-per-million
scores and explicit resource receipts. It distinguishes enrichment depth from model
disclosure depth:

| Level | Enrichment family | Default behavior |
|---:|---|---|
| E0 | exact identity, source handles, provenance | baseline |
| E1 | names, lexical fields, labels, cheap sparse features | baseline |
| E2 | structural fingerprints, shingles, LSH, graph locality | when structurally applicable |
| E3 | signatures, types, ports, effects, errors, constraints | when composition or hard filtering matters |
| E4 | purpose-specific semantic descriptions and embeddings | when cheaper arms leave ambiguity |
| E5 | runtime, trace, performance, behavioral projections | when authorized evidence is worth the cost |
| E6 | execution, tests, formal or independent verification | correctness-critical finalists |

The selector combines subject-local need, expected marginal utility, redundancy, arm
dependencies, and storage/latency/compute/token/money budgets. Every arm ends in an
explicit `queue`, `retain`, `defer`, or `blocked` decision. Deferred generation is not
encoded as a missing row.

An arm has a policy-local recipe identity separate from its descriptor. Several model,
provider, preprocessor, parameter, or index arms may therefore produce the same
semantic descriptor while being scheduled and ablated independently.

This is a scheduler, not a feature cap. A future policy can add signals or arms
without changing entity identity or overwriting prior receipts.

## Multi-resolution LSH

One band layout can miss a useful candidate or flood a bucket. Taedri now emits three
parameterized and overlapping table families for both SimHash64 and MinHash16:

| Profile | SimHash64 | MinHash16 | Primary role |
|---|---|---|---|
| narrow | 8 bands × 8 bits, offsets 0/4 | 8 bands × 2 rows, offsets 0/1 | high-recall candidate union |
| medium | 4 × 16 bits, offsets 0/8 | 4 × 4 rows, offsets 0/2 | balanced default |
| wide | 2 × 32 bits, offsets 0/16 | 2 × 8 rows, offsets 0/4 | high-precision candidate arm |

Every key encodes version, algorithm, profile, width/rows, table, offset, and band. Query
receipts state which profiles matched. Each algorithm/profile is a separate typed
variant with its own content, assertion, lineage, lifecycle, and ablation surface;
the bucket keys remain disposable index rows. Policies may union profiles for recall,
intersect them for precision, cascade narrow to wide, enforce family quotas, or keep a
bypass lane. Exact distance, typed contracts, and verification still decide.

The labels `narrow`, `medium`, and `wide` are ergonomic only; the parameters are the
contract. Their operating points must be calibrated on real clone, containment,
hard-negative, and package-scale corpora.

## Monorepo boundary

One repository is the right default because the wire schema, conformance corpus,
ingestors, analyzers, indexers, APIs, and agent contracts must evolve together. It
does not imply one deployable or one Python package.

```text
packages/       versioned libraries and shared contracts
services/       independently deployable indexing and query processes
integrations/   MCP and coding-agent surfaces
apps/           human-facing explorers
architecture/   machine-checked component graph
schemas/        generated/exported public schema artifacts
deploy/         migrations, local stacks, observability, policy
eval/           real-package data, ablations, promotion receipts
docs/           specifications, reports, and rendered visuals
```

Registry-native primitives add `packages/primitive-registry` for capsule/revision/ref
contracts and `services/registry-api` for submissions and authorized pulls. A primitive
does not require its own repository or PyPI project. The detailed content-addressing,
forking, thin-pack, and deployment decision is in
[Primitive capsule registry and deployment evolution](PRIMITIVE_CAPSULE_REGISTRY_AND_DEPLOYMENT.md).

The current `src/taedri_codegraph` remains the working vertical slice. Empty moves
would create churn without isolation. New work should land in the target component,
and existing modules should be extracted behind conformance tests one boundary at a
time. `architecture/components.json` is the machine-readable map; an architecture
test checks path existence, dependency integrity, and acyclicity.

### Extraction sequence

1. Extract canonical values, identity, and provenance into `shared-kernel`.
2. Extract descriptor/predicate registries and fixtures into `shared-schemas`.
3. Move wheel acquisition and Python analysis behind stable adapter protocols.
4. Split canonical storage from query projections.
5. Move retrieval and compatibility into independent libraries.
6. Extract capsule/revision/ref contracts and their storage adapters.
7. Make indexer, query, and registry boundaries independently runnable behind versioned
   contracts; keep them in one deployable until a measured split gate passes.
8. Point MCP, skills, hooks, and the explorer only at the serving contracts.

Each step must preserve the current CLI and golden corpus until a replacement passes
the same tests and real-package evaluation.

## Remaining validation gates

- Run actual semantic embedding providers; the current lexical hash vector is not a
  semantic embedding.
- Compare narrow/medium/wide LSH individually, in union, and as cascades against exact
  distance on real clone and containment labels.
- Validate typed long-table storage in PostgreSQL and Parquet against the PyPDF
  footprint that exposed JSONL/SQLite duplication.
- Add remote PyPI Simple API and Git object acquisition receipts.
- Import real non-Python semantic indexes through SCIP/CPG/Tree-sitter adapters.
- Evaluate dynamic enrichment using equal-storage, equal-latency, and
  failure-inclusive verified-success budgets.
- Validate license, tenant, secrecy, retention, and deletion policy before any shared
  deployment.
