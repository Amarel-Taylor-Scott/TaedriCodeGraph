# Primitive truth, release, curation, and language scope

Status: implemented local/transitional decision, 2026-07-16

## Decision

Taedri stores code knowledge and serves reusable primitives, but those are different
truth classes. A source fragment, descriptor, embedding, candidate, or curated review
record is never a working primitive. Public primitive search, resolution, and pack
delivery read only the append-only `primitive_release` relation.

A release binds one immutable revision to its complete capsule, source digest,
runtime, exact contract, executable examples and tests, oracle, license evidence,
provenance, acceptance receipt, policy decision, and authorizer. Search projections
can be rebuilt; this release fact cannot be inferred from similarity or a label.

## Truth states

| State | Meaning | Public primitive APIs | How it advances |
|---|---|---:|---|
| `received` | Immutable intake record exists | No | Safe intake |
| `quarantined` | Content is retained but untrusted | No | Static validation |
| `structurally_valid` | Schemas and digests parse | No | Candidate projection |
| `indexed_candidate` | Candidate-only search data exists | No | Human/policy curation |
| `curated_candidate` | A reviewer considers it worth completing | No | Build a complete capsule and run release verification |
| `released` | Complete capsule passed executable acceptance and authorization | Yes | New immutable release record |
| `rejected` / `revoked` | Candidate or release must not serve | No | Append-only decision and projection invalidation |

Candidate pack download remains available to authorized reviewers by revision ID. It
is intentionally a different endpoint from released primitive pack delivery.

## Complete capsule contract

Every released primitive contains all of these roles. Multiple source or documentation
files are permitted; the remaining machine-readable records are singular in v1.

| Role | Release requirement |
|---|---|
| `source` | Real implementation or explicit upstream adapter body |
| `contract` | Typed inputs/output plus explicit errors and effects |
| `descriptor` | Substantive summary, keywords, use cases, and limitations |
| `runtime` | Language, pinned runtime version, source entrypoint, dependency-lock digest, and network policy |
| `dependency_lock` | Digest-bound dependency closure or explicit no-dependency lock |
| `example` | Positive, boundary, and negative executable vectors |
| `test` | Additional executable vectors |
| `verifier` | Oracle producer and exact comparison policy |
| `license` | Verified state, SPDX expression, and evidence digest |
| `provenance` | Source URI, immutable source revision/digest, and implementation producer |
| `graph_delta` | Evidence-bound implementation/contract/example/test/runtime relations, typed contract ports, compatibility dimensions, and a capability group |
| `documentation` | Human-usable implementation guidance |

The release worker downloads the same pack a client receives, materializes it with the
client digester, executes every example and test under a bounded runtime, checks exact
values or exception classes, stores an immutable acceptance receipt, checks duplicate
source bodies, authorizes the release, proves it is searchable, and only then inserts
`primitive_release`. A separate append-only revocation record removes a release from
search, resolution, and pack delivery without deleting its history.

## Practical curation now; stronger operations at scale

The functional definition of a release does not weaken when the registry is small.
What changes with scale is separation and operating cost:

| Assurance | Intended phase | Functional proofs | Required identity separation |
|---|---|---:|---|
| `bootstrap` | Founder/local development | All 14 proof kinds | Same team identities permitted and recorded |
| `standard` | Shared/team registry | All 14 proof kinds | Verifier, oracle, and authorizer independent of implementation producer |
| `high_assurance` | Sensitive or large public registry | All 14 proof kinds | Implementation, oracle, verifier, and authorizer all distinct |

Early operation can therefore use one explicit command and a trusted-source local
worker without a multi-person queue. It still cannot release a two-file description,
skip execution, hide an unknown license, or expose a duplicate body under thousands of
names. At scale, policy selects higher assurance, sampling, isolated worker pools,
reputation, re-verification, revocation, and prioritized enrichment.

## Language and source scope

The graph identity, occurrence, relation, representation, provenance, and capsule
models are language-neutral. Acquisition source and analysis depth are separate:

