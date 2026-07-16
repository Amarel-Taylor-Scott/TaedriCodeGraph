# Taedri CodeGraph

**Repo:** `taedri-codegraph`
**Tagline:** Turn existing code into a language-neutral, evidence-backed graph that agents can search, trace, verify, and safely reuse.
**Primary first slice:** Exhaustively digest one large PyPI package into searchable code entities, evidence-bearing edges, black-box descriptions, context projections, and deterministic modification handles.
**Expansion path:** Other Python packages and environments, then npm, Maven, NuGet, crates.io, Go modules, RubyGems, native packages, repositories, services, and mixed-language systems.

## 1. Executive definition

Taedri CodeGraph is not a generic repository chatbot, a vector database over source chunks, or another code summarizer.

It is an **existing-code semantic compiler**. Given a precise package release, source snapshot, build environment, or workspace, it discovers and identifies every statically observable code entity; records what is known, inferred, observed, and verified about each entity; connects the entities with typed, evidence-linked edges; builds multiple exact, lexical, structural, graph, and semantic indexes; and serves the smallest useful black-box projection to humans, tools, and language models.

For a large PyPI package, the first target is:

```text
distribution / repository / installed environment
                    │
                    ▼
        immutable PackageSnapshot
                    │
                    ▼
  metadata + files + syntax + symbols + types + runtime probes
                    │
                    ▼
 packages, modules, classes, functions, methods, variables,
 parameters, fields, properties, decorators, tests, schemas,
 commands, effects, object families, examples, and groups
                    │
                    ▼
     Universal Code Entity Graph (UCEG)
                    │
                    ├── exact identity and occurrence indexes
                    ├── fielded lexical and fuzzy indexes
                    ├── structural fingerprints and LSH
                    ├── typed forward/reverse adjacency
                    ├── multi-view sparse/dense embeddings
                    ├── behavioral and evidence projections
                    └── compact CodeEntityCards
                    │
                    ▼
 search / trace / explain / impact / reuse / compose / modify
                    │
                    ▼
 deterministic verification + receipts + cheaper future context
```

The central result is that an agent should not need to reread 500 files or ask an LLM to rediscover a package’s architecture on every task. It should be able to ask:

- Which existing function already converts this input type to this output type?
- Which variables can influence this result?
- Which methods mutate this object’s state?
- What calls this private helper, directly or indirectly?
- Which tests, examples, and documentation substantiate this method’s behavior?
- Which entities perform network, filesystem, subprocess, database, secret, or global-state effects?
- Which public APIs would break if this parameter changed?
- Which five entities and twelve edges are sufficient context for this task?
- Is there already a verified route through the package that solves the requested capability?

The answer should normally be a compact graph slice and exact handles—not thousands of raw source tokens.

## 2. Project naming and internal vocabulary

### Recommended public name

**Taedri CodeGraph** is recommended because it is direct, retains the existing Taedri architecture continuity, and covers more than symbols. An exact GitHub repository-name check found no obvious `Taedri CodeGraph` or `taedri-codegraph` collision as of 2026-07-15. Generic `CodeGraph` is crowded, so the prefix should not be dropped. This is a repository-name check, not trademark or domain clearance.

### Stable internal terms

| Term | Meaning |
|---|---|
| `UCEG` | Universal Code Entity Graph: the language-neutral interchange kernel |
| `PackageSnapshot` | Immutable acquisition and environment boundary for one analysis |
| `CodeEntityID` / `CEID` | Collision-resistant sidecar identity; never a forced source rename |
| `CodeEntityCard` | Compact black-box description and expansion handles for one entity |
| `RelationAssertion` | Typed n-ary relationship assertion plus producer, scope, modality, evidence, and confidence |
| `CodeGroup` | Evidence-backed synthetic entity grouping related entities or edges |
| `CodeDemandIR` | Structured description of what a user or tool needs from existing code |
| `CodeSliceManifest` | Bounded set of entity/edge/detail handles selected for one task |
| `AnalysisManifest` | Exact inputs, tools, versions, configs, coverage, and output shards |
| `GraphEpoch` | Immutable published graph/index version |
| `ChangePlan` | Typed, impact-aware plan referencing exact entities and occurrences |
| `ChangeReceipt` | Evidence of source selection, edits, tests, effects, and final result |

Alternative names considered: Taedri SourceLattice, Taedri SymbolMesh, Taedri EntityWeave, Taedri CorpusGraph, Taedri SourceAtlas, and Taedri CodeLedger. `CodeGraph` is the clearest. `SymbolMesh` is too narrow; `SourceAtlas` underemphasizes executable relationships and proof; `CodeLedger` underemphasizes retrieval and graph composition.

## 3. Exact scope and the meaning of “every entity”

The project should promise **complete accounting of what each analysis layer attempted**, not impossible omniscience.

For a fixed package snapshot, Taedri should enumerate every parseable syntactic entity and occurrence it supports. It must then report how much semantic resolution, dynamic observation, and behavioral verification was achieved.

Python can generate names and objects dynamically through `eval`, `exec`, imports, decorators, descriptors, metaclasses, module `__getattr__`, monkey patching, native extensions, plugin discovery, and data-driven code generation. A program can create an unbounded number of runtime instances. Therefore:

- Taedri can exhaustively identify **declared and syntactically observable entities** in a fixed snapshot.
- It can resolve a large subset of **semantic bindings** under a pinned interpreter, dependency closure, platform, and configuration.
- It can record **potential dynamic entities and targets** as bounded candidate sets or unknowns.
- It can observe **runtime object shapes, calls, values, and effects** for a declared probe/test workload.
- It cannot enumerate every object that could ever exist for arbitrary future inputs.

The system should model constructors, classes, factories, protocols, object shapes, state machines, and observed instance families. Individual runtime objects are retained only when an observation or trace makes that identity useful.

### Completeness vocabulary

Every analysis family reports one of:

| State | Meaning |
|---|---|
| `not_attempted` | The analysis was outside the selected profile |
| `unsupported` | No suitable extractor exists for this language/artifact |
| `attempted_partial` | Some inputs or constructs could not be analyzed |
| `complete_for_declared_syntax` | Every supported syntactic construct in the snapshot was inventoried |
| `resolved_under_environment` | Bindings/types were resolved for the pinned environment |
| `observed_for_workload` | Runtime behavior was observed only for the declared workload |
| `verified_for_contract` | A claim passed a named independent oracle within a bounded scope |
| `unknown` | Evidence is insufficient; absence must not be interpreted as false |

This coverage ledger is part of every query response. An agent must be able to distinguish “no callers exist” from “no callers were found because dynamic dispatch was not analyzed.”

## 4. Entity universe for a Python package

### 4.1 Package and artifact entities

- Registry authority and package lineage.
- Normalized distribution name and original spelling.
- Release and version.
- Source distribution, wheel, installed distribution, editable install, and repository snapshot.
- Artifact hashes, wheel tags, build details, platform, interpreter, and dependency closure.
- Core metadata, extras, environment markers, entry points, project URLs, licenses, classifiers, and yanked state.
- Namespace packages and import packages, which are not assumed to map one-to-one to distribution packages.
- Native libraries, shared objects, generated sources, stubs, type information, and vendored code.

