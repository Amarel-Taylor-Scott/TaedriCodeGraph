# Taedri CodeGraph

Taedri CodeGraph is a language-neutral code-knowledge and reusable-component database.
It ingests immutable snapshots from packages, Git repositories, and other codebases;
stores exact entities, relationships, evidence, and search representations; and can
also hold Taedri-authored primitives as complete, versioned, downloadable capsules.
Tools and agents can search, trace, verify, and reuse those records without rereading
an entire package or treating generated descriptions as truth.

This repository currently contains the first executable vertical slice:

- deterministic, canonical-CBOR-backed sidecar identities that retain their full
  identity keys;
- AST-only Python ingestion that does **not** import or execute target code;
- entities, exact source occurrences, n-ary relation assertions, evidence, coverage,
  extension assertions, descriptions, and structural fingerprints;
- immutable candidate epochs and atomic publication with rollback-friendly history;
- replaceable SQLite exact, FTS5, and forward/reverse adjacency projections;
- compact CLI operations for analysis, entity search/show, and edge search/neighbors.
- typed, unlimited representation variants that separate reusable content, subject
  assertions, generation attempts, and role-labeled lineage;
- explainable hybrid retrieval over exact, FTS5, facet, scalar, blocking/LSH, bounded
  vector, and graph lanes;
- a reusable versioned mechanism runtime plus API/MCP-accessible adaptive exact → sparse
  → semantic → structural search with capability, budget, escalation, and abstention
  receipts;
- verified local-wheel ingestion with declared license provenance and distribution/import
  namespace separation;
- registry-native primitive capsules with content-addressed trees, immutable revision
  DAGs, compare-and-swap branches, forks/merges, and selective thin downloads;
- a proof-carrying primitive release path: staged candidates remain private until a
  complete 12-role capsule passes executable examples, tests, provenance, license,
  graph, deduplication, queryability, separation-of-duty, and authorization checks;
- append-only release revocation that immediately removes a primitive from public
  search, resolution, and packs without deleting its audit history;
- an AST-only primitive factory that turns real functions and methods into candidate
  capsules, contracts, graph neighborhoods, and exact/lexical/blocking/LSH search data;
- append-only candidate intake, worker lease, and privacy-aware prompt-session ledgers
  that prevent generated code from self-promoting, with automatic lease heartbeat and
  cooperative cancellation receipts;
- a sealed matched-lane benchmark worker that compares bare-model, search-context,
  primitive-plan, and materialized-composition runs with failure-inclusive receipts;
- a persistent single-node SaaS control plane with tenants, hashed scoped API keys,
  graph mounts, append-only audit chains, content-addressed job payloads, leases,
  atomic tenant quotas, and immutable usage receipts;
- an authenticated HTTP search/context/graph/job API plus a source-mounted worker that
  can publish a new immutable epoch without importing or executing target Python;
- a live browser explorer and hardened API/worker/frontend container definitions;
- a separate public SaaS portal, versioned plan catalog, append-only subscription
  revisions, replay-safe billing-event contracts, and computed feature entitlements;
- one API/worker pipeline catalog plus allowlisted replay-safe PyPI/GitHub discovery
  events shared by admission and execution;
- a polyglot inventory adapter boundary plus optional MCP, Codex, and Claude harnesses.

The implementation deliberately separates canonical graph truth from disposable
search projections. Similarity can nominate candidates; it never proves that code
is compatible or safe to connect.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .

tcg analyze path ./src --store .tcg --publish
tcg search "extension registry" --store .tcg
tcg context "find an extension registry" --store .tcg
tcg edge search --predicate uceg.predicate.calls_may --store .tcg

# Generate real-source primitive candidates and the product console.
PYTHONPATH=src python tools/populate_primitive_candidates.py
python tools/generate_registry_console.py

# Generate the no-model benchmark-worker conformance evidence and console.
PYTHONPATH=src python tools/run_benchmark_worker_conformance.py
python tools/generate_benchmark_console.py

# Exercise a real Git-style custom primitive end to end.
PYTHONPATH=src python tools/run_reference_primitive_acceptance.py

