# Taedri component and capability inventory

As of 2026-07-16. This inventory contains all 32 declared components.

**Count rule:** no production database is committed to Git. Every numeric count below names its immutable evaluation source; stateless components and missing hosted evidence are stated explicitly.

| Component | Folder | Status | Measured records / evidence | Core capabilities |
|---|---|---|---|---|
| `vertical-slice` | `src/taedri_codegraph` | **working** | Real PyPI evidence: 25,347 entities; 74,327 occurrences; 153,909 relations | current executable implementation while packages are extracted |
| `mechanism-runtime` | `src/taedri_codegraph/mechanisms` | **working** | Stateless executor; immutable waterfall receipts are caller-owned | versioned mechanism registry; budgeted waterfall execution; attempt and abstention receipts |
| `pipeline-catalog` | `src/taedri_codegraph/pipelines` | **working** | 4 executable pipelines; 6 admitted worker operations | ingestion and generation pipeline definitions; operation admission contracts; source-discovery event routing |
| `shared-kernel` | `packages/shared-kernel` | **working** | N/A — stateless identity/canonicalization library | identity; canonical encoding; typed envelopes; provenance primitives |
| `shared-schemas` | `packages/shared-schemas` | **partial** | 19 checked-in JSON Schemas | descriptor schemas; predicate schemas; registry manifests; conformance fixtures |
| `schema-artifacts` | `schemas` | **partial** | 19 JSON Schemas; 44 PostgreSQL tables | exported JSON Schema; PostgreSQL DDL; schema acceptance checks |
| `primitive-capsules` | `packages/primitive-registry` | **working** | Data cohort: 11 public releases / 109 blobs / 11 downloadable packs | primitive handles; content trees; revision DAGs; refs; thin pack contracts; proof-gated releases; evidence-backed interface graphs; strict complete-capsule authoring compiler |
| `primitive-factory` | `packages/primitive-factory` | **working** | 347 real-source candidates; 1,388 intake events; 0 released by factory | source-backed primitive candidate extraction; candidate contracts; search descriptors; candidate graph neighborhoods |
| `ingestion-pypi` | `packages/ingestion-pypi` | **working** | 4 real wheels evidenced (3 benchmark + usaddress); latest usaddress mount: 101 entities / 614 relations | PyPI acquisition receipts; wheel verification; distribution metadata |
| `ingestion-git` | `packages/ingestion-git` | **working** | 1 immutable real GitHub commit archive; 417 entities / 2,282 relations | Git object acquisition; commit and tree lineage; repository policy |
| `analyzer-python` | `packages/analyzer-python` | **working** | Real PyPI evidence: 25,347 entities / 153,909 relations across 140 files | Python syntax and semantic extraction; Python conformance corpus |
| `analyzer-polyglot` | `packages/analyzer-polyglot` | **partial** | No dedicated durable rows; working file-inventory boundary, semantic adapters not claimed | language-neutral file inventory; polyglot analyzer adapter boundary |
| `storage` | `packages/storage` | **working** | 5 real published evaluation epochs; usaddress runs: 518 entities / 9,961 typed variants | canonical ledger adapters; CAS; typed long tables; projection epochs |
| `retrieval` | `packages/retrieval` | **working** | 36 retained real-package hybrid query receipts | query planning; sparse and LSH retrieval; bounded vector scoring; fusion receipts |
| `compatibility` | `packages/compatibility` | **partial** | Data cohort: 66 evidence edges / 22 typed ports / 18 blocked exact compatibility edges / 2 executed routes | typed compatibility dimensions; directional exact evaluation; unknown and poison policy; exact port matching; adapter-free unary pipeline plans and receipts |
| `session-ledger` | `packages/session-ledger` | **working** | Reference factory evidence: 1 digest-only session / 7 events / 0 model calls | prompt privacy modes; harness session events; acceptance and abstention receipts |
| `benchmarking` | `packages/benchmarking` | **conformance_only** | 2 tasks / 4 lanes / 16 conformance receipts; efficacy_claimable=false | matched-lane experiments; sealed task references; run receipts; contamination strata; paired metrics; claim eligibility |
| `saas-control-plane` | `packages/saas-control-plane` | **working** | Real acquisition evidence: 1 tenant / 2 succeeded jobs / 4 audit events | tenant identity; scoped API keys; graph mounts; audit chains; persistent job payloads and leases; quota policy and immutable usage receipts |
| `worker-runtime` | `services/worker-runtime` | **working** | Real acquisition evidence: 2 leased and succeeded network jobs | idempotent jobs; capability-aware leases; lease heartbeats and cooperative cancellation; attempt receipts; retry and dead-letter policy |
| `benchmark-worker` | `services/benchmark-worker` | **conformance_only** | 16 deterministic fixture receipts; 0 real-model efficacy runs | matched run scheduling; lane disclosure enforcement; terminal receipt validation; contamination strata; claim eligibility comparison |
| `discovery-worker` | `services/discovery-worker` | **partial** | 0 hosted poll/webhook rows; replay-safe local router is tested | allowlisted discovery event contracts; replay-safe discovery-to-job routing |
| `ingestion-worker` | `services/ingestion-worker` | **working** | 2 real acquisition jobs; 518 entities / 2,896 relations published | bounded remote acquisition; safe extraction; atomic graph publication; acquisition receipts |
| `primitive-worker` | `services/primitive-worker` | **working** | 347 candidates plus 11 independently verified and released working primitives | source-backed candidate generation; candidate provenance; candidate curation; complete-capsule release verification; one-at-a-time primitive validation and release; curated reusable data-primitive generation |
| `indexer-service` | `services/indexer` | **working** | 5 real evaluation epochs (3 PyPI benchmark + 2 usaddress acquisition) | local ingestion orchestration; atomic publication; rebuildable projection builds |
| `query-api` | `services/query-api` | **working** | 41 operations across 37 paths | authenticated graph and primitive search; context disclosure; tenant quota admission; usage and provenance responses |
| `registry-api` | `services/registry-api` | **working** | Data cohort: 11 public releases; 0 candidate rows serving as primitives | candidate intake and curation; staged branch and tag mutations; fork commands; proof-gated release search and pack delivery |
| `mcp-integration` | `integrations/mcp` | **working** | Protocol and remote round-trip evidence; no durable MCP-owned rows | MCP tool and resource contracts; bounded context adapters |
| `agent-integrations` | `integrations/agents` | **partial** | 1 digest-only harness session; 0 model calls; no efficacy claim | Codex and Claude instructions; local search skill; harness policy guidance |
| `explorer-app` | `apps/explorer` | **working** | Static application; records are read from authenticated APIs | authenticated browser console; search and record inspection UI |
| `portal-app` | `apps/portal` | **working** | Static application + versioned plan/subscription contracts; no checked-in customer rows | public plan catalog; tenant subscription and entitlement view; provider redirect initiation |
| `deployment` | `deploy` | **poc_only** | 44 PostgreSQL tables; Docker/Compose and one-Machine Fly POC | local containers; PostgreSQL migrations; single-Machine Fly.io POC; deployment policy |
| `evaluation` | `eval` | **partial** | 3 real PyPI packages + 2 real usaddress sources + 11 real custom releases + 2 no-model routes + 16 non-claimable benchmark receipts | real-package corpora; ablation receipts; promotion gates; deterministic primitive-composition receipts; reports |

## What the statuses mean

- **working:** the stated local/transitional scope has executable acceptance evidence.
- **partial:** the narrow stated scope works; broader capabilities remain named gates and are not advertised as implemented.
- **conformance_only:** contracts and deterministic receipts work, but there is no claimable external execution.
- **poc_only:** the bounded proof works but lacks production durability or hosted operations.

## Primitive truth boundary

The factory's candidate rows are not primitive releases. Public primitive search, resolution, and pack delivery read only `primitive_release`, whose rows require the complete capsule and all executable acceptance proofs. The checked-in data cohort has 11 active releases; the 347 static candidates remain candidate-only.
