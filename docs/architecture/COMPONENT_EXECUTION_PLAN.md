# Component execution plan

This is the delivery plan for moving Taedri CodeGraph from its executable local
vertical slice to a claimable multi-tenant SaaS. “100%” means every declared gate has
machine-verifiable evidence in its target environment. It does not mean relabeling a
local adapter as production or treating a configured external service as a successful
test.

The machine-readable source of current truth is
`architecture/component-readiness.v1.json`. A component may be working in a declared
local scope while still having production promotion gates.

## Ordered delivery waves

1. **Truthful local platform.** Identity, ingestion, registries, storage, retrieval,
   APIs, workers, sessions, metering, UI, backups, and real-package evidence run with
   no hidden service dependencies.
2. **Managed staging data plane.** PostgreSQL repositories, S3-compatible immutable
   objects, a production HTTP server, migrations, observability, backup/restore, and
   Fly or equivalent deployment pass destructive staging drills.
3. **Real-model efficacy.** One fixed model and harness run sealed non-synthetic tasks
   through matched bare/search/plan/materialized lanes. An isolated verifier retains
   all failures and reports uncertainty; only then can speed, token, quality, or cost
   benefits be claimed.
4. **Identity and commercial operations.** OIDC organizations/roles, tenant admin,
   entitlement policy, invoice export/reconciliation, support tooling, and privacy
   controls pass end-to-end tests.
5. **Scale and enterprise promotion.** Load/SLO gates, resource-isolated workers,
   signed primitive packs, private source adapters, disaster recovery, security review,
   and upgrade/rollback exercises pass before general availability.

## Component-by-component gates

| Component | Executable scope now | Next completion gate | External dependency for that gate |
|---|---|---|---|
| Vertical slice | Local modular monolith | Replay the same identities through production adapters | PostgreSQL and object-store staging |
| Shared kernel | Canonical identities/contracts in the Python package | Extract and compatibility-test a separately versioned package | None |
| Shared schemas | Core JSON Schema contracts | Export every public record and add cross-version fixtures/drift generation | None |
| Schema artifacts | JSON Schema plus PostgreSQL DDL | Add Arrow/Parquet contracts and run migrations on real PostgreSQL | Disposable PostgreSQL |
| Primitive capsules | Durable tenant registry, revisions, refs, forks, thin packs | Signed packs and production metadata/blob adapters | Signing key in KMS; PostgreSQL/S3 |
| Primitive factory | AST-only Python candidates | Isolated behavioral verification and non-Python factories | Sandbox; optional models/analyzers |
| PyPI ingestion | Exact verified public wheels | Private-index policy and supply-chain attestations | Optional private-index read token |
| Git ingestion | Exact public GitHub commit archives | Submodule/LFS policy, private repository test, more Git hosts | Scoped GitHub App installation |
| Python analyzer | Static entities/relations with poison tests | Larger poison corpus and optional types/runtime evidence | Optional isolated runtime |
| Polyglot analyzer | Language-neutral file inventory | SCIP importer and semantic Tree-sitter/CPG adapters | None for public fixtures |
| Storage | Immutable local CAS, epochs, backup/restore, S3 conformance fake | Live S3 test and disaster-recovery drill | Staging bucket and scoped credentials |
| Retrieval | Exact/FTS/facet/LSH/vector/graph lanes | Real embeddings, ANN adapter, relevance/load promotion gates | Embedding endpoint; staging ANN if chosen |
| Compatibility | Directional exact evaluator | Persist signatures, block candidates, produce adapter witnesses and route plans | None initially |
| Session ledger | Durable private prompt/tool evidence with automatic digest-only MCP search receipts | OIDC harness identities and encrypted-capture operations | OIDC staging application |
| Benchmarking | Matched-lane and Ollama protocol conformance | Live model, sealed task suite, isolated verifier | Ollama/model endpoint and sandbox |
| SaaS control plane | Tenants, scoped keys, jobs, audit, quotas, usage receipts | PostgreSQL repositories, OIDC organizations, invoice reconciliation | PostgreSQL, OIDC, billing sandbox |
| Worker runtime | Durable claims, retries, heartbeats, cancellation | Resource isolation and concurrent PostgreSQL claim tests | Container/sandbox runtime; PostgreSQL |
| Benchmark worker | Deterministic non-claimable campaign | Execute matched real-model lanes and independent verification | Model endpoint and sandbox |
| Indexer service | Local source/acquisition jobs | Dependency invalidation scheduler and distributed concurrency | PostgreSQL/object store staging |
| Query API | Authenticated API with tenant admission, epoch-bound search cursors, and Gunicorn boundary | Distributed traces, remaining collection cursors, multi-tenant SLO | Staging environment and telemetry sink |
| Registry API | Publish/resolve/fork/candidate review | Reviewed merge operation, signed packs, OIDC reviewer roles | OIDC and signing KMS |
| MCP integration | Protocol-tested local/remote stdio tools with optional session receipts | Hosted harness evaluation and OIDC identity | MCP-capable test harness/model |
| Agent integrations | Instructions and local search skill | Installable plugin/hooks and hosted harness evaluation | Target harness environments |
| Explorer | Static authenticated operations console | OIDC sign-in, tenant admin, graph/provenance visualization, browser E2E | OIDC and deployed staging API |
| Deployment | Hardened containers, Compose, Fly POC manifests, CI definition | Green hosted CI, Fly smoke, managed stores, restore/incident drill | GitHub Actions, Fly, PostgreSQL, S3 |
| Evaluation | Real-package static evidence and deterministic benchmark fixtures | Sealed executable tasks, real-model lanes, longitudinal thresholds | Model, sandbox, repeatable hosted runners |