# Validate one complete primitive without executing it.
tcg primitive validate examples/primitives/casefold-text

# Release, search, download, and compose two real primitives without an LLM.
PYTHONPATH=src python tools/run_deterministic_primitive_pipeline.py

# Regenerate the evidence-backed component/status/record inventory.
PYTHONPATH=src python tools/generate_component_inventory.py
```

## Runnable authenticated SaaS slice

The local cloud-shaped path uses one SQLite control database and local immutable graph
store. It is a real multi-process POC, not the horizontally scalable production
adapter.

```bash
# Create the tenant and print a scoped API token once.
tcg admin bootstrap \
  --control .tcg/control.sqlite \
  --tenant demo \
  --name "Demo" \
  --graph-store "$(pwd)/.tcg/tenant-demo"

# Terminal 1: authenticated API.
tcg serve --control .tcg/control.sqlite --cors-origin http://localhost:8080

# Terminal 2: persistent source-analysis worker.
tcg worker run --control .tcg/control.sqlite --source-root "$(dirname "$(pwd)")"

# Or build the API, worker, explorer, and portal containers.
docker compose up --build
```

Open `http://localhost:8080`, enter the one-time token, submit a relative source path,
and search the epoch after the worker succeeds. Open `http://localhost:8081` for the
public plan and tenant-entitlement portal. API contracts are published at
`/openapi.json`. See
[`docs/architecture/AUTHENTICATED_SAAS_VERTICAL_SLICE.md`](docs/architecture/AUTHENTICATED_SAAS_VERTICAL_SLICE.md)
for the trust boundary and Fly.io promotion gates, and the
[`validation report`](docs/reports/AUTHENTICATED_SAAS_VERTICAL_SLICE_2026-07-16.md)
for the executed test and HTTP evidence.

The ordered production program and least-privilege environment matrix are in the
[`component execution plan`](docs/architecture/COMPONENT_EXECUTION_PLAN.md). Current
claims and open gates are machine-readable in
[`component-readiness.v1.json`](architecture/component-readiness.v1.json). The latest
[`working-system checkpoint`](docs/reports/WORKING_SYSTEM_CHECKPOINT_2026-07-16.md)
records its earlier 175-test acceptance pass, production-socket smoke, database contract,
non-synthetic evidence, readiness chart, and remaining external gates.

The current mechanism/storage/search/trigger/portal/worker design is consolidated in
[`PRIMITIVE_PLATFORM_WATERFALLS.md`](docs/architecture/PRIMITIVE_PLATFORM_WATERFALLS.md),
with its machine-readable seven-waterfall contract in
[`primitive-platform-waterfalls.v1.json`](architecture/primitive-platform-waterfalls.v1.json).
It includes the regression that proved new license, integer, character, and vector
facets can receive their declared projections without a ledger migration.
The latest
[`primitive-platform acceptance report`](docs/reports/PRIMITIVE_PLATFORM_WATERFALLS_2026-07-16.md)
records the full current acceptance pass. The current contract has 41 API operations across
37 paths and 44 PostgreSQL tables, including proof-gated releases and revocations; the
report also links the installable wheel, component inventory, CSV/JSON evidence, and
explicit hosted gates.

No third-party runtime dependency is required for the graph core. Install
`taedri-codegraph[agents]` for the optional MCP server. The supported baseline is
Python 3.12.

## Verify

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

## Architectural invariants

1. Source-native names never change; uniqueness lives in sidecar identities.
2. Every exact ID is checked against its stored canonical identity key.
3. Every graph claim is scoped and provenance-bearing.
4. Missing and unknown never mean false, compatible, or wildcard.
5. Extensions are additive, namespaced, versioned, and independently governed.
6. Candidate compatibility is not canonical graph adjacency.
7. Build or runtime execution is always a separate, explicit, receipt-producing step.
8. Published epochs are immutable; indexes can be rebuilt from their manifests.
9. Sealed evaluation tasks, hidden tests, gold outputs, and answer-derived features
   never feed production retrieval, embeddings, primitive generation, or training.
