# Taedri component and capability inventory

As of 2026-07-16. This inventory contains all 32 declared components.

## Launch truth

**private alpha candidate; not a production SaaS launch.** `serves_truth=false` and `public_paid_saas_ready=false`. Public multi-tenant production operation, managed PostgreSQL/object-store runtime use, hostile-code isolation, OIDC/RBAC, live billing and webhook reconciliation, production observability, full-service backup/restore, retention operations, and staged deploy/rollback.

**Count rule:** no production database is committed to Git. Every numeric count below names its immutable evaluation source; stateless components and missing hosted evidence are stated explicitly.

| Component | Folder | Status | Measured records / evidence | Core capabilities |
|---|---|---|---|---|
| `vertical-slice` | `src/taedri_codegraph` | **working** | Real PyPI evidence: 25,347 entities; 74,327 occurrences; 153,909 relations | current executable implementation while packages are extracted |
| `mechanism-runtime` | `src/taedri_codegraph/mechanisms` | **working** | Stateless executor; immutable waterfall receipts are caller-owned | versioned mechanism registry; budgeted waterfall execution; attempt and abstention receipts |
| `pipeline-catalog` | `src/taedri_codegraph/pipelines` | **working** | 4 executable pipelines; 6 admitted worker operations | ingestion and generation pipeline definitions; operation admission contracts; source-discovery event routing |
| `shared-kernel` | `packages/shared-kernel` | **working** | N/A — stateless identity/canonicalization library | identity; canonical encoding; typed envelopes; provenance primitives |
| `shared-schemas` | `packages/shared-schemas` | **partial** | 19 checked-in JSON Schemas | descriptor schemas; predicate schemas; registry manifests; conformance fixtures |
| `schema-artifacts` | `schemas` | **partial** | 19 JSON Schemas; 44 PostgreSQL tables | exported JSON Schema; PostgreSQL DDL; schema acceptance checks |
| `primitive-capsules` | `packages/primitive-registry` | **working** | Data cohort: 13 public releases / 129 blobs / 13 downloadable packs | primitive handles; content trees; revision DAGs; refs; thin pack contracts; proof-gated releases; evidence-backed interface graphs; strict complete-capsule authoring compiler |
| `primitive-factory` | `packages/primitive-factory` | **working** | 347 real-source candidates; 1,388 intake events; 0 released by factory | source-backed primitive candidate extraction; candidate contracts; search descriptors; candidate graph neighborhoods |
| `ingestion-pypi` | `packages/ingestion-pypi` | **working** | 4 real wheels evidenced (3 benchmark + usaddress); latest usaddress mount: 101 entities / 614 relations | PyPI acquisition receipts; wheel verification; distribution metadata |
| `ingestion-git` | `packages/ingestion-git` | **working** | 1 immutable real GitHub commit archive; 417 entities / 2,282 relations | Git object acquisition; commit and tree lineage; repository policy |
| `analyzer-python` | `packages/analyzer-python` | **working** | Real PyPI evidence: 25,347 entities / 153,909 relations across 140 files | Python syntax and semantic extraction; Python conformance corpus |
| `analyzer-polyglot` | `packages/analyzer-polyglot` | **partial** | No dedicated durable rows; working file-inventory boundary, semantic adapters not claimed | language-neutral file inventory; polyglot analyzer adapter boundary |
| `storage` | `packages/storage` | **working** | 5 real published evaluation epochs; usaddress runs: 518 entities / 9,961 typed variants | canonical ledger adapters; CAS; typed long tables; projection epochs |
| `retrieval` | `packages/retrieval` | **working** | 36 retained real-package hybrid query receipts; primitive-card program: 31 deterministic cases / 26/26 positive rank-1 hits / 5/5 unsupported abstentions / 83→34 returned candidates | query planning; sparse and LSH retrieval; bounded vector scoring; fusion receipts; versioned cost-budgeted primitive retrieval programs; representation lifecycle and path receipts |
| `compatibility` | `packages/compatibility` | **partial** | Data cohort: 78 evidence edges / 26 typed ports / 31 blocked exact compatibility edges / 4 executed routes | typed compatibility dimensions; directional exact evaluation; unknown and poison policy; exact port matching; adapter-free unary pipeline plans and receipts |
| `session-ledger` | `packages/session-ledger` | **working** | Reference factory evidence: 1 digest-only session / 7 events / 0 model calls | prompt privacy modes; harness session events; acceptance and abstention receipts |
| `benchmarking` | `packages/benchmarking` | **partial** | 16 deterministic worker-conformance receipts plus 1 primitive retrieval program benchmark / 31 cases; 13 checked live campaign documents (7 strict v2; 6 legacy non-claimable v1); 192 provider-call attempts / 96 matched-pair observations / 346 case-execution observations; strict-v2 usage-complete observation 50,369→20,248 across 50 pairs; legacy-v1 observation 39,415→15,611 across 39 pairs; claimable_token_savings=false | deterministic capability, privacy, cost, and latency model-arm routing; bounded Ollama, Mistral, OpenRouter, and OpenAI-compatible provider adapters; matched-lane experiments; sealed-task reference contracts; run receipts; contamination strata; paired metrics; body-free primitive prompt interception and checked execution; campaign-v2 task manifests, exact arm matrices, and occurrence-bound verification receipts; trusted-evidence interfaces and fail-closed token claim evaluation; deterministic primitive retrieval benchmarks |
| `saas-control-plane` | `packages/saas-control-plane` | **working** | Real acquisition evidence: 1 tenant / 2 succeeded jobs / 4 audit events | tenant identity; scoped API keys; graph mounts; audit chains; persistent job payloads and leases; quota policy and immutable usage receipts |
| `worker-runtime` | `services/worker-runtime` | **working** | Real acquisition evidence: 2 leased and succeeded network jobs | idempotent jobs; capability-aware leases; lease heartbeats and cooperative cancellation; attempt receipts; retry and dead-letter policy |
| `benchmark-worker` | `services/benchmark-worker` | **conformance_only** | 16 deterministic fixture receipts; 0 live campaigns executed by the durable worker service | matched run scheduling; lane disclosure enforcement; terminal receipt validation; contamination strata; claim eligibility comparison |
| `discovery-worker` | `services/discovery-worker` | **partial** | 0 hosted poll/webhook rows; replay-safe local router is tested | allowlisted discovery event contracts; replay-safe discovery-to-job routing |
| `ingestion-worker` | `services/ingestion-worker` | **working** | 2 real acquisition jobs; 518 entities / 2,896 relations published | bounded remote acquisition; safe extraction; atomic graph publication; acquisition receipts |
| `primitive-worker` | `services/primitive-worker` | **working** | 347 candidates plus 13 locally acceptance-verified released primitives | source-backed candidate generation; candidate provenance; candidate curation; complete-capsule release verification; one-at-a-time primitive validation and release; curated reusable data-primitive generation |
| `indexer-service` | `services/indexer` | **working** | 5 real evaluation epochs (3 PyPI benchmark + 2 usaddress acquisition) | local ingestion orchestration; atomic publication; rebuildable projection builds |
| `query-api` | `services/query-api` | **working** | 41 operations across 37 paths | authenticated graph and primitive search; context disclosure; tenant quota admission; usage and provenance responses |
| `registry-api` | `services/registry-api` | **working** | Data cohort: 13 public releases; 0 candidate rows serving as primitives | candidate intake and curation; staged branch and tag mutations; fork commands; proof-gated release search and pack delivery |
| `mcp-integration` | `integrations/mcp` | **working** | Protocol and remote round-trip evidence; no durable MCP-owned rows | MCP tool and resource contracts; bounded context adapters |
| `agent-integrations` | `integrations/agents` | **partial** | 1 digest-only harness session; 0 model calls; no efficacy claim | Codex and Claude instructions; local search skill; harness policy guidance |
| `explorer-app` | `apps/explorer` | **working** | Static application; records are read from authenticated APIs | authenticated browser console; search and record inspection UI |
| `portal-app` | `apps/portal` | **working** | Static application + versioned plan/subscription contracts; no checked-in customer rows | public plan catalog; tenant subscription and entitlement view; provider redirect initiation |
| `deployment` | `deploy` | **poc_only** | 44 PostgreSQL tables; Docker/Compose and one-Machine Fly POC | local containers; PostgreSQL migrations; single-Machine Fly.io POC; deployment policy |
| `evaluation` | `eval` | **partial** | 3 real PyPI packages + 2 real usaddress sources + 13 real custom releases + 4 no-model routes + 31 primitive retrieval cases + 9 constructed tasks/18 cases + 5 external issue-derived positive tasks/10 cases + 13 checked live campaign documents (7 strict v2; 6 legacy non-claimable v1); 192 provider-call attempts / 96 matched-pair observations / 346 case-execution observations; strict-v2 usage-complete observation 50,369→20,248 across 50 pairs; legacy-v1 observation 39,415→15,611 across 39 pairs; claimable_token_savings=false | real-package corpora; ablation receipts; promotion gates; deterministic primitive-composition receipts; bounded live-provider primitive-selection observations; strict campaign-v2 integrity summaries; external issue-derived positive retrieval workload; versioned primitive retrieval program receipts; token-savings proof classification; reports |