## Minimum access matrix

Secrets must be installed in a secret manager, GitHub environment, or scoped runtime
environment. They must never be pasted into chat, committed, included in receipts, or
placed in a frontend bundle.

| Access | Why it helps | Minimum useful scope | Needed now? |
|---|---|---|---|
| GitHub publishing session | Commit/push this tested branch and run the existing draft PR | This repository only; contents write, pull-request write, Actions read | Yes for publication/hosted CI |
| Public PyPI | Acquire exact wheels and metadata | No credential | Already working |
| Public GitHub source | Acquire immutable public commit archives | No credential unless rate limits become material | Already working |
| Private GitHub App | Test private repositories without a personal token | Contents read on one disposable fixture repository | Later staging gate |
| Ollama | Run real matched model lanes | Reachable base URL and exact model name; optional bearer only for a protected proxy | Yes for efficacy work |
| Embedding provider | Produce real semantic variants | One staging endpoint/model and least-privilege key | Yes for semantic promotion |
| PostgreSQL | Exercise production repositories and concurrent claims | Disposable database owner for migrations, restricted runtime role afterward | Yes for cloud promotion |
| S3-compatible store | Exercise immutable objects and recovery | One staging bucket/prefix with read/write/list only | Yes for cloud promotion |
| Fly.io or equivalent | Run staging smoke and rollback | One staging app/org deploy token, not account-wide production access | Yes for hosted promotion |
| OIDC provider | Test browser and harness identity/roles | One staging client, redirect URIs, issuer/audience; secret only if confidential client | Yes for multi-user SaaS |
| Billing sandbox | Reconcile usage receipts to invoices/credits | Test-mode restricted key and webhook secret | Later commercial gate |
| Telemetry backend | Validate traces, metrics, alerts, and retention | Staging ingest endpoint/key only | Later operations gate |
| Isolated verifier | Execute untrusted generated code and hidden tests | Ephemeral network-denied runner with CPU/memory/time limits | Yes for claimable benchmarks |

Ollama itself is normally a server URL plus a model name, not an API-key service. A
key is useful only when an authenticated gateway protects the server. More keys do not
improve architecture quality; they unlock live integration evidence after deterministic
contracts pass.

## Promotion protocol

For each row, implementation follows the same sequence:

1. freeze the public contract and threat boundary;
2. implement the smallest durable adapter;
3. add unit, failure, restart, isolation, and idempotency tests;
4. run a non-synthetic fixture and retain raw receipts;
5. run the target-environment acceptance command;
6. update readiness only after evidence exists;
7. publish through a draft PR and require hosted gates before promotion.

A missing credential, unavailable cloud environment, absent licensing decision, or
unselected provider is a visible blocked gate—not permission to weaken the test or
invent a successful result.