The PyPA core metadata specification defines distribution identity and fields such as dependencies, Python compatibility, project URLs, entry points, and license expressions; wheels also contain exact installation records and platform tags. Taedri stores those source facts rather than recreating them from prose. See the [Core Metadata](https://packaging.python.org/en/latest/specifications/core-metadata/), [Wheel](https://packaging.python.org/en/latest/specifications/binary-distribution-format/), [Entry Points](https://packaging.python.org/en/latest/specifications/entry-points/), and [Simple Repository API](https://packaging.python.org/en/latest/specifications/simple-repository-api/) specifications.

### 4.2 Source and namespace entities

- Repository, commit, tree, directory, file, notebook, generated file, and source map.
- Module, submodule, package, namespace, import alias, re-export, and `__all__` declaration.
- Conditional imports, optional dependency regions, version/platform guards, and plugin namespaces.
- Documentation page, README section, example block, changelog item, migration guide, and API reference section.
- Configuration file, schema, environment variable, command, resource, endpoint, event, and database object.

### 4.3 Type and object-model entities

- Class, metaclass, abstract base class, protocol, enum, named tuple, typed dictionary, dataclass, and generated model.
- Base class, mixin, trait-like protocol, generic type, type parameter, type alias, union, overload, and specialization.
- Constructor, alternate constructor, factory, singleton, registry, container, and object pool.
- Instance attribute, class attribute, descriptor, property, cached property, slot, field, validator, serializer, and computed field.
- Object-shape family and state machine.

### 4.4 Callable entities

- Function, nested function, lambda, method, class method, static method, abstract method, property accessor, descriptor hook, dunder method, coroutine, async generator, generator, callback, closure, and partial application.
- Overload declaration and implementation.
- Decorated callable before and after wrapping when mapping is available.
- Native/builtin callable boundary.
- CLI command, entry point, web handler, task, signal receiver, event consumer, plugin hook, test case, fixture, property test, benchmark, and oracle.

### 4.5 Variable and value entities

“Every variable” includes more than assignments:

- Module globals and constants.
- Imported bindings and aliases.
- Class variables and instance fields.
- Parameters, positional-only parameters, keyword-only parameters, variadic parameters, and type parameters.
- Local variables, closure cells, nonlocal/global declarations, loop targets, comprehension targets, exception targets, context-manager targets, pattern-match captures, and assignment-expression targets.
- Aliases and points-to sets.
- Literal values, enums, sentinels, default values, configuration values, environment-derived values, secrets, paths, URLs, SQL fragments, regular expressions, feature flags, and error codes when useful.
- Data-shape variables representing frames, tensors, arrays, tables, records, messages, schemas, or request/response bodies.

The graph does not create a globally renamed source variable. It assigns exact sidecar identities to bindings and occurrences while retaining the native spelling.

### 4.6 Synthetic CodeGroups

Raw code entities are necessary but insufficient. Taedri also creates evidence-linked group nodes:

- Public API surface.
- Import/export surface.
- Feature or subsystem.
- Object lifecycle/state machine.
- Request path or data pipeline.
- Initialization and teardown path.
- Error-handling family.
- Security/authentication/authorization boundary.
- Serialization/deserialization family.
- Test cluster and covered implementation slice.
- Documentation-to-code topic.
- Call-graph community.
- Co-change cluster from version history.
- Similar-behavior or interchangeable implementation family.
- Adapter/converter family.
- Effect domain: filesystem, network, database, subprocess, GPU, secret, global state.
- Performance-critical hot path.
- Deprecated/migration surface.
- Verified route macro that composes several existing entities.

Groups never replace members. They are additional nodes with membership criteria, evidence, validity scope, and expansion handles.

## 5. Native names plus collision-resistant sidecar identity

### 5.1 Why source renaming is rejected

Renaming all variables and functions to globally unique source names would break or destabilize:

- public imports and keyword-call APIs;
- reflection, `getattr`, module `__getattr__`, dependency injection, and plugin lookup;
- pickling, serialization, ORM fields, validation aliases, and wire schemas;
- FFI, native extensions, ABI boundaries, and generated bindings;
- stack traces, profiling, coverage, examples, documentation, and developer workflows;
- downstream patches and upgrades;
- string-based configuration and dynamic dispatch.

Global uniqueness belongs in the graph, not in source spelling.

### 5.2 Identity lattice

No single ID can safely mean all forms of “same code.” Use separate identities:

| Identity | Scope |
|---|---|
| `PackageLineageID` | Registry package family independent of version |
| `ReleaseID` | Exact package release |
| `SourceSnapshotID` | Exact source revision/tree/content |
| `DistributionID` | Exact wheel, sdist, archive, image, or binary bytes |
| `BuildID` | Artifact plus recipe, toolchain, platform, inputs, and dependency closure |
| `FileContentID` | Exact file bytes |
| `OccurrenceID` | Exact byte range, role, and file content |
| `RevisionEntityID` | Entity resolved inside one snapshot/build/environment |
| `ConceptID` | Revisable logical lineage across renames/refactors/releases |
| `BehaviorID` | Behavior under a bounded input/environment/oracle contract |
| `RuntimeObjectID` | One observed object within one trace/session, never global logical identity |

### 5.3 CEID construction

```text
CEID =
  "uceg:v1:" + entity_kind + ":" +
  base32(sha256(canonical_cbor(identity_key)))
```

The full canonical identity key is stored beside the digest and compared on insertion. The digest is an index key, not the only record of identity.

For a Python callable, the identity key can include:

```yaml
registry_authority: https://pypi.org
distribution: sqlalchemy
release: <exact-version>
source_snapshot: swh:1:rev:...
artifact_digest: sha256:...
python_version: 3.14
platform_tag: ...
language: python
entity_kind: method
module: sqlalchemy.orm.session
descriptor_path: [Session, execute]
structured_signature: ...
locator_scheme: scip-python-vN
```

Local variables additionally bind to the containing revision entity, exact defining occurrence, lexical scope, and role. Cross-version local-variable equivalence is a probabilistic lineage claim, never silently promoted to exact identity.

## 6. Universal Code Entity Graph kernel

The architecture is **native facts + minimal kernel + purpose-specific projections**.

Do not build one universal AST. Preserve the Python AST, symbol table, lossless concrete syntax tree, type-checker facts, SCIP index, CodeQL database, runtime traces, test results, and package metadata. Normalize only the facts needed for identity, retrieval, evidence, and composition.

### 6.1 Core records

```yaml
PackageSnapshot:
  snapshot_id: ...
  registry_authority: ...
  package_lineage_id: ...
  release_id: ...
  source_snapshot_id: ...
  distributions: []
  repository_origin: ...
  interpreter: ...
  platform: ...
  dependency_lock_digest: ...
  build_manifest_ref: ...
  policy_and_license_ref: ...
```

```yaml
EntityEnvelope:
  revision_entity_id: ...
  concept_id: optional
  package_snapshot_id: ...
  entity_kind_key: "uceg.entity.python.method"
  language_key: "uceg.language.python"
  native_name_assertion_refs: []
  occurrence_refs: []
  aspect_assertion_refs: []
  native_fact_refs: []
  lifecycle_assertion_refs: []
```

The envelope intentionally does not canonically bake in signatures, ports, effects, visibility, storage, runtime, or object semantics. Those live in extensible `CallableAspect`, `TypeAspect`, `StorageAspect`, `ModuleAspect`, `ClassAspect`, `RuntimeObjectAspect`, `PolicyAspect`, and future aspect assertions. Hot serving columns may mirror stable aspects, but the assertions remain canonical.

```yaml
Occurrence:
  occurrence_id: ...
  entity_id: optional
  file_content_id: ...
  byte_range: [start, end]
  line_column_projection: optional
  roles: [definition, reference, read, write, call]
  enclosing_entity_id: ...
  syntax_path: ...
  generated_from: optional
  producer: ...
```

```yaml
RelationAssertion:
  relation_key_id: ...
  edge_assertion_id: ...
  predicate_descriptor_id: "uceg.predicate.calls_may@1"
  participant_refs:
    - {role_key: "uceg.role.caller", ref: entity:...}
    - {role_key: "uceg.role.callee", ref: entity:...}
    - {role_key: "uceg.role.callsite", ref: occurrence:...}
  relation_node_id: optional
  modality: asserted|extracted|inferred|observed|verified
  polarity: positive|negative|unknown
  quantifier: may|must|observed|not_applicable
  producer_id: ...
  producer_version: ...
  analysis_manifest_id: ...
  confidence: optional
  calibration_version: optional
  evidence_refs: []
  snapshot_scope: ...
  build_scope: optional
  workload_scope: optional
  valid_time: ...
  transaction_time: ...
  access_and_license_class: ...
```

Binary subject/object edges are optional serving projections of `RelationAssertion`; they are not canonical relation truth.

Descriptions use the shared `ProjectionEnvelope` defined in section 8 and the specialized `DescriptionAssertion` contract in section 11. Original docstrings/comments are source assertions; generated descriptions are derived projections and never replace them.

```yaml
CoverageLedger:
  snapshot_id: ...
  relation_or_entity_family: ...
  attempted_inputs: ...
  successful_inputs: ...
  unresolved_inputs: ...
  unsupported_constructs: []
  completeness_state: ...
  extractor_versions: []
```

### 6.2 N-ary relations

Binary property graphs lose critical detail. Calls, data flows, mutations, tests, builds, and runtime observations should be relation nodes.

```yaml
CallRelation:
  callsite_occurrence: ...
  caller: ...
  candidate_callees: []
  receiver_candidates: []
  argument_bindings: []
  return_binding: optional
  dispatch_kind: static|virtual|dynamic|reflection|native|unknown
  resolution_kind: compiler|static|runtime|heuristic
  may_or_must: ...
  observed_counts: optional
```

```yaml
MutationRelation:
  mutator_entity: ...
  target_entity_or_state_slot: ...
  prior_state_constraint: optional
  new_state_expression: optional
  condition: optional
  effect_domain: ...
  reversibility: ...
  idempotency: ...
```

```yaml
BehaviorObservation:
  subject: ...
  build_id: ...
  workload_id: ...
  input_shape_or_digest: ...
  environment_digest: ...
  result_shape_or_digest: ...
  observed_calls: []
  observed_reads_writes: []
  observed_effects: []
  status: ...
  oracle_result: ...
  uncertainty: ...
```

### 6.3 Evidence and serving lifecycle

Extraction, verification, and product serving are distinct states. Use an explicit monotone-by-evidence lifecycle; revocation or staleness can always demote serving eligibility without erasing history.

| Level | Meaning |
|---|---|
| `L0 raw` | acquired bytes, external reference, or analyzer payload; not normalized |
| `L1 candidate` | candidate entity/card/edge exists but may be incomplete or duplicated |
| `L2 structured` | identity, schema/aspects, occurrences, ports, and core edges validate |
| `L3 source_backed` | decisive claims link to exact source/native analyzer evidence |
| `L4 tested` | named static/dynamic oracle passed in a declared scope |
| `L5 promoted` | policy permits the record to serve as trusted current evidence |
| `L6 preferred` | measured preferred entity/group/adapter/route for a named demand profile |

Keep `candidate=true`, `serves_truth=false` until the applicable promotion gate passes. `L6` is contextual and reversible: safest, fastest, minimal-dependency, standards-first, or cheapest profiles may prefer different implementations. Candidate, checked, verified, served, adopted, and repeat-reused are separate outcome fields, not aliases.

## 7. Edge ontology

The ontology is open and namespaced; there is no hard cap on relation types. The first stable kernel includes:

Every predicate and participant role is itself registered:

```yaml
PredicateDescriptor:
  predicate_key: "uceg.predicate.calls_may"
  immutable_version: 1
  descriptor_digest: ...
  arity: {minimum: 2, maximum: unbounded}
  required_roles: [caller, callee]
  optional_roles: [callsite, receiver, argument, result]
  role_kind_constraints: []
  directionality: directed
  inverse_predicate_key: "uceg.predicate.called_by_may"
  symmetric: false
  transitive: false
  allowed_quantifiers: [may, observed]
  allowed_modalities: [extracted, inferred, observed, verified]
  canonicalization_ref: ...
  inference_and_index_policy: ...
```

`RelationRoleDescriptor` defines each role key, allowed subject kinds, cardinality, ordering/ordinal semantics, and canonicalization. Only trusted predicate descriptors may authorize inverse projections, symmetry/transitivity, role reordering, or direction-normalized hashes.

### Structural and namespace

- `contains`, `contained_by`, `declares`, `defines`, `member_of`, `encloses`.
- `imports`, `imports_conditionally`, `reexports`, `exports`, `aliases`, `shadows`.
- `generated_from`, `compiled_into`, `packaged_as`, `installed_as`.

### Binding and occurrence

- `references`, `binds`, `reads`, `writes`, `deletes`, `captures`, `escapes`.
- `aliases_value`, `points_to_may`, `points_to_must`, `same_occurrence_family`.
- `definition_of`, `declaration_of`, `callsite_of`, `decorates`.

### Type and object model

- `type_of`, `accepts`, `returns`, `yields`, `raises`, `narrows_to`, `converts_to`.
- `extends`, `implements`, `conforms_to`, `overrides`, `overloads`, `specializes`.
- `constructs`, `factory_for`, `instance_of`, `descriptor_for`, `property_of`.

### Execution and control

- `calls_may`, `calls_must`, `dispatches_to`, `awaits`, `spawns`, `schedules`.
- `control_flows_to`, `dominates`, `postdominates`, `guards`, `handles_error_from`.
- `enters`, `exits`, `initializes`, `tears_down`, `registers`, `unregisters`.

### Data and mutation

- `data_flows_to`, `derived_from`, `transforms`, `serializes`, `deserializes`.
- `mutates`, `may_mutate`, `invalidates`, `caches`, `memoizes`, `synchronizes`.
- `reaching_definition`, `taints`, `sanitizes`, `validates`, `normalizes`.

### Effects and capabilities

- `reads_file`, `writes_file`, `opens_network`, `queries_database`, `starts_subprocess`.
- `reads_secret`, `writes_global_state`, `uses_gpu`, `allocates_large_memory`, `blocks_thread`.
- `requires_capability`, `requires_permission`, `idempotent_under`, `compensated_by`.

### Documentation, tests, and evidence

- `documents`, `example_of`, `claims_behavior`, `claims_parameter`, `contradicted_by`.
- `tests`, `covers`, `uses_fixture`, `uses_oracle`, `observed_pass`, `observed_fail`.
- `supports_claim`, `refutes_claim`, `derived_from_evidence`, `verified_by`.

### Lineage and similarity

- `renamed_from`, `moved_from`, `extracted_from`, `inlined_from`, `split_into`, `merged_from`.
- `forked_from`, `supersedes`, `deprecated_by`, `same_concept_as`.
- `lexically_similar`, `structurally_similar`, `behaviorally_similar`, `substitutable_under`.

### Search and composition

- `satisfies_demand`, `composes_with`, `adapter_for`, `requires_predecessor`.
- `historically_selected_for`, `historically_succeeded_on`, `failed_on`, `misleading_match_for`.
- `member_of_group`, `grouped_by_call_community`, `grouped_by_cochange`, `grouped_by_effect`.

Every edge is directional. Reverse adjacency is materialized or computed consistently. Negative edges and unknowns are first-class; silence is never proof of incompatibility.

## 8. Extensibility is a kernel property, not an afterthought

The stable data model must remain small while the descriptive surface can grow without a ceiling. Taedri should not add a nullable database column every time a new analyzer, embedding model, compatibility rule, hash family, description, language, or research idea appears.

The stable kernel contains only:

- immutable identity and graph-epoch scope;
- the subject or relation being described;
- a namespaced extension key and schema version;
- a typed value or content-addressed payload reference;
- producer, configuration, derivation, evidence, modality, and confidence;
- access, license, retention, and freshness policy;
- validity and transaction time;
- optional index and comparator declarations.

Everything else is a versioned extension assertion or a reproducible projection.

### 8.1 Universal extension descriptor

```yaml
ExtensionDescriptor:
  extension_key: "uceg.compatibility.python.type_assignability"
  descriptor_version: "1.2.0"
  authority: "https://taedri.dev/registry"
  applies_to:
    subject_kind_keys: ["uceg.subject.entity", "uceg.subject.port", "uceg.subject.relation"]
    entity_kind_keys: ["uceg.entity.callable", "uceg.entity.python.method"]
    language_keys: ["uceg.language.python"]
  value_schema:
    schema_uri: "uceg-schema://compatibility/python/type-assignability/1.2.0"
    schema_digest: "sha256:..."
    wire_type: structured
    cardinality: repeated
    units: null
  semantics:
    human_definition: "..."
    machine_interpretation_ref: "cas://..."
    missing_value_semantics: unknown
    merge_semantics: retain_parallel_assertions
  canonicalization:
    canonicalizer_id: "uceg.c14n.type-expr.python"
    canonicalizer_version: "3.0.1"
  indexing:
    exact: true
    range: false
    lexical_fields: []
    lsh_families: []
    embedding_families: []
    graph_projection: true
  compatibility:
    evaluator_ids: ["uceg.eval.python.assignability"]
    hard_gate_capability_hint: true
  governance:
    status: experimental|stable|deprecated
    supersedes: []
    privacy_class: public
    license_class: metadata_only
```

Keys use reverse-domain or URI-like namespaces. Subject kinds are also registered and additive, covering entities, occurrences, artifacts, snapshots, build universes, ports, relations, groups, routes, signatures, assessments, evidence, models/tools, indexes, receipts, and future objects. A registry validates ownership, schema compatibility, canonicalization, and index cost. Private organizations can mount their own registry and overlays without minting public meanings.

An extension cannot grant itself hard-rejection or auto-use authority. `hard_gate_capability_hint` only declares intended use; actual authority requires stable/trusted registry promotion, evaluator conformance tests, calibration or proof rules, and explicit policy allowlisting.

### 8.2 Universal feature assertion

```yaml
FeatureAssertion:
  feature_assertion_id: ...
  subject_ref: {subject_kind_key: "uceg.subject.relation", id: ...}
  extension_key: "org.example.compatibility.tensor.layout"
  descriptor_version: "2.0.0"
  typed_value:
    enum_value: contiguous_c
  payload_ref: optional
  modality: extracted
  polarity: positive
  producer: {id: tensor-analyzer, version: 4.1.0, config_digest: ...}
  derivation_refs: []
  evidence_refs: []
  scope: {snapshot_id: ..., build_id: ..., workload_id: optional}
  confidence: optional
  calibration_version: optional
  access_and_license_class: ...
  valid_time: ...
  transaction_time: ...
```

`FeatureAssertion` carries atomic typed claims: attributes, compatibility-dimension values, semantic roles, and graph metrics. Hot stable fields can be materialized as typed columns for speed, but the assertion remains canonical.

All derived descriptions, hashes, embeddings, cards, bundles, and search documents share a `ProjectionEnvelope`:

```yaml
ProjectionEnvelope:
  projection_id: ...
  subject_ref: {subject_kind_key: ..., id: ...}
  projection_key: ...
  projection_schema_version: ...
  input_fact_and_assertion_refs: []
  input_projection_refs: []
  generator: {id: ..., version: ..., config_digest: ...}
  coverage_refs: []
  evidence_refs: []
  access_policy_ref: ...
  derived_tenant_license_retention_class: ...
  invalidation_keys: []
  index_manifest_id: optional
  supersedes_projection_ids: []
  graph_epoch: ...
```

Specialized records such as `DescriptionAssertion`, `FingerprintProjection`, `EmbeddingProjection`, `EdgeFeatureBundle`, and `CodeCapsule` extend this envelope with typed payload fields. They are not duplicated as atomic `FeatureAssertion`s.

The projection’s tenant, ACL, license, retention, residency, and disclosure policy is the conservative join of every input; a derived summary or vector cannot be less restricted merely because it omits literal source text. Reverse dependency references drive invalidation.

### 8.3 Extension families

The initial registries are:

| Registry | Examples |
|---|---|
| Entity kinds and aspects | Python descriptor, SQL view, tensor, HTTP endpoint, test oracle |
| Predicates and relation roles | caller, argument, candidate callee, source value, sink |
| Ports and contracts | input, output, error, event, state, effect, capability |
| Attribute schemas | units, shape, mutability, ownership, complexity, deprecation |
| Compatibility dimensions | type assignability, schema evolution, async mode, policy |
| Compatibility evaluators | Python type checker, JSON Schema comparator, unit converter |
| Description views | synopsis, behavior, risks, negative use cases, examples |
| Fingerprint algorithms | MinHash, SimHash, AST path, graph neighborhood, behavior trace |
| Embedding models and views | source, docs, ports, edges, graph neighborhoods, traces |
| Index providers | exact, BM25, bitmap, range, LSH, ANN, graph, temporal |
| Scorers and rerankers | deterministic fusion, learned ranker, cross-encoder, LLM judge |
| Analyzers and evidence types | AST, compiler, SCIP, CodeQL, test, trace, human review |
| Policies and controls | tenant, license, data residency, source disclosure, execution |

There is no hard-coded maximum number of features, views, or embedding models. Budgets, storage tiers, and promotion rules control what is materialized.

### 8.4 Additive evolution rules

1. Never reinterpret an existing extension key. Publish a new descriptor version or key.
2. Never overwrite a feature generated by another producer. Retain parallel assertions.
3. Never make a derived feature part of exact entity identity.
4. Never compare vectors produced by different model revisions unless a declared alignment exists.
5. Never treat missing as false, zero, empty, compatible, or incompatible without the descriptor explicitly saying so.
6. Never delete an old model’s projection merely because a new model exists; retire it through epoch and retention policy.
7. Every materialized index has an `IndexManifest` that lists exact inputs, descriptor versions, algorithm parameters, shards, and reproducibility status.
8. Promotion from experimental to stable requires test vectors, calibration data, backward-compatibility rules, and cost measurements.

Protocol Buffers can carry the stable cross-language envelopes, with immutable field numbers and reserved retired fields; large or novel payloads live in typed, schema-addressed content-addressed blobs. JSON-LD-style contexts are useful at import/export boundaries for external vocabulary mapping, but internal queries should resolve keys to registry IDs rather than repeatedly processing contexts. Arrow extension types and typed feature tables can preserve efficient analytical representations. These choices follow the compatibility discipline in the [Protocol Buffers language guide](https://protobuf.dev/programming-guides/proto3/), the vocabulary-linking model in [JSON-LD 1.1](https://www.w3.org/TR/json-ld/), and the extensible physical/logical type split in [Apache Arrow extension types](https://arrow.apache.org/docs/python/extending_types.html).

## 9. Edges are first-class searchable objects

An edge is not only `(subject, predicate, object)`. It is a queryable, describable, comparable, versioned claim with endpoints, participant roles, constraints, evidence, compatibility surfaces, and multiple retrieval projections.

Use three identities rather than an overloaded `EdgeID`:

- `RelationKeyID`: hash of the canonical scoped proposition—participants, roles, predicate/quantifier semantics, and snapshot/build scope—independent of producer, evidence, or asserted polarity;
- `EdgeAssertionID`: immutable hash of relation key plus producer, analysis, evidence, modality, polarity, and validity;
- `EdgeSearchDocumentID`: disposable projection identity over selected assertions, endpoint fields, descriptions, features, and index configuration.

Multiple analyzers can publish separate assertions about the same relation key. A reconciled `EdgeView` may group them without discarding disagreement. Rebuilding an embedding, field weight, or description changes a search-document/projection ID, never the relation or assertion identities.

### 9.1 Edge record and feature bundle

```yaml
SearchableEdge:
  projection_envelope_ref: ...
  edge_search_document_id: ...
  relation_key_id: ...
  edge_assertion_ids: []
  edge_class: asserted_relation|materialized_compatibility
  relation_family: data_flow
  predicate_key: "uceg.edge.data_flows_to"
  participant_refs:
    - {role: source, ref: port:...}
    - {role: sink, ref: port:...}
    - {role: transfer_site, ref: occurrence:...}
  direction: source_to_sink
  inverse_predicate_key: "uceg.edge.receives_data_from"
  endpoint_kind_signature: "return_port->parameter_port"
  constraint_refs: []
  feature_bundle_refs: []
  description_view_refs: []
  compatibility_signature_refs: []
  fingerprint_refs: []
  embedding_refs: []
  evidence_refs: []
  coverage_refs: []
  projection_lifecycle: current|superseded|deprecated|rejected
  graph_epoch: ...
```

Unverified potential pairs are `CompatibilityAssessment` search hypotheses, not `SearchableEdge` adjacency. A potential pair enters canonical/materialized compatibility adjacency only through a permitted verdict, evidence policy, and exact promotion receipt. Assertion modality/polarity remains separate from projection lifecycle.

```yaml
EdgeFeatureBundle:
  projection_envelope_ref: ...
  bundle_id: ...
  relation_key_id: ...
  edge_assertion_ids: []
  bundle_schema_version: ...
  exact_keys: []
  blocking_keys: []
  feature_assertion_refs: []
  fingerprint_refs: []
  embedding_refs: []
  description_view_refs: []
  compatibility_signature_refs: []
  graph_stat_refs: []
  negative_constraint_refs: []
  index_membership_refs: []
  producer_and_derivation: ...
```

Bundles and search documents are immutable content-addressed projections. Adding a new embedding, hash, or description creates a new `BundleID` and `EdgeSearchDocumentID` with `supersedes_projection_ids`; the epoch manifest selects the current projection. Nothing is appended in place under an existing projection ID.

### 9.2 Exact and fielded search keys

Every edge should expose as many applicable exact keys as can be defended:

- exact `RelationKeyID`, `EdgeAssertionID`, `EdgeSearchDocumentID`, relation-node ID, snapshot, build, producer, and evidence digest;
- ordered endpoint IDs and participant-role tuple; unordered endpoint keys only when the predicate descriptor permits them; source and target occurrences;
- predicate, inverse predicate, predicate family, modality, polarity, may/must, lifecycle;
- endpoint kind pair, port direction pair, language pair, package/module/file pair;
- canonical qualified-name pair and structured-signature pair;
- input/output type IDs, normalized schema IDs, shape IDs, unit IDs, serialization IDs;
- effect, capability, permission, exception, state-transition, and environment keys;
- test, documentation, trace, workload, issue, commit, and change-set keys;
- version ranges, dependency markers, platform tags, interpreter/compiler versions;
- tenant, license, source-disclosure, residency, and policy labels;
- source/destination group IDs, motif IDs, route IDs, and adapter family IDs.

Fielded BM25 indexes native names, aliases, docstrings, edge descriptions, endpoint summaries, errors, effects, examples, negative use cases, and evidence text separately. Field weights depend on query intent: an exact error message should not compete equally with a general behavior summary.

### 9.3 CompatibilitySignature

A compatibility signature is a sparse set of typed assertions, not a fixed struct with every future dimension baked in.

```yaml
CompatibilitySignatureFamily:
  family_id: ...
  subject_ref: {subject_kind_key: "uceg.subject.port", id: ...}
  variant_ids: []
  graph_epoch: ...

CompatibilitySignatureVariant:
  signature_variant_id: ...
  family_id: ...
  orientation: provides|requires|bidirectional
  activation_constraints: []
  dimension_feature_assertion_ids:
    - feature:uceg.compat.type.canonical:...
    - feature:uceg.compat.effect.filesystem_write:...
    - feature:org.example.compat.tensor.device:...
  coverage_refs: []
  canonical_digest: ...
  producer_suite: ...
  graph_epoch: ...

CompatibilityRequirementSet:
  requirement_set_id: ...
  purpose: compose_output_to_input
  required_dimensions: []
  preferred_dimensions: []
  prohibited_values: []
  obligation_and_loss_policy: ...
  authority_policy_ref: ...
```

Signatures contain evidence-backed values only. Whether a dimension is required, preferred, prohibited, or a hard gate belongs to the purpose/demand/policy-specific `CompatibilityRequirementSet`.

Initial compatibility dimensions should cover at least the following. Each item is an independent, namespaced dimension and may have language- or domain-specific subdimensions.

#### Value, type, and schema

- nominal and structural type identity;
- subtype/supertype, variance, generics, bounds, overloads, protocols, and traits;
- nullability, optionality, sentinel conventions, missing versus null;
- scalar domain, numeric range, precision, signedness, endianness, encoding;
- record fields, required fields, aliases, defaults, additional-field policy;
- collection element/key/value type, cardinality, uniqueness, and ordering;
- tensor/array/table dimensions, symbolic shapes, rank, axes, dtype, sparsity, layout;
- units, coordinate/reference systems, locale, timezone, currency, and scale;
- serialization/wire format, media type, compression, schema version, framing;
- validation constraints, predicates, preconditions, postconditions, and invariants.

#### Invocation and control

- parameter name, position, keyword rules, variadic behavior, and default behavior;
- sync, async, coroutine, generator, stream, callback, event, batch, and interactive modes;
- eager/lazy, push/pull, request/response, duplex, backpressure, cancellation, timeout;
- blocking/non-blocking behavior and event-loop/thread affinity;
- lifecycle phase, initialization prerequisites, teardown obligations, state transition;
- reentrancy, thread safety, process safety, signal safety, transaction context;
- determinism, ordering guarantees, idempotency, retry safety, deduplication semantics.

#### Ownership, state, and effects

- borrowed/owned/shared/unique lifetime, mutability, copy/view/alias behavior;
- allocation, memory tier, device placement, cache invalidation, resource cleanup;
- filesystem, network, database, subprocess, GPU, clock, randomness, environment, secret, and global-state effects;
- read/write resource patterns, transaction/isolation level, lock expectations;
- capability and permission requirements, privilege level, authentication state;
- reversibility, compensation, rollback, at-most-once/at-least-once/exactly-once claims.

#### Failure and uncertainty

- declared and observed exceptions, error codes, status variants, partial-result modes;
- retryable/permanent/ambiguous failure, fallback, circuit-breaker, poison-message behavior;
- may/must/observed modality, confidence, coverage, path condition, workload scope;
- dynamic dispatch, reflection, native boundary, unknown target, unverified behavior.

#### Environment, supply chain, and policy

- package/dependency/version ranges and mutually exclusive extras/features;
- language/runtime/compiler/ABI/platform/architecture/OS constraints;
- hardware/accelerator, memory/disk/network resource bounds and latency/throughput class;
- license compatibility, provenance, trust tier, vulnerability and deprecation state;
- tenant/ACL, data classification, privacy, residency, retention, export, and egress policy;
- permitted source disclosure and whether remote models may receive bodies, summaries, or only hashes.

#### Semantic fit and operational quality

- capability, domain role, intended use, explicitly unsupported use, and semantic ontology terms;
- information loss, approximation, stability, monotonicity, commutativity, associativity;
- quality, accuracy, freshness, performance envelope, cost, availability, and rate limits;
- evidence strength, test coverage, production history, user acceptance, and staleness.

Unknown dimensions remain unknown. A compatibility evaluator must not silently coerce them into a match.

#### Signature variants, purposes, and verdict lattice

Do not average mutually exclusive overloads, platforms, configurations, dependency extras, or protocol states into one permissive signature. Publish a `CompatibilitySignatureVariant` for each defensible conjunctive contract and attach activation constraints. The query planner evaluates only variants satisfiable in the requested environment.

Every assessment declares a purpose because the rules differ:

- `compose_output_to_input`;
- `substitute_implementation`;
- `override_method`;
- `serialize_across_boundary`;
- `migrate_version`;
- `call_in_environment`;
- `test_as_oracle`.

For substitution of `Q` for required implementation `R`, the conservative rule family is:

```text
Pre_R  implies Pre_Q
Post_Q implies Post_R
Effects_Q subset_of AllowedEffects_R
Errors_Q  subset_of AllowedErrors_R
Resources_Q within Budget_R
Protocol_Q refines Protocol_R
Environment_Q is satisfiable
```

Expose a user-facing verdict lattice rather than only one score, but derive it from orthogonal stored dimensions:

| Verdict | Meaning and automatic-use policy |
|---|---|
| `exact` | Canonical required facets match in scope; eligible for auto-use under policy |
| `proved_refinement` | Deterministic native-aware rules prove directional refinement |
| `verified_lossless_adapter` | Endpoint-bound verified adapter closes every required gap without declared loss |
| `verified_lossy_adapter` | Adapter works with declared information/quality loss; demand must explicitly permit it |
| `conditional` | Named obligations, runtime checks, or environment conditions remain |
| `empirical` | Bounded tests/traces support compatibility only in a declared domain |
| `semantic_candidate` | Search hypothesis worth assessing; never auto-wirable |
| `incompatible` | At least one authoritative required dimension fails |
| `unknown` | Evidence or evaluator coverage is insufficient |

Only `exact`, `proved_refinement`, and policy-approved verified adapter results can be used automatically. `Conditional` first requires receipted obligation discharge. Scores rank candidates inside a verdict/risk class; they never average a security failure into a pass. Because an assessment can be simultaneously adapter-mediated, empirical, conditional, and lossy, the table labels are views—not the canonical storage enum.

### 9.4 Compatibility assessment

Binary comparison features live in a lazy `PairFeatureBundle`, distinct from unary signatures. It records exact facet comparisons, directional differences, candidate-generator reasons, adapters considered, and unresolved predicates for one producer/consumer/purpose/context tuple. It is computed only for a bounded candidate set and can be discarded or cached independently.

```yaml
CompatibilityAssessment:
  assessment_id: ...
  provided_signature_variant_id: ...
  required_signature_variant_id: ...
  purpose: compose_output_to_input
  requirement_set_id: ...
  demand_constraint_digest: ...
  environment_profile_digest: ...
  policy_epoch: ...
  graph_epoch: ...
  evidence_and_reconciliation_epoch: ...
  adapter_graph_epoch: ...
  evaluator_suite_id: ...
  evaluator_suite_version: ...
  evaluator_config_digest: ...
  relation_verdict: direct_exact|refinement|adapter_required|incompatible|unknown
  evidence_grade: proved|verified_empirical|observed|inferred|unknown
  obligation_status: discharged|pending|failed|not_applicable
  adapter_lossiness: none|lossless|lossy|unknown
  auto_use_decision: allow|deny|requires_verification
  display_label: derived
  dimension_results:
    - dimension_key: "uceg.compat.type.canonical"
      outcome: compatible
      requirement_severity: hard
      reason_code: structural_subtype
      evidence_refs: []
    - dimension_key: "uceg.compat.units"
      outcome: compatible_with_adapter
      adapter_candidates: [entity:...]
  unsatisfied_hard_dimensions: []
  unresolved_predicates: []
  contradiction_refs: []
  minimal_unsat_or_unknown_core: []
  adapter_route_refs: []
  information_loss: optional
  risk_score: ...
  probability_verified_success: optional
  probability_calibration_version: optional
  cache_key: sha256(provided_variant|required_variant|purpose|demand|environment|policy_epoch|graph_epoch|evidence_epoch|adapter_epoch|suite_config)
  expires_or_invalidates_on: []
```

Compatibility is directional and contextual. “A fits B” may not imply “B fits A.” An adapter can make two ports compatible while introducing cost, loss, latency, failure modes, or policy violations. Those costs become edges and constraints in route solving.

### 9.5 Avoiding the all-pairs explosion

Do not materialize compatibility for every pair of ports or entities. For `N` ports, an all-pairs table is `O(N^2)` and mostly useless.

Use this sparse strategy:

1. Store one signature family per subject and independently indexed variants, plus independent extension projections.
2. Generate coarse blocking keys: direction, port kind, type family, schema family, effect class, execution mode, environment, package boundary, and policy class. Maintain an explicit `unknown` posting for every high-recall block family.
3. Apply bitmap and typed range intersections to eliminate impossible candidates.
4. Probe exact signature and known-adapter indexes.
5. Use LSH, structural, graph, lexical, and embedding candidates only within plausible blocks.
6. Run the declared compatibility evaluators on demand.
7. Cache the assessment by both variant digests, purpose, demand/environment, evaluator suite/config, policy, evidence/reconciliation, adapter-graph, and graph epochs.
8. Persist verified or frequently used compatibility edges; let low-value speculative pairs expire.
9. Invalidate only assessments whose input signatures, evaluator, adapter graph, or policy changed.

Observed calls, assignments, test fixtures, pipelines, and successful historical routes seed high-value compatibility edges. Negative assessments are cached too, with the reason and coverage scope.

Only authoritative hard evidence may exclude at the blocking stage. Missing or low-authority values enter explicit unknown canopies and are progressively broadened under query budgets. Randomly sample blocked-out pairs for full offline assessment to estimate hidden false negatives.

## 10. Hash, LSH, embedding, and graph feature atlas

No single similarity representation is adequate. Each edge, endpoint, entity, group, description, and route may carry multiple feature records produced from different views.

### 10.1 FingerprintProjection

```yaml
FingerprintProjection:
  projection_envelope_ref: ...
  fingerprint_id: ...
  subject_ref: {subject_kind_key: "uceg.subject.relation", id: ...}
  fingerprint_key: "uceg.fp.edge.wl_neighborhood"
  algorithm_id: ...
  algorithm_version: ...
  parameters: {radius: 2, rounds: 3, seed: 17}
  input_fact_and_assertion_refs: []
  input_view_ids: []
  preprocessing_digest: ...
  value_bytes_or_ref: ...
  bands_or_buckets: []
  invariances: [alpha_rename, source_location]
  known_non_invariances: [predicate_direction, type_change]
  collision_policy: candidate_only
  producer_and_evidence: ...
  coverage_refs: []
  access_policy_ref: ...
  derived_tenant_license_retention_class: ...
  invalidation_keys: []
  index_manifest_id: ...
  graph_epoch: ...
```

### 10.2 Exact and locality-sensitive fingerprint families

| Family | Candidate use | Important limitation |
|---|---|---|
| Cryptographic content hash | Exact bytes, canonical records, signatures, evidence | No graded similarity |
| Direction-normalized edge hash | Exact or inverse-equivalent relations | Canonicalization bugs create false distinctions |
| Canonical signature/schema hash | Exact interface candidate | Exact schema equality is not semantic compatibility |
| Token winnowing/fingerprints | Copied or locally edited code | Sensitive to tokenization and generated boilerplate |
| Shingle MinHash | Jaccard-like set similarity for tokens, paths, fields, neighbors | Candidate generator; ignores multiplicity/order unless encoded |
| Weighted MinHash | Weighted feature-set similarity | Weight/canonicalization choices dominate result |
| SimHash | Hamming-near similarity of weighted lexical/feature vectors | Different semantics can collide; threshold is corpus-specific |
| Random-hyperplane LSH | Cosine-similar sparse/dense features | Approximate and model/view specific |
| Cross-polytope or multiprobe LSH | Higher-quality angular candidates | More implementation and tuning complexity |
| p-stable LSH | Euclidean-distance candidates | Only meaningful for a calibrated vector space |
| TLSH or similar fuzzy digest | Near-similar byte/code artifacts | Not for tiny inputs; not proof of source or behavior identity |
| Bloom/Xor/Cuckoo filters | Fast membership and block rejection | False positives or update constraints; never compatibility proof |
| AST/CST subtree multiset hash | Structurally similar implementation | Parser/language/version specific |
| Normalized control-flow hash | Similar control structure | Can miss semantic changes in predicates and calls |
| Data-flow/path fingerprint | Similar transformations and dependencies | Precision depends on alias and call resolution |
| API-surface fingerprint | Similar ports, errors, effects, docs | A coarse black-box approximation |
| Weisfeiler-Lehman neighborhood hash | Similar typed local graph neighborhoods | WL is not a complete graph-isomorphism test |
| Motif and path multiset hash | Similar architectural role or route fragment | Motif selection can bias retrieval |
| Call-stack/trace n-gram hash | Similar observed execution | Workload-bound, not universal behavior |
| Input/output behavior signature | Same observed contract outcomes | Only as complete as generators and oracle |
| Test-coverage bitmap hash | Similar test support | Coverage does not establish correctness |
| Co-change sketch | Historically changed together | Repository history can reflect organization, not semantics |

Direction-normalized, endpoint-reordered, inverse, symmetric, or transitive fingerprints may be emitted only when the trusted `PredicateDescriptor` explicitly permits that transformation. Otherwise direction and participant roles remain part of the fingerprint.

The Weisfeiler-Lehman family is useful because repeated neighborhood relabeling produces efficient structural features, but it must remain a similarity projection rather than exact identity; see the [JMLR paper on Weisfeiler-Lehman graph kernels](https://www.jmlr.org/papers/v12/shervashidze11a.html). SimHash has a strong precedent for near-duplicate candidate generation at large scale; the original Google work reports that role for web crawling, not semantic proof. See [Detecting near-duplicates for web crawling](https://research.google/pubs/detecting-near-duplicates-for-web-crawling/).

### 10.3 EmbeddingProjection

```yaml
EmbeddingProjection:
  projection_envelope_ref: ...
  embedding_id: ...
  subject_ref: {subject_kind_key: ..., id: ...}
  embedding_key: "uceg.embedding.edge.behavior.en.v1"
  model:
    provider: ...
    model_id: ...
    revision_digest: ...
    tokenizer_digest: ...
    license: ...
  input:
    fact_and_assertion_refs: []
    view_ids: []
    ordered_input_digest: ...
    language: en
    preprocessing_id: ...
    truncation_and_chunking: ...
  vector:
    dimension: ...
    scalar_type: float16
    metric: cosine
    normalization: l2
    storage_ref: ...
  aggregation:
    kind: none|mean|max|attention|late_interaction
    component_embedding_ids: []
  evaluation:
    benchmark_id: ...
    calibration_version: ...
  policy:
    generated_locally: true
    source_egress_class: none
    access_policy_ref: ...
    derived_tenant_license_retention_class: ...
  coverage_refs: []
  invalidation_keys: []
  index_manifest_id: ...
  graph_epoch: ...
```

### 10.4 Multi-vector views to support

Do not collapse all information into one “code embedding.” Maintain independently selectable vector spaces:

- native name, aliases, and qualified-name tokens;
- source implementation body with and without identifiers/literals;
- exact structured signature and individual ports;
- original docstring/comment and external documentation;
- deterministic black-box behavior description;
- examples and common-intent paraphrases;
- explicit negative-use and incompatibility descriptions;
- errors, risks, effects, permissions, and operational constraints;
- normalized AST/CST path representation;
- control-flow and data-flow path representation;
- local typed graph neighborhood;
- motif, route, and group-boundary representation;
- runtime call/trace sequence and input/output behavior;
- tests, fixtures, assertions, and evidence statements;
- change history, co-change neighborhood, and migration description;
- task-to-capability compatibility representation;
- domain-specific views such as tensor shape, dataframe schema, SQL lineage, or HTTP contracts.

An edge can have one vector per description, one vector per participant role, a composite relation vector, and late-interaction token vectors. The query planner chooses the applicable spaces; it never averages unrelated spaces by default.

### 10.5 Embedding and fingerprint extensibility

New models are installed by registering:

- model and exact revision identity;
- accepted input view schemas;
- dimensionality, scalar type, metric, normalization, and maximum input;
- chunking and aggregation rules;
- supported languages and domains;
- license, egress, tenant, and hardware policies;
- cost/latency/resource estimates;
- benchmark and calibration records;
- invalidation and retirement rules;
- ANN index providers and parameters.

Re-embedding is a new projection epoch. Old and new vectors may coexist. A routing experiment can compare them through interleaving or shadow evaluation without changing canonical facts.

### 10.6 Graph features

Graph-derived feature extensions include:

- in/out degree by predicate, modality, confidence, package, and time;
- k-hop typed-neighborhood histograms;
- dominator/postdominator, SCC, bridge, articulation, reachability, and centrality roles;
- call/data/effect fan-in and fan-out;
- bounded path-language signatures;
- graphlets, motifs, typed metapaths, and route fragments;
- community and minimum-boundary memberships;
- distance to public API, effect boundary, test, vulnerability, or changed entity;
- entropy of candidate callees/types/points-to targets;
- evidence diversity and contradiction counts;
- historical selection, success, failure, and verification rates;
- incremental delta features between graph epochs.

Graph embeddings such as random-walk, message-passing, knowledge-graph relation, or path encoders may be added as extensions. Their training graph, negative sampling, feature leakage boundaries, random seeds, checkpoints, and evaluation corpus must be recorded.

## 11. Extensible black-box descriptions and CodeCapsules

The system should describe every useful entity and group without making generated prose canonical truth. Original names, signatures, source, docs, tests, static facts, and runtime observations remain separate. Descriptions are evidence-linked views over those facts.

### 11.1 DescriptionViewSpec

```yaml
DescriptionViewSpec:
  view_key: "uceg.description.edge.compatibility_explanation"
  version: "1.0.0"
  applies_to: [edge, relation, route]
  output_schema_ref: "uceg-schema://description/compatibility-explanation/1"
  audience: agent|developer|operator|security_reviewer|search_index
  purpose: retrieval|selection|composition|modification|verification
  required_input_features: []
  optional_input_features: []
  generation_arms:
    - deterministic_template
    - local_extractive_model
    - local_slm
    - remote_general_model
  maximum_abstraction_loss: ...
  forbidden_claim_classes: []
  validation_rules: []
  index_policies: []
  freshness_and_invalidation: ...
```

```yaml
DescriptionAssertion:
  projection_envelope_ref: ...
  description_id: ...
  subject_ref: ...
  view_key_and_version: ...
  payload_ref_or_inline_value: ...
  source_language: python
  natural_language: en
  generation_arm: deterministic_template|extractive|model|human
  generator_id_and_version: ...
  ordered_input_refs: []
  prompt_or_template_digest: ...
  claim_refs: []
  evidence_refs: []
  contradiction_refs: []
  coverage_and_abstraction_loss: ...
  confidence_and_calibration: ...
  access_and_license_class: ...
  graph_epoch: ...
```

Any team can register more descriptions, edge descriptions, languages, audiences, or domain schemas. A new description never overwrites a docstring or older view.

### 11.2 Initial description atlas

The first registry should include these optional views. Materialize only views justified by retrieval or evaluation data.

| Family | Views |
|---|---|
| Identity | native name, qualified name, aliases, provenance, release/build scope |
| Locator | file/module/package path, definition/reference summary, generated-source chain |
| Interface | signature, parameter contract, return/yield contract, callbacks/events, generic constraints |
| Behavior | one-line synopsis, detailed black-box behavior, algorithm role, state transition |
| Data | reads, writes, transforms, schemas, shapes, units, lineage, information loss |
| Effects | filesystem/network/database/subprocess/global/GPU/clock/randomness effects |
| Failure | exceptions, error codes, partial results, retry/idempotency/rollback behavior |
| Dependencies | direct requirements, implicit prerequisites, environment, optional features |
| Compatibility | provides/requires, compatible-with, adapters, blockers, unknown dimensions |
| Usage | minimal example, common patterns, anti-patterns, migration example |
| Negative | what this is not, unsuitable inputs, misleading query terms, known counterexamples |
| Quality | tests, oracles, coverage, confidence, contradictions, freshness, verified scope |
| Performance | complexity, allocations, blocking, resource needs, hot-path evidence |
| Security | trust boundary, permissions, secret handling, taint/sanitization, policy limits |
| Lifecycle | construction, initialization, valid states, teardown, deprecation, replacements |
| Change | stability, callers, impact surface, co-change history, safe edit handles |
| Observability | logs, metrics, traces, audit events, diagnostic messages |
| Domain | tensors, dataframes, SQL, HTTP, queues, ML models, geospatial, finance, etc. |

Variables require their own black-box treatment. A `VariableCard` can include declaration role, lexical scope, native name, structured type/value-domain claims, default/initial value, read/write/delete occurrences, reaching definitions, alias/points-to candidates, captured/escaped status, lifetime, mutability, thread/shared-state status, sensitivity, units/schema/shape, state slots influenced, outputs influenced, tests, and exact body/source handles. The card must distinguish a binding from the runtime values it may reference.

Edges also receive multiple views:

- exact relation synopsis;
- why the relationship exists and which analyzer found it;
- source-to-target argument or value mapping;
- preconditions, guards, path conditions, and may/must status;
- compatibility explanation and individual failed dimensions;
- introduced adapters, conversions, information loss, effects, and cost;
- supporting and contradicting evidence;
- inverse-language phrasing for reverse search;
- common user intents and negative query aliases;
- change impact if the edge disappears or its contract changes;
- observed frequency, latency, failure, and workload scope;
- concise agent projection and detailed reviewer projection.

### 11.3 CodeCapsule for any group of existing code

For an entity set `S`, derive a capsule from the graph boundary rather than merely summarizing concatenated files.

```text
CodeCapsule(S) =
  identity and membership definition
  + inbound boundary delta-(S)
  + outbound boundary delta+(S)
  + state owned and mutated inside S
  + external effects and capabilities
  + errors and failure propagation
  + invariants, preconditions, and postconditions
  + public and hidden extension points
  + tests, examples, docs, traces, and contradictions
  + decisive internal edges
  + compatibility signatures
  + coverage and abstraction-loss ledger
  + expansion handles to exact entities, edges, evidence, and bodies
```

```yaml
CodeCapsule:
  projection_envelope_ref: ...
  capsule_id: ...
  entity_set_id: ...
  membership_definition_ref: ...
  frozen_membership_digest: ...
  inbound_port_refs: []
  outbound_port_refs: []
  state_slot_refs: []
  internal_invariant_refs: []
  effect_and_error_refs: []
  decisive_edge_refs: []
  compatibility_signature_refs: []
  description_view_refs: []
  evidence_and_test_refs: []
  coverage_ledger_refs: []
  abstraction_loss:
    hidden_entities: ...
    unresolved_dynamic_edges: ...
    omitted_effects: ...
    unsupported_constructs: ...
  expansion_handles: []
  graph_epoch: ...
```

Capsules can represent one closure, class, module, package subsystem, route, test cluster, or the complete PyPI release. A capsule is usable as a black box only under its stated contract and coverage. It is not a proof that every internal implementation is irrelevant.

### 11.4 Hierarchical and bottom-up generation

Generate descriptions and capsules bottom-up:

1. Extract exact facts for occurrences, bindings, ports, effects, and tests.
2. Deterministically render compact entity and edge facts.
3. Aggregate boundaries and decisive edges for classes and small modules.
4. Detect contradictions and missing coverage before summarization.
5. Use extractive/local methods to form higher-level views.
6. Invoke an LLM only for views whose measured benefit exceeds cost and risk.
7. Validate generated claims against the underlying graph; retain unsupported statements only as unpromoted hypotheses.
8. Recompute only views whose input digests changed.

This avoids asking a frontier model to read the entire package simply to rediscover import paths and signatures.

## 12. Processing one large PyPI package end to end

The first vertical slice should process one exact package release with multiple artifacts and optionally its repository—not an ambiguous package name floating outside an environment.

### 12.1 Stage A: resolve and acquire without execution

Inputs:

```yaml
SourceSpec:
  registry_authority: https://pypi.org
  distribution_name: sqlalchemy
  version: <exact-version>
  artifact_policy: wheel_and_sdist
  artifact_digests: optional
  repository_ref: optional
  python_targets: [cp312, cp313]
  platform_targets: [...]
  extras: []
  analysis_profile: exhaustive_static
```

Actions:

- normalize the distribution name while preserving original spelling and registry authority;
- query the PyPI Simple API, retain yanked state, hashes, core-metadata links, Python constraints, upload time, and artifact details;
- download selected wheels/sdists under size and policy limits and verify advertised hashes;
- safely unpack into a content-addressed store, rejecting traversal, special files, dangerous links, path collisions, and decompression bombs;
- read wheel `METADATA`, `WHEEL`, `RECORD`, entry points, top-level import packages, licenses, and typing markers;
- map distribution, import packages, repository claims, and installed files as separate evidenced relationships;
- do not run `setup.py`, build hooks, imports, entry points, plugins, or package code.

PyPI distribution metadata and import-package identity are not one-to-one. The authoritative first records come from the [PyPA Core Metadata](https://packaging.python.org/en/latest/specifications/core-metadata/), [Wheel](https://packaging.python.org/en/latest/specifications/binary-distribution-format/), [Entry Points](https://packaging.python.org/en/latest/specifications/entry-points/), and [Simple Repository API](https://packaging.python.org/en/latest/specifications/simple-repository-api/) specifications.

### 12.2 Stage B: exact snapshot and inventory

Create:

- `DistributionID` for exact artifact bytes;
- `SourceSnapshotID` for exact unpacked source content;
- `WorkspaceSnapshotID` if a dirty repository/worktree is also analyzed;
- `BuildUniverseID` for interpreter, platform, dependency lock, extras, flags, and generated sources;
- `AnalysisManifest` covering every file and pass;
- `FileContentID` and canonical byte spans;
- file classifications: source, stub, tests, docs, examples, data, config, generated, vendored, native, unknown.

A Git commit alone is not a complete workspace identity. Dirty files, untracked files, submodules, symlinks, generated content, case behavior, tool configuration, and dependency state affect the program.

### 12.3 Stage C: cheap exhaustive syntax pass

Run over every supported Python/stub/notebook source unit:

- encoding and parse diagnostics;
- Python AST for declarations, statements, imports, expressions, literal/value sites, decorators, pattern captures, comprehensions, scopes, and source coordinates;
- lossless CST for comments, formatting, syntactic distinctions, and future edits;
- `symtable` for lexical scope and binding categories;
- token/shingle/fingerprint extraction;
- docstring, comment, directive, TODO, error text, and example extraction;
- configuration, environment, URL, path, SQL, regex, and secret-pattern candidates;
- deterministic entity, occurrence, containment, binding, import, and basic read/write edges.

Python’s `ast`, `symtable`, and `inspect` modules expose different layers: syntax, compiler symbol-table scope, and live-object introspection. They should not be conflated. See the official [`ast`](https://docs.python.org/3/library/ast.html), [`symtable`](https://docs.python.org/3/library/symtable.html), and [`inspect`](https://docs.python.org/3/library/inspect.html) documentation.

### 12.4 Stage D: semantic resolution

Add parallel analyzers rather than replacing the cheap facts:

- SCIP-compatible symbol definitions, references, implementations, and structured external symbols;
- one or more type checkers for inferred/declared types, overloads, protocols, generics, and diagnostics;
- import graph and re-export/public API reconciliation;
- decorator, descriptor, dataclass/model/CLI/framework recognizers;
- points-to, call target, control-flow, data-flow, mutation, exception, and effect analysis;
- CodeQL or comparable deeper analysis for selected security/data-flow questions;
- native-extension and dynamic-boundary markers;
- docs/tests/examples to code linking.

SCIP is a useful interchange input for navigation facts because it is language-agnostic and covers definitions, references, and implementations across several languages; it is not the entire UCEG. [SCIP](https://github.com/scip-code/scip) and [Kythe’s typed schema](https://kythe.io/docs/schema/) provide concrete precedents. [CodeQL’s Python data-flow model](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/) illustrates why local and global flow, sources, sinks, barriers, and path results need richer relation records.

### 12.5 Stage E: framework and domain analyzers

The extensible analyzer registry can add package-specific knowledge without polluting the kernel:

- dataclass, attrs, Pydantic, SQLAlchemy, Django, FastAPI, Click/Typer, pytest;
- NumPy tensor/array shapes, pandas schemas, PyArrow tables, ML model inputs/outputs;
- HTTP, OpenAPI, GraphQL, protobuf, JSON Schema, SQL, migrations, message queues;
- plugin systems, entry-point groups, registries, dependency injection, serializers;
- generated clients, native bindings, FFI, Cython, Rust/PyO3, shared libraries.

Each recognizer declares patterns, emitted aspects and edges, false-positive expectations, supported versions, and test fixtures.

### 12.6 Stage F: optional sandboxed build and runtime observation

Runtime analysis is a separate opt-in job:

- build a pinned environment in a network-restricted sandbox;
- verify dependency and artifact digests;
- impose CPU, memory, disk, process, syscall, time, and output limits;
- run declared tests, examples, imports, and generated probes;
- trace calls, imports, allocations, I/O, subprocesses, exceptions, state changes, and selected values/shapes;
- fuzz/property-test compatibility boundaries where safe;
- store workload and oracle identity with every observation;
- destroy or quarantine the environment after producing a receipt.

Observed behavior is workload-bound. A passed test does not promote unrelated inferred claims to verified.

### 12.7 Stage G: reconcile, describe, index, and publish

1. Retain native analyzer outputs in immutable content-addressed bundles.
2. Normalize facts into entities, occurrences, relation claims, features, and coverage records.
3. Keep conflicting assertions parallel; build explicit reconciliation views.
4. Generate exact identity, fielded lexical, forward/reverse adjacency, structural, LSH, graph, and optional vector projections.
5. Generate deterministic cards and selected description views.
6. Validate referential integrity, scope, source spans, schemas, extension descriptors, collisions, policy, and checksums.
7. Atomically publish a `GraphEpochManifest`.

Analysis jobs are resumable and idempotent. Recommended states are `resolved`, `acquired`, `inventoried`, `planned`, `analyzing`, `normalizing`, `validating`, `projecting`, `publishing`, `complete`, `failed`, `retryable`, `quarantined`, and `cancelled`. Each transition records exact input/output digests, heartbeat, shard, attempts, last error, and next action. Zero selected files/shards is an explicit outcome, never silent success.

The immutable-facts plus derived-views pattern has a strong systems precedent in [Glean](https://github.com/facebookincubator/Glean). Broad structural parsing can use Tree-sitter queries, while Python modifications should use a lossless representation such as LibCST rather than regenerating files from `ast`. See [Tree-sitter query syntax](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html) and [Why LibCST](https://libcst.readthedocs.io/en/latest/why_libcst.html).

### 12.8 Analysis profiles

| Profile | Included work | Expected use |
|---|---|---|
| `inventory` | safe acquisition, files, metadata, AST/CST entities | rapid package census |
| `navigation` | inventory + symbols/references/imports/types | code search and browsing |
| `composition` | navigation + ports/effects/errors/compatibility/indexes | agent retrieval and reuse |
| `deep_static` | composition + call/data/control/taint/security analyzers | impact and security tasks |
| `observed` | deep static + sandboxed tests/traces/probes | behavior calibration |
| `exhaustive_bounded` | every installed analyzer within explicit budgets | benchmark/release proof |

Each profile is a planner preset, not a semantic ceiling. Users can add analyzer and projection extensions.

## 13. Retrieval and composition waterfall

The default path should spend zero generative-model tokens until deterministic and local methods have failed or uncertainty justifies escalation.

### 13.1 Input normalization

```yaml
ContextManifest:
  conversation_digest: ...
  active_task_turns: []
  historical_memory_handles: []
  workspace_snapshot_id: ...
  package_snapshot_ids: []
  graph_epoch: ...
  user_constraints: []
  policy_and_budget: ...
```

```yaml
CodeDemandIR:
  task_kind: locate|understand|compose|impact|modify|verify|compare
  target_hints: []
  required_capabilities: []
  provided_ports: []
  required_ports: []
  hard_constraints: []
  soft_preferences: []
  negative_constraints: []
  desired_evidence: []
  uncertainty: ...
  output_contract: ...
```

The first parser is deterministic: Unicode normalization, code/error/path detection, exact symbol and package recognizers, quoted phrases, version constraints, negation, task verbs, language/domain dictionaries, and prior selection/history. A lightweight classifier or local SLM adds intent and slot candidates only when needed. A model-generated query is the final fallback.

### 13.2 Typed QueryIR

```yaml
CodeQueryIR:
  epoch: ...
  target_kinds: [method, function]
  exact_terms: []
  lexical_clauses: []
  endpoint_constraints: []
  compatibility_requirements: []
  edge_predicate_patterns: []
  graph_path_automata: []
  lsh_probes: []
  vector_probes: []
  evidence_thresholds: []
  exclusions: []
  budget:
    latency_ms: ...
    max_candidates: ...
    max_pair_solves: ...
    max_block_expansions: ...
    max_lsh_probes: ...
    max_ann_candidates: ...
    max_route_states: ...
    max_adapter_hops: ...
    per_lane_deadlines_ms: {}
    max_context_tokens: ...
  expansion_policy: ...
```

The query receipt reports actual usage for every bound and which stage stopped or broadened. A timeout or exhausted cap returns an explicit partial/abstained result with continuation handles; it never silently converts to “no match.”

Common queries use reviewed templates:

- `find entity WHERE kind IN ? AND name/doc/behavior MATCH ?`;
- `find edge WHERE predicate IN ? AND endpoint_signature COMPATIBLE_WITH ?`;
- `trace reverse (reads|writes|calls|data_flows_to)* from ?`;
- `solve route from provided_signature to required_signature under constraints`;
- `find adapter from schema/type/effect A to B`;
- `find alternatives similar to selected edge/entity but excluding failed dimension X`;
- `explain incompatibility between A and B`;
- `return smallest evidence-connected slice answering demand D`.

### 13.3 Candidate waterfall

Run lanes concurrently where useful, but preserve their provenance:

0. authorization, tenant, source-disclosure, license, environment, and hard policy gates;
1. exact IDs, artifact hashes, source positions, quoted strings, qualified names, signatures;
2. session selections, accepted route history, user/repository patterns, query-result cache;
3. fielded filters and BM25 across names, docs, interfaces, effects, errors, examples, negatives;
4. typed forward/reverse adjacency and bounded bidirectional path/route solving;
5. exact compatibility signature joins and known adapter tables;
6. structural fingerprints, code-clone candidates, MinHash/SimHash/LSH blocks;
7. graph neighborhoods, motifs, metapaths, communities, and co-change candidates;
8. sparse semantic retrieval and domain-specific features;
9. one or more selected dense embedding spaces;
10. deterministic feature fusion and constraint evaluation;
11. local cross-encoder or SLM reranker/classifier;
12. small general model for ambiguous selection or query repair;
13. strong/frontier model for novel multi-hop planning, custom query synthesis, or unresolved ambiguity.

Failure at one lane does not force the query through every subsequent lane. The planner estimates expected information gain, cost, latency, privacy, and verification risk.

### 13.4 Hard gates before scores

Reject or quarantine candidates violating:

- wrong exact package/build/snapshot when exactness is required;
- incompatible direction, entity kind, arity, type/schema, execution mode, or environment;
- prohibited effect, capability, source egress, license, tenant, or trust rule;
- known hard negative or failed verified compatibility dimension;
- insufficient evidence/coverage for the requested operation;
- stale or unresolvable occurrence/body handle.

Only surviving candidates receive a ranking score. A representative fusion is:

```text
score(c, q) =
    w_exact      * exact_feature_score
  + w_lexical    * normalized_fielded_bm25
  + w_type       * typed_compatibility_score
  + w_graph      * path_and_neighborhood_score
  + w_structural * fingerprint_similarity
  + w_semantic   * calibrated_vector_similarity
  + w_evidence   * evidence_strength_and_diversity
  + w_history    * bounded_success_history
  + w_freshness  * freshness
  - w_cost       * execution_and_context_cost
  - w_risk       * uncertainty_policy_and_effect_risk
  - w_redundancy * marginal_duplicate_information
```

Weights are profile- and intent-specific, versioned, and evaluated. Raw BM25 and cosine values are not directly commensurate; calibrate or rank-fuse per lane. Return feature-level explanations.

### 13.5 Routes and alternatives

The solver operates on port-level hyperedges with direction, compatibility, adapters, effects, uncertainty, and cost. It can use typed bidirectional search, A*, constrained shortest path, k-shortest paths, multiobjective Pareto search, or answer-set/SMT/constraint solving for difficult cases.

Start with route handles, then disclose progressively:

| Level | Payload |
|---|---|
| `H0` | route/entity handles, score, decisive match reasons |
| `H1` | compact cards, ports, effects, errors, evidence grade |
| `H2` | decisive edges, compatibility assessments, tests, constraints |
| `H3` | selected implementations and neighboring bodies |
| `H4` | full evidence, native facts, traces, broad neighborhoods |

Experiment with `1/2/4/8` alternatives at each level. Deduplicate by concept, interface, implementation fingerprint, path overlap, evidence source, and semantic cluster. Too many near-duplicates waste tokens and bias selection; diversity helps only when alternatives differ along meaningful compatibility, evidence, implementation, cost, or risk axes.

### 13.6 Context slice optimization

A `CodeSliceManifest` should maximize covered demand and evidence connectivity subject to token, latency, policy, and uncertainty budgets. Penalize redundancy, stale facts, weak evidence, disconnected snippets, and unnecessary bodies. This resembles a prize-collecting connected-subgraph/knapsack problem rather than top-k chunk retrieval.

Always include expansion handles so the next call can request one body, edge, route alternative, or evidence chain without resending the entire slice.

### 13.7 Queryless exits, active discrimination, and bypass

Not every task should generate a search query. Check these fast paths first:

- explicit entity, edge, route, package, schema, test, or occurrence handle;
- exact prior verified task/route replay under unchanged inputs and policy;
- deterministic hook, command, file pattern, error code, AST trigger, or skill applicability rule;
- direct type/schema/standard lookup;
- named CodeCapsule, workflow, solution pack, or accepted package subsystem;
- a unique permitted route from already-bound input/output ports.

When a few candidates remain ambiguous, choose the cheapest distinguishing evidence instead of immediately asking a larger model. Examples include an exact type-check, schema validation, static flow query, two harmless property examples, focused unit test, import check, or sandboxed differential probe. Record the probe’s selection policy so evaluation does not leak answer keys.

Permit a direct no-reuse/no-graph bypass when:

- the helper is trivial and selection/verification overhead exceeds implementation cost;
- required evidence or source access is unavailable;
- compatibility remains unknown after the allowed budget;
- the package route requires more model-visible body context than a bounded direct implementation;
- the task requests genuinely novel behavior absent from the corpus;
- policy or licensing prohibits reuse;
- route quality, security, latency, or maintenance gates fail.

The bypass still produces a receipt and can feed a later candidate-ingestion pipeline. Reuse is a means, not the objective; verified total task value is the objective.

## 14. Model routing, orchestration, and the agent harness

Model routing should be an optional stage inside the larger retrieval and execution system. It must not become the first reflex for parsing every user request.

### 14.1 Separate three routing problems

1. **Work routing:** decide whether the next step is a deterministic parser, index lookup, graph solver, local classifier, SLM, LLM, analyzer, test, or human decision.
2. **Capability routing:** if a model is needed, select the cheapest model predicted to satisfy the task’s quality, tool-use, context, privacy, latency, and output-contract requirements.
3. **Deployment routing:** select a healthy provider/deployment for that model class under price, quota, locality, rate, and latency constraints.

Do not ask a gateway load balancer to infer semantic task difficulty. Do not ask a semantic router to handle provider failover. Each router emits its own receipt.

### 14.2 Execution arms

| Arm | Typical work | Escalation trigger |
|---|---|---|
| `D0` deterministic | parsing, templates, exact search, graph traversal, schema/type checks, test execution | unsupported or ambiguous input |
| `D1` statistical local | fastText/linear/tree classifier, CRF/NER, keyword/keyphrase extraction, calibrated heuristics | low margin or novel class |
| `D2` embedding/local route | semantic intent/feature route, ANN candidates, local cross-encoder | poor retrieval separation |
| `M0` local specialist | code parser model, reranker, query slot filler, verifier | failed output contract or low confidence |
| `M1` local/general SLM | constrained QueryIR, card synthesis, candidate selection | ambiguity, complex multi-hop need |
| `M2` cheap hosted model | structured planning or synthesis over a small slice | verification failure or high risk |
| `M3` strong model | difficult composition, code reasoning, query repair | independent checks fail or abstention |
| `M4` frontier model | genuinely novel, high-ambiguity, high-value task | final bounded fallback, not default |
| `H` human | policy, destructive ambiguity, unresolved safety, product judgment | authority or value judgment required |

Every arm must be able to abstain. An arm’s output is accepted only if it passes the stage’s schema and validators.

### 14.3 ModelCapabilityCard

Treat models, analyzers, and tools like other capabilities:

```yaml
ModelCapabilityCard:
  model_route_id: ...
  model_or_tool_id: ...
  exact_revision: ...
  deployment_classes: []
  supported_task_kinds: []
  input_modalities: []
  structured_output_support: []
  tool_use_support: []
  context_and_output_limits: ...
  language_and_domain_profiles: []
  privacy_and_residency: ...
  measured_quality_by_workload: []
  calibrated_failure_and_abstention: ...
  latency_and_cost_distributions: ...
  reliability_and_rate_limits: ...
  known_failure_clusters: []
  valid_from_and_freshness: ...
```

The router selects a feasible set using hard gates and then minimizes expected total cost:

```text
expected_total_cost =
  call_cost
  + latency_cost
  + expected_retry_cost
  + expected_escalation_cost
  + expected_verification_cost
  + expected_failure_or_rework_loss
  + privacy/policy risk
```

The cheapest call is not always the cheapest completed task. Sometimes a slightly better local/cheap model reduces retries and context enough to win.

### 14.4 Routing features

Use features already produced by CodeGraph:

- task kind, language, framework, entity/edge kinds, and requested output schema;
- exact-vs-open-ended demand, ambiguity, number of unresolved slots, and novelty;
- graph slice size, route length, branch factor, dynamic-edge entropy, and evidence gaps;
- whether exact/history/template retrieval succeeded;
- top-candidate score margin, cross-lane agreement, contradiction count, and coverage;
- required tools, source bodies, transformations, tests, and policy class;
- context tokens, deadline, budget, user risk tolerance, and reversibility;
- prior model/tool success for the same task cluster and package subsystem;
- model availability, latency, price, quota, and health.

Never route on protected or private features unless policy explicitly permits it. Prevent label leakage from post-outcome features during offline training.

### 14.5 Router progression

Start simple and measurable:

1. deterministic rules and hard capability gates;
2. calibrated logistic/gradient-boosted success predictors for each arm;
3. champion/challenger shadow evaluation;
4. contextual bandit only after counterfactual data and safety constraints exist;
5. learned multi-model route selection only when it beats the rule baseline on held-out, time-split, and package-split workloads.

Use conservative escalation:

```text
run cheapest feasible arm
-> validate schema and deterministic invariants
-> check confidence/margin/coverage/risk
-> verify against graph or tool oracle
-> accept, repair locally, or escalate with the same compact evidence bundle
```

Escalation sends the prior arm’s structured output, failure codes, and decisive graph slice—not the whole conversation and repository again.

### 14.6 How existing routing/orchestration tools fit

| Tool/pattern | Useful role | What Taedri still supplies |
|---|---|---|
| LiteLLM Router/gateway | provider abstraction, load balancing, cooldowns, retries, fallbacks, latency/cost/usage strategies | task difficulty, graph-aware capability selection, evidence, verifier loop |
| RouteLLM | research baseline for calibrated strong-vs-weak routing and cost-quality thresholds | more than two arms, tools, local deterministic stages, code-specific features |
| Semantic Router | low-latency intent routing, including local encoders/models | typed CodeDemandIR, graph constraints, verification, long-term evaluation |
| LangGraph-style state graph | explicit conditional workflow, persistence, human checkpoints, parallel branches | CodeGraph data contracts, retrieval and compatibility engine |
| General agent harness | tool loop, skills, subagents, context management | stable entity/edge handles, exact receipts, policy and graph epoch |
| MCP | compact interoperable meta-tools | underlying search/resolve/verify semantics and authorization |

LiteLLM’s current router documentation distinguishes deployment strategies such as weighted, rate-limit-aware, latency, least-busy, and cost routing, along with retries/fallbacks; this is valuable beneath Taedri’s task router. [LiteLLM Router](https://docs.litellm.ai/docs/routing) RouteLLM demonstrates threshold calibration for routing between a stronger and weaker model, which is a useful baseline but not the complete multi-stage system. [RouteLLM](https://github.com/lm-sys/RouteLLM) Semantic Router demonstrates fast semantic route selection and supports local encoders/models, useful for the early local arm. [Semantic Router](https://github.com/aurelio-labs/semantic-router)

### 14.7 Harness files, hooks, tools, agents, and skills

The repository should ship:

- `AGENTS.md`: concise cross-agent invariants, commands, graph contracts, change protocol;
- `CLAUDE.md`: import or mirror the portable rules plus Claude-specific notes;
- path-scoped rules: analyzer, schema, storage, security, and benchmark instructions loaded only when relevant;
- skills: reusable workflows such as index-package, investigate-edge, add-analyzer, add-extension, change-symbol, verify-release;
- hooks: deterministic authorization, snapshot checks, QueryIR validation, secret/source-egress filtering, formatter/linter/test triggers, receipt capture;
- subagent roles: acquisition, analyzer reconciliation, retrieval evaluation, change planning, independent verification;
- MCP meta-tools: search, resolve, expand, path, compatibility, slice, evidence, coverage, diff, verify;
- model/provider gateway adapter and router policy files;
- eval fixtures and replayable traces.

Keep always-loaded instruction files small. Put facts the graph can retrieve behind handles, and put enforcement in hooks/policy code. Current Claude Code documentation explicitly treats `CLAUDE.md` as context rather than hard enforcement and recommends hooks for fixed lifecycle enforcement; it also supports importing `AGENTS.md`. See [Claude Code memory/instructions](https://code.claude.com/docs/en/memory) and [hooks](https://code.claude.com/docs/en/hooks).

### 14.8 Self-optimization without self-deception

Record for every task:

- demand, features, candidates, routes, contexts, selected arm, model/deployment revision;
- prompt/template/query digest and exact token counts;
- latency, monetary/compute cost, cache hits, retries, and escalation;
- schema validity, verifier outcomes, tests, human acceptance/correction, and downstream rollback;
- graph/feature/index/policy epochs.

Use these receipts to:

- promote recurring successful free-form queries into deterministic templates;
- manufacture shortcuts and route macros from verified repeated compositions;
- tune alternative counts, detail levels, and candidate budgets;
- retire embeddings or descriptions that do not improve recall/quality;
- recalibrate router thresholds and per-task arm capability;
- detect drift by package, language, model, analyzer, and time.

Never train directly on unverified model self-scores. Use independent tests, replayable oracles, accepted changes, and carefully designed human labels.

## 15. Cheap and accurate use of retrieved code

Retrieval is only half the problem. The selected entities and edges must be composed or modified without turning a model into an unobserved compiler.

### 15.1 Post-selection resolution

The first model call receives cards and route handles. After it selects a route, the harness resolves only:

- exact source bodies required for implementation;
- defining occurrences and selected call sites;
- port contracts and compatibility assessments;
- decisive effects, state, errors, and policy constraints;
- relevant tests, fixtures, examples, and build commands;
- current workspace versions and change preconditions.

If several alternatives remain, resolve them incrementally at `1/2/4/8` detail rather than dumping all bodies at once.

### 15.2 GraphIR and ChangeIR

`GraphIR` represents a selected composition as typed entities, ports, adapters, routes, effects, and constraints. `ChangeIR` represents intended edits against exact occurrences.

```yaml
ChangeIR:
  change_plan_id: ...
  base_workspace_snapshot_id: ...
  graph_epoch: ...
  intent: ...
  target_entity_and_occurrence_ids: []
  preconditions:
    file_content_digests: []
    expected_structure: []
    expected_contracts: []
  operations:
    - kind: rename_binding|change_signature|insert_call|replace_expression|add_test|...
      target_ref: ...
      typed_payload: ...
  predicted_graph_delta: ...
  required_verifiers: []
  rollback_plan: ...
```

Use language-specific lossless transformation engines. Stable sidecar IDs guide selection and tracing; they are not injected into user-facing identifiers.

### 15.3 Independent verification waterfall

After composition or change:

1. compare-and-swap check on exact workspace/file digests;
2. parse and lossless round-trip checks;
3. formatter/linter/type-checker/static analyzer;
4. focused tests and declared oracles;
5. impacted tests from reverse graph traversal;
6. broader package test suite as risk requires;
7. optional sandboxed runtime/effect verification;
8. semantic graph diff: intended changed entities/edges, unexpected deltas, unresolved IDs;
9. policy, license, security, and source-egress checks;
10. independent verifier arm distinct from the drafting model when risk warrants;
11. publish a `ChangeReceipt`, then incrementally update the graph.

An LLM saying its work is correct is not verification.

### 15.4 Exact receipt

```yaml
ChangeReceipt:
  demand_digest: ...
  context_manifest_digest: ...
  code_slice_manifest_id: ...
  selected_route_and_alternatives: ...
  model_tool_and_query_receipts: []
  base_and_result_workspace_snapshots: ...
  changed_occurrences: []
  graph_delta_ref: ...
  verification_results: []
  effects_observed: []
  token_compute_latency_and_cost: ...
  unresolved_risks: []
  rollback_ref: ...
```

## 16. Storage, indexing, and scale

### 16.1 Five planes

1. **Immutable fact plane:** source/artifact bytes, native analyzer bundles, exact entities, occurrences, assertions, observations, hashes, and provenance.
2. **Logical overlay plane:** lineage, semantic roles, policy, ownership, human annotations, inferred groups, and reconciled views.
3. **Serving projection plane:** exact/lexical/range/bitmap/adjacency/LSH/vector indexes, cards, capsules, routes, and caches.
4. **Transactional change plane:** snapshot locks, ChangeIR, patches, verification, rollback, and receipts.
5. **Evidence and learning plane:** task traces, outcomes, evaluation labels, router data, and promotion decisions.

Generated descriptions and embeddings can be discarded and rebuilt. Canonical facts and evidence are immutable within an epoch.

### 16.2 Practical first storage profile

- content-addressed filesystem/object storage for artifacts, sources, analyzer payloads, descriptions, evidence, and models;
- SQLite/WAL locally, PostgreSQL in shared deployments, for catalogs, jobs, registries, epochs, policy, and small hot records;
- Zstandard-compressed Arrow/Parquet shards for entities, occurrences, assertions, features, signatures, and receipts;
- Tantivy or equivalent fielded inverted index for exact terms and BM25;
- sorted forward/reverse adjacency with stable integer ordinals and Roaring bitmaps;
- typed range/interval indexes for versions, shapes, numeric ranges, time, and resources;
- LSH bucket tables partitioned by algorithm/model/view/version;
- optional vector provider behind a stable port; local HNSW/FAISS-style index is sufficient to start;
- DuckDB for analytical inspection and evaluation;
- append-only `GraphEpochManifest` as the atomic publication boundary.

The canonical truth should not be trapped in one graph database or vector store. Those are replaceable projections.

### 16.3 Edge-specific physical indexes

For every published epoch, build as applicable:

1. edge ID and claim-key map;
2. predicate and inverse-predicate postings;
3. participant-role and ordered endpoint-pair postings;
4. subject/outgoing and object/incoming adjacency;
5. endpoint kind, package, module, file, language, and visibility bitmaps;
6. modality, polarity, may/must, confidence, evidence, lifecycle, and freshness bitmaps/ranges;
7. compatibility-dimension postings and hard-negative indexes;
8. exact fingerprint maps and each LSH family’s band tables;
9. graph-neighborhood/motif/path fingerprint postings;
10. description field indexes and selected embedding ANN indexes;
11. policy/tenant/license/source-body authorization bitmaps;
12. verified pair assessment and negative-assessment caches.

Authorization is intersected before retrieval and traversal so private edge existence does not leak through scores or counts.

### 16.4 Scale principles

- Shard primarily by graph epoch and package/source boundary; use stable ordinals inside shards.
- Keep hot stable fields columnar; keep long-tail extension payloads in typed feature tables/CAS.
- Materialize reverse edges and frequent route macros; compute rare projections lazily.
- Cache unary signatures broadly and pairwise compatibility selectively.
- Rebuild derived indexes from manifests; never mutate them invisibly.
- Reuse analyzer outputs and features by exact input digest.
- Apply dependency-aware invalidation to files, entities, edges, features, groups, descriptions, embeddings, and routes.
- Compact tombstones only under retention and epoch rules.
- Sample candidates excluded by blocking and evaluate them offline to detect hidden false negatives.
- Support tens of millions of entities/edges without a full in-memory graph; design load tests toward 50–100 million records.
- Do not impose arbitrary product caps on attributes, views, embedding models, or relation types. Use quotas, tiering, materialization policy, and query budgets.

Illustrative raw payload sizes at 100 million subjects, before metadata, postings, graph links, replicas, and build headroom:

| Representation | Raw bytes/subject | Raw size at 100M |
|---|---:|---:|
| SHA-256 | 32 | 3.2 GB |
| 128-bit SimHash | 16 | 1.6 GB |
| Four 128-bit WL digests | 64 | 6.4 GB |
| 64 × 16-bit compressed MinHash coordinates | 128 | 12.8 GB |
| 128 × 32-bit MinHash coordinates | 512 | 51.2 GB |
| 384-dimensional FP16 vector | 768 | 76.8 GB |
| 768-dimensional FP16 vector | 1,536 | 153.6 GB |

This argues for broad exact/SimHash/small graph fingerprints, selective high-dimensional MinHash/vector views, content deduplication, hot/cold tiers, half precision or product quantization where measured, and full-precision reranking only for a bounded pool. HNSW adjacency and replication can exceed raw vector size, so benchmark total index footprint rather than vector bytes alone.

### 16.5 Atomic publication

```text
write immutable candidate shards
-> validate schema and extension registries
-> validate identities, references, spans, evidence, policy, and collisions
-> build exact/lexical/adjacency/LSH/vector projections
-> run known-answer and poison-corpus queries
-> sign/finalize GraphEpochManifest
-> atomically swap visible epoch pointer
-> retain prior epoch for replay and rollback
```

## 17. Repository blueprint

### 17.1 Public names

- Project: **Taedri CodeGraph**
- Repository: `taedri-codegraph`
- Python distribution: `taedri-codegraph`
- Python import package: `taedri_codegraph`
- CLI: `tcg`
- MCP server: `taedri-codegraph-mcp`
- Interchange standard: Universal Code Entity Graph (`UCEG`)

### 17.2 Modular-monolith layout

```text
taedri-codegraph/
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── GOVERNANCE.md
├── AGENTS.md
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── justfile
├── proto/taedri/codegraph/v1/
│   ├── identity.proto
│   ├── source.proto
│   ├── entity.proto
│   ├── occurrence.proto
│   ├── relation.proto
│   ├── assertion.proto
│   ├── extension.proto
│   ├── feature.proto
│   ├── compatibility.proto
│   ├── fingerprint.proto
│   ├── embedding.proto
│   ├── description.proto
│   ├── evidence.proto
│   ├── coverage.proto
│   ├── query.proto
│   ├── card.proto
│   ├── capsule.proto
│   ├── slice.proto
│   ├── change.proto
│   ├── receipt.proto
│   └── service.proto
├── schemas/
│   ├── jsonschema/
│   ├── ontology/
│   ├── extensions/
│   ├── compatibility/
│   ├── descriptions/
│   └── examples/
├── src/taedri_codegraph/
│   ├── contracts/
│   ├── registry/
│   ├── identity/
│   ├── sources/
│   ├── acquisition/
│   ├── planning/
│   ├── analyzers/
│   ├── normalize/
│   ├── evidence/
│   ├── graph/
│   ├── edges/
│   ├── ports/
│   ├── compatibility/
│   ├── fingerprints/
│   ├── embeddings/
│   ├── descriptions/
│   ├── groups/
│   ├── projections/
│   ├── query/
│   ├── routes/
│   ├── cards/
│   ├── capsules/
│   ├── slices/
│   ├── router/
│   ├── harness/
│   ├── change/
│   ├── verify/
│   ├── lineage/
│   ├── policy/
│   ├── storage/
│   ├── publish/
│   ├── telemetry/
│   ├── api/
│   ├── mcp/
│   └── cli/
├── analyzers/
│   ├── python-metadata/
│   ├── python-syntax/
│   ├── python-scip/
│   ├── python-types/
│   ├── python-interface/
│   ├── python-flow/
│   ├── python-effects/
│   ├── python-runtime/
│   └── analyzer-conformance/
├── extensions/
│   ├── core/
│   ├── python/
│   └── domains/
├── clients/{python,typescript}/
├── services/{api,indexer-worker,mcp,router}/
├── fixtures/{python-golden,packages,repos,native-facts,expected-graphs,hostile}/
├── tests/{unit,contract,golden,differential,integration,e2e,security,performance}/
├── eval/{corpus,workloads,baselines,reports}/
├── deployments/{local,docker,kubernetes}/
├── docs/{spec,adr,analyzers,extensions,operations,security,tutorials}/
└── tools/
```

Begin as a modular monolith with analyzers isolated behind a versioned subprocess/gRPC contract. Separate deployable services can share the same core library until scale measurements justify network boundaries.

### 17.3 Core interfaces

```text
SourceAdapter.resolve/acquire/inventory
Analyzer.describe/plan/analyze
Normalizer.normalize/native_fact_refs
ExtensionRegistry.register/resolve/validate
ProjectionProvider.plan/build/query
CompatibilityEvaluator.describe/evaluate/explain
DescriptionGenerator.describe/generate/validate
ModelRouter.select/report_outcome
Verifier.describe/verify
Publisher.validate/publish
```

Every plugin declares input schemas, output extension keys, deterministic status, cost/resource needs, network/execute requirements, supported versions, policy needs, invalidation keys, and conformance fixtures.

### 17.4 CLI surface

```bash
# Acquire, plan, analyze, and publish
tcg source resolve 'pypi:sqlalchemy==<exact-version>' --json
tcg source acquire <source-id> --artifact-digest sha256:...
tcg analyze plan <source-id> --profile composition
tcg analyze run <plan-id>
tcg epoch validate <candidate-epoch>
tcg epoch publish <candidate-epoch>

# Resolve and search every entity kind
tcg resolve 'sqlalchemy.orm.Session.execute' --epoch <epoch>
tcg search 'async method that executes a statement without filesystem writes' \
  --kind method --effect-not filesystem.write --detail card
tcg entity show <ceid> --views interface,behavior,effects,errors,tests
tcg variable show <ceid> --reads --writes --aliases --influences
tcg capsule build --members query:session-subsystem --detail boundary

# First-class edge operations
tcg edge show <edge-id> --assertions --features --descriptions --evidence
tcg edge search 'public methods calling network writers without direct tests' \
  --predicate calls_may --source-visibility public \
  --target-effect network.write --without incoming:tests
tcg edge neighbors <ceid> --direction both --predicate calls_may,tests
tcg edge pattern run queries/untested-network-path.yaml --max-expansions 100000
tcg edge diff --from <epoch-a> --to <epoch-b> --coverage-changes
tcg edge features describe uceg.fp.edge.wl_neighborhood

# Compatibility and route operations
tcg compat signature show <port-id> --variants --detail full
tcg compat check --producer <a>:output --consumer <b>:input \
  --purpose compose --environment env:python312-linux --explain
tcg compat candidates --producer <port-id> --limit 100
tcg compat adapters --producer <a> --consumer <b> --max-hops 3
tcg compat explain <assessment-id> --dimensions --witness --minimal-core
tcg route solve --from <port-a> --to <port-b> --alternatives 4 --detail handles

# Query and model-router diagnostics
tcg query compile 'what writes Session identity state?' --show-ir --no-model
tcg query replay <query-receipt-id>
tcg router explain <task-receipt-id>
tcg router evaluate --workload eval/workloads/package-code.yaml

# Change and verification
tcg impact <ceid> --change signature
tcg change plan change.yaml --base <workspace-snapshot>
tcg change apply <plan-id> --verify --receipt
tcg diff graph --from <base> --to <result>
```

No unbounded all-pairs compatibility command should exist. Every query has graph, policy, candidate, path, time, result, detail, and token budgets.

### 17.5 REST/gRPC surface

Core operations:

- `POST /v1/sources:resolve`, `:acquire`, `:inventory`;
- `POST /v1/analysis-plans`, `/v1/analysis-runs`, `/v1/epochs:publish`;
- `POST /v1/entities:search`, `GET /v1/entities/{id}`, `:expand`;
- `POST /v1/edges:search`, `:neighbors`, `:pattern`, `:diff`;
- `GET /v1/edges/{id}/assertions|features|descriptions|evidence`;
- `GET /v1/entities/{id}/compatibility-signatures`;
- `POST /v1/compatibility:check`, `:candidates`, `:adapter-paths`;
- `GET /v1/compatibility-assessments/{id}` and `:replay`;
- `POST /v1/routes:solve`, `/v1/slices:build`, `/v1/capsules:build`;
- `POST /v1/changes:plan`, `:apply`, `:verify`;
- registry APIs for extensions, analyzers, descriptions, fingerprints, embeddings, evaluators, and models.

High-volume streams use gRPC. Every request pins epochs and budgets; every response includes coverage, truncation, continuation, cache status, decisive score contributions, and a receipt ID.

### 17.6 Compact MCP surface

Avoid one MCP tool per predicate or analyzer. Use meta-tools:

| Tool | Operations |
|---|---|
| `code_search` | search entities, variables, groups, descriptions, edges, signatures |
| `code_resolve` | resolve IDs, occurrences, cards, bodies, native facts |
| `code_expand` | typed neighborhoods, details, evidence, alternate views |
| `code_edge_search` | search, show, pattern, diff, negatives, explain |
| `code_compatibility` | signatures, check, candidates, adapters, explain, replay |
| `code_path` | exact graph paths and separately labeled potential composition routes |
| `code_slice` | token/policy-bounded context selection |
| `code_capsule` | build/resolve black-box group boundary |
| `code_diff` | source, entity, edge, contract, coverage, and semantic graph diff |
| `code_evidence` | evidence, contradictions, derivations, receipts |
| `code_coverage` | attempted/supported/resolved/observed/verified coverage |
| `code_verify` | run permitted deterministic/static/test/runtime oracles |

Return handles and compact cards by default. Source bodies require an explicit resolve operation after authorization and selection.

## 18. Test and evaluation architecture

### 18.1 Contract, identity, and extension tests

- canonical CBOR/ID vectors shared across Python, TypeScript, Rust, and JVM clients;
- Unicode, paths, namespaces, byte ranges, overloads, locals, generated code, and versions;
- hash collision defense by comparing stored canonical keys;
- Protobuf forward/backward compatibility and retired-field reservation;
- registry namespace ownership, schema compatibility, deprecation, and migration;
- arbitrary new feature/description/embedding/compatibility extensions without kernel changes;
- n-ary relation projections round-trip to the same canonical relation;
- deterministic reproduction across process order and machines.

### 18.2 Python golden corpus

Hand-verify fixtures for:

- every binding form listed in section 4.5;
- nested scopes, closures, comprehensions, pattern matching, descriptors, metaclasses;
- overloads, protocols, generics, decorators, re-exports, namespace packages;
- dynamic imports, `getattr`, monkey patches, module `__getattr__`, plugins;
- async/generators/context managers/exceptions/cancellation;
- dataclasses, Pydantic, SQLAlchemy, Click/Typer, FastAPI, pytest;
- stubs versus runtime source, generated files, C/native boundaries;
- hostile archives, metadata, encodings, paths, symlinks, and decompression cases.

Differentially compare supported facts against Python AST/symtable, SCIP, type checkers, runtime inspection, coverage, and CodeQL where appropriate. Disagreement is a test outcome to explain, not automatically a system failure.

### 18.3 Edge and compatibility poison corpus

Create pairs that look similar but differ in one or interacting hard dimension:

- same name but incompatible type; different name but compatible contract;
- same schema fields but units or timezone mismatch;
- sync/async, stream/batch, nullable/non-null, ordered/unordered;
- lossless versus lossy converter; retry-safe versus non-idempotent;
- same type but forbidden network/secret/global-state effect;
- same API across incompatible versions/platforms/ABIs;
- permissive-looking docs contradicted by type/test/runtime evidence;
- embedding-near descriptions with opposite negative constraints;
- compatible individual edges whose complete route violates a global resource, state, or policy constraint.

Launch criteria include zero false automatic connections on the poison corpus. Unsupported reasoning returns `unknown`, never compatible. Because zero errors on a finite fixture is not a production risk estimate, also report a one-sided statistical upper confidence bound from held-out, time/package-split, and randomly blocked-pair audits.

### 18.4 Fingerprint and retrieval tests

- exact canonical digest sensitivity and declared invariances;
- MinHash/SimHash empirical recall and collision curves by feature family;
- clone fingerprint stability under formatting/alpha-renaming and sensitivity to behavior changes;
- graph fingerprint response to relevant and irrelevant topology edits;
- ANN recall@k by model/view, quantization, and package split;
- BM25, LSH, graph, sparse, dense, and fusion ablations;
- same-package, cross-version, cross-package, and future cross-language evaluation;
- randomly sample blocked-out pairs and fully assess them to estimate hidden false negatives.

### 18.5 Route, change, and receipt tests

- direct, one-adapter, multi-adapter, ambiguous, cyclic, and no-route cases;
- bidirectional solver agreement with exhaustive search on small graphs;
- dominance pruning preserves the only valid route;
- every route edge has a witness or explicit candidate/unknown label;
- body resolution happens only after selection;
- change applies only against matching snapshot/occurrence preconditions;
- semantic graph diff identifies expected and unexpected deltas;
- a clean runner reproduces the full query, selection, change, verification, and receipt.

Required property/metamorphic tests:

- adding an authoritative hard constraint cannot enlarge the eligible candidate set;
- adding unknown or low-authority evidence cannot create authoritative incompatibility;
- stronger evidence cannot silently erase conflicting assertions;
- exact verified replay outranks similar unverified candidates within the same policy;
- every query respects pair-solve, block-expansion, LSH-probe, ANN-candidate, adapter-hop, and route-state counters as corpus size grows.

### 18.6 Security, policy, and fault tests

- authorize before search, adjacency expansion, denormalization, caching, and vector retrieval;
- ensure result counts, scores, embeddings, shared caches, and graph topology do not leak other tenants;
- malicious package source/docstrings cannot rewrite instructions, extension definitions, or policy;
- source egress and model routing honor body/summary/hash-only classes;
- analyzer crashes, timeouts, malformed shards, stale caches, partial publication, and corrupted CAS objects fail closed;
- builds/runtime probes remain sandboxed and opt-in;
- license, takedown, revocation, and retention changes invalidate serving projections promptly.

### 18.7 Core metrics

| Area | Metrics |
|---|---|
| Inventory | supported entity/occurrence recall, coverage-accounting completeness |
| Edge extraction | precision/recall by predicate, modality, dynamic class, analyzer |
| Blocking | pair reduction ratio and compatible-pair recall |
| Search | recall@k, MRR, nDCG, no-match abstention, diversity, explanation fidelity |
| Compatibility | false auto-wire rate, verdict precision/recall, unknown quality, minimal-core accuracy |
| Routes | verified success, adapter loss/cost, path length, pair solves, no-route accuracy |
| Context | answer/change success versus tokens, bodies, entities, edges, alternatives, detail |
| Router | quality/cost/latency Pareto frontier, escalation, retries, regret, calibration |
| Incremental | invalidation precision/recall, reuse, update amplification, stale-hit rate |
| Operations | p50/p95/p99 latency, index bytes/entity/edge, throughput, recovery |
| Safety | policy leaks, sandbox violations, unverified promotions, rollback rate |

Measure `1/2/4/8` alternatives and `H0`–`H4` detail as explicit experimental factors. Also vary numbers of entities, ports, edge claims, decisive edges, descriptions, and embedding channels independently. More context should have to earn its tokens.

## 19. Twelve-week first build

This is the recommended first slice, assuming a small experienced team and one representative large PyPI package plus a growing golden corpus.

### Week 1 — contracts and threat model

- freeze identity lattice, entity/occurrence/relation/extension envelopes, epochs, coverage states;
- define safe acquisition and runtime separation;
- publish canonical cross-language ID vectors and initial predicate/role registries.

**Gate:** byte-identical IDs across two clients; malformed/ambiguous identity cases fail explicitly.

### Week 2 — extension registry and evidence kernel

- implement descriptor/feature registries, evidence, modality, polarity, derivation, policy labels;
- implement analyzer SDK and conformance runner;
- register initial entity, edge, port, description, compatibility, hash, and embedding extensions.

**Gate:** a third-party extension can be added without modifying kernel tables or Protobuf envelopes.

### Week 3 — safe PyPI acquisition

- resolve and acquire exact wheel/sdist artifacts, verify hashes, safely unpack;
- extract metadata, files, entry points, typing markers, licenses, provenance;
- create snapshot/build/analysis manifests.

**Gate:** hostile acquisition fixtures fail closed; no package code executes.

### Week 4 — exhaustive Python entity inventory

- AST, lossless CST, symtable, tokens, docs, metadata;
- enumerate packages, modules, classes, callables, variables, ports, occurrences;
- initial cards and coverage ledger.

**Gate:** at least 99% recall for declared supported golden syntactic entities and 100% visible parse/coverage gaps.

### Week 5 — precise symbols, types, and core edges

- integrate SCIP/type-checker facts;
- definitions, references, imports, calls, inheritance, reads/writes, tests/docs;
- preserve candidate/dynamic/native uncertainty.

**Gate:** exact navigation known-answer queries pass and every edge has producer/scope/evidence.

### Week 6 — ports, edge features, and immutable publication

- semantic ports, explicit edge assertions, n-ary calls, feature bundles;
- CAS/Parquet/adjacency/registry storage and atomic epoch publication;
- dependency graph for incremental invalidation.

**Gate:** interrupted jobs cannot expose partial epochs; graph replay is deterministic.

### Week 7 — exact, lexical, and typed graph retrieval

- exact maps, fielded BM25, bitmap filters, paged adjacency, bounded QueryIR;
- edge search/show/explain and query receipts;
- known-answer entity/edge workload.

**Gate:** exact queries are top-1; all results show coverage, decisive fields, and truncation.

### Week 8 — compatibility signatures and deterministic solver

- direction/purpose variants and initial compatibility dimensions;
- typed blocking, exact pair checks, adapters, unknown semantics, minimal blockers;
- direct and one-adapter routes.

**Gate:** zero false auto-wires on poison fixtures; unknown is never a wildcard.

### Week 9 — fingerprints, embeddings, and route alternatives

- exact structural hashes, MinHash/SimHash, graph neighborhoods, optional selected embeddings;
- calibrated fusion, diversity, 1/2/4/8 route alternatives and H0–H4 details;
- CodeCapsules and CodeSlice optimizer.

**Gate:** approximate lanes improve a named retrieval metric or remain disabled; blocking removes at least 99% of naïve pairs while retaining all labeled compatible pairs in the evaluation set.

### Week 10 — CLI, API, MCP, and harness

- deliver surfaces in section 17;
- AGENTS.md/CLAUDE.md, path rules, skills, hooks, router gateway, receipts;
- demonstrate two agent harnesses.

**Gate:** an agent finds, explains, and resolves a selected entity/edge/route without receiving whole-package source.

### Week 11 — effects, tests, runtime, model-router evaluation

- static effects/errors, test/doc linkage, optional sandboxed runtime traces;
- deterministic/local/SLM/cheap/strong selector arms and verifier loop;
- package/release/time-split router evaluation.

**Gate:** learned routing must beat rule-only baseline on verified total-cost/quality metrics or stay in shadow mode.

### Week 12 — scale, security, and reproducible release proof

- 10M-edge synthetic-plus-real load test and 100K-port compatibility benchmark;
- fault, policy, hostile-package, stale-index, and publication tests;
- clean install and exact proof bundle.

**Gate:** all earlier gates pass; selected route execution/change verifies independently and reproduces from receipts.

## 20. First backlog

### P0: truth and contracts

- `CORE-001` Canonical CBOR, ID lattice, collision table, cross-language test vectors.
- `CORE-002` Immutable epoch, manifest, shard, and publication contracts.
- `CORE-003` Evidence, modality, polarity, may/must, coverage, and contradiction model.
- `EXT-001` Namespaced extension descriptor registry and schema resolver.
- `EXT-002` Typed `FeatureAssertion` storage, indexes, policy, and derivation.
- `EXT-003` Extension conformance kit, migrations, deprecation, and test vectors.
- `REL-001` Binary/n-ary relation identity, assertions, inverse projections, endpoint roles.
- `REL-002` Predicate ontology with entity-kind constraints and 100 golden relations.
- `PORT-001` Extensible port and boundary contracts.
- `DESC-001` Description view registry and deterministic core renderers.

### P0: package and Python ingestion

- `PYPI-001` Simple API resolver, artifact selection, hash verification, acquisition receipts.
- `SEC-001` Safe archive extraction and hostile fixture corpus.
- `PY-001` AST/CST/token file and declaration inventory.
- `PY-002` Symtable binding, variable-role, scope, occurrence, read/write extraction.
- `PY-003` SCIP/native symbol reconciliation and exact references.
- `PY-004` Type/signature/overload/protocol extraction.
- `PY-005` N-ary call, argument binding, dispatch uncertainty, and call edges.
- `PY-006` Dataclass/model/descriptor/framework surface recognizers.
- `PY-007` Tests/docs/examples/entry-point linkage.
- `PY-008` Optional effects, flow, and sandboxed runtime analyzer.

### P0: edge search and compatibility

- `EDGE-001` First-class edge search document and feature bundle.
- `EDGE-002` Exact/predicate/endpoint/role/modality/evidence indexes.
- `EDGE-003` Fielded edge BM25 and score explanations.
- `EDGE-004` Paged forward/reverse adjacency and bounded edge pattern DSL.
- `COMP-001` Sparse compatibility signatures and variant activation.
- `COMP-002` Dimension/evaluator registry, directional verdicts, witnesses, unknowns.
- `COMP-003` Typed block indexes and randomized blocked-pair audit.
- `COMP-004` Pair assessment cache and dependency-aware invalidation.
- `COMP-005` Adapter registry and bounded route solver.
- `COMP-006` Compatibility poison corpus and zero-false-auto-wire gate.

### P1: retrieval, descriptions, and models

- `FP-001` Exact signature/schema/effect/error/environment hashes.
- `FP-002` Token/AST winnowing, MinHash, weighted MinHash, and SimHash projections.
- `FP-003` Typed WL-neighborhood, motif, path, and trace fingerprints.
- `EMB-001` Embedding registry, multi-vector records, policy, parallel model revisions.
- `EMB-002` First endpoint/edge/behavior ANN channels and ablation harness.
- `CAP-001` VariableCard, CodeEntityCard, EdgeCard, and CompatibilityCard.
- `CAP-002` CodeCapsule boundary derivation and abstraction-loss ledger.
- `SLICE-001` Demand-aware, token-bounded CodeSlice optimizer.
- `QUERY-001` Deterministic prompt-to-DemandIR/QueryIR compiler and templates.
- `ROUTER-001` Deterministic arm router and deployment-gateway adapter.
- `ROUTER-002` Calibrated arm success/cost models, shadow evaluation, escalation.

### P1: surfaces, changes, and evaluation

- `CLI-001` Source/analyze/entity/variable/edge/compat/route commands.
- `API-001` Versioned REST/gRPC and stable pagination/streaming.
- `MCP-001` Compact meta-tools with handles, budgets, and receipts.
- `HARNESS-001` AGENTS/CLAUDE rules, skills, hooks, and two-harness proof.
- `CHANGE-001` Workspace CAS, ChangeIR, lossless Python edits, rollback.
- `VERIFY-001` Static/test/runtime/semantic-graph verification pipeline.
- `EVAL-001` Package/entity/edge/search/compatibility/change gold corpus.
- `EVAL-002` 1/2/4/8 alternative and H0–H4 detail factorial experiments.
- `EVAL-003` Token/compute/cost/quality router evaluation and replay dashboard.
- `SCALE-001` 10M/50M/100M entity-edge synthetic load profiles.

## 21. Alternatives considered for every major layer

Taedri should support adapters for several of these, but the recommended combination is chosen for precision, extensibility, replay, and cost.

| Layer | Alternatives | Recommended role |
|---|---|---|
| Context state | raw chat history, rolling summary, event log, blackboard, task-state machine, pointer manifest | pointer-rich `ContextManifest`; resolve history lazily |
| Intent | keyword taxonomy, rules, classifier, semantic routes, frame/slot grammar, LLM plan | rules/templates first, typed `CodeDemandIR`, escalating parser arms |
| Query representation | SQL, Datalog, Cypher/GQL, SPARQL, GraphQL, JSON DSL, AST query, natural language | stable `CodeQueryIR` compiled to multiple backends |
| Entity identity | source name, qualified name, AST path, compiler symbol, UUID, purl/SWHID, content hash | identity lattice plus native locators; no forced global rename |
| Entity description | docstrings, symbol docs, source chunks, generated summaries, learned vectors, examples | parallel evidence-linked `DescriptionAssertion`s |
| Entity card | flat JSON, protobuf message, RDF shape, document chunk, tool schema | small stable envelope plus extension/aspect registry |
| Relation storage | property graph, RDF/RDF-star, relational facts, Datalog, CPG, document store | immutable relation facts + n-ary nodes + replaceable projections |
| Graph execution IR | DAG, hypergraph, Petri net, dataflow IR, workflow DSL, constraint model | port-level hypergraph/GraphIR with adapters and global constraints |
| Exact retrieval | hash/KV, trie/FST, SQL index, compiler/LSP/SCIP, ripgrep | use all applicable exact lanes before semantics |
| Lexical retrieval | grep, trigram, BM25, learned sparse/SPLADE, fuzzy edit distance | fielded BM25 plus exact/fuzzy specialized fields |
| Structural retrieval | AST patterns, tree edit, clone index, CFG/DFG, WL/motifs | several versioned fingerprints, task-selected |
| Semantic retrieval | one general embedding, code embedding, doc embedding, graph embedding, late interaction | extensible multi-vector channels; never one universal vector |
| Approximate blocking | MinHash, SimHash, LSH, ANN, canopy clustering, Bloom filters | typed blocks first, multiple candidate-only approximate lanes |
| Graph search | BFS/DFS, bidirectional, A*, Dijkstra, k-shortest, beam, SMT/ASP/Datalog | typed bidirectional multiobjective route solver with bounded fallbacks |
| Compatibility | name/signature equality, type checker, schema diff, test co-use, learned score, LLM judge | axis/evaluator registry with hard evidence and explicit unknown |
| Adapters | hard-coded converters, registry, synthesis, search existing code, generated glue | verified existing-code adapters first; synthesized adapter must verify |
| Result payload | full source, top-k chunks, entity cards, routes, capsules, handles | handles → cards → decisive edges → selected bodies |
| Alternative count | single winner, fixed top-k, diversity/MMR, Pareto frontier, adaptive | experiment 1/2/4/8; adaptive by ambiguity and risk |
| Selector | deterministic rules, rank fusion, classifier, cross-encoder, bandit, SLM/LLM judge | rules/fusion first; calibrated local then stronger arms |
| Orchestration | scripts, DAG engine, actor system, LangGraph, Temporal, queue workers, multi-agent | modular jobs/state machine; add workflow engine when operations justify it |
| Provider routing | direct SDKs, gateway, LiteLLM, custom proxy, managed router | gateway adapter below Taedri’s capability router |
| Editing | text patch, regex, AST regenerate, lossless CST, LSP refactor, synthesis | exact occurrences + language-specific lossless/refactor engine |
| Verification | model review, compile, static analysis, tests, property tests, sandbox trace, human | independent layered oracles proportional to risk |
| Storage | graph DB, relational DB, search engine, vector DB, lakehouse, CAS | canonical CAS/columnar facts; specialized replaceable indexes |
| Evolution | destructive migration, schemaless blobs, EAV, plugin aspects, event sourcing | typed namespaced extension assertions plus immutable epochs |

The architecture deliberately combines approaches rather than declaring one winner. Exact facts, typed graphs, fingerprints, embeddings, and models answer different questions and fail differently.

## 22. Recommended first vertical slice

The smallest slice that proves the core thesis is:

1. One exact, large, pure-Python-or-mostly-Python PyPI release plus wheel and sdist.
2. `ContextManifest`, `CodeDemandIR`, and deterministic QueryIR templates.
3. Exact package/snapshot/build identity and exhaustive supported entity/variable occurrence inventory.
4. Verified `CodeEntityCard`, `VariableCard`, `EdgeCard`, and evidence/coverage ledger.
5. Port-level n-ary UCEG and a minimal `GraphIR` for routes.
6. First-class searchable edges with extensible feature bundles and descriptions.
7. Exact/history + fielded BM25 + typed forward/reverse adjacency.
8. Compatibility signatures and directional typed route solving without all-pairs materialization.
9. Exact contract hashes, token/AST fingerprints, MinHash/SimHash, typed graph-neighborhood hashes, and one or two benchmarked embedding channels.
10. Route-handle experiments at `1/2/4/8` alternatives and `H0`–`H4` detail.
11. Deterministic, local classifier/SLM, cheap model, and strong-model selector arms in shadow comparison.
12. Post-selection source-body resolution, lossless ChangeIR, independent verification, semantic graph diff, and exact receipts.

Success means an agent can locate, understand, connect, or safely change existing package code using a small evidence-backed slice, while using fewer model tokens than a repository-reading baseline and achieving equal or better verified outcomes.

## 23. Non-negotiable invariants

1. Source-native names remain unchanged; global uniqueness lives in sidecar identities.
2. Every exact ID stores and checks the canonical identity key behind its digest.
3. Every entity, occurrence, edge, feature, description, embedding, and observation is scoped and provenance-bearing.
4. Original facts are retained when reconciliation or summaries are generated.
5. Missing and unknown are not false, zero, wildcard, compatible, or incompatible.
6. Similarity can nominate; only declared evaluators, evidence policy, adapters, and verification can authorize composition.
7. Potential compatibility edges are not silently mixed with observed/extracted code edges.
8. No all-pairs compatibility materialization; unary signatures and sparse on-demand pairs only.
9. Authorization precedes retrieval, traversal, denormalization, embeddings, caches, and aggregate statistics.
10. Runtime/build execution is opt-in, isolated, bounded, and receipt-producing.
11. Queries and results pin graph, policy, analyzer, schema, feature, model, and solver epochs.
12. LLM output remains an inferred assertion until independently supported.
13. Source bodies resolve only after selection unless the task inherently requires body search.
14. Every automatic code change has exact preconditions, a semantic delta, verifiers, rollback, and receipt.
15. Extensibility does not mean semantic ambiguity: every extension has a namespace, schema, missing semantics, producer, policy, and tests.

## 24. Research and standards register

The design should integrate with, preserve, or learn from these primary sources rather than reinventing them:

- Python packaging: [Core Metadata](https://packaging.python.org/en/latest/specifications/core-metadata/), [Wheel](https://packaging.python.org/en/latest/specifications/binary-distribution-format/), [Entry Points](https://packaging.python.org/en/latest/specifications/entry-points/), [Simple Repository API](https://packaging.python.org/en/latest/specifications/simple-repository-api/).
- Python analysis: [`ast`](https://docs.python.org/3/library/ast.html), [`symtable`](https://docs.python.org/3/library/symtable.html), [`inspect`](https://docs.python.org/3/library/inspect.html), [`importlib.metadata`](https://docs.python.org/3/library/importlib.metadata.html).
- Cross-language code facts: [SCIP](https://github.com/scip-code/scip), [Kythe schema](https://kythe.io/docs/schema/), [Glean](https://github.com/facebookincubator/Glean).
- Syntax and edits: [Tree-sitter query syntax](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html), [LibCST](https://libcst.readthedocs.io/en/latest/why_libcst.html).
- Deeper code analysis: [CodeQL Python data flow](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/).
- Extensible interchange: [Protocol Buffers](https://protobuf.dev/programming-guides/proto3/), [JSON-LD 1.1](https://www.w3.org/TR/json-ld/), [Apache Arrow extension types](https://arrow.apache.org/docs/python/extending_types.html).
- Software identity/provenance: [package URL](https://github.com/package-url/purl-spec), [Software Heritage identifiers](https://www.swhid.org/specification/v1.1/), [SPDX](https://spdx.dev/use/specifications/), [SLSA provenance](https://slsa.dev/spec/v1.2/provenance), and [W3C PROV](https://www.w3.org/TR/prov-overview/).
- Exact and locality-sensitive fingerprints: [NIST Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final), Broder’s [MinHash/resemblance paper](https://doi.org/10.1109/SEQUEN.1997.666900), Charikar’s [similarity estimation/SimHash paper](https://www.cs.princeton.edu/courses/archive/spring04/cos598B/bib/CharikarEstim.pdf), Ioffe’s [weighted MinHash work](https://research.google/pubs/improved-consistent-sampling-weighted-minhash-and-l1-sketching/), and [SourcererCC](https://arxiv.org/abs/1512.06448).
- Graph similarity: [Weisfeiler-Lehman graph kernels](https://www.jmlr.org/papers/v12/shervashidze11a.html), [graphlet kernels](https://proceedings.mlr.press/v5/shervashidze09a.html), [GIN/WL expressiveness](https://arxiv.org/abs/1810.00826), and [nauty/Traces](https://pallini.di.uniroma1.it/).
- Code and semantic retrieval candidates: [CodeSearchNet](https://arxiv.org/abs/1909.09436), [CodeBERT](https://arxiv.org/abs/2002.08155), [GraphCodeBERT](https://arxiv.org/abs/2009.08366), [UniXcoder](https://arxiv.org/abs/2203.03850), [CodeT5+](https://arxiv.org/abs/2305.07922), [CoIR](https://arxiv.org/abs/2407.02883), [CoQuIR](https://arxiv.org/abs/2506.11066), [SPLADE](https://arxiv.org/abs/2107.05720), and [ColBERT](https://arxiv.org/abs/2004.12832). These are evaluation candidates, not mandatory dependencies.
- Native compatibility models: [Python protocols](https://typing.python.org/en/latest/spec/protocol.html), [TypeScript compatibility](https://www.typescriptlang.org/docs/handbook/type-compatibility.html), [Rust SemVer compatibility](https://doc.rust-lang.org/cargo/reference/semver.html), [OpenAPI 3.2.0](https://spec.openapis.org/oas/v3.2.0.html), [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core), [WIT](https://component-model.bytecodealliance.org/design/wit.html), and [Buf breaking-change detection](https://buf.build/docs/breaking/).
- Hybrid and approximate retrieval: [RRF](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf), [HNSW](https://arxiv.org/abs/1603.09320), [FAISS](https://arxiv.org/abs/1702.08734), [DiskANN](https://www.microsoft.com/en-us/research/publication/diskann-fast-accurate-billion-point-nearest-neighbor-search-on-a-single-node/), [pgvector hybrid search](https://github.com/pgvector/pgvector#hybrid-search), and [Qdrant hybrid/multi-stage queries](https://qdrant.tech/documentation/search/hybrid-queries/).
- Near-duplicate systems precedent: [Google SimHash near-duplicate work](https://research.google/pubs/detecting-near-duplicates-for-web-crawling/).
- Routing/harness precedents: [LiteLLM Router](https://docs.litellm.ai/docs/routing), [RouteLLM](https://github.com/lm-sys/RouteLLM), [Semantic Router](https://github.com/aurelio-labs/semantic-router), [Claude Code project instructions](https://code.claude.com/docs/en/memory), and [Claude Code hooks](https://code.claude.com/docs/en/hooks).

These are ingredients and precedents, not a claim that any one existing project already implements Taedri CodeGraph.

## 25. Final recommendation

Build **Taedri CodeGraph** as a code semantic compiler and retrieval control plane, not as a source-chunk RAG application.

The key abstraction is:

```text
existing package bytes
  -> exact entities and occurrences
  -> evidence-bearing relation hypergraph
  -> extensible features, descriptions, compatibility signatures,
     hashes, LSH families, embeddings, and graph projections
  -> cheap typed retrieval and bounded composition
  -> progressive context and model escalation
  -> exact execution/change handles
  -> independent verification and receipts
```

The most important implementation decision is to keep truth, search, compatibility, and generated descriptions separate but linkable. That makes it possible to add hundreds of future description types, compatibility axes, analyzers, fingerprint families, embedding models, languages, and domain schemas without weakening identity or making old results unreplayable.