## What the statuses mean

- **working:** the stated local/transitional scope has executable acceptance evidence.
- **partial:** the narrow stated scope works; broader capabilities remain named gates and are not advertised as implemented.
- **conformance_only:** contracts and deterministic receipts work, but there is no claimable external execution.
- **poc_only:** the bounded proof works but lacks production durability or hosted operations.

## Primitive truth boundary

The factory's candidate rows are not primitive releases. Public primitive search, resolution, and pack delivery read only `primitive_release`, whose rows require the complete capsule and all executable acceptance proofs. The checked-in data cohort has 13 active releases; the 347 static candidates remain candidate-only.

## Prompt-interception evidence boundary

The checked-in live evidence contains 7 strict campaign-v2 documents and 6 readable legacy-v1 documents. Strict v2 validates the declared task/seed/two-condition matrix and binds verifier occurrences to each arm. Legacy v1 remains observation-only because it cannot detect omitted whole tasks or prove arm-specific verifier occurrence identity.

The strict-v2 usage-complete observations report 50,369 prompt-plus-completion tokens when every primitive description was shown and 20,248 when local retrieval selected a smaller set, across 50 matched-pair observations. The legacy-v1 observations separately report 39,415→15,611 across 39 pairs. The combined 89,784→35,859 total is only a non-claimable inventory observation because versions and repeated cohorts overlap. `claimable_token_savings=false`: none of these counters include all required runtime, retrieval, verification, repair, cache, and tool overhead or trusted isolated-runtime attestation.

The fixtures contain 14 unique tasks and 28 unique cases (9 constructed tasks/18 cases plus 5 external issue-derived positive tasks/10 cases). Campaign totals are deliberately called provider-call attempts, matched-pair observations, and case-execution observations because the same fixture cases are executed repeatedly across widths, seeds, and campaign formats.