10. A candidate is never a public primitive. Search, resolution, and download serve
    only an active release backed by a complete capsule and immutable acceptance proof.

See [docs/spec/FIRST_VERTICAL_SLICE.md](docs/spec/FIRST_VERTICAL_SLICE.md) for the
implemented boundary and the next gates.

## Real-package benchmark

The current slice has completed atomic end-to-end publication for real installed
Wheel 0.47.0, Packaging 26.2, and Pydantic 2.13.4 distributions. The largest run
accounted for all 105 Pydantic Python files and produced 20,616 entities, 59,423
occurrences, and 123,342 evidence-bearing relations without importing package code.

![UCEG record counts on real PyPI distributions](docs/reports/assets/real-pypi/real_pypi_record_counts.svg)

Read the [full real-PyPI benchmark report](docs/reports/REAL_PYPI_BENCHMARK_2026-07-15.md)
or inspect the [raw CSV and JSON results](eval/results/real-pypi-2026-07-15/).

The follow-up [architecture challenge](docs/architecture/UNIVERSAL_REPRESENTATION_ARCHITECTURE.md)
tests unlimited typed/provenanced variants, verified wheels, polyglot inventory, hybrid
retrieval, provider/router contracts, and agent harnesses. Its
[real-package report](docs/reports/HYBRID_ARCHITECTURE_CHALLENGE_2026-07-15.md) retains
both successful and failed retrieval cases with raw query receipts.

## Description atlas and architecture explorer

The [18,608-word Code Entity Description Atlas](docs/spec/TAEDRI_CODE_ENTITY_DESCRIPTION_ATLAS.md)
is now part of the repository. Its implementation direction uses typed long tables,
content-addressed payloads, immutable production attempts, assertion and lineage rows,
explicit materialization states, and role-scoped views—not an ever-widening entity
table.

The executable follow-up adds subject-local adaptive enrichment and overlapping
narrow/medium/wide SimHash and MinHash LSH families. A useful helper can earn deeper
descriptions independently of its parent package's stated purpose.

[Open the architecture and monorepo decision](docs/architecture/ADAPTIVE_PORTFOLIO_MONOREPO.md)
or browse the [interactive and static visual atlas](docs/visuals/README.md). The
[validation report](docs/reports/ADAPTIVE_PORTFOLIO_VISUAL_VALIDATION_2026-07-16.md)
includes the real-usaddress LSH smoke test and its intentionally retained collision
finding.

![Typed long-table representation spine](docs/visuals/assets/typed-long-table-model.svg)

![Adaptive enrichment depth](docs/visuals/assets/adaptive-enrichment-depth.svg)

## Primitive registry and deployment evolution

Taedri-generated primitives do not need one repository or PyPI distribution each. The
default is a candidate capsule containing digest-bound source/runtime content, contract,
tests or verifiers, graph deltas, and provenance. Mature groups can later be exported as
normal Git repositories, OCI artifacts, or ecosystem packages when those collaboration
and distribution boundaries are useful.

The executable POC implements immutable revisions, optimistic branch updates, immutable
tags, cross-namespace forks, merges, role-selective packs, cached-blob omission, and
append-only revocation. Two repository-native primitives contain executable source,
contract, descriptor, examples, test vectors, verifier policy, evidence-backed interface
graphs, documentation, runtime locks, license evidence, and source provenance. They remain
hidden while staged, then pass real local execution before release, search, and download.
The checked-in exact route trims text and applies Unicode case folding by materializing
and executing both packs without a model call, generated code, or rewritten primitive
bytes. Read the
the [primitive truth and release policy](docs/architecture/PRIMITIVE_TRUTH_RELEASE_AND_LANGUAGE_SCOPE.md),
the [one-at-a-time authoring guide](docs/guides/PRIMITIVE_AUTHORING.md),
the [reuse proof status](docs/reports/PRIMITIVE_REUSE_PROOF_STATUS_2026-07-16.md),
the [component inventory](docs/reports/COMPONENT_CAPABILITY_INVENTORY_2026-07-16.md), or
browse the [interactive inventory](docs/visuals/component-capability-inventory.html).
Also read
the [primitive registry and staged deployment decision](docs/architecture/PRIMITIVE_CAPSULE_REGISTRY_AND_DEPLOYMENT.md)
or inspect the machine-readable [deployment topology](deploy/topology.v1.json). The
[validation report](docs/reports/PRIMITIVE_CAPSULE_VALIDATION_2026-07-16.md) links the
real-source capsule receipt and downloadable pack.

