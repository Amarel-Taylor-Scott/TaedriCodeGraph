# Taedri CodeGraph: Exhaustive Code Entity Description Atlas

**Status:** architecture and implementation registry  
**Date:** 2026-07-15  
**Scope:** existing code in PyPI packages first; language- and ecosystem-neutral kernel  
**Repository:** `TaedriCodeGraph`  

## Contents

1. [The answer in one sentence](#1-the-answer-in-one-sentence)
2. [Non-negotiable separations](#2-non-negotiable-separations)
3. [What can be described](#3-what-can-be-described-the-subject-universe)
4. [Describe the correct referent](#4-describe-the-correct-referent)
5. [Universal projection envelope](#5-universal-projection-envelope)
6. [Exact and lossless descriptions](#6-exact-and-lossless-descriptions)
7. [Plain-text description atlas](#7-plain-text-description-atlas)
8. [Keywords, keyphrases, and lexical microfeatures](#8-keywords-keyphrases-and-lexical-microfeatures)
9. [Labels, tags, taxonomies, and ontologies](#9-labels-tags-taxonomies-and-ontology-descriptions)
10. [Typed facts, schemas, logic, and contracts](#10-typed-facts-schemas-logic-and-contract-descriptions)
11. [Compatibility descriptions](#11-compatibility-descriptions)
12. [Sparse and deterministic retrieval](#12-sparse-and-deterministic-retrieval-representations)
13. [Hashes, fingerprints, sketches, LSH, and ANN](#13-hash-fingerprint-sketch-lsh-and-ann-description-atlas)
14. [Embedding atlas](#14-embedding-description-atlas)
15. [Graph and relational descriptions](#15-explicit-graph-and-relational-descriptions)
16. [Behavior, history, usage, and quality](#16-behavioral-historical-social-and-operational-descriptions)
17. [Evidence, provenance, contradiction, and trust](#17-evidence-provenance-contradiction-and-trust-descriptions)
18. [Entity-by-entity portfolios](#18-entity-by-entity-descriptor-portfolios)
19. [Extensible registry architecture](#19-fully-extensible-registry-architecture)
20. [Physical index mapping](#20-physical-index-mapping)
21. [Generation and invalidation waterfall](#21-generation-and-invalidation-waterfall)
22. [Coverage and completeness ledger](#22-coverage-and-completeness-ledger)
23. [Evaluation atlas](#23-evaluation-atlas)
24. [Design anti-patterns](#24-design-anti-patterns)
25. [Research and standards foundation](#25-research-and-standards-foundation)
26. [Final architecture recommendation](#26-final-architecture-recommendation)

## 1. The answer in one sentence

Every code entity should be represented by an **open, versioned `DescriptionPortfolio`** containing separate exact facts, source and structural forms, plain-language views, keywords, labels, typed contracts, sparse features, hashes and similarity sketches, multiple purpose-specific embeddings, graph features, observed behavior, history, policy, and evidence—with explicit applicability, provenance, invariance, uncertainty, freshness, and index semantics for every projection.

There must not be one universal description, one universal vector, one universal hash, or one universal score.

This document is an exhaustive **bootstrap registry**, not a closed universe. No finite document can enumerate every future language construct, framework contract, embedding model, domain ontology, or fingerprint. The system is exhaustive in the stronger operational sense: every descriptor family is registered, every applicable descriptor has an explicit materialization state, and new descriptors can be added without changing canonical entity identity or destructively migrating old records.

## 2. Non-negotiable separations

The architecture must keep the following concepts distinct:

1. **Identity:** which entity, occurrence, version, build, or observation is being discussed.
2. **Canonical facts:** exact source, signature, type facts, package metadata, and analyzer outputs.
3. **Claims:** statements derived from facts, possibly uncertain or contradictory.
4. **Descriptions:** audience- and task-specific renderings of facts and claims.
5. **Candidate features:** hashes, LSH buckets, embeddings, and learned scores used to retrieve or rank.
6. **Contracts:** typed requirements, provisions, effects, errors, state, and compatibility dimensions.
7. **Evidence:** source spans, analyzer records, tests, traces, and verification results supporting a claim.
8. **Policy:** tenant, license, retention, secrecy, egress, and execution constraints.

The governing rule is:

> Exact identity and evidence establish what something is. Similarity proposes candidates. Typed contracts and verification decide whether it can be used.

Consequences:

- A source hash is not a semantic description.
- A fuzzy hash is not proof of equivalence or provenance.
- An embedding is not a type system or compatibility oracle.
- A generated summary is not a canonical fact.
- A label without provenance is not trustworthy metadata.
- An absent field is not `false`, zero, empty, or incompatible.
- Two values from different embedding spaces are not comparable merely because both are vectors.
- Global uniqueness should be supplied through sidecar identity, not forced source-code renaming.

## 3. What can be described: the subject universe

The same projection system applies to all of these subject kinds. A registry key, rather than a hard-coded enum, identifies each kind.

### 3.1 Software artifacts and provenance

- ecosystem, registry, index, catalog, mirror, and source host;
- project, repository, monorepo, subrepository, vendor tree, and fork;
- distribution package, import package, package family, namespace package, and plugin package;
- release, version, tag, commit, tree, source archive, wheel, binary package, and container;
- build, build target, build rule, toolchain, compiler invocation, generated artifact, and deployment;
- dependency declaration, resolved dependency, lock entry, optional feature, extra, platform tag, and environment marker;
- license, notice, attestation, signature, SBOM component, vulnerability record, and policy decision.

### 3.2 Source, syntax, and namespace

- file, virtual file, notebook, cell, source fragment, generated fragment, and embedded language region;
- module, namespace, package namespace, scope, block, compilation unit, translation unit, and crate;
- comment, doc comment, docstring, annotation, attribute, decorator, pragma, directive, and suppression;
- import, include, require, use, export, re-export, alias, wildcard import, and dynamic import;
- token, trivia, identifier occurrence, literal occurrence, expression, statement, declaration, and definition;
- AST node, CST node, IR instruction, bytecode instruction, basic block, SSA value, and phi node;
- macro definition, macro invocation, expansion, template, specialization, generated declaration, and source map.

### 3.3 Values, variables, and storage

- language primitive type and primitive value;
- literal, constant, enum member, flag value, sentinel, default value, and symbolic value;
- declaration, name, binding, variable, parameter, type parameter, field, slot, property, descriptor, and cell;
- global, local, nonlocal, closure capture, receiver, implicit parameter, environment variable, configuration value, and secret reference;
- l-value, r-value, reference, pointer, address, alias set, points-to set, region, buffer, tensor, dataframe, stream, and resource handle;
- heap allocation, stack allocation, object instance, object family, prototype, singleton, pool entry, and serialized object.

### 3.4 Callables and executable units

- function, nested function, anonymous function, lambda, closure, thunk, and partial application;
- method, instance method, class method, static method, extension method, trait method, and interface method;
- constructor, factory, initializer, finalizer, destructor, allocator, deallocator, and context manager;
- getter, setter, deleter, property accessor, descriptor hook, and operator overload;
- overload declaration, implementation, generic instantiation, specialization, bridge, thunk, and wrapper;
- callback, hook, handler, listener, subscriber, middleware, interceptor, validator, and serializer;
- coroutine, async function, generator, async generator, task, actor behavior, job, and scheduled callback;
- query, stored procedure, trigger, migration, shader, kernel, notebook cell, and embedded script.

### 3.5 Types and object models

- class, metaclass, record, struct, union, tagged union, variant, enum, interface, trait, protocol, and mixin;
- abstract base class, data class, schema model, ORM model, message type, event type, exception type, and error code family;
- nominal type, structural type, alias, refinement, dependent type, opaque type, existential, generic type, and higher-kinded type;
- type variable, lifetime parameter, variance declaration, bound, constraint, associated type, and type-level function;
- inheritance relation, implementation, conformance, override, overload set, method-resolution order, and vtable slot;
- schema, shape, unit, dimension, encoding, media type, serialization format, ABI type, and wire type.

### 3.6 Interfaces, operations, and runtime surfaces

- input port, output port, error port, effect port, event port, control port, state port, and resource port;
- API endpoint, RPC method, route, socket, topic, queue, event, signal, channel, and protocol message;
- CLI command, subcommand, positional argument, flag, option, exit code, stdin/stdout/stderr contract, and completion item;
- database table, column, view, index, query, transaction, migration, lineage step, and constraint;
- configuration key, feature flag, environment contract, plugin entry point, extension point, and capability;
- filesystem path contract, network destination, credential scope, permission, trust boundary, and sandbox boundary.

### 3.7 Verification and operational subjects

- test suite, test case, property, invariant, assertion, oracle, fixture, mock, stub, fake, and test parameter;
- benchmark, workload, trace, span, log event, metric, profile, coverage region, and failure sample;
- issue, pull request, review, commit, change set, migration, deprecation, and release note;
- static-analysis finding, diagnostic, warning, vulnerability, exploit condition, and remediation;
- execution, run, environment, observation window, input sample, output sample, state snapshot, and incident.

### 3.8 First-class relations and groups

- directed edge, inverse edge, symmetric relation, ordered n-ary relation, hyperedge, and evidence edge;
- call, reference, define, bind, read, write, mutate, alias, flow, influence, taint, sanitize, throw, catch, import, depend, instantiate, override, satisfy, generate, document, test, and co-change relation;
- entity set, overload set, alias set, call-site candidate set, strongly connected component, community, clone family, and code cluster;
- class capsule, module capsule, subsystem capsule, package capsule, route, workflow, pipeline, agent toolchain, and deployment topology;
- candidate route, chosen route, adapter chain, compatibility assessment, change plan, and verification receipt.

## 4. Describe the correct referent

Before generating any feature, identify the referent layer. The text `x`, the binding named `x`, and the runtime objects observed through `x` are different subjects.

| Referent layer | Example | Why it must remain separate |
|---|---|---|
| Artifact | `foo-2.1.0-py3-none-any.whl` | Bytes, signatures, build tags, and license scope belong here. |
| Snapshot | repository commit or unpacked wheel | Fixes the universe in which identities and edges are valid. |
| File/region | `pkg/a.py`, bytes 100–160 | Anchors exact evidence and parser results. |
| Occurrence | one use of identifier `x` | Has a location, syntactic role, and resolution status. |
| Symbol/entity | `pkg.a.C.m` | Groups definitions and references under a semantic identity. |
| Declaration | overload or forward declaration | May differ from the completing definition. |
| Definition/body | executable implementation | Owns source, control flow, effects, and complexity. |
| Binding | local `x` in one lexical scope | Owns reads, writes, capture, lifetime, and reaching definitions. |
| Type/schema | `list[int]` or JSON schema | Owns assignability, shape, bounds, and serialization rules. |
| Port/contract | parameter `items` | Owns compatibility requirements and mappings. |
| Runtime object/value | one observed list instance | Owns an observation-scoped identity and state; it is not the binding. |
| Object family | values constructed at a site | Aggregates observed shapes and behavior without pretending one instance is universal. |
| Relation | call from `f` to `g` under guard `p` | Direction, roles, modality, and evidence belong to the edge. |
| Group/capsule | class, SCC, subsystem | Owns members and boundary behavior, not concatenated-member prose. |
| Execution observation | test run in environment `E` | Behavior claims are valid only for the stated workload and environment. |
| Release lineage | entity across versions | Owns rename, split, merge, migration, stability, and compatibility history. |

Each projection therefore names at least:

```yaml
subject_ref:
  subject_kind_key: uceg.subject.binding
  subject_id: ceid:...
  snapshot_id: ...
  occurrence_id: null
  build_id: null
  environment_id: null
  observation_id: null
  graph_epoch: ...
```

## 5. Universal projection envelope

Every description, keyword list, label, fingerprint, vector, graph feature, or behavioral summary must use a common envelope.

```yaml
ProjectionEnvelope:
  projection_id: ...
  subject_ref: ...
  descriptor_key: uceg.description.behavior.black_box
  descriptor_version: 1.2.0
  value_schema_ref: uceg-schema://description/black-box/1

  value_or_storage_ref: ...
  value_digest: ...
  natural_language: en
  programming_language: python
  domain_keys: [dataframe]

  producer:
    kind: source|parser|compiler|static_analyzer|runtime|template|model|human
    producer_id: ...
    producer_version: ...
    configuration_digest: ...

  inputs:
    ordered_fact_refs: []
    assertion_refs: []
    source_span_refs: []
    observation_refs: []
    input_digest: ...

  semantics:
    status: present
    assertion_mode: asserted|extracted|inferred|observed|verified
    modality: must|may|must_not|unknown
    confidence: ...
    calibration_id: ...
    applicability_scope: ...
    coverage: ...
    abstraction_loss: ...
    invariances: []
    known_non_invariances: []

  trust:
    evidence_refs: []
    contradiction_refs: []
    verification_refs: []
    freshness_at: ...
    valid_from: ...
    valid_until: ...

  lifecycle:
    created_at: ...
    supersedes: []
    invalidation_keys: []
    graph_epoch: ...
    index_manifest_ids: []

  policy:
    tenant_scope: ...
    access_policy_ref: ...
    license_class: ...
    secrecy_class: ...
    retention_class: ...
    egress_class: ...
```

### 5.1 Explicit materialization states

Every registered descriptor applicable to a subject has one of these states:

- `present`: a current value exists;
- `not_computed`: applicable, deliberately not materialized yet;
- `queued`: applicable and scheduled;
- `stale`: an invalidating input changed;
- `failed`: generation was attempted and failed, with a diagnostic;
- `unsupported`: the current analyzer cannot derive it;
- `unknown`: analysis completed but the value remains unknown;
- `not_applicable`: the descriptor does not semantically apply;
- `withheld`: policy permits recording existence but not value;
- `redacted`: a safe derivative replaced sensitive content;
- `contradictory`: credible assertions disagree;
- `superseded`: retained for history but not current;
- `tombstoned`: the source entity was removed in a later snapshot.

Never encode these states as an empty string, zero vector, all-zero bitset, `false`, or missing row. That would corrupt retrieval, analytics, compatibility, and evaluation.

### 5.2 Descriptor registry definition

```yaml
DescriptorDefinition:
  descriptor_key: uceg.embedding.function.error_behavior
  version: 1.0.0
  family: embedding
  applies_to: [function, method, route, capsule]
  input_view_schema_refs: []
  output_schema_ref: ...
  missing_semantics: explicit_state
  deterministic: false
  candidate_only: true
  allowed_producers: []
  invariance_contract: []
  validation_rules: []
  index_recipes: []
  cost_profile: ...
  policy_requirements: ...
  invalidation_recipe: ...
  evaluation_suite_refs: []
  owner_namespace: ...
```

Registry keys are namespaced. Third parties can add descriptor kinds, models, languages, domains, index recipes, and evidence types without taking ownership of canonical entities.

## 6. Exact and lossless descriptions

These representations answer exact identity, reconstruction, and evidence questions. They should be generated before semantic projections.

### 6.1 Identity and locator fields

- registry and ecosystem identifier;
- normalized distribution name and original distribution name;
- Package URL (`purl`) and qualifiers where applicable;
- Software Heritage identifier or equivalent content-origin identifier;
- repository remote, forge, owner, project, fork lineage, and subdirectory;
- release, semantic version, source tag, commit, tree, archive, and artifact identifiers;
- artifact filename, wheel tag, platform tag, ABI tag, interpreter tag, and build tag;
- exact artifact digests, signature records, attestations, and acquisition receipt;
- snapshot ID, build-universe ID, graph epoch, analyzer epoch, and observation ID;
- language, corpus, root, path, native qualified name, symbol identity, and sidecar CEID;
- occurrence ID, byte range, line/column range, token range, AST/CST node path, and source map;
- definition/declaration/completion relationship and generated-source lineage;
- stable historical identity links for rename, move, split, merge, extraction, inline, and replacement.

SCIP demonstrates a language-neutral index format for definitions and references, while Kythe demonstrates namespaced node facts, semantic node kinds, source anchors, and typed forward/reverse edges. Taedri should ingest those identities and edges where available rather than replacing them with generated prose. See [SCIP](https://scip-code.org/) and the [Kythe schema](https://kythe.io/docs/schema/).

### 6.2 Source-preserving forms

- original artifact bytes;
- original file bytes, encoding, BOM, newline convention, and executable bit;
- exact source slice for declaration, definition, body, expression, statement, and occurrence;
- exact token stream including token classes and byte offsets;
- lossless CST including comments, whitespace, delimiters, and recovery nodes;
- parsed AST including parser version and diagnostics;
- documentation source, markup format, link targets, examples, and source spans;
- literal spelling and decoded value as separate facts;
- macro/template input, expansion output, hygiene/source-map relationships, and compiler-generated entities;
- notebook cell source, execution order, metadata, and output references;
- embedded-language source and host-language boundaries;
- disassembly, bytecode, compiler IR, object symbols, debug symbols, and source maps when available.

### 6.3 Exact structural and contract forms

- native and canonical signature;
- overload-specific signature and overload-set membership;
- declared, inferred, narrowed, observed, and erased types kept separately;
- type parameters, bounds, constraints, variance, defaults, lifetimes, and associated types;
- parameter order, kind, name, optionality, default expression, and calling convention;
- return, yield, awaited result, exception, effect, event, and state ports;
- schema, field order, required fields, nullability, cardinality, shape, dimension, units, precision, encoding, and constraints;
- ABI, calling convention, layout, size, alignment, packing, vtable, mangled name, and symbol visibility;
- preconditions, postconditions, invariants, guards, refinements, and path conditions in structured logic where derivable;
- declared dependency, environment, feature, permission, capability, and version constraints;
- exact participant order and role for edges and n-ary relations.

### 6.4 Canonical serializations

Maintain multiple named canonicalization profiles rather than declaring one representation canonical for every task:

- canonical JSON/CBOR/Protobuf record serialization;
- canonical entity identity tuple;
- canonical signature serialization;
- canonical type and schema serialization;
- canonical port contract serialization;
- canonical effect/error/state contract serialization;
- canonical dependency and environment serialization;
- canonical token stream;
- canonical AST/CST tree serialization;
- canonical CFG/DFG/PDG/SSA serialization;
- canonical graph neighborhood, path, route, and hyperedge serialization;
- canonical runtime trace and input/output observation serialization;
- canonical evidence bundle and exact verification receipt.

Each profile records its implementation, language rules, version, ordering, normalization, collision policy, and known information loss. A canonicalization bug creates a new profile version; it must not rewrite old evidence.

## 7. Plain-text description atlas

Each item below is an independent, versioned view. It may be author-written, extractive, deterministically rendered, model-generated, human-reviewed, or translated. Retain those arms separately.

### 7.1 Identity and orientation views

- native name;
- fully qualified name;
- display name;
- aliases, re-export names, historical names, and common misspellings;
- symbol-kind sentence;
- declaration/definition location sentence;
- owning package/module/class/group sentence;
- provenance and release-scope sentence;
- public/private/internal/generated/test-only status sentence;
- one-line synopsis;
- elevator description;
- concise developer card;
- detailed developer card;
- agent-oriented black-box card;
- operator, security-reviewer, maintainer, beginner, and domain-expert versions;
- “what changed since version X” orientation;
- “why this entity exists” design-intent statement;
- “what this entity is not” contrastive statement.

### 7.2 Purpose, capability, and mechanism views

- problem solved;
- user intent satisfied;
- business/domain capability;
- functional responsibility;
- architectural role;
- algorithm family;
- design pattern or anti-pattern role;
- mechanism or implementation approach;
- inputs transformed into outputs;
- state transition performed;
- orchestration or coordination role;
- abstraction level;
- capability provided;
- capability required;
- delegated responsibilities;
- extension points and customization hooks;
- assumptions and environmental prerequisites;
- limitations and intentionally unsupported behavior;
- alternatives, substitutes, complements, wrappers, and adapters;
- comparative description against sibling overloads or similar entities.

### 7.3 Interface and contract views

- full human-readable signature;
- parameter-by-parameter contract;
- positional, keyword-only, named, variadic, and implicit argument behavior;
- default semantics, including whether a default is computed, shared, or sentinel-based;
- input type, schema, shape, units, encoding, range, precision, nullability, and cardinality;
- accepted coercions, normalization, parsing, and validation;
- output, return, yield, awaited, callback, event, and stream contracts;
- ordering, stability, uniqueness, mutability, ownership, lifetime, copying, and borrowing;
- preconditions, postconditions, invariants, refinements, guards, and path-sensitive requirements;
- sync/async, batch/stream, push/pull, eager/lazy, blocking/nonblocking, and cancellation behavior;
- idempotence, retry safety, atomicity, determinism, commutativity, associativity, and reversibility;
- compatibility description, compatible consumers/providers, required adapters, and lossy conversions;
- version-, platform-, environment-, feature-, and dependency-conditioned contracts.

### 7.4 Behavior and algorithm views

- black-box behavior;
- stepwise algorithm narrative;
- white-box implementation summary;
- control-flow narrative;
- data-flow and lineage narrative;
- branch and path-condition narrative;
- state-machine narrative;
- lifecycle narrative from construction through teardown;
- normal-case, boundary-case, invalid-input, and failure-case behavior;
- numerical properties, tolerances, convergence, stability, and precision loss;
- caching, memoization, laziness, batching, vectorization, and parallelism behavior;
- recursion, iteration, termination, and complexity behavior;
- receiver mutation and global/closure/external state changes;
- temporal ordering and happens-before requirements;
- behavior observed under each named workload and environment;
- discrepancy between documented, statically inferred, and observed behavior.

### 7.5 Data, state, effects, and resources

- data read, written, created, deleted, transformed, filtered, aggregated, joined, encoded, or serialized;
- source-to-sink lineage and information-loss description;
- receiver, argument, global, closure, filesystem, database, cache, and remote-state mutations;
- filesystem, network, database, subprocess, device, clock, randomness, logging, telemetry, and UI effects;
- events emitted or consumed;
- transactions opened, committed, rolled back, or compensated;
- locks, synchronization, threads, tasks, processes, actors, GPU streams, and concurrency constraints;
- permissions, credentials, secrets, trust boundaries, data residency, and privacy classes;
- allocation behavior, memory ownership, pooling, caching, and resource lifecycle;
- CPU, GPU, memory, disk, network, latency, throughput, startup, and scaling characteristics;
- worst-case, amortized, empirical, and workload-conditioned cost descriptions;
- backpressure, quotas, rate limits, timeouts, and circuit-breaker behavior;
- cleanup, cancellation, leak, and partial-resource behavior.

### 7.6 Failure and recovery views

- declared errors, exceptions, status codes, error values, and exit codes;
- observed errors and assertion failures;
- triggering conditions and path guards;
- propagated, wrapped, translated, swallowed, logged, or retried failures;
- error message templates and diagnostic fields;
- partial result and partial mutation behavior;
- retryability, backoff, idempotency, and deduplication needs;
- atomicity boundary and rollback/compensation behavior;
- cancellation, timeout, resource exhaustion, corruption, and concurrency failure behavior;
- recovery action, remediation, fallback, and user-facing symptom;
- known incidents, regressions, vulnerabilities, and fixed versions;
- contradictions between declared and observed failure behavior.

### 7.7 Usage, examples, and negative views

- minimal invocation;
- canonical example;
- realistic end-to-end example;
- example for each overload or mode;
- setup and teardown example;
- async, streaming, callback, CLI, endpoint, and configuration examples;
- accepted-input examples;
- rejected-input examples;
- boundary and adversarial examples;
- expected output, state change, effects, and errors for each example;
- integration example with common producers and consumers;
- adapter and migration example;
- test and fixture example;
- anti-pattern and common misuse;
- “do not use when” contraindications;
- false-friend APIs and misleading query terms;
- counterexamples distinguishing semantically different lookalikes;
- safe alternative or replacement recommendation.

### 7.8 Quality, evidence, and change views

- author documentation status;
- extraction coverage and unresolved constructs;
- static-analysis confidence and call/type/alias ambiguity;
- supporting source spans, docs, tests, traces, and independent verification;
- contradiction and negative-evidence summary;
- test inventory, coverage, mutation testing, property testing, fuzzing, and differential testing;
- benchmark quality, workload relevance, and sample size;
- API stability, churn, age, ownership, and support maturity;
- deprecation status, replacement, removal schedule, and migration path;
- callers, dependents, impact surface, and safe edit handles;
- commit, issue, pull-request, review, and incident history;
- semantic diff, API diff, behavior diff, and performance diff;
- freshness, valid scope, known gaps, abstraction loss, and verification grade.

### 7.9 Relation, group, and route text views

For a relation or edge:

- exact forward sentence and exact inverse sentence;
- predicate definition and participant-role descriptions;
- why the relation exists and which analyzer asserted it;
- call argument-to-parameter, source-to-sink, or producer-to-consumer mapping;
- direction, polarity, `may`/`must`/`must_not`, guard, path, environment, and temporal scope;
- compatibility explanation by dimension;
- adapters, conversions, information loss, cost, and new effects;
- supporting and contradicting evidence;
- change impact if the relation disappears or changes;
- observed frequency, latency, failure, and workload;
- likely user intents, alternate phrases, and negative aliases.

For a group or capsule:

- membership rule and frozen member list;
- capability union and capability intersection;
- inbound and outbound boundary ports;
- owned and mutated state;
- external effects, errors, invariants, and lifecycle;
- internal decisive edges and hidden complexity;
- cohesion, coupling, boundary cut, and architectural role;
- abstraction-loss and unresolved-edge ledger;
- expansion handles to members, source, edges, and evidence.

For a route or workflow:

- goal and accepted starting state;
- ordered steps or graph topology;
- boundary inputs and outputs;
- each intermediate compatibility decision and adapter;
- cumulative effects, permissions, dependencies, state, errors, and cost;
- transaction, retry, rollback, compensation, and verification plan;
- alternatives, decisive differences, and reasons for selection;
- execution result, independent verification, and exact receipt.

## 8. Keywords, keyphrases, and lexical microfeatures

Keyword projections should preserve exact source, normalized form, weight, field, language, provenance, and whether the term was extracted or generated.

### 8.1 Name-derived terms

- raw identifier;
- qualified-name segments;
- snake-case, kebab-case, dot-case, slash, and camel/Pascal splits;
- acronym-preserving and acronym-expanded splits;
- digits and version fragments;
- prefixes, suffixes, infixes, stems, roots, lemmas, and affixes;
- singular/plural and verb/noun/adjective variants;
- abbreviations and expansions;
- aliases, re-exports, historical names, renamed symbols, and common typos;
- language-specific operator and dunder/common-method meanings;
- file, module, namespace, package, repository, and build-target path terms;
- neighboring type, field, parameter, caller, callee, and import names.

### 8.2 Source- and contract-derived terms

- language keywords and syntactic constructs;
- API and library calls;
- types, schemas, field names, shapes, units, encodings, media types, and protocols;
- exception names, error codes, log keys, metric names, event names, topics, and routes;
- effect verbs such as read, write, mutate, allocate, send, retry, cache, lock, and serialize;
- resource names such as file, socket, database, GPU, clock, secret, queue, and process;
- algorithm, data structure, design pattern, architectural layer, and capability names;
- standards, RFCs, CWEs, CVEs, SPDX identifiers, formats, frameworks, and domains;
- CLI commands, flags, environment variables, configuration keys, and entry points;
- literal strings and numeric tokens under sensitivity-aware redaction policies;
- precondition, postcondition, invariant, failure, and contraindication phrases;
- test names, assertion terms, fixture names, benchmark terms, and incident vocabulary.

### 8.3 Documentation- and usage-derived terms

- author-provided metadata keywords and classifiers;
- title, headings, glossary terms, code examples, and link anchor terms;
- noun phrases, verb phrases, subject–verb–object triples, and dependency-parse phrases;
- named entities and domain concepts;
- synonyms, hypernyms, hyponyms, meronyms, and ontology ancestors;
- user-intent paraphrases and natural-language questions;
- common successful query terms and reformulations;
- query terms leading to verified use;
- hard-negative terms leading to rejection or incompatibility;
- multilingual translations and transliterations;
- organization- and user-specific vocabulary, isolated by policy.

### 8.4 Character, string, and token microfeatures

These cheap features are useful for blocking and fuzzy candidate generation, especially before a model call:

- byte, Unicode code-point, grapheme, character, subword, token, and identifier n-grams;
- skip-grams, shingles, word boundaries, token-class n-grams, and API-call n-grams;
- byte/character/token length and distributions;
- casing pattern, capitalization transitions, acronym pattern, and case-folded form;
- underscore, hyphen, dot, slash, punctuation, whitespace, digit, and symbol counts/ratios;
- Unicode script and category histograms;
- alphabetic, numeric, alphanumeric, printable, and non-ASCII ratios;
- vowel, consonant, digit, separator, and repeated-character counts/ratios;
- character entropy, token entropy, identifier diversity, and repetition/run-length features;
- prefix/suffix/substring containment and longest common prefix/suffix/substring/subsequence;
- Hamming distance for equal-length forms;
- Levenshtein and Damerau–Levenshtein distance;
- Jaro and Jaro–Winkler similarity;
- token/character Jaccard and weighted Jaccard;
- Sørensen–Dice, overlap coefficient, cosine n-gram similarity, and edit-script features;
- phonetic keys such as Soundex or Metaphone for human-language-like identifiers;
- keyboard-adjacency and OCR-confusion features where user input warrants them;
- regex shape, identifier grammar, and language naming-convention match;
- reserved-word, stopword, boilerplate, and generated-name indicators.

These features are candidates, never semantic proof. Vowel ratios and phonetic encodings may help misspelled natural-language identifiers but should normally receive less weight than exact symbols, typed contracts, and domain terms.

### 8.5 Keyword record

```yaml
KeywordProjection:
  projection_envelope_ref: ...
  terms:
    - raw: dataframe
      normalized: dataframe
      field_key: uceg.field.behavior
      term_kind: domain_concept
      language: en
      weight: 2.4
      extraction_method: author|parser|ontology|nlp|learned_sparse|query_history
      source_refs: []
      polarity: positive|negative|contraindication
      positions: []
```

## 9. Labels, tags, taxonomies, and ontology descriptions

Labels should be namespaced assertions with definitions, hierarchy, provenance, confidence, temporal scope, and evidence. Store negative labels and “unknown” separately; never infer either from absence.

### 9.1 Universal label dimensions

- subject kind and subkind;
- language, dialect, language version, runtime, compiler, ABI, platform, architecture, and ecosystem;
- scope, visibility, export status, audience, and API tier;
- generated, vendored, handwritten, test, example, benchmark, migration, or production status;
- declaration, definition, overload, specialization, wrapper, adapter, facade, or implementation status;
- lifecycle: experimental, alpha, beta, stable, deprecated, removed, superseded, orphaned;
- stability: frozen, evolving, volatile, compatibility-guaranteed, internal-only;
- documentation: undocumented, author-documented, generated, reviewed, contradicted;
- verification: unverified, statically supported, test-observed, independently verified;
- purity, referential transparency, determinism, idempotence, reversibility, and totality;
- synchronous/asynchronous, eager/lazy, batch/stream, blocking/nonblocking, finite/infinite;
- stateful/stateless, mutable/immutable, persistent/ephemeral, cached/memoized;
- ownership: owned, borrowed, shared, copied, moved, aliased, escaped, captured;
- concurrency: thread-safe, reentrant, lock-free, atomic, serialized, single-thread-only, unknown;
- transaction: atomic, transactional, compensatable, partially committing, retry-safe;
- error: throws, returns error, partial result, retries, swallows, fatal, fail-open, fail-closed;
- effect classes: filesystem, network, database, subprocess, global, environment, clock, randomness, logging, metrics, GPU, UI;
- security: source, sink, sanitizer, validator, parser, authenticator, authorizer, cryptographic, secret-handling, trust-boundary crossing;
- privacy, confidentiality, integrity, availability, residency, retention, and compliance classes;
- performance tier, latency class, throughput class, memory class, startup class, hot/cold path;
- domain, subdomain, task, capability, algorithm, data structure, design pattern, and architecture layer;
- framework, protocol, standard, file format, media type, schema family, and hardware target;
- quality, maintainability, complexity, test maturity, coverage, flakiness, and risk tier;
- ownership team, maintainer, code owner, service, subsystem, product, and tenant;
- popularity, usage maturity, support status, and operational criticality;
- vulnerability, deprecation, license, export-control, and supply-chain status;
- human-curated, source-declared, analyzer-inferred, runtime-observed, model-predicted, or policy-assigned provenance.

### 9.2 Entity-role labels

- parser, lexer, tokenizer, validator, normalizer, converter, serializer, deserializer;
- loader, reader, writer, importer, exporter, downloader, uploader, fetcher, client, server;
- mapper, reducer, filter, sorter, grouper, aggregator, joiner, indexer, sampler;
- factory, builder, constructor, initializer, registry, resolver, locator, dispatcher;
- adapter, wrapper, facade, bridge, proxy, decorator, middleware, interceptor;
- controller, handler, listener, subscriber, publisher, producer, consumer, coordinator;
- scheduler, worker, queue, retryer, circuit breaker, rate limiter, cache;
- repository, gateway, service, model, entity, value object, DTO, schema, view model;
- source, sink, transform, sanitizer, encoder, decoder, compressor, encryptor;
- test helper, fixture, mock, stub, fake, oracle, generator, assertion, benchmark;
- entry point, plugin, hook, callback, command, endpoint, route, job, task;
- state machine, state holder, resource owner, context manager, transaction boundary;
- utility, primitive, composite, orchestrator, workflow, route, and compatibility adapter.

### 9.3 Label assertion

```yaml
LabelAssertion:
  projection_envelope_ref: ...
  label_uri: uceg-label://role/validator
  label_definition_version: 3
  polarity: positive|negative|unknown
  strength: 0.94
  hierarchy_paths: []
  source_kind: declared|extracted|inferred|observed|human|policy
  evidence_refs: []
  conflicts_with: []
```

## 10. Typed facts, schemas, logic, and contract descriptions

Not every useful description is text or a vector. Many decisive properties should be machine-readable values.

### 10.1 Supported value forms

- boolean and tri-state boolean;
- integer, decimal, rational, arbitrary-precision number, and symbolic number;
- string, byte string, enum, URI, entity reference, and evidence reference;
- timestamp, date, duration, temporal interval, observation window, and recurrence;
- semantic version, version range, platform selector, and environment predicate;
- quantity with unit, dimension, coordinate system, reference frame, tolerance, and conversion rule;
- numeric interval, lower/upper bound, confidence interval, quantile, histogram, probability distribution, mixture, and time series;
- ordered list, unordered set, multiset, tuple, map, record, table, tensor, graph, and tagged union;
- type expression, schema, refinement, regular expression, glob, grammar, automaton, and language expression;
- logical expression, constraint-solver expression, precondition, postcondition, invariant, and proof obligation;
- source span, code snippet, AST/CST/IR fragment, graph pattern, path expression, state machine, workflow fragment, and Petri net;
- command, query, invocation, adapter, migration, test, benchmark, and verification templates;
- digest, signature, attestation, evidence bundle, and exact receipt;
- unknown, redacted, withheld, estimated, sampled, contradictory, and explicitly absent values with reasons.

Canonicalization, units, null semantics, comparison semantics, ordering, encoding, timezone, locale, and precision must be explicit.

### 10.2 Identity, occurrence, and source aspects

- canonical identity tuple and aliases;
- snapshot, artifact, build, environment, and observation scope;
- source file and exact spans;
- native syntax kind, semantic kind, symbol kind, and subkind;
- definition, declaration, reference, call, write, read, import, export, and documentation occurrence roles;
- lexical scope, semantic scope, ownership, visibility, and export status;
- macro/template/generated origin and source-map chain;
- parse status, recovery status, language version, and parser diagnostics;
- original and normalized source digests.

### 10.3 Callable and port aspects

- callable kind, dispatch kind, calling convention, overload group, and generic specialization;
- receiver, implicit parameters, explicit parameters, return, yield, await, exception, event, callback, state, resource, and control ports;
- parameter position, role, name, aliases, passing mode, required/optional state, and default;
- accepted type/schema/shape/unit/encoding/range/cardinality/nullability;
- coercions, validators, normalizers, sanitizers, and rejection conditions;
- cross-parameter dependencies, mutual exclusions, conditionals, and overload guards;
- ownership, borrowing, lifetime, mutability, copying, and view semantics;
- sync/async, scalar/batch/stream, push/pull, eager/lazy, blocking/nonblocking, and backpressure;
- declared and inferred preconditions, postconditions, invariants, and refinements;
- output guarantees, error model, cancellation, timeout, retry, and partial-result behavior.

### 10.4 Variable, binding, and storage aspects

- binding kind: parameter, local, global, nonlocal, closure cell, field, class attribute, import alias, pattern target, comprehension target, exception target, constant, temporary;
- declaration, definition, assignment, read, delete, capture, and escape sites;
- shadowed and shadowing bindings;
- definite assignment, initialization path, default, sentinel, and constant/final status;
- declared, inferred, narrowed, and runtime-observed type distributions;
- abstract value domain, ranges, shapes, schemas, units, encodings, cardinality, and missingness;
- reaching definitions, use-def/def-use chains, alias set, points-to set, and lineage;
- lifetime, storage duration, allocation region, ownership, borrowing, mutation, escape, and thread/task locality;
- state-machine role, configuration/feature-flag role, source/sink/sanitizer role, taint, and sensitivity;
- serialization, persistence, caching, invalidation, and concurrency rules.

### 10.5 Type, class, and object-model aspects

- construct kind, nominal identity, structural shape, opaque/alias/refinement status;
- generic parameters, bounds, constraints, variance, defaults, lifetimes, and associated types;
- bases, inheritance, implemented interfaces/protocols/traits, mixins, MRO/linearization, and sealed/final status;
- abstract, virtual, final, override, hide, shadow, and dynamic-dispatch relationships;
- constructor/factory/destructor/finalizer inventory;
- field, slot, class attribute, property, descriptor, method, and extension-point inventory;
- class invariants, object state schema, lifecycle, legal/illegal transitions, and valid phases;
- equality, hashing, comparison, ordering, copying, cloning, serialization, and representation semantics;
- memory layout, size, alignment, packing, slot restrictions, vtable, ABI, and FFI behavior;
- iteration, context-management, awaitability, callability, indexing, arithmetic, and language protocol behavior;
- resource ownership, concurrency, thread safety, reentrancy, and synchronization.

### 10.6 Behavior, effect, state, and error aspects

- capability and transformation kind;
- algorithm, approximation, convergence, numerical stability, tolerance, and information loss;
- purity, determinism, idempotence, commutativity, associativity, monotonicity, reversibility, and termination;
- reads, writes, creates, deletes, emits, consumes, allocates, releases, spawns, waits, locks, logs, and traces;
- argument, receiver, global, closure, file, database, cache, process, device, UI, and remote state changes;
- effect order, causal dependency, transaction, rollback, compensation, retry, and cleanup;
- filesystem, network, database, subprocess, environment, time, randomness, secret, credential, GPU, device, and dynamic-code capabilities;
- declared/inferred/observed exceptions, error values/codes, warnings, partial results, silent failures, and undefined behavior;
- triggers, propagation, wrapping, translation, suppression, retryability, permanence, recovery, and symptom;
- sync/async behavior, locks, races, deadlocks, ordering, delivery guarantee, cancellation points, and parallelizability.

### 10.7 Performance and operational aspects

- asymptotic time, space, I/O, communication, and energy complexity;
- best, expected, amortized, and worst case;
- empirical latency, throughput, allocations, memory, disk, network, CPU, GPU, and energy distributions;
- cold/warm start, cache state, input-size/shape, batch size, concurrency, platform, and compiler sensitivity;
- recommended operating range, quotas, rate limits, resource ceilings, and SLOs;
- benchmark workload, environment, harness, sample count, uncertainty, and reproducibility;
- logs, metrics, traces, spans, audit events, health checks, diagnostic fields, and support playbooks.

### 10.8 Security, privacy, license, and policy aspects

- trust boundary, threat model, required privilege, authentication, authorization, and approval;
- source, sink, sanitizer, validator, encoder, parser, deserializer, and dynamic-execution roles;
- injection, traversal, SSRF, unsafe deserialization, memory safety, race, cryptography, and supply-chain risks;
- secret inputs/outputs, credential use, sensitive data, privacy class, retention, redaction, and residency;
- network destination, filesystem scope, database scope, process scope, and sandbox requirement;
- vulnerability, weakness, advisory, fixed version, mitigation, and exploit preconditions;
- source and descriptor license, package license expression, notice obligations, compatibility, and redistribution/egress constraints;
- signature, attestation, SBOM, provenance, reproducible build, scanner, and policy decision status.

JSON Schema already treats annotations such as title, description, default, examples, read-only, write-only, and deprecated as distinct keywords rather than one summary field; Taedri should preserve the same kind of separation for code contracts. See the [JSON Schema 2020-12 validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation).

### 10.9 Numeric, metric, and information-theoretic descriptions

- byte, character, token, statement, expression, block, function, method, field, class, and file counts;
- physical/logical/source/comment/blank lines and comment/doc density;
- identifier count, vocabulary size, unique token count, literal count, operator count, and API-call count;
- cyclomatic, essential, NPath, cognitive, nesting, decision, exception-path, and state complexity;
- Halstead vocabulary, length, volume, difficulty, effort, time, and defect proxies;
- fan-in, fan-out, call depth, inheritance depth, number of children, coupling, cohesion, instability, abstractness, and distance-from-main-sequence metrics;
- basic blocks, CFG edges, loops, SCCs, dominators, def-use chains, live ranges, aliases, dynamic targets, and unresolved candidates;
- parameter count, overload count, type-variable count, schema width/depth, shape rank, effect count, error count, and boundary-port count;
- edit distance, tree/graph edit distance, semantic diff size, churn, age, ownership count, and co-change strength;
- byte/character/token/identifier/API/path/edge entropy;
- conditional entropy, cross-entropy, perplexity, and model surprisal under named models;
- term/document frequency, inverse document frequency, uniqueness, rarity, and discriminative information gain;
- pointwise mutual information and normalized PMI for names, APIs, types, effects, errors, callers, callees, and domains;
- mutual information between features and task/capability/quality/compatibility outcomes;
- redundancy, duplication, compression ratio, normalized compression distance, and minimum-description-length proxies;
- KL, Jensen–Shannon, Hellinger, total-variation, Wasserstein, cosine, correlation, and covariance distances between observed distributions;
- anomaly, novelty, out-of-distribution, leverage, influence, uncertainty, and calibration scores;
- Gini, concentration, diversity, evenness, dominance, and long-tail measures;
- feature stability across normalization profiles, releases, environments, workloads, and models;
- marginal retrieval utility, marginal verified-success utility, information gain per byte/token/millisecond/dollar, and redundancy with other projections.

Every metric records its formula, implementation, configuration, population/reference set, sample/window, units, uncertainty, and scope. Complexity and maintainability proxies are signals, not universal quality truth.

### 10.10 Formal, executable, and visual descriptions

Formal/executable views:

- type stub, interface/protocol declaration, header, signature file, and ABI declaration;
- JSON Schema, OpenAPI, AsyncAPI, Protocol Buffers, GraphQL, Avro, database DDL, and domain schema;
- pre/postcondition language, refinement type, SMT formula, temporal logic, policy rule, grammar, regex, automaton, and state machine;
- truth table, decision table/tree, transition table, lookup table, symbolic expression, and piecewise function;
- executable example, doctest, unit test, property, generator, oracle, mock, stub, fake, sandbox recipe, and replayable trace;
- invocation, query, CLI, request, adapter, migration, rollback, verification, and composition templates;
- reference interpreter, emulator, surrogate, learned behavior model, and finite-state transducer, each with coverage and error bounds.

Visual/multimodal views:

- syntax-highlighted source card and annotated signature;
- entity/port/compatibility table;
- AST/CST tree, CFG, DFG, PDG, call graph, dependency graph, inheritance graph, evidence graph, and knowledge graph;
- UML class, component, package, deployment, activity, state, and sequence diagrams;
- C4 context/container/component/code views;
- data-lineage, taint, trust-boundary, state-transition, event-flow, and route diagrams;
- architecture map, subsystem boundary, Sankey, chord, matrix, adjacency, and hierarchy views;
- flame graph, call tree, allocation graph, coverage heat map, profile timeline, trace waterfall, and error propagation diagram;
- release timeline, semantic diff, migration before/after, and blast-radius visualization;
- rendered notebook output, UI screenshot, diagram, chart, and source-to-pixel relationship.

Visuals are projections linked back to exact entities and edges. Image embeddings can retrieve them, but pixels do not replace underlying graph or contract facts.

## 11. Compatibility descriptions

Compatibility is a directional, scoped relation between a provider offer and a consumer requirement. It is never “cosine similarity above X.”

### 11.1 Dimensions to compare

- semantic purpose and capability;
- nominal and structural type;
- subtype, protocol, trait, refinement, and generic constraints;
- schema, field names/types, shape, rank, dimensions, axes, and layout;
- cardinality, optionality, nullability, missingness, default, and sentinel semantics;
- numeric range, precision, tolerance, signedness, units, coordinate system, and conversion;
- encoding, endianness, serialization, media type, file format, and protocol;
- ordering, uniqueness, stability, sorting, and partitioning guarantees;
- ownership, lifetime, borrow/copy/view, mutability, aliasing, and receiver mutation;
- scalar/batch/stream, sync/async, push/pull, eager/lazy, and blocking/nonblocking mode;
- callback, iterator, generator, coroutine, event, backpressure, cancellation, and delivery protocol;
- precondition implication, postcondition satisfaction, and invariant preservation;
- error type/model, partial results, retry, idempotence, timeout, rollback, and compensation;
- required/provided state, lifecycle phase, and legal state transition;
- effects, effect ordering, cleanup, resource ownership, and transaction boundary;
- concurrency, thread/process/task safety, reentrancy, lock ordering, and parallelism;
- CPU, GPU, memory, disk, network, latency, throughput, quota, and SLO budget;
- OS, architecture, ABI, interpreter, runtime, language version, compiler, and platform;
- dependency/API/protocol version, optional extra, feature flag, build option, and configuration;
- authentication, authorization, secret availability, network reachability, trust, sandbox, tenant, and data residency;
- license, redistribution, source egress, retention, policy, and human-approval constraints;
- evidence grade, freshness, stability, support maturity, and verification requirement.

### 11.2 Assessment outcomes

- exact compatible;
- nominal subtype compatible;
- structurally compatible;
- semantically compatible;
- compatible in a specified environment or input region;
- compatible after validation or narrowing;
- compatible after safe coercion;
- compatible through a lossless adapter;
- compatible through a lossy adapter with stated loss;
- compatible with new effects, permissions, dependencies, or cost;
- compatible only with policy or human approval;
- possibly compatible;
- unknown due to missing analysis;
- contradicted by evidence;
- incompatible with decisive blockers;
- forbidden by policy.

Every assessment records decisive dimensions, unknown dimensions, blockers, adapters, conversions, losses, new effects, cost, evidence, verifier, environment, temporal validity, and expiry conditions.

```yaml
CompatibilityAssessment:
  provider_port_ref: ...
  consumer_port_ref: ...
  scope: ...
  outcome: compatible_with_lossless_adapter
  dimensions:
    - key: uceg.compatibility.unit
      result: needs_adapter
      offer: milliseconds
      requirement: seconds
      adapter_ref: ...
      loss: none
      evidence_refs: []
  hard_blockers: []
  unknown_dimensions: []
  verification_plan_ref: ...
```

## 12. Sparse and deterministic retrieval representations

Sparse representations are often cheaper, more interpretable, and better for rare identifiers than dense vectors.

### 12.1 Inverted-index fields

- exact native name;
- exact and normalized qualified name;
- aliases and historical names;
- identifier subtokens;
- package/module/file/path segments;
- signature and type tokens;
- parameter, field, schema, unit, effect, error, and dependency tokens;
- author docs and each generated text view in separate fields;
- example and counterexample terms;
- positive, negative, and contraindication terms;
- API calls, imports, strings, operators, and token-class sequences;
- test, incident, vulnerability, license, and provenance terms;
- forward-edge, inverse-edge, path, motif, and boundary terms.

### 12.2 Sparse vector families

- raw term frequency;
- binary term presence;
- TF–IDF;
- BM25/BM25F and field-specific variants;
- character, byte, identifier, token, API-call, AST-production, and path n-gram vectors;
- bag, multiset, sequence, and position-aware feature vectors;
- feature hashing/hashing trick vectors;
- ontology-concept and taxonomy-path vectors;
- graph-neighborhood, motif, metapath, and edge-predicate histograms;
- behavior, trace, error, effect, and state-transition histograms;
- learned sparse expansion such as SPLADE-style vocabulary-aligned weights;
- query-log and hard-negative expansion vectors;
- binary bitmaps for labels, predicates, capabilities, environments, and evidence grades;
- numeric/range indexes for versions, quantities, performance, confidence, freshness, and coverage.

### 12.3 Deterministic matching and blocking

- exact equality and canonical equality;
- prefix, suffix, substring, phrase, regex, glob, and grammar match;
- edit-distance and token-set thresholds;
- type unification, subtyping, constraint solving, and schema compatibility;
- range, interval, version, platform, unit, and environment predicates;
- bitmap and set intersection;
- required/forbidden label and effect filters;
- graph adjacency, reachability, path language, motif, dominator, and neighborhood constraints;
- provenance, policy, license, tenant, verification, and freshness gates;
- history and user-pattern lookup;
- cached exact query, route, and verified-receipt reuse.

The planner should run these methods before model-generated queries whenever the user demand can be compiled into exact fields and typed conditions.

### 12.4 Blocking-key variants and policies

Candidate blocking itself is variant-based. Useful keys include exact entity/artifact IDs; normalized and package-scoped names; language-scoped symbols; path components; arity/signature/type/schema/shape keys; capability/effect/error/protocol/standard labels; character/token/AST/path shingles; call/dependency neighborhoods; MinHash buckets; SimHash prefixes; vector/graph cluster IDs; behavioral signatures; and tenant/policy/license/lifecycle/residency partitions.

```yaml
BlockingKeyVariant:
  variant_id: ...
  subject_ids: []
  blocking_family: exact|lexical|type|schema|minhash|simhash|vector|graph|behavior|policy
  source_attribute_refs: []
  normalization_pipeline: []
  algorithm_and_version: ...
  parameters:
    width_bits: ...
    shingle_size: ...
    hash_count: ...
    bands: ...
    rows_per_band: ...
    prefix_length: ...
    table_count: ...
    probe_count: ...
    seed: ...
  key_values_or_refs: []
  intended_similarity_or_partition: ...
  measured_operating_characteristics_ref: ...
  lineage_and_evidence_refs: []
```

“Narrow,” “medium,” “wide,” “high recall,” and “high precision” are presentation labels; exact parameters define the variant. Policies may use one key, unions for recall, intersections for precision, coarse-to-fine cascades, ordered fallbacks, family quotas, learned/calibrated selectors, and a bypass lane that protects recall. Every executed blocking policy is a versioned `RepresentationCombination` with measured false-positive, false-negative, recall, latency, compute, and storage behavior.

## 13. Hash, fingerprint, sketch, LSH, and ANN description atlas

Every output in this section is an append-only `FingerprintProjection`, not a fixed column on the entity.

```yaml
FingerprintProjection:
  projection_envelope_ref: ...
  objective: raw_identity|canonical_identity|clone|lineage|containment|blocking|behavior
  input_view_id: ...
  input_view_digest: ...
  feature_schema_id: ...
  feature_extractor_id_and_version: ...
  canonicalization_profile_id: ...
  algorithm_id_and_version: ...
  implementation_id_and_version: ...
  parameters: {}
  seeds_or_salts: []
  value_encoding: ...
  value_or_storage_ref: ...
  distance_or_similarity: ...
  invariance_contract: []
  known_blind_spots: []
  applicability_predicate: ...
  calibration_id: ...
  candidate_thresholds: []
  collision_policy: candidate_only|verify_exact
  verification_requirement: ...
```

Never compare outputs unless their projection definitions say they share compatible input features, normalization, parameters, and distance semantics.

### 13.1 Distinct objectives

- exact raw-byte identity;
- equality under one named canonicalization;
- provenance integrity;
- lineage or revision similarity;
- type-1 clone: formatting/comment differences;
- type-2 clone: identifier/literal substitutions;
- type-3 clone: copied code with local additions, deletions, or edits;
- type-4 or behavioral clone: similar behavior through different syntax;
- local copied-region detection;
- whole-entity resemblance;
- small-in-large containment;
- structural/architectural-role similarity;
- graph-neighborhood, path, motif, and route similarity;
- contract candidate blocking;
- behavioral substitutability within an evidenced input region;
- membership avoidance;
- approximate population statistics;
- change localization and incremental invalidation.

### 13.2 Exact and content-addressed families

- raw SHA-256/SHA-512 digest;
- SHA3-256/SHA3-512 algorithm-diversity digest;
- BLAKE2/BLAKE3 high-throughput digest;
- Git object ID and tree/commit identity;
- Software Heritage content, directory, revision, release, and snapshot identifiers;
- HMAC/keyed digest for tenant-specific or low-entropy private projections;
- CRC, Adler, Rabin, or rolling checksums for corruption/windowing only;
- fast noncryptographic hashes such as xxHash/Murmur-style values for ephemeral partitioning and caches only;
- canonical JSON/CBOR/Protobuf/Arrow record digest;
- canonical signature, type, schema, port, effect, error, state, policy, and environment digests;
- Merkle AST/CST, directory, package, group, graph, evidence bundle, route, and receipt roots;
- content-defined chunk manifest root;
- build, toolchain, dependency-lock, runtime, platform, and configuration manifest digests;
- test-vector suite and verification-receipt roots.

For permanent public identities, use a self-describing algorithm tag and a cryptographic digest of at least 256 bits. A shorter unverified key can be a bucket key only if the authoritative identity is checked after lookup. Software Heritage provides a useful content-addressed reference model, while Package URL provides ecosystem package coordinates; preserve both where available. See [SWHIDs](https://docs.softwareheritage.org/devel/swh-model/persistent-identifiers.html) and the [purl specification](https://github.com/package-url/purl-spec).

### 13.3 Canonical and normalization-specific fingerprints

Each bullet is a separate profile with its own invariance contract:

- raw bytes;
- decoded text with original encoding recorded;
- UTF-8 transport normalization;
- newline, BOM, and trailing-whitespace normalization;
- Unicode NFC and, only when safe, NFKC variants;
- formatter-normalized source;
- comment-stripped and comment-preserving forms;
- docstring-stripped and documentation-only forms;
- token stream without trivia;
- token-kind-only and token-kind-plus-value forms;
- keyword/operator/control-skeleton form;
- scope-aware local alpha-renaming;
- parameter-position renaming;
- imported/global symbol preserving local renaming;
- fully resolved qualified-symbol form;
- literal-preserving, literal-class, literal-bucket, redacted-literal, and literal-erased forms;
- default-preserving and default-erased forms;
- type-erased and type-enriched forms;
- decorator/annotation-preserving and erased forms;
- desugared source and language-neutral AST/IR forms;
- import-alias and absolute-import-resolved forms;
- constant-folded forms;
- dead-code-preserving and eliminated forms;
- SSA-renamed dataflow form;
- canonical basic-block, exception-region, and variable numbering;
- bytecode with offsets removed;
- machine code with addresses, registers, relocations, and constants normalized;
- compiler IR at each optimization level;
- architecture-neutral opcode/micro-operation category form.

Unsafe transformations must be declared. For example, alpha-renaming may change reflective lookup or serialized field semantics; operand sorting is valid only if the operation is proven commutative and evaluation-order effects are absent.

### 13.4 Rolling, chunking, substring, and clone fingerprints

- fixed-block digest;
- Rabin–Karp rolling fingerprint;
- rsync weak-plus-strong block signature;
- content-defined chunks using Rabin/Gear/FastCDC-style boundaries;
- multi-resolution chunk manifests;
- AST-, symbol-, block-, scope-, SCC-, community-, and semantic-boundary chunks;
- byte, character, token, API-call, AST-production, and path k-grams;
- skip-grams and bounded-gap shingles;
- rolling n-gram hashes with source positions;
- Winnowing-selected local fingerprints;
- exact normalized token digest;
- token set, bag, multiset, ordered-sequence, and position-aware fingerprints;
- suffix-array/tree/FM-index sequence keys;
- SourcererCC-style token-overlap candidates;
- NiCad-style normalized text candidates;
- Deckard-style AST characteristic vectors;
- local sequence alignment and token edit scripts for verification;
- AST/tree edit distance for verification;
- program slice, dependence, and symbolic-trace comparison for higher-cost verification.

Winnowing deliberately selects k-gram fingerprints and guarantees detection of shared regions above its configured threshold; it does not establish semantic equivalence. See the original [Winnowing paper](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf). Token-overlap clone detection can scale to very large corpora, as illustrated by [SourcererCC](https://arxiv.org/abs/1512.06448).

### 13.5 Set and weighted-set sketches

- classic MinHash for Jaccard similarity;
- bottom-k/K-minimum-values sketches;
- b-bit MinHash;
- one-permutation MinHash;
- densified one-permutation hashing;
- SuperMinHash;
- HyperMinHash;
- SetSketch;
- multi-seed MinHash ensembles;
- containment-oriented MinHash;
- cardinality-partitioned LSH Ensemble for small-in-large containment;
- consistent weighted sampling and weighted MinHash;
- improved consistent weighted sampling;
- BagMinHash;
- DartMinHash;
- ProbMinHash/probability-Jaccard sketches;
- weighted bottom-k and priority sampling;
- separate positive and negative weighted channels.

Useful feature sets include tokens, AST paths, callees, callers, imports, fields, types, schema keys, effects, errors, permissions, tests, graph neighbors, motifs, paths, trace events, examples, and evidence providers. Encode order and multiplicity in the features when they matter; ordinary MinHash discards them.

Weighted MinHash is appropriate for nonnegative call frequencies, edge confidence, effect importance, or token counts; the feature and weighting recipes dominate the meaning of the result. See Google Research’s [improved consistent sampling, weighted MinHash, and L1 sketching](https://research.google/pubs/improved-consistent-sampling-weighted-minhash-and-l1-sketching/).

### 13.6 Vector LSH and binary candidate codes

- SimHash/random-hyperplane LSH for angular/cosine similarity;
- bit-sampling LSH for Hamming features;
- p-stable LSH for calibrated L1/L2 spaces;
- cross-polytope LSH for angular candidates;
- winner-take-all and densified WTA hashing for rank similarity;
- asymmetric LSH for maximum inner product and producer/consumer roles;
- LSH Forest;
- multi-probe LSH;
- tensoring or other table-reduction variants;
- learned semantic hashing;
- supervised compatible/incompatible binary codes;
- multi-index hashing over long binary codes;
- Matryoshka-compatible truncated semantic codes where the model supports them.

Store the source vector/feature space, component count, bit width, seeds, band/table layout, bucket encoding, query/document role, distance, empty-bin rules, and corpus-specific threshold calibration. SimHash’s successful use for large-scale near-duplicate detection is evidence for candidate generation, not semantic proof. See Google’s [near-duplicate crawling work](https://research.google/pubs/detecting-near-duplicates-for-web-crawling/).

### 13.7 Fuzzy byte and artifact digests

- ssdeep/context-triggered piecewise hashing;
- TLSH;
- sdhash;
- LZJD;
- Nilsimsa legacy compatibility;
- MRSH-v2;
- mvHash-B;
- normalized-source fuzzy digests;
- normalized-bytecode and normalized-instruction fuzzy digests;
- fuzzy digest over ordered chunk IDs.

Run these only on input views for which their size and entropy requirements hold. Keep raw-byte, normalized-source, bytecode, and binary projections separate. TLSH and ssdeep are appropriate near-artifact candidates but not proofs of source lineage or behavior. See the official [TLSH](https://github.com/trendmicro/tlsh) and [ssdeep](https://ssdeep-project.github.io/ssdeep/index.html) projects.

### 13.8 AST, type, flow, and graph fingerprints

- CST and AST canonical serialization hashes;
- per-node AST/CST Merkle hashes;
- subtree multisets and subtree MinHash;
- AST node-kind, depth, branching, and production histograms;
- root-to-leaf and leaf-to-leaf path hashes;
- type-expression tree and generic-substitution hashes;
- scope tree, symbol table, name-binding, inheritance, MRO, protocol, and override graph hashes;
- public API and class-member set/Merkle roots;
- CFG canonical form, basic-block token/opcode hashes, successor-degree and loop-nesting signatures;
- dominator, postdominator, exception-flow, and SCC condensation hashes;
- DFG, SSA use-def/def-use, reaching-definition, PDG, slice, taint, lineage, and Code Property Graph hashes;
- call, import/export, construction, object lifecycle, dependency, coverage, co-change, ownership, and provenance graph hashes;
- Weisfeiler–Lehman whole-graph and per-node hashes across multiple radii;
- direction-, predicate-, and role-aware WL variants;
- line-graph WL for edge neighborhoods;
- hypergraph-incidence and relational WL;
- graphlet, typed motif, triad/tetrad, and metapath histograms;
- motif/path MinHash and SimHash;
- shortest-path label sequences and bounded path-language hashes;
- random-walk and anonymous-walk sketches;
- degree and label histograms;
- spectral, Laplacian, heat-kernel, wave-kernel, and NetLSD-style signatures;
- community, centrality-role, k-core, boundary-cut, and bridge/articulation signatures;
- graph edit features and neighborhood overlap features.

Weisfeiler–Lehman features efficiently capture typed local structure but do not solve graph isomorphism and can collide. They remain candidate projections. See [Weisfeiler–Lehman graph kernels](https://www.jmlr.org/papers/v12/shervashidze11a.html).

### 13.9 Edge and hyperedge fingerprints

- exact edge-claim hash including evidence and snapshot;
- semantic edge key excluding duplicate evidence;
- source–predicate–target hash;
- endpoint-pair and predicate-family block keys;
- forward and inverse lookup keys;
- direction-normalized key only for ontology-declared symmetric predicates;
- ordered edge and role-sorted n-ary relation keys;
- position-sensitive hyperedge key;
- source-port-to-target-port key;
- qualifier, guard, environment, temporal-scope, and policy roots;
- evidence-bundle and provenance-chain Merkle roots;
- positive, negative, unknown, and contradictory edge-state keys;
- compatibility-axis bitmap, MinHash, and SimHash;
- adapter, loss, coercion, new-effect, and incompatibility-reason signatures;
- line-graph neighborhood, k-hop typed neighborhood, motif, route-position, co-change, and trace-confirmation fingerprints;
- edge description and embedding-input digests;
- verification-receipt root.

Participant sorting is forbidden unless predicate semantics permit it. `calls(A,B)` and `calls(B,A)` are different; a symmetric relation may share a normalized candidate key while retaining both exact claims.

### 13.10 Signature and compatibility fingerprints

- exact and type-erased callable signature hashes;
- structural-type and nominal-type hashes;
- generic bound and variance hashes;
- individual port and complete port-set hashes;
- schema, field-set, shape, rank, dimension, unit, range, precision, encoding, serialization, nullability, cardinality, and ordering hashes;
- ownership, mutability, lifetime, sync/async, batch/stream, callback, cancellation, and backpressure hashes;
- precondition, postcondition, invariant, and state-machine roots;
- effect-set and weighted-effect MinHash;
- error-set and recovery-policy MinHash;
- permission/capability and policy-set MinHash;
- hard-gate bitmap and soft-preference SimHash;
- version interval and platform/environment blocking keys;
- ABI/calling-convention and dependency-lock keys;
- known-adapter and known-incompatibility lookup keys;
- typed compatibility blocking tuple.

A shared blocking key only authorizes a more precise comparison. The typed compatibility solver remains decisive.

### 13.11 Dynamic behavior, test, trace, and performance fingerprints

- canonical test input, output, and input/output pair hashes;
- ordered test-vector suite Merkle root;
- pass/fail/skip/error vectors;
- property-test seed/result and counterexample hashes;
- metamorphic and differential result vectors;
- mutation-test kill vector;
- function, block, branch, edge, condition, call, dataflow, and taint coverage bitmaps;
- path profiles and trace n-grams;
- exact and winnowed call/API/syscall/effect/event sequences;
- trace-set and weighted-trace MinHash;
- trace-event SimHash;
- exception type, message template, and stack-shape signatures;
- span, state-transition, lifecycle, allocation, lock, concurrency, and partial-order graph hashes;
- read/write/resource/environment/feature-flag access-set sketches;
- dynamic invariant set hash;
- fuzz corpus coverage and crash-stack signatures;
- sanitizer-finding signatures;
- fault-injection behavior vector;
- latency, throughput, memory, allocation, I/O, CPU, GPU, error-rate, and value-shape sketches;
- behavior matrices across versions, platforms, dependencies, workloads, and input regions.

Every dynamic fingerprint carries the environment, dependency versions, workload/input domain, seed, repetition count, instrumentation, timeout, sandbox policy, and coverage. Unobserved behavior is not proven absent.

### 13.12 Binary and compiled-code fingerprints

- exact executable-section and function-byte hashes;
- relocation/address-normalized hashes;
- opcode, mnemonic, operand-class, register-renamed, and constant-bucket sequence hashes;
- instruction n-gram and function-feature SimHash;
- basic-block Merkle and CFG structural hashes;
- import/API call and string/constant set MinHash;
- call-graph neighborhood and compiler/optimization-conditioned hashes;
- architecture-neutral micro-operation and normalized compiler-IR hashes;
- ABI, symbol, object-layout, debug-map, decompiler-AST, WebAssembly, and JIT-tier fingerprints.

### 13.13 Approximate-membership structures

These answer “definitely absent” or “possibly present,” not similarity:

- Bloom filter;
- partitioned and blocked Bloom filters;
- counting Bloom filter;
- scalable and stable Bloom filters;
- Cuckoo filter;
- quotient/counting quotient filter;
- XOR and binary-fuse filters;
- Ribbon filter;
- Bloomier approximate key/value filter;
- learned Bloom filter with authoritative fallback.

Useful questions include whether a group might contain a symbol/type/effect/motif, whether a node might have a predicate family, whether a package might contain a token/subtree hash, and whether a candidate adapter might exist. A positive always leads to authoritative lookup. A negative is safe only under documented construction, update, deletion, and false-negative guarantees.

### 13.14 Mergeable statistical sketches

- Count–Min and Count sketches;
- heavy-hitter/frequent-item sketches;
- HyperLogLog and CPC distinct-count sketches;
- KMV/Theta, HyperMinHash, and SetSketch unions/intersections;
- reservoir and priority samples;
- KLL, t-digest, DDSketch, and logarithmic histograms;
- matrix/AMS frequency moments;
- TensorSketch and random projections;
- feature hashing;
- motif, degree, call, effect, error, value, shape, and performance distribution sketches.

These describe populations and distributions, not individual identity.

### 13.15 ANN and vector-code index projections

These are physical candidate indexes over a named representation space, not intrinsic entity descriptions:

- exact flat vector scan;
- binary flat/Hamming and multi-index hashing;
- random-projection, KD, ball, and forest structures for appropriate dimensions;
- IVF-Flat;
- scalar quantization;
- product quantization and optimized PQ;
- IVF-PQ;
- residual and additive quantization;
- polysemous codes;
- HNSW and related proximity graphs;
- NSG;
- DiskANN;
- ScaNN;
- Annoy-style projection forests;
- LSH and multi-probe tables;
- metadata-filtered and policy-filtered ANN;
- language/entity-kind/domain shards;
- late-interaction multi-vector indexes;
- centroid-plus-residual group indexes;
- Matryoshka/truncated-vector indexes;
- exact reranking over original vectors.

Record the input projection, model, dimension, dtype, normalization, metric, quantizer/codebooks, index implementation/version, shard/filter policy, build snapshot, seeds, parameters, rerank depth, and measured recall/latency/memory curve. HNSW, IVF, and product quantization are ANN mechanisms, not LSH; preserving that vocabulary prevents design errors.

### 13.16 Hash and sketch correctness rules

- a fuzzy-hash score is not semantic equivalence;
- an LSH collision is not proof of similarity;
- MinHash estimates a specified set overlap, not control-flow or compatibility;
- SimHash estimates angular similarity over chosen features, not substitutability;
- ANN may miss neighbors; benchmark against exact reference samples;
- filter positives do not prove membership;
- graph hashes can collide, and spectral signatures can be cospectral;
- runtime similarity covers only observed inputs and environments;
- static absence may reflect incomplete resolution;
- normalization can erase meaningful differences;
- thresholds must be calibrated by entity kind, language, size, corpus, and input view;
- low-entropy values may leak through hashes; use policy checks, redaction, and keyed projections;
- preserve seed, parameter, algorithm, input digest, and original occurrence;
- `failed`, `unknown`, and `unsupported` must not emit a valid-looking empty fingerprint;
- exact comparison, typed constraints, evidence, and independent verification promote a candidate.

## 14. Embedding description atlas

An entity owns an unbounded set of immutable embedding projections:

```text
subject → facet → input view → generator recipe → vector space → role
```

For subject `s`, facet `f`, view `v`, model `m`, and role `r`, the projection is `E(s,f,v,m,r)`. Direct vector comparison is permitted only when the vector-space and role contracts are compatible.

### 14.1 Embedding projection record

```yaml
EmbeddingProjection:
  projection_envelope_ref: ...
  facet_uri: uceg-facet://behavior/errors
  view_uri: uceg-view://deterministic-error-card/v2
  representation_kind: dense_single|learned_sparse|late_interaction|graph|...
  role: document|query|producer|consumer|relation|path|prototype

  generator:
    provider: ...
    model_id: ...
    model_revision: ...
    weights_digest: ...
    license: ...
    tokenizer_id: ...
    tokenizer_revision_and_digest: ...
    architecture: ...
    layers_and_pooling: ...
    query_instruction: ...
    document_instruction: ...
    prompt_template_digest: ...

  input:
    ordered_projection_refs: []
    ordered_content_digest: ...
    natural_language: en
    programming_language: python
    normalization_recipe_id: ...
    redaction_policy_id: ...
    chunking_recipe_id: ...
    truncation: ...

  vector_space:
    vector_space_id: ...
    dimension_or_shape: ...
    dtype: float16
    normalization: l2
    metric: cosine
    asymmetric_space_pair: ...
    quantization: ...

  payload:
    inline_or_blob_ref: ...
    payload_digest: ...
    token_chunk_source_map_ref: ...

  evaluation:
    benchmark_bundle_id: ...
    calibration_id: ...
    recall_at_k: ...
    ndcg_at_k: ...
    compatibility_false_positive_rate: ...
    ood_score: ...

  lifecycle:
    status: active|shadow|deprecated|invalid
    supersedes: []
    index_build_ids: []
```

A model update, tokenizer update, instruction change, preprocessing change, or role change creates a new vector space. Old and new spaces may coexist for shadow evaluation and reproducibility.

### 14.2 Representation architectures

- lexical sparse vectors;
- learned sparse vocabulary-aligned vectors;
- dense single-vector natural-language embeddings;
- dense code embeddings;
- asymmetric query/document dual encoders;
- natural-language/code dual encoders;
- producer/output and consumer/input dual encoders;
- bi-encoders with cross-encoder reranking;
- token, span, statement, block, and chunk multi-vector representations;
- late-interaction/MaxSim-style representations;
- chunk-set and set-encoder representations;
- hierarchical statement → block → callable → class → module → package embeddings;
- multi-centroid, prototype, medoid, and mixture representations;
- probabilistic/Gaussian/mixture embeddings carrying ambiguity;
- Matryoshka/nested vectors with valid dimension prefixes;
- float32, float16, bfloat16, int8, scalar-quantized, product-quantized, and binary forms;
- source-sequence, bytecode, compiler-IR, and binary-function embeddings;
- AST-path, tree, production-rule, and syntax-graph embeddings;
- CFG, DFG, PDG, SSA, taint, and Code Property Graph embeddings;
- random-walk/node2vec, message-passing/GraphSAGE, relational-GNN, and heterogeneous-graph embeddings;
- knowledge-graph entity/relation embeddings such as translation- and rotation-style spaces;
- edge, pair, hyperedge, hypergraph, motif, subgraph, and whole-graph embeddings;
- role/structural-position and positional embeddings;
- hyperbolic hierarchy embeddings;
- order/partial-order embeddings for subtype, containment, and capability inclusion;
- ordered sequence, trace, event, state-machine, and temporal-graph embeddings;
- symbolic-trace and observed-behavior embeddings;
- test, failure, diff, change, co-change, migration, and release embeddings;
- multimodal code/text/diagram/screenshot/notebook-output embeddings;
- query-conditioned, task-conditioned, domain-conditioned, and user/organization-adaptive spaces;
- supervised compatibility, substitution, vulnerability, repair, ownership, quality, and performance spaces;
- ensembles of independently indexed projections with calibrated fusion.

Learned sparse vectors can preserve exact vocabulary and inverted-index operation while adding expansion, as in [SPLADE v2](https://arxiv.org/abs/2109.10086). Late interaction retains token-level evidence while precomputing document representations, as in [ColBERT](https://arxiv.org/abs/2004.12832). Matryoshka training makes prefixes of one representation useful at different capacities; arbitrary truncation of a model without that property is invalid. See [Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147).

### 14.3 Identity and lexical embedding facets

- native name;
- fully qualified name;
- aliases and re-export names;
- historical names and rename lineage;
- identifier subtokens and acronym expansions;
- file/module/package/namespace path;
- symbol-kind and role description;
- import, dependency, API, operator, and literal vocabulary;
- exact domain terminology;
- positive search aliases;
- negative aliases and false friends;
- query-log paraphrases under policy isolation;
- multilingual translations and transliterations.

### 14.4 Natural-language embedding facets

- original docstring/comment;
- README, API reference, tutorial, example, changelog, and issue-derived text;
- one-line, short, standard, deep, and exhaustive black-box descriptions;
- purpose, intent, problem, mechanism, architecture role, and algorithm;
- “when to use,” “when not to use,” assumptions, limitations, and contraindications;
- inputs, outputs, state, effects, errors, resources, security, privacy, and performance;
- preconditions, postconditions, invariants, and lifecycle;
- examples, counterexamples, common misuse, migration, and alternatives;
- beginner, expert, maintainer, operator, planner, executor, and verifier views;
- entity-to-intent, intent-to-entity, question, symptom-to-solution, error-to-solution, and replacement wording;
- author, deterministic template, extractive NLP, local model, remote model, human-reviewed, and consensus descriptions retained independently.

### 14.5 Source-code embedding facets

- raw source;
- formatting-normalized source;
- comment/docstring-preserving and stripped variants;
- identifier-preserving and alpha-renamed variants;
- literal-preserving, masked, bucketed, and redacted variants;
- signature only, body only, signature plus docs, and public surface;
- statement, expression, basic-block, semantic-slice, and sliding-window chunks;
- slices around definitions, uses, calls, returns, raises, yields, awaits, mutations, and resource access;
- canonical AST and lossless CST serializations;
- AST paths and productions;
- bytecode, language-neutral IR, compiler IR, normalized binary IR, and decompiler views;
- before/after diff and semantic-diff views.

Code-specific models learn different signals and are not interchangeable. [CodeBERT](https://arxiv.org/abs/2002.08155) aligns programming and natural language; [GraphCodeBERT](https://arxiv.org/abs/2009.08366) adds data-flow structure; [UniXcoder](https://arxiv.org/abs/2203.03850) combines code, comments, and AST information with cross-language objectives; [CodeT5+](https://arxiv.org/abs/2305.07922) mixes several understanding and generation objectives; [code2vec](https://arxiv.org/abs/1803.09473) learns from AST paths. Their benchmark success does not make their vector spaces equivalent.

### 14.6 Signature, type, schema, and port embedding facets

- canonical and native callable signatures;
- each overload separately;
- type-erased and fully expanded signatures;
- generic parameters, bounds, variance, and protocols;
- positional, keyword-only, variadic, implicit, and default semantics;
- return, yield, awaited, exception, callback, event, state, and resource ports;
- nominal/structural type, schema, shape, rank, axes, units, encoding, precision, range, cardinality, nullability, ownership, and lifetime;
- ordering, uniqueness, mutability, copy/view, serialization, and coercion semantics;
- version-, platform-, dependency-, feature-, and configuration-conditioned contracts;
- positive accepted examples and negative rejected examples;
- port lineage and graph neighborhood;
- adapter candidates and conversion loss.

For each port, create distinct role projections:

- neutral descriptor;
- producer/output offer;
- consumer/input requirement;
- query demand;
- adapter input and adapter output;
- compatibility-positive and incompatibility-negative prototypes.

Do not use one symmetric port vector for compatibility. Producer and consumer semantics are directional.

### 14.7 Behavior, effect, error, and state embedding facets

- input → output examples;
- input/state → output/state transitions;
- symbolic and abstracted symbolic traces;
- static path and branch signatures;
- observed runtime event and call sequences;
- state-machine transitions and lifecycle phases;
- properties, invariants, metamorphic relations, and differential behavior;
- determinism, idempotence, commutativity, numerical stability, tolerance, and error envelope;
- invalid-input, resource-exhaustion, fault-injection, cancellation, timeout, and concurrency behavior;
- positive effects, forbidden effects, `may` effects, and `must` effects as separate facets;
- filesystem, network, database, subprocess, clock, randomness, logging, secret, permission, transaction, lock, GPU, and resource effects;
- declared, inferred, and observed exception/error facets;
- triggering condition, propagation, wrapping, retryability, atomicity, recovery, and user symptom;
- state read/write sets, receiver mutation, ownership transfer, cleanup, rollback, and compensation.

Symbolic- or execution-trace-derived embeddings can recover semantic signals missed by syntax, but remain bounded by path and environment coverage. See [Code Vectors from abstracted symbolic traces](https://arxiv.org/abs/1803.06686) and [Dynamic Neural Program Embedding](https://arxiv.org/abs/1711.07163).

### 14.8 Test, evidence, runtime, and performance embedding facets

- test name, intent, source, fixture, setup, teardown, input construction, assertion, oracle, and expected error;
- mock/patch graph and test dependency graph;
- covered entities/edges/routes and coverage trace;
- passing, failing, flaky, quarantined, mutation, property, fuzz, benchmark, and counterexample views;
- static evidence, runtime evidence, human review, contradiction, and verification note;
- call, allocation, I/O, branch, type, value-shape, latency, throughput, resource, failure, and environment traces;
- stack, flame graph, syscall, network, database, log, metric, and span views;
- workload, cold/warm state, cache, compiler/runtime, platform, and dependency context;
- performance distribution rather than only a mean;
- before/after regression and improvement views.

Runtime and test embeddings always reference the exact build universe, environment, input region, and coverage. Raw secrets, personal data, credentials, or unbounded runtime values should not be embedded.

### 14.9 Graph embedding facets

Maintain distinct spaces for:

- AST and CST;
- CFG, DFG, PDG, SSA, and CPG;
- call, import, export/re-export, type, inheritance/MRO, protocol, override, and dispatch graphs;
- construction, object lifecycle, alias, data-lineage, effect/resource, exception-propagation, and state graphs;
- test/coverage, documentation, dependency, co-change, ownership, vulnerability, provenance, cross-language binding, runtime trace, and usage graphs;
- individual node neighborhoods by predicate and radius;
- structural role and graph position;
- communities, motifs, graphlets, paths, metapaths, route fragments, boundaries, and whole subgraphs;
- edge and n-ary hyperedge representations;
- temporal graph snapshots and deltas.

Random-walk methods preserve sampled neighborhoods; inductive message passing can generate embeddings for unseen nodes; relation-aware knowledge-graph spaces can encode typed, asymmetric, inverse, or compositional patterns. These learned spaces supplement the explicit typed graph. See [node2vec](https://arxiv.org/abs/1607.00653), [GraphSAGE](https://arxiv.org/abs/1706.02216), [R-GCN](https://arxiv.org/abs/1703.06103), [TransE](https://proceedings.neurips.cc/paper_files/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html), and [RotatE](https://arxiv.org/abs/1902.10197).

### 14.10 History, evolution, domain, and trust facets

- commit message and semantic diff;
- added/removed behavior, contract, effect, error, and performance;
- blame, author, ownership, review, issue, incident, and co-change neighborhoods;
- release note, changelog, deprecation, migration, replacement, and compatibility change;
- rename/move/split/merge/inline/extract and concept lineage;
- before/after tests, traces, vulnerabilities, and performance;
- domain, task, algorithm, pattern, architecture, standard, protocol, format, framework, hardware, and ontology concepts;
- source authority, analyzer/evidence quality, coverage, contradiction, supply-chain provenance, license, vulnerability, review, and policy context;
- verified-success, verified-failure, rollback, and route-selection history.

Trust, authorization, license, and policy embeddings may help ordering within an already authorized set; they can never replace hard policy predicates.

### 14.11 First-class relation, hyperedge, and route embeddings

For every edge or relation, support:

- predicate definition;
- forward sentence and inverse sentence;
- source context, target context, and participant-role views;
- relation-only and endpoint-conditioned relation vectors;
- typed triple/knowledge-graph embedding;
- pairwise joint source/target representation;
- producer-port/consumer-port pair;
- direction, polarity, `may`/`must`, qualifiers, guards, scope, and temporal validity;
- compatibility dimensions, blockers, adapters, losses, costs, and new effects;
- evidence, contradiction, graph neighborhood, path, motif, history, and trace confirmation;
- n-ary call/binding/evidence hyperedge representation;
- pairwise cross-encoder assessment stored as an assessment—not misrepresented as a reusable entity vector.

For every route, support:

- user goal and demand;
- ordered primitive and typed-edge sequences;
- whole sequence, DAG, cyclic workflow, or hypergraph;
- boundary inputs/outputs and each intermediate port match;
- state transitions, cumulative effects, error propagation, transaction, compensation, permissions, dependencies, cost, latency, and reliability;
- successful, failed, proposed, selected, rejected, and verified routes;
- route alternatives and deltas;
- exact execution and verification receipt.

A route embedding must preserve order, topology, boundary contract, and decisive edges. A mean of member vectors is insufficient.

### 14.12 Group, class, module, and package aggregation

Do not store only one centroid. A group can have:

- member multi-vector set;
- centroid and robust centroid;
- medoid;
- several learned or clustered prototypes;
- capability-union and capability-intersection vectors;
- boundary-port vector set;
- internal-topology and boundary-cut vectors;
- attention/set-pooled and hierarchical embeddings;
- relation-aware graph pooling;
- outlier vectors and rare-decisive-capability vectors;
- negative-constraint and contraindication vectors;
- diversity, entropy, coverage, and abstraction-loss measures;
- centroid plus residuals;
- late interaction against member or facet vectors.

Means can erase rare capabilities and incompatibilities. Retrieval should be able to expand from a group hit to the exact member, edge, and evidence that caused the match.

### 14.13 Cross-language and multimodal spaces

- natural language ↔ source code;
- code ↔ code across programming languages;
- implementations aligned by shared tests/properties;
- source ↔ canonical AST/IR;
- source ↔ compiler IR ↔ binary;
- binary ↔ binary across compilers and architectures;
- API ↔ wire schema and foreign-function binding;
- generated code ↔ source schema;
- human-language translations of descriptions;
- code ↔ UML/architecture diagram;
- code ↔ notebook output/chart;
- UI code ↔ rendered screenshot;
- documentation ↔ diagram.

Cross-language analogy is not equivalence: runtime semantics, error behavior, ownership, concurrency, platform, and ecosystem conventions must still be compared.

### 14.14 Fusion and query-time selection

- independent index per vector space;
- top candidates per facet/model;
- exact identifiers and sparse terms preserved alongside dense recall;
- reciprocal-rank fusion as a deterministic baseline;
- calibrated weighted sum, maximum, Borda, learned-to-rank, stacking, and mixture-of-experts policies;
- gates by query language, programming language, subject kind, domain, task, environment, policy, and evidence availability;
- diversity-aware reranking to avoid clone-family domination;
- hard negatives from sibling overloads, rejected routes, incompatible ports, renamed-but-changed entities, and syntax-similar behavior-different code;
- exact score receipt retaining every arm even when a fused score is emitted;
- query-time cost/latency/detail arms and shadow evaluation;
- weights learned from independently verified execution outcomes, not only clicks or model judgments.

Do not compare raw cosine values across spaces, concatenate unrelated vectors without a trained fusion layer, or average facets by default.

### 14.15 Embedding failure boundaries

- similarity does not prove equivalence, compatibility, or correctness;
- dense vectors commonly underweight rare identifiers, numbers, literals, and exact errors;
- negation, modality, direction, and producer/consumer asymmetry may collapse;
- long source truncation loses dependencies and decisive edge cases;
- source vectors may learn naming, formatting, or repository style more than behavior;
- alpha-renaming may erase domain semantics;
- graph embeddings inherit missing or stale edges and can oversmooth distinctions;
- knowledge-graph link prediction invents plausible edges but supplies no evidence;
- dynamic and test embeddings inherit limited workloads and oracles;
- history/co-change vectors encode organizational habits and popularity;
- centroids suppress rare capabilities and blockers;
- cross-language and multimodal models can align superficial likeness;
- quantization, dimensional truncation, ANN, and LSH trade recall for cost;
- generated descriptions can hallucinate, then amplify the hallucination through their embeddings;
- comments and identifiers can poison search;
- runtime data can leak secrets;
- model updates silently mixed into one index corrupt scores;
- vector scores never authorize access, clear a license, approve security, or prove compatibility.

## 15. Explicit graph and relational descriptions

Graph topology should remain queryable as exact facts and typed scalar/set features even when graph hashes and embeddings also exist.

### 15.1 Local adjacency and neighborhood

- exact incoming and outgoing edges by predicate, role, modality, confidence, analyzer, package, environment, and time;
- unique and multiplicity-aware degree by predicate;
- self-loops, parallel edges, hyperedge participation, and inverse relations;
- callers/callees, definitions/references, reads/writes, producers/consumers, sources/sinks, and tests/subjects;
- k-hop typed neighborhoods for multiple radii;
- neighbor-kind, predicate, role, type, effect, error, package, and evidence histograms;
- may/must, static/dynamic, direct/inferred, positive/negative, and verified/unverified neighborhood partitions;
- unresolved, ambiguous, speculative, and contradicted neighbor counts;
- neighborhood entropy and candidate-target entropy;
- distance to public API, entry point, side-effect boundary, secret, sink, test, vulnerability, changed entity, owner, and package boundary.

### 15.2 Reachability and control/data roles

- exact and bounded reachability;
- shortest, cheapest, safest, highest-confidence, and policy-valid paths;
- dominator and postdominator relationships;
- immediate dominator/postdominator and depth;
- loop header, nesting depth, back edge, natural loop, and irreducible region;
- strongly/weakly connected component membership;
- condensation-DAG position;
- articulation point, bridge, cut vertex/edge, separator, and minimum cut;
- source, sink, transform, merge, split, fan-in, fan-out, gateway, hub, authority, and broker roles;
- reaching definitions, live variables, def-use/use-def, alias, points-to, taint, sanitizer, and lineage reachability;
- exception, cancellation, retry, rollback, and compensation reachability;
- resource acquisition/release, ownership, and leak paths;
- state-machine reachability and invalid-transition paths.

### 15.3 Centrality, community, and architecture

- in/out/total degree centrality by predicate family;
- PageRank and personalized PageRank for relevant teleport sets;
- betweenness, closeness, harmonic, eigenvector, HITS, Katz, and flow centralities;
- k-core, k-shell, degeneracy, rich-club, and coreness;
- community/cluster membership under multiple algorithms and resolutions;
- modularity contribution, conductance, expansion, cohesion, coupling, and boundary cut;
- structural equivalence and role similarity;
- graph orbit, graphlet, motif, triad, tetrad, and metapath participation;
- layer, bounded context, subsystem, service, ownership, and runtime-cluster membership;
- package/module/class/public/private boundary-crossing counts;
- architecture violation and forbidden dependency edges;
- change propagation, blast radius, influence, and risk centrality.

### 15.4 Path, motif, route, and hypergraph descriptions

- typed path language and regular-path-query membership;
- ordered edge-label, participant-role, guard, and port-mapping sequences;
- path preconditions, cumulative effects, errors, permissions, resources, cost, latency, and evidence;
- common predecessor/successor paths and frequent subroutes;
- motif membership such as adapter, validator, factory, fan-out dispatcher, retry loop, transaction boundary, observer, and pipeline stage;
- hyperedge arity, participant roles, order, optional participants, and role constraints;
- route alternatives, Pareto frontier, dominance, bottlenecks, decisive edges, and fragile joins;
- boundary input/output, internal state, error exits, compensation paths, and exact expansion handles.

### 15.5 Temporal and probabilistic graph descriptions

- first/last observed and valid interval for node/edge/path;
- added, removed, modified, resurrected, or superseded across graph epochs;
- edge frequency, probability, confidence, and workload-conditioned prevalence;
- dynamic dispatch and points-to probability distributions;
- co-change, co-use, co-failure, and co-verification weights;
- edge survival, churn, stability, and freshness;
- temporal motif and route evolution;
- graph delta and affected-neighborhood summary;
- evidence accumulation, contradiction, promotion, and invalidation history.

## 16. Behavioral, historical, social, and operational descriptions

### 16.1 Observed behavior

- import, construction, invocation, completion, yield, await, callback, event, and teardown observations;
- concrete and abstract input/output/state tuples;
- runtime types, shapes, schemas, units, ranges, cardinalities, null/missing rates, and value distributions;
- branch/path/call/effect/error/state-transition frequencies;
- side effects, resources, permissions, destinations, files, queries, events, logs, and metrics observed;
- latency, throughput, allocation, memory, CPU, GPU, disk, network, energy, and error distributions;
- cold/warm, cached/uncached, small/large, valid/invalid, normal/adversarial, and fault-injected regimes;
- deterministic/nondeterministic outcome distribution and random-seed behavior;
- concurrency, race, lock, order, cancellation, timeout, retry, and partial-failure observations;
- property, invariant, metamorphic, differential, fuzz, mutation, and sanitizer results;
- discrepancy from documentation, static analysis, another version, or another implementation.

### 16.2 Code history and lineage

- introduced, modified, renamed, moved, copied, forked, vendored, generated, split, merged, extracted, inlined, deprecated, removed, and reintroduced events;
- exact and semantic diffs;
- signature, type, schema, behavior, effect, error, state, dependency, policy, security, and performance changes;
- before/after descriptors, hashes, embeddings, graphs, tests, traces, and receipts;
- commit, tag, release, changelog, migration, issue, pull request, review, and incident associations;
- blame, author, committer, reviewer, owner, maintainer, and team lineage;
- API stability, breaking-change status, compatibility windows, replacements, and migration recipes;
- change frequency, churn, age, survival, regression, revert, and hot-spot statistics;
- co-change, co-review, co-release, and co-deprecation neighborhoods.

### 16.3 Usage and ecosystem signals

- internal/external caller count;
- distinct repositories, packages, versions, tenants, users, and environments using the entity;
- import, call, construction, subclass, implementation, override, and composition frequencies;
- common predecessors, successors, arguments, types, shapes, errors, adapters, and routes;
- package downloads or adoption indicators with source and caveat;
- documentation links, examples, snippets, citations, issues, and support activity;
- search impressions, exact hits, candidate hits, selections, rejections, reformulations, and abandoned searches;
- agent selections, execution successes/failures, verification outcomes, rollbacks, and human overrides;
- adoption, growth, abandonment, replacement, and support trends;
- user/org pattern features isolated by tenant and policy;
- popularity-bias and exposure-bias corrections.

### 16.4 Quality, maturity, and risk

- documentation, type, schema, example, and descriptor completeness;
- parser, symbol, type, call, alias, flow, behavior, and evidence coverage;
- unit, integration, end-to-end, property, fuzz, differential, mutation, and benchmark status;
- line, function, branch, condition, path, edge, dataflow, and state coverage;
- static findings, complexity, duplication, dead code, maintainability, coupling, and cohesion;
- defect, incident, vulnerability, regression, flaky-test, and support burden;
- API, behavior, compatibility, performance, and ownership stability;
- provenance, supply-chain, signature, attestation, SBOM, license, and reproducibility completeness;
- retrieval precision/recall, compatibility false-positive rate, execution success, and verification success;
- abstraction loss, unknown dimensions, contradictions, staleness, and technical debt;
- quality trend and uncertainty interval rather than one opaque “quality score.”

## 17. Evidence, provenance, contradiction, and trust descriptions

W3C PROV’s separation among entities, activities, agents, derivation, revision, specialization, attribution, and qualified relations is a useful interoperability model for descriptor provenance. See [PROV-O](https://www.w3.org/TR/prov-o/).

### 17.1 Evidence-source taxonomy

- original author, maintainer, contributor, reviewer, security reviewer, domain expert, user, policy owner, and curator;
- declaration, annotation, docstring, comment, README, API reference, tutorial, example, changelog, migration guide, standard, issue, PR, review, commit, and release note;
- parser, CST/AST analyzer, symbol table, resolver, type checker, compiler, linker, linter, static call/flow/taint/alias analyzer, abstract interpreter, symbolic executor, model checker, clone detector, security/license/dependency scanner;
- import/reflection/introspection observation, execution/stack/coverage/profile/syscall/network/database trace, telemetry, runtime type/heap observation, fuzz/property/sandbox/production observation;
- unit, integration, end-to-end, regression, differential, metamorphic, property, fuzz, mutation, benchmark, static proof, formal proof, reproduction, and independent verification;
- deterministic NLP, statistical NLP, local SLM, general LLM, code model, frontier model, model consensus, judge, analyzer-corrected model claim, and test-verified model claim.

### 17.2 Claim semantics

- polarity: positive, negative, mixed;
- quantifier: all, most, usually, sometimes, exists, may, never, unknown;
- modality: asserted, extracted, inferred, predicted, observed, tested, proved, verified;
- path/context sensitivity: insensitive, context-, flow-, path-, field-, object-, or environment-sensitive;
- confidence, calibration, confidence interval, and out-of-distribution status;
- evidence coverage, diversity, independence, and source reliability;
- temporal, version, environment, input-region, configuration, feature, tenant, and access scope;
- candidate, schema-valid, source-backed, corroborated, observed, tested, independently verified, contradicted, superseded, or expired status.

### 17.3 Contradiction and negative knowledge

- documentation/code disagreement;
- static/runtime disagreement;
- analyzer/analyzer, model/model, and human/analyzer disagreement;
- apparent contradiction explained by different version, environment, input region, path, or quantifier;
- confirmed contradiction and decisive evidence;
- unsupported claim and missing evidence;
- non-occurrence observed only within stated coverage;
- proven absence under explicit analysis assumptions;
- unknown because not computed, unsupported, dynamic, unreachable, timed out, denied, withheld, or redacted;
- expired or stale claim;
- rejected search alias, retrieval false positive/negative, compatibility false positive/negative, and failed route;
- resolution claim, policy, reviewer, and remaining uncertainty.

“Unknown,” “not observed,” and “proven absent” are distinct values. Confidence is not truth. A claim may be preferred for retrieval without being authoritative for execution.

### 17.4 Trust and promotion ladder

- L0 unparsed/untrusted input;
- L1 schema-valid candidate;
- L2 source-span-backed or deterministic extraction;
- L3 corroborated by independent static or documentary evidence;
- L4 runtime-observed within explicit coverage;
- L5 test-verified or proof-supported within explicit scope;
- L6 independently reproduced/verified with exact receipt.

Promotion is facet-specific. A test can verify one behavior without verifying thread safety, license compatibility, or all error paths.

## 18. Entity-by-entity descriptor portfolios

Every subject inherits the universal families above. The following overlays identify the descriptors that are especially important for each construct.

### 18.1 Language primitive, literal, constant, enum member, or sentinel

- exact spelling, decoded value, byte representation, source span, and language version;
- primitive/value kind, declared/inferred type, width, signedness, precision, base, encoding, and endianness;
- value domain, range, unit, dimension, tolerance, special values, overflow/underflow, NaN/infinity, and comparison semantics;
- mutability, identity, interning, allocation, truthiness, hashing, equality, ordering, conversion, and serialization behavior;
- literal role: default, sentinel, discriminator, flag, enum, format string, path, URL, SQL, regex, secret, user-facing text, test value;
- symbolic/constant-propagation value and expressions derived from it;
- read/reference sites, aliases, exported names, config bindings, and replacement history;
- sensitivity, redaction, entropy, secret/credential indicators, and safe keyed fingerprints;
- raw/canonical/value-class hashes; numeric buckets; string n-grams; format/regex/URL/path fingerprints; value-safe embeddings only when policy permits;
- plain-language meaning, domain keyword, labels, examples, boundary values, invalid values, and counterexamples.

### 18.2 Token, occurrence, expression, statement, block, and syntax node

- exact source/byte/token range, file, cell, macro expansion, and source-map chain;
- raw token, token kind, trivia, normalized form, identifier/literal role, parser state, and diagnostics;
- AST/CST kind, parent/children/siblings, field role, depth, scope, evaluation order, and language-specific semantics;
- expression type, value category, constant value, nullability, purity, effects, exceptions, short-circuit behavior, and precedence;
- statement control role, guards, successors/predecessors, dominator/postdominator, loop/exception region, and reachability;
- definition/reference/call/read/write/import/export/documentation occurrence role and resolved candidates;
- def-use/use-def, data/control dependence, taint, alias, state, and lineage edges;
- raw/token/normalized/subtree/Merkle/path/WL fingerprints and source/code embeddings;
- local text description, keywords, labels, surrounding context, historical change, tests, coverage, and evidence.

### 18.3 Variable, binding, local, global, closure capture, field, or slot

- native/qualified/display names, aliases, historical names, exact definition and occurrence IDs;
- binding kind, lexical/semantic scope, owner, visibility, export status, shadowing, and generated status;
- declaration, initialization, assignment, augmented assignment, read, delete, capture, escape, and teardown sites;
- definite assignment, reaching definitions, live range, use-def/def-use, alias/points-to set, and lineage;
- declared, inferred, narrowed, and observed types plus distributions;
- abstract value domain, examples, range, schema, shape, axes, units, encoding, cardinality, nullability, sentinel, and default;
- storage duration, allocation region, lifetime, ownership, borrowing, mutability, copy/view, thread/task/process locality, and sharing;
- global/receiver/closure/object state slot, state-machine role, cache/config/feature-flag/secret/source/sink/sanitizer role;
- validation, invariants, sensitivity, taint, persistence, serialization, caching, invalidation, and concurrency rules;
- name/character/phonetic/keyword features; scope-aware role hash; type/value/shape hashes; context shingles; use-def graph features; value-distribution sketches; name/context/type/behavior embeddings;
- black-box variable card: “what value this binding represents, where it comes from, where it flows, what mutates it, and what depends on it.”

The binding and runtime values remain separate. A global sidecar identity can disambiguate every binding without renaming native source identifiers.

### 18.4 Parameter, return, yield, callback, event, error, state, or resource port

- exact owner and port position/role/direction;
- name, aliases, semantic role, positional/keyword/variadic/implicit mode, required status, default, and default computation;
- declared/inferred/observed type, schema, shape, units, range, precision, encoding, cardinality, nullability, ordering, and uniqueness;
- ownership, lifetime, mutability, borrow/copy/view, streaming/batch, sync/async, push/pull, backpressure, and cancellation;
- validation, coercion, normalization, sanitization, refinement, accepted/rejected examples, and error behavior;
- pre/postconditions, cross-port constraints, environment/version conditions, privacy, permission, and policy;
- producer offer and consumer requirement descriptions and embeddings kept distinct;
- exact port/signature/schema/shape/unit/effect/error hashes; blocking bitmaps; set sketches; port graph neighborhood; compatibility history;
- known producers, consumers, adapters, conversions, blockers, losses, verified pairings, and counterexamples.

### 18.5 Function, lambda, closure, generator, coroutine, handler, or callable

- callable kind, exact identity, native and canonical signatures, overloads, type parameters, calling convention, decorators/annotations, and visibility;
- parameter/return/yield/await/error/callback/event/state/resource/control port inventory;
- captured variables and closure environment;
- black-box purpose, intent, capability, input/output transformation, algorithm, white-box mechanism, and architectural role;
- preconditions, postconditions, invariants, refinements, dispatch guards, and termination conditions;
- purity, determinism, idempotence, reversibility, numerical behavior, state reads/writes, receiver/argument/global mutation, and external effects;
- exception, error, cancellation, timeout, retry, partial result, cleanup, transaction, rollback, and compensation behavior;
- sync/async/generator, blocking, batching, streaming, recursion, parallelism, thread safety, reentrancy, and resource behavior;
- callers, callees, call sites, dynamic targets, imports, types, def-use, CFG/DFG/PDG/CPG, state, effect, error, test, documentation, and history neighborhoods;
- complexity, empirical performance distributions, hot paths, allocation, I/O, and workload sensitivity;
- raw/normalized source, token/winnowing/MinHash/SimHash/TLSH candidates; signature/contract hashes; AST/flow/graph fingerprints; source/doc/port/behavior/test/trace/history embeddings;
- examples, counterexamples, misuse, alternative functions, wrappers/adapters, deprecation/replacement, test coverage, evidence, contradictions, and exact use receipts.

### 18.6 Method, constructor, property, descriptor, or operator

All callable descriptors, plus:

- owning type, receiver type/role, binding kind, visibility, and lifecycle phase;
- instance/class/static/extension/trait/interface/operator/getter/setter/deleter/descriptor kind;
- abstract/concrete, virtual/final, overload, override, implementation, hide, and super-call relationships;
- MRO/vtable/dispatch slot, dynamic target set, covariant/contravariant compatibility, and protocol obligations;
- receiver-state preconditions, receiver and class-state mutations, invariant preservation, lock requirements, and fluent-return behavior;
- construction/allocation/initialization/finalization semantics;
- property storage versus computation, caching/invalidation, validation, side effects, and descriptor binding behavior;
- equality, hashing, comparison, indexing, iteration, context, arithmetic, conversion, serialization, and other operator protocol semantics;
- override-family and receiver-state fingerprints/embeddings, class graph role, subclass usage, and behavior variation by dynamic type.

### 18.7 Class, struct, record, enum, interface, protocol, trait, mixin, or metaclass

- construct kind, exact identity, native declaration, public API, documentation, purpose, domain, and architecture role;
- bases, superclasses, implemented interfaces/protocols/traits, mixins, MRO/linearization, metaclass, subclasses, and conformance;
- generic parameters, bounds, variance, associated types, abstract/sealed/final status, and required overrides;
- constructors, factories, allocators, initializers, destructors/finalizers, context hooks, and lifecycle;
- fields, slots, class attributes, properties, descriptors, methods, operators, enum members, nested types, and extension points;
- object schema, invariants, state machine, valid phases, ownership, resources, equality, hashing, ordering, copying, serialization, and representation;
- memory layout, size, alignment, packing, vtable, ABI, slots, native-extension, and FFI facts;
- thread/process safety, reentrancy, synchronization, mutation, persistence, caching, and event behavior;
- instantiation, subclass, implementation, usage, test, co-change, ownership, deprecation, and migration history;
- declaration/source hashes; public API Merkle root; method/field/effect/error set sketches; inheritance/MRO/state graph hashes; class/source/doc/API/graph/behavior embeddings;
- capability union/intersection, cohesion, coupling, representative methods, rare decisive capabilities, anti-use cases, and compatible substitutes.

### 18.8 Runtime object, instance, allocation family, or resource handle

- observation-scoped object identity, dynamic type/class, construction/allocation site, factory, process/thread/task, and environment;
- creation, initialization, valid-state, mutation, use, escape, ownership transfer, finalization, deallocation, and garbage-collection events;
- current privacy-safe state schema, state snapshot digest, dynamic attributes, structural shape, aliases/references, reachability, and invariant status;
- identity/equality/hash/order observations;
- methods called, ports used, state transitions, effects, errors, resources, locks, and concurrency history;
- serialization/repr shape, memory footprint, device placement, resource handles, taint, sensitivity, residency, and redaction;
- construction-site, type, field-key, schema/shape, lifecycle, state-machine, trace, and resource fingerprints;
- state/behavior/trace/object-shape embeddings only from policy-safe abstractions;
- distinguish one object, an allocation-site family, a type-wide observed family, and a snapshot distribution;
- never embed raw secrets, credentials, personal data, or arbitrary object values by default.

### 18.9 Macro, template, generic specialization, decorator, annotation, or generated construct

- definition and invocation identities, parameters, arguments, hygiene, expansion context, compiler phase, and source maps;
- raw input, expanded output, generated entities/edges, ordering, conditional compilation, and environment/version guards;
- template/generic bounds, substitutions, specializations, monomorphizations, instantiations, and code-size impact;
- decorator/annotation target, order, transformation, injected behavior, registration, metadata, effects, and runtime hooks;
- exact definition/invocation/expansion hashes, expansion-tree fingerprints, generated-code lineage, and pre/post expansion embeddings;
- black-box transformation description, examples, invalid uses, errors, security risks, compile/runtime cost, and verification coverage.

### 18.10 Type, schema, protocol, data contract, dataframe, tensor, or message

- identity, dialect, version, nominal/structural/refinement status, title, purpose, domain, producers, and consumers;
- scalar/container/table/tensor/graph classification;
- fields/properties/keys/axes, types, positions, cardinalities, requiredness, null/missing semantics, defaults, constants, enums, ranges, patterns, units, and formats;
- shape, rank, dimensions, dynamic axes, layout, strides, dtype, precision, device, and coordinate/reference system;
- generics, variance, bounds, union/intersection, conditional/cross-field constraints, keys, uniqueness, relationships, and indexes;
- encoding, serialization, wire/media format, endianness, ordering, stability, version negotiation, and compatibility/evolution policy;
- examples, counterexamples, validation tools, migrations, provenance, security classes, privacy, and license;
- canonical schema/type/shape/unit/constraint hashes; field and path MinHash; compatibility blocks; ontology labels; schema/doc/producer/consumer embeddings;
- exact assignability/constraint solving and adapter verification remain decisive.

### 18.11 Module, namespace, source file, notebook, or cell

- path, module/import name, namespace, package parent, language, encoding, content digest, generated/vendor/test/example status, and license;
- declarations, definitions, exports, re-exports, imports, optional/lazy/dynamic imports, circular dependencies, and public/internal surface;
- globals, initialization order, import-time effects, registration, entry points, plugins, hidden notebook state, and cell execution order;
- subsystem role, boundary ports, owned state, effects, errors, tests, docs, examples, ownership, platform/feature guards, and support status;
- parse/resolve/type/graph coverage, diagnostics, unresolved constructs, abstraction loss, cohesion, coupling, fan-in/out, SCCs, and cycles;
- raw/file/module hashes, chunk manifests, public API root, symbol/dependency set sketches, module graph fingerprints, aggregate text/code/graph embeddings;
- history, churn, co-change, semantic diff, blame, migration, vulnerabilities, and exact expansion handles.

### 18.12 Package, distribution, release, repository, artifact, build, or binary

- project/distribution/import names, purl/SWHID/repository/release/artifact/build IDs, versions, tags, commits, digests, signatures, and attestations;
- registry/core metadata version, authors, maintainers, URLs, summary, description, keywords, classifiers, license, notices, and funding/governance;
- language/runtime requirements, dependencies, optional extras/groups, environment markers, entry points, plugins, build backend/requirements/options, platform/ABI tags, and native extensions;
- artifact contents, modules, public API, subsystems, schemas, endpoints, commands, tests, docs, examples, install/import/build behavior, and boundary contract;
- compatibility matrix, platform/runtime support, security advisories, SBOM, vulnerabilities, reproducibility, supply-chain provenance, and policy;
- release/changelog/deprecation/migration history, download/adoption/support indicators, ownership and maintenance health;
- raw artifact and Merkle roots, chunk manifests, public API/dependency/effect/error set sketches, package graph fingerprints, release-delta and package-level embeddings;
- source distribution, wheel, installed tree, binary, and runtime build are separate subjects because metadata and behavior may differ.

PyPA core metadata already separates name, version, summary, description, keywords, classifiers, dependencies, Python requirements, extras, licenses, and project URLs; Taedri should ingest these as individual claims rather than flattening them. See the [PyPA core metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/).

### 18.13 Test, fixture, property, assertion, oracle, benchmark, or failure case

- test identity, framework, level, style, intent, requirement, target entities/edges/routes, and source;
- setup, teardown, fixtures, parameters, generators, seeds, mocks/stubs/fakes/patches, inputs, environment, and isolation;
- oracle, assertions, expected outputs/errors/effects/state, tolerance, property, metamorphic relation, and counterexample;
- execution result, duration, resources, logs, traces, artifacts, coverage contribution, mutation kills, sanitizer findings, and benchmark distributions;
- determinism, flakiness, quarantine, reliability, historical results, linked regression/issue/commit, and last verified snapshot;
- source/input/oracle/trace/failure/coverage hashes and sketches; test intent/code/trace/failure embeddings; test-to-subject graph role;
- evidence grade, independence, covered input region, unsupported claims, and exact reproduction/verification receipt.

### 18.14 Configuration, feature flag, CLI command, endpoint, RPC, event, query, or external surface

- canonical name/path/route/topic/key, namespace, version, aliases, precedence, source, and owner;
- input/output/error/event schemas and individual ports;
- method/verb, protocol, media types, status/exit codes, headers/flags/options/arguments, auth, permissions, and rate limits;
- default, allowed values, range, regex, units, secret status, dynamic/static, reload/restart, tenant/environment scope, and feature conditions;
- handlers, producers, consumers, middleware, database/resources, effects, state, transactions, retries, timeouts, idempotency, ordering, and delivery guarantees;
- examples, invalid examples, security threats, observability, deprecation, replacement, versions, compatibility, and runtime observations;
- canonical contract and route hashes; schema/keyword/LSH blocks; handler/dataflow graph; text/port/behavior/error embeddings; verified request/response or invocation receipts.

### 18.15 Edge, relation claim, or n-ary relation

- exact edge and relation-instance IDs, subject/predicate/object, participants, participant roles/order, source occurrences, and snapshot;
- direction, inverse, symmetry, reflexivity, transitivity policy, multiplicity, cardinality, polarity, and `may`/`must` modality;
- static/dynamic, direct/inferred/derived, flow/path/context/field/object sensitivity;
- guards, path conditions, version/environment/input/configuration/feature/tenant/temporal scope;
- causal/correlational/structural status, ordering, frequency, weight, confidence, and analyzer;
- source-to-target value/argument/port mapping, propagated effects/errors/state, compatibility signature, adapters, loss, cost, and blockers;
- evidence, counterevidence, contradictions, verification, freshness, alternatives, supersession, and impact if removed/changed;
- forward/inverse plain text, why/when/when-not/what-breaks views, search aliases, negative aliases, labels, and query intents;
- exact/semantic/inverse/port/evidence/compatibility/graph/trace/history fingerprints and relation/pair/hyperedge/path embeddings.

### 18.16 Group, subsystem, capsule, cluster, overload set, clone family, or collection

- group kind, explicit/inferred status, membership rule, exclusions, frozen member list, confidence, evidence, hierarchy, and alternative partitions;
- inbound/outbound boundary ports, effects, errors, state, permissions, dependencies, invariants, and compatibility contract;
- internal/external decisive edges, emergent capabilities, hidden complexity, cohesion, coupling, cut edges, modularity, central members, representatives, and outliers;
- member/source/doc/label unions and intersections, coverage, descriptor completeness, abstraction loss, unresolved edges, and expansion handles;
- stability across versions, co-change/co-use/runtime/test/ownership evidence, architecture role, and support status;
- Merkle member root, set/multiset/containment sketches, boundary and graph hashes, centroid/medoid/prototype/member/late-interaction embeddings;
- never use one average as the only representation.

### 18.17 Route, plan, pipeline, workflow, or composition

- route identity, demand/goal, form (sequence, DAG, loop, conditional graph, hypergraph), versions, and plan lock;
- primitive bindings, ports, data/control/state mappings, adapters, coercions, guards, branches, loops, and parallel regions;
- initial/final state, global invariants, pre/postconditions, cumulative effects, permissions, dependencies, resources, environment, and policy;
- error paths, retries, timeouts, cleanup, transaction boundaries, rollback, compensation, and fallback;
- latency/cost/resource/reliability/risk estimates and observed distributions;
- alternatives, Pareto/dominance status, decisive tradeoffs, selection reason, rejected candidates, and counterexamples;
- verification plan, intermediate receipts, execution receipt, failure/rollback receipt, replayability, reproducibility, drift, and expiry;
- exact ordered/path/DAG/Merkle hashes, sequence/path/motif sketches, boundary contract fingerprints, and goal/sequence/graph/effect/error/cost embeddings.

### 18.18 Applicability matrix

Legend: `●` broadly useful, `○` conditional/specialized. All projections remain optional materializations with explicit state.

| Subject | Exact/source | Text | Keywords | Labels | Typed contracts | Hash/LSH | Embeddings | Graph | Runtime | History/evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Literal/primitive | ● | ● | ● | ● | ● | ● | ○ | ● | ○ | ● |
| Token/occurrence/AST node | ● | ○ | ● | ● | ○ | ● | ○ | ● | ○ | ● |
| Variable/binding/field | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Parameter/port | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Function/callable | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Method/property/operator | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Class/interface/type | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Runtime object/family | ● | ● | ○ | ● | ● | ● | ● | ● | ● | ● |
| Macro/template/decorator | ● | ● | ● | ● | ● | ● | ● | ● | ○ | ● |
| Schema/data contract | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| File/module/notebook | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Package/release/artifact | ● | ● | ● | ● | ● | ● | ● | ● | ○ | ● |
| Test/benchmark | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Config/CLI/endpoint/event | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Edge/hyperedge | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Group/capsule | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Route/workflow | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |

## 19. Fully extensible registry architecture

The kernel should standardize the envelope and registry protocol, not freeze the universe of possible attributes.

### 19.1 Description portfolio

```yaml
DescriptionPortfolio:
  subject_ref: ...
  snapshot_id: ...
  projection_refs: []             # unbounded
  descriptor_state_manifest_ref: ...
  coverage_manifest_ref: ...
  preferred_view_bindings: []     # preferred only for a scope/purpose
  contradiction_set_refs: []
  policy_projection_refs: []
  graph_epoch: ...
```

### 19.2 Provider manifest

```yaml
DescriptorProviderManifest:
  provider_namespace: org.example.python-security
  provider_version: 2.4.1
  implementation_and_digest: ...
  supported_subject_kinds: []

  descriptor_definitions:
    - descriptor_key: org.example.python-security.deserialization_risk
      family: structured_claim
      value_schema_ref: https://example.org/schema/deserialization-risk-v2.json
      cardinality: many
      merge_policy: preserve_all_claims
      missing_semantics: explicit_state
      compatibility_role: hard_gate
      validators: []
      index_recipes: []

  description_views: []
  embedding_recipes: []
  fingerprint_recipes: []
  edge_predicate_definitions: []
  migrations: []
  default_trust_status: candidate
  policy_requirements: ...
```

### 19.3 Cardinality and immutable variant-production rules

Every semantic attribute is a **set of immutable typed variants**, not a privileged scalar:

```yaml
AttributeVariantSet:
  subject_id: ...
  attribute_key: uceg.attribute.effects
  variant_refs: []                # unbounded
  combination_refs: []
  preferred_view_refs: []
  extension_registry_refs: []
```

This rule applies to identities, kinds, names, aliases, descriptions, keywords, languages, translations, labels, types, schemas, ports, effects, errors, permissions, lifecycle, trust, measurements, embeddings, hashes, structural views, nodes, edges, compatibility judgments, tests, observations, retrieval outcomes, route candidates, and model-visible projections.

Unlimited variants do **not** mean recursively turning every field into `any[]`:

- the entity has an unlimited collection of typed variant records;
- one variant describes one exact production or observation event;
- intrinsically plural fields such as evidence inputs may be collections inside that record;
- a different model, revision, prompt, seed, preprocessor, environment, scope, or output creates another record;
- exact duplicate payloads may share content-addressed bytes, while their production and evidence lineages remain distinct.

Variants remain separate whenever any of these differ:

- producer, provider, runtime, endpoint, implementation, or version;
- model family, checkpoint, weights digest, tokenizer, pooling, dimension, dtype, or quantization;
- prompt program, rendered prompt, system instruction, persona, parameters, or random seed;
- ordered inputs, artifact, build, dependency closure, preprocessing, postprocessing, or environment;
- output bytes, human edit, evidence, intended purpose, audience, language, detail level, policy, access scope, or time.

```yaml
GenerationRun:
  generation_run_id: ...
  task_key: ...
  producer_ref: ...
  model_or_tool_ref: ...
  prompt_program_ref: ...
  rendered_prompt_digest: ...
  ordered_role_labeled_inputs: []
  preprocessing_chain: []
  parameters: {}
  random_seed: ...
  artifact_build_environment_scope: ...
  started_at: ...
  completed_at: ...
  output_variant_refs: []
  usage_and_cost_receipt_refs: []
  failure_ref: ...
```

Representation lineage is a many-to-many DAG. Derived variants store ordered or role-labeled inputs, derivation activity, supersession, invalidation, and output refs; a single `parent_id` is insufficient.

### 19.4 Required extension guarantees

- namespaced subject kinds, facets, descriptors, labels, predicates, roles, models, and view keys;
- semantic versions and immutable definition versions;
- schema references and schema validation;
- unknown-field round-tripping;
- no fixed attribute, description, keyword, label, fingerprint, embedding, edge, example, or evidence count;
- multiple provider and model versions at once;
- append-only original facts and claims;
- explicit derivation, invalidation, supersession, and retirement rather than overwrite;
- deterministic input digests and reproducible recipes;
- provider-specific validators, evidence requirements, compatibility roles, index mappings, policies, and UI projections;
- registry collision detection and namespace ownership;
- local/private/tenant namespaces;
- import/export without semantic loss;
- offline operation and local-model support;
- independent logical schema and physical materialization/index policy;
- reprocessing and re-embedding as new projection epochs;
- per-projection ACL, secrecy, license, retention, and egress controls;
- explicit graph/snapshot/build/environment scope;
- typed `not_computed`, `not_applicable`, `unknown`, `withheld`, `failed`, and `stale` states.

An open `extensions: map<string, any>` may preserve unknown data, but it must not be the only extension mechanism. Useful extensions should be registered, schema-validated, versioned, and independently indexable.

### 19.5 Multi-view axes

Keep all of these axes independent:

- subject kind and referent layer;
- programming language and language version;
- natural language, locale, script, and translation lineage;
- domain, framework, ecosystem, and organization;
- audience and purpose;
- retrieval direction and role;
- detail and abstraction level;
- source, producer, model, prompt/rule, and evidence grade;
- version, snapshot, build, platform, dependency, environment, input region, and time;
- tenant, principal, access, secrecy, license, retention, and egress policy.

### 19.6 Preferred values are scoped views

A preferred value is a reversible, versioned selection result—not privileged storage and never deletion of alternatives.

```yaml
PreferredValueView:
  view_id: ...
  subject_id: ...
  attribute_key: ...
  consumer_or_purpose: retrieval|solving|selection|execution|verification|human
  scope:
    task_families: []
    natural_languages: []
    programming_languages: []
    environments: []
    tenants: []
    policies: []
  eligible_variant_refs: []
  selected_variant_refs: []
  selection_mode: single|ordered|set|combined
  selection_policy_ref: ...
  selection_policy_version: ...
  explanation_and_evidence_refs: []
  valid_interval: ...
```

Several preferred views may coexist. Retrieval may prefer a locally generated multilingual description, the solver may prefer compiler-derived contracts, and a verifier may ignore both in favor of tests and exact evidence. Every underlying variant remains directly listable, filterable, comparable, and traversable through lineage.

### 19.7 Representation combinations are first-class variants

```yaml
RepresentationCombination:
  combination_id: ...
  subject_ids: []
  purpose: retrieval|ranking|solving|selection|disclosure
  combination_kind: union|intersection|ordered_fallback|cascade|rrf|weighted_sum|vote|concatenation|late_interaction|learned_fusion|graph_projection
  members:
    - variant_ref: ...
      role: ...
      weight: ...
  combiner_ref_and_version: ...
  configuration: {}
  training_or_calibration_ref: ...
  output_variant_refs: []
  lineage_and_evidence_refs: []
```

Valid combinations include lexical candidate unions, hard-filter intersections, several blocking families, rank fusion, multi-vector late interaction, description/model cross-products, analyzer consensus, graph projections, label votes, compatibility witnesses, and progressive disclosure bundles. Combination semantics—AND, OR, order, fallback, weighting, voting, calibration, or composition—must be explicit.

Do not eagerly materialize the Cartesian product of every description, model, preprocessor, and index. Register the possible axes; materialize useful runs; retain every executed combination with exact lineage and measured operating characteristics.

## 20. Physical index mapping

Logical descriptions can be materialized into several independently replaceable index planes.

| Descriptor family | Primary indexes | Verification/source of truth |
|---|---|---|
| Identity and exact facts | key/value, relational uniqueness, content-addressed store | canonical entity/fact store |
| Source/evidence | blob/content store, source-span table, Merkle store | exact artifact and acquisition receipt |
| Plain text | fielded BM25/BM25F, phrase, prefix/suffix, identifier-aware postings | underlying description assertions |
| Keywords/keyphrases | postings, positional index, weighted sparse vector | term projection and source refs |
| Labels/taxonomies | bitmap/facet index, hierarchy closure, ontology graph | label assertions and scheme definitions |
| Scalars/quantities/versions | typed columns, range/interval/unit-aware indexes | typed assertion |
| Types/schemas/contracts | structural indexes, unification/constraint solver | canonical contract and evidence |
| Exact hashes | hash table/KV/content store | exact bytes or canonical serialization |
| MinHash/LSH/fuzzy | bucket tables and candidate postings | exact comparison/typed verifier |
| Embeddings | ANN per vector space plus exact rerank store | source projection and downstream verifier |
| Graph facts | adjacency/CSR, graph database, path/motif indexes | first-class typed edge assertions |
| Temporal/history | bitemporal/interval index, epoch/delta store | versioned facts and provenance |
| Runtime/performance | trace store, columnar series, sketch store | exact observations/workload metadata |
| Evidence/trust | evidence graph, claim table, contradiction index | signed/source/test/verification records |
| Policy | authoritative policy engine and ACL prefilter | policy decision and audit receipt |

Index manifests record shard, tenant/policy filter, snapshot/graph epoch, projection versions, build time, feature/model/seed/configuration, item counts, calibration, measured recall, and invalidation state.

### 20.1 Retrieval waterfall enabled by the portfolio

1. Authenticate and apply tenant, ACL, secrecy, license, retention, and policy filters.
2. Reuse exact query, verified route, user/org history, and cache hits.
3. Resolve exact CEID, native/qualified name, alias, package, signature, error, and literal matches.
4. Run fielded BM25/keyword/label/ontology and deterministic string matching.
5. Compile typed demand into type/schema/unit/version/environment/policy constraints.
6. Run bidirectional provider/consumer port blocking and graph route solving.
7. Use membership filters to skip definitely absent shards/neighborhoods.
8. Generate token/winnowing/MinHash/weighted-MinHash/SimHash/fuzzy candidates.
9. Add AST/CFG/DFG/graph/motif/path candidates.
10. Add one or more relevant embedding spaces and late-interaction candidates.
11. Fuse calibrated ranks while retaining per-arm results.
12. Apply hard typed compatibility gates and evidence/freshness/quality ranking.
13. Resolve source bodies only for finalists.
14. Cross-encode or invoke an SLM/LLM only when uncertainty and expected value justify it.
15. Execute or independently verify where the task requires correctness.
16. Store exact success, failure, incompatibility, adapter, and receipt evidence for reuse.

This is the practical token-saving payoff: most queries can be compiled from the user demand into exact fields, terms, labels, sketches, graph constraints, and templates before any model drafts a custom query.

### 20.2 Role-specific canonical and disclosure views

Canonical views are versioned selection policies over retained variants:

```text
RetrievalView
  aliases, keywords, descriptions, examples, sparse/dense variants

SolverView
  ports, types, schemas, effects, constraints, adapter witnesses

SelectorView
  contrastive alternatives, decisive differences, risk, cost, evidence, uncertainty

ExecutionView
  immutable artifact, runtime, dependency closure, authority, policy, secret classes

VerificationView
  claims, oracles, expected evidence, reconciliation and receipt requirements

HumanView
  readable explanation, provenance, alternatives, limitations, expansion handles
```

Progressive model disclosure:

```text
D0  opaque stable handle
D1  name, labels, and one-line capability
D2  ports, effects, failures, state, and operational constraints
D3  decisive edges and contrastive alternatives
D4  selected examples, tests, evidence, and uncertainty
D5  full entity/edge/group/route card
D6  selected implementation body only when inspection or modification requires it
```

Search may use thousands of variants outside the model. Model-visible exact and near-duplicate variants should normally be clustered; provenance differences or semantic disagreements are exposed as deltas when they can change the decision. The disclosure optimizer minimizes context subject to preserving every decision-changing fact.

## 21. Generation and invalidation waterfall

1. Acquire and content-address exact artifacts without executing them.
2. Inventory every file, region, occurrence, symbol, binding, callable, type, port, relation, test, artifact, and failure.
3. Emit exact identities, source facts, tokens, AST/CST, metadata, docs, and evidence.
4. Resolve symbols, scopes, types, imports, calls, aliases, control/data flow, effects, and errors.
5. Deterministically render plain-text cards, keywords, labels, schemas, contracts, and graph features.
6. Produce exact and normalized hashes, shingles, sketches, LSH buckets, and membership filters.
7. Produce cheap sparse and local dense embeddings for separately selected facets.
8. Aggregate class/module/package/group boundaries bottom-up, retaining coverage and abstraction loss.
9. Run framework/domain analyzers and add domain-specific facets.
10. Run sandboxed tests, traces, fuzzing, profiling, or reflection only under an explicit execution policy.
11. Generate higher-cost descriptions, embeddings, pair assessments, and route projections only when evaluation or demand justifies them.
12. Validate model-generated claims against facts; unsupported claims remain candidate hypotheses.
13. Publish an immutable graph/projection epoch atomically.
14. Invalidate projections by dependency/input digest; recompute only affected records.
15. Keep old epochs addressable for reproduction, comparison, rollback, and model evaluation.

### 21.1 Broad initial materialization profile—not a schema limit

For every discovered entity, broadly materialize:

- exact identity, occurrence, source handle, kind, scope, version, and provenance;
- native/qualified names and identifier-aware lexical forms;
- deterministic one-line and structured black-box cards;
- author docs and examples;
- labels for kind, visibility, lifecycle, execution mode, state, effect, error, domain, and trust where known;
- signature/type/schema/port/effect/error/state contracts;
- exact source/signature/schema hashes;
- several normalized source/token fingerprints;
- token shingles plus MinHash/SimHash candidates where size permits;
- fielded sparse search representation;
- exact typed graph adjacency and core graph statistics;
- evidence, contradiction, coverage, freshness, and policy records;
- at least independent text, code, and port/contract embedding arms when models are available and policy permits.

Then materialize additional models, detail levels, fingerprints, graph embeddings, runtime projections, pair assessments, and route descriptions according to measured value, query demand, policy, and compute/storage budgets. This is an open scheduling policy, not a feature cap.

### 21.2 Lifecycle, supersession, revocation, and deletion

- Creation is append-only.
- Corrections create new variants.
- Rejection retains the attempted run and negative evidence.
- Supersession and invalidation are explicit typed edges.
- Revocation prevents selection or execution without erasing audit history.
- Model, analyzer, prompt, preprocessor, or tokenizer upgrades create new variants.
- Re-embedding, rewording, recalibration, and index rebuilds create new projection epochs.
- Preferred pointers can change independently of retained records.
- Time-, environment-, version-, policy-, and tenant-scoped validity is explicit.
- Physical deletion follows privacy, access, retention, license, or legal policy.
- Deletion leaves an authorization-safe tombstone, digest, or non-disclosing audit marker where permitted.
- Downstream projections are invalidated through lineage and input digests, not by global rebuild assumptions.

## 22. Coverage and completeness ledger

“Describe every entity” requires a negative-space manifest.

```yaml
CoverageManifest:
  snapshot_id: ...
  graph_epoch: ...
  entity_counts:
    discovered: ...
    parsed: ...
    resolved: ...
    typed: ...
    documented: ...
    runtime_observed: ...

  descriptor_coverage:
    uceg.identity: 1.0
    uceg.description.black_box: 0.93
    uceg.contract.errors: 0.41

  by_subject_kind: {}
  by_module_package_visibility: {}
  by_provider_and_version: {}
  by_environment_and_input_region: {}
  by_evidence_grade: {}

  unsupported_constructs: []
  failed_subjects: []
  unknown_reasons: []
  withheld_counts: []
  analyzers_run: []
  verification_coverage: ...
```

Coverage should be queryable by entity kind, facet, provider, package/module, visibility, version, environment, input region, policy, and verification level.

## 23. Evaluation atlas

### 23.1 Query classes

- exact symbol/name/package lookup;
- typo, alias, historical-name, and multilingual lookup;
- natural-language intent-to-code;
- code-to-code and cross-language analogy;
- copied-region, clone, lineage, containment, and refactoring lookup;
- signature/type/schema/unit/effect/error compatibility;
- producer-to-consumer and consumer-to-provider search;
- behavior, example, test, error, trace, and incident retrieval;
- graph neighbor, path, motif, role, and route retrieval;
- substitute, adapter, migration, deprecation, and change-impact search;
- quality-, trust-, freshness-, license-, security-, environment-, and policy-constrained retrieval;
- package/subsystem/group-level capability and boundary search.

### 23.2 Metrics

- Recall@k, precision@k, MRR, nDCG, MAP, and calibrated score quality;
- exact-name and rare-identifier recall;
- clone/containment recall by edit and normalization type;
- compatibility false-positive and false-negative rates per dimension;
- typed-solver agreement and adapter correctness;
- route discovery, verified execution, output correctness, rollback, and receipt reproducibility;
- retrieval-to-body-resolution ratio and tokens avoided;
- local compute, model tokens, latency, storage, index build time, memory, and energy;
- ANN/LSH recall against exact samples;
- evidence coverage, contradiction rate, staleness, and claim calibration;
- cross-version, cross-language, platform, framework, and package generalization;
- tenant/policy isolation and sensitive-data leakage;
- marginal utility and cost of every descriptor/model/index arm.

### 23.3 Hard-negative and poison suites

- sibling overloads differing by one decisive constraint;
- same name/different behavior and different name/same behavior;
- syntax-similar/behavior-different and syntax-different/behavior-similar entities;
- renamed-but-semantically-changed entities;
- same type but incompatible units, shapes, ownership, effects, error model, state, platform, version, or policy;
- comments/docstrings contradicting source;
- adversarial identifier and documentation search poisoning;
- clone boilerplate and generated code overwhelming unique logic;
- missing/stale graph edges and incomplete dynamic coverage;
- one rare decisive member hidden by a group centroid;
- cross-tenant, secret, license, and policy leakage attempts;
- LSH, fuzzy-hash, graph-hash, short-ID, and ANN collisions/misses;
- model/tokenizer/index upgrades and mixed-space corruption tests.

Code-retrieval evaluation should not rely on one benchmark. CodeSearchNet established a large multi-language corpus but its human relevance set is small relative to the corpus; [CoIR](https://arxiv.org/abs/2407.02883) broadens code-information-retrieval tasks, while [CoQuIR](https://arxiv.org/abs/2506.11066) explicitly separates relevance from code quality. Taedri needs its own compatibility, evidence, package-scale, route, and execution benchmarks in addition to these public references.

### 23.4 Real-world proof and promotion gate

Projected savings, invented workloads, synthetic provider receipts, and fabricated results must never be presented as real-world proof. Promotion tests use, where lawfully available:

- real released packages, source repositories, artifacts, and version incompatibilities;
- real package tests, builds, compiler or analyzer outputs, and execution environments;
- real user or production-derived demands with privacy and access controls;
- actual provider, model, or tool calls and provider-returned usage records;
- independent deterministic, test, domain, security, policy, or formal oracles;
- failure-inclusive costs per independently verified success.

For every representation, generator, model, preprocessor, blocking policy, index, fusion, selector, and disclosure policy, run individual-arm, cumulative-addition, leave-one-out, equal-candidate-budget, equal-latency-budget, frozen-candidate selector, frozen-selector retrieval, generator-by-generator, model-by-model, and description-source × embedding-model cross comparisons.

A variant earns a default or production role only when its measured marginal improvement repays storage, index-build, update, latency, compute, token, verification, error, and governance cost. Experimental variants may remain queryable without being promoted.

## 24. Design anti-patterns

- one universal code embedding;
- one summary field presented as truth;
- one closed list of labels, descriptions, edges, or models;
- fixed columns named after current embedding or hash providers;
- global source-code renaming to obtain uniqueness;
- missing value encoded as false, zero, empty, or an all-zero vector;
- unversioned canonicalization, preprocessing, tokenizer, prompt, model, seed, or index;
- comparing unrelated vector spaces or LSH configurations;
- using a fuzzy digest, vector score, or graph hash as equivalence proof;
- direction-normalizing relations without ontology permission;
- collapsing producer and consumer port semantics into one symmetric score;
- averaging all facets or all group members;
- flattening exact facts, generated claims, observations, and verified claims together;
- treating runtime observations as universal behavior;
- treating test coverage as correctness;
- all-pairs compatibility materialization;
- indexing unauthorized source before policy filtering;
- embedding raw secrets or sensitive runtime values;
- generated descriptions recursively used as evidence for themselves;
- destructive overwrite instead of append, supersession, and invalidation;
- benchmark optimization without hard negatives, execution, or independent verification;
- relying on an LLM to rediscover exact names, signatures, types, or graph paths already available deterministically.

## 25. Research and standards foundation

### Code identity, structure, and package facts

- [SCIP Code Intelligence Protocol](https://scip-code.org/)
- [Kythe schema reference](https://kythe.io/docs/schema/)
- [Python AST](https://docs.python.org/3/library/ast.html), [symbol tables](https://docs.python.org/3/library/symtable.html), [inspection](https://docs.python.org/3/library/inspect.html), [bytecode](https://docs.python.org/3/library/dis.html), and [data model](https://docs.python.org/3/reference/datamodel.html)
- [PyPA core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/)
- [Package URL](https://github.com/package-url/purl-spec) and [Software Heritage identifiers](https://docs.softwareheritage.org/devel/swh-model/persistent-identifiers.html)
- [SPDX 3.0.1](https://spdx.github.io/spdx-spec/v3.0.1/)

### Provenance, labels, and schemas

- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [W3C SKOS](https://www.w3.org/TR/skos-reference/)
- [JSON Schema 2020-12 validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation)
- [OpenTelemetry code semantic attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/code/)

SKOS’s distinction among preferred, alternate, and hidden labels is especially useful for public names, synonyms, misspellings, and retrieval-only aliases. OpenTelemetry’s separate code-function, namespace, file, line, column, and stack-trace attributes reinforce occurrence-level rather than prose-only observability.

### Sparse, fingerprints, sketches, and graphs

- [Winnowing](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf)
- [SimHash near-duplicate detection](https://research.google/pubs/detecting-near-duplicates-for-web-crawling/)
- [Weighted MinHash](https://research.google/pubs/improved-consistent-sampling-weighted-minhash-and-l1-sketching/)
- [SourcererCC](https://arxiv.org/abs/1512.06448)
- [TLSH](https://github.com/trendmicro/tlsh) and [ssdeep](https://ssdeep-project.github.io/ssdeep/index.html)
- [Weisfeiler–Lehman graph kernels](https://www.jmlr.org/papers/v12/shervashidze11a.html)
- [SPLADE v2](https://arxiv.org/abs/2109.10086)

### Learned code, text, and graph representations

- [CodeBERT](https://arxiv.org/abs/2002.08155)
- [GraphCodeBERT](https://arxiv.org/abs/2009.08366)
- [UniXcoder](https://arxiv.org/abs/2203.03850)
- [CodeT5+](https://arxiv.org/abs/2305.07922)
- [code2vec](https://arxiv.org/abs/1803.09473)
- [ColBERT](https://arxiv.org/abs/2004.12832)
- [Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147)
- [node2vec](https://arxiv.org/abs/1607.00653), [GraphSAGE](https://arxiv.org/abs/1706.02216), [TransE](https://proceedings.neurips.cc/paper_files/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html), and [RotatE](https://arxiv.org/abs/1902.10197)
- [Code Vectors from symbolic traces](https://arxiv.org/abs/1803.06686)

## 26. Final architecture recommendation

Implement `TaedriCodeGraph` around five open registries:

1. `SubjectKindRegistry` — every semantic, occurrence, runtime, relation, group, and route referent.
2. `DescriptorRegistry` — exact facts, text views, keywords, labels, schemas, contracts, behavior, history, trust, and policy.
3. `FingerprintRegistry` — canonical hashes, clone fingerprints, sketches, LSH families, graph/trace signatures, filters, and ANN-code projections.
4. `EmbeddingRegistry` — unbounded facet/view/model/role/vector-space projections.
5. `IndexRecipeRegistry` — exact, full-text, bitmap/range, constraint, LSH, ANN, graph, temporal, trace, and evidence indexes.

Then give every subject a `DescriptionPortfolio` and every portfolio a coverage ledger. The exact source graph remains authoritative; descriptions make it understandable; sparse features, fingerprints, and embeddings make it findable; typed ports and constraints make it composable; evidence and verification make it trustworthy.

The condensed operating rule is:

```text
exact identity and facts
  → cheap lexical, label, schema, history, and graph retrieval
  → fingerprint/LSH and selected embedding candidates
  → typed directional compatibility
  → evidence-aware ranking
  → post-selection body resolution
  → execution or independent verification
  → exact reusable receipt
```