| Source/runtime | Acquisition and exact inventory | Semantic depth today | Executable primitive release today |
|---|---|---|---|
| PyPI wheel | Working, verified wheel and distribution/import separation | Python AST working | Python 3.12 trusted-source verifier working |
| GitHub immutable commit archive | Working | Python AST or language-neutral file inventory | Python 3.12 when a complete capsule selects a Python entrypoint |
| Local/custom Git directory | Working | Python AST or language-neutral file inventory | Python 3.12 reference capsule working |
| Other languages in any codebase | Working file/language/artifact inventory | Adapter boundary exists; SCIP/Tree-sitter/CPG importers are not yet claimed | Fails closed until a real verifier is registered for that runtime |

`PrimitiveVerifierRegistry` dispatches by the exact runtime language in the capsule.
Adding JavaScript, Rust, Java, Go, or another runtime means implementing and testing a
new verifier; it does not require widening the release table or weakening the common
capsule contract.

Custom Taedri primitives may live in this monorepo, another Git repository, or an
upstream package. Git remains the collaboration surface for review, branching, and
authorship. The Taedri registry is the serving surface for immutable trees, typed
edges, evidence, search, selective packs, and tenant policy. Mature groups may also be
exported to PyPI, npm, Cargo, Go modules, or OCI; one repository/package per function
is neither required nor desirable.

## Standards alignment and resulting choices

- The [OCI Distribution Specification](https://specs.opencontainers.org/distribution-spec/)
  separates digest-addressed blobs/manifests from mutable human-readable tags and
  supports subject/referrer relationships. Taedri similarly separates immutable trees
  and revisions from CAS-updated branches and attaches release evidence by digest.
- [SLSA 1.1 artifact verification](https://slsa.dev/spec/v1.1/verifying-artifacts)
  requires matching artifact subjects, trusted builder identity, signatures, build
  type, and external parameters. Taedri now binds acceptance to tree/source/runtime
  identity; signed provenance and roots of trust remain an explicit production gate.
- [PyPI's Integrity API](https://docs.pypi.org/api/integrity/) exposes PEP 740
  provenance and attestations per distribution file. The PyPI worker should ingest and
  verify those attestations when present; absence remains explicit.
- [SPDX](https://spdx.dev/use/specifications/) provides standardized license
  expressions. A declared package classifier is evidence, not verification; a release
  requires an evidence digest and an explicit verified state.
- [W3C PROV-O](https://www.w3.org/TR/prov-o/) models entities, activities, agents,
  derivation, revision, and qualified responsibility. Taedri's content, generation,
  assertion, evidence, and lineage rows preserve those distinctions instead of
  overwriting one canonical value.
- [SCIP](https://scip-code.org/) demonstrates a language-agnostic index format with
  indexers across major languages. Taedri keeps an adapter boundary for SCIP facts
  while retaining richer evidence, runtime, representation, and release relations.
- GitHub recommends validating the `X-Hub-Signature-256` HMAC before processing a
  [webhook delivery](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
  Hosted discovery remains partial until that ingress and replay store are deployed.

## Implemented evidence

The reference primitive at `examples/primitives/normalize-text` is not a mock row. The
checked-in acceptance bundle proves that it was invisible before release, materialized,
executed against six cases, released under standard assurance, searched, and downloaded
as a 13-payload pack. See
`eval/results/reference-primitive-acceptance-2026-07-16`.

The second complete primitive at `examples/primitives/casefold-text` is independently
released in the deterministic composition run. That run searches for both releases,
checks 12 evidence-bound edges and four typed ports, builds one exact adapter-free wire,
downloads both packs, and executes `"  Straße  " → "strasse"` with zero model calls or
rewritten primitive bytes. See
`eval/results/deterministic-primitive-pipeline-2026-07-16`.

The 347 factory outputs remain `indexed_candidate` records with zero releases. This is
intentional: static extraction found potentially reusable code, but did not invent
tests, runtime locks, license verification, or behavioral truth.

## Explicit next gates

The local Python worker is a real trusted-source acceptance worker, not a hostile-code
security boundary. Before arbitrary customer code can execute, deployment needs an
isolated, disposable runtime with read-only inputs, blocked network, CPU/memory/process/
filesystem limits, independent oracle credentials, signed receipts, and no access to
the production control plane. Non-Python verifiers, PostgreSQL repository conformance,
signed packs, and PyPI integrity attestations are also named gates; none are
advertised as working today.