## Primitive factory, product console, and business model

The next vertical slice runs the primitive factory over Taedri's own implementation. It
produced 347 real-source function/method candidates, 1,812 syntax-derived call edges,
1,388 append-only intake events, two successful leased worker jobs, and a digest-only
coding-harness trace. No model or verifier was configured, so the sample session
abstained; all 347 records remain candidate-only and zero were released.

![Real-source primitive candidate distribution](docs/visuals/assets/primitive-candidate-kinds.svg)

![Taedri product and operating model](docs/visuals/assets/product-operating-model.svg)

Read the [business model and product vertical-slice decision](docs/product/BUSINESS_MODEL_AND_PRODUCT_VERTICAL_SLICE.md),
inspect the [validation report](docs/reports/PRIMITIVE_FACTORY_PRODUCT_SLICE_2026-07-16.md),
or open the [interactive registry console](apps/explorer/registry-console.html). Raw
CSV, JSONL, GraphML, Mermaid, pack, receipt, and console data live in
[`eval/results/primitive-factory-2026-07-16`](eval/results/primitive-factory-2026-07-16/).

The commercial hypothesis is a private capability registry plus coding-harness wedge,
followed by team subscription, metered managed verification, and enterprise deployment.
The governing value unit is an independently accepted, policy-compliant outcome.
Currency prices and ROI claims remain unset pending customer, cost, quality, and
retention evidence; the current absence of a project license also blocks describing a
community tier as open source.

## SaaS benchmark worker

Taedri now has an executable controller for testing the product hypothesis at fixed
model quality. It defines identical real coding tasks across bare-model,
search-context, primitive-plan, and primitive-materialized lanes and validates supplied
failure-inclusive receipts containing build/test/policy outcomes, provider and tool
usage, tokens, latency, cost, component reuse, consistency, and contamination strata.
The current conformance run does not yet execute model providers or a hostile-code
sandbox; those remain required before an efficacy claim.

![Matched benchmark worker and sealed evidence boundary](docs/visuals/assets/benchmark-worker-evidence-boundary.svg)

Read the [architecture and real campaign design](docs/architecture/SAAS_BENCHMARK_WORKER.md),
inspect the [POC report](docs/reports/SAAS_BENCHMARK_WORKER_POC_2026-07-16.md), or open
the [benchmark evidence console](apps/explorer/benchmark-console.html). The checked-in
16-run bundle uses two real Taedri source tasks and real primitive/search snapshot
identities, but deterministic fixture receipts and no model call. Its report therefore
sets `efficacy_claimable` to `false`; it validates the worker, not the SaaS benefit.

## Project status

Pre-alpha. The current slice proves the identity/evidence/ingestion/publication/query
spine, the universal representation extension mechanism, real-source primitive
candidate generation, a complete Git-hostable custom primitive, proof-gated Python
release and revocation, append-only operational receipts, and self-contained frontends.
Inventory and exact graph storage are language-neutral; semantic extraction and
executable release verification are Python-first. Remote PyPI/Git acquisition for the
factory, semantic analyzers and trusted release verifiers for additional languages,
PostgreSQL repository and object-store adapters, real model and embedding providers,
OIDC browser sessions, independent sandbox verification, calibrated fusion, a live
billing-provider adapter, and broad compatibility/adapter/branching routing remain
explicit later milestones. Exact adapter-free unary Python wiring is implemented.
Tenant authorization and a
persistent HTTP/worker path now execute with the single-node SQLite adapter.

No project license has been selected yet; all rights are reserved until one is added.
