# Primitive factory and product-slice validation — 2026-07-16

## Result

The POC completed a content-addressed, AST-only run over the real Taedri CodeGraph
implementation and generated a searchable primitive corpus, worker receipts, intake
history, a prompt-session trace, a selective pack, CSV/JSONL/GraphML/Mermaid data, two
GitHub-renderable SVG views, and an interactive registry console.

| Measure | Observed |
|---|---:|
| Python source files | 24 |
| Source bytes scanned | 371,909 |
| Function candidates | 85 |
| Method candidates | 248 |
| Nested-function candidates | 14 |
| Total primitive candidates | 347 |
| Syntax-derived `calls_may` edges | 1,812 |
| Parse diagnostics | 0 |
| Unique content-addressed blobs | 1,435 |
| Logical unique blob bytes | 2,246,166 |
| Intake events | 1,388 |
| Promoted candidates | 0 |
| Worker jobs / events | 2 / 6 |
| Sample harness model calls | 0 |
| Sample harness verification calls | 0 |
| Selected thin pack | 3,424 bytes |
| Repository tests after implementation | 89 passed |

The exact run identity and source root digest are retained in
[`candidate-manifest.json`](../../eval/results/primitive-factory-2026-07-16/candidate-manifest.json).
The source revision is intentionally `null`: this was a working-tree POC whose complete
input is bound by content digest, not a claim that the input already existed in a Git
commit.

## What was validated

- Target code was parsed as data and never imported or executed.
- Repeated original-file payloads deduplicated in the content-addressed registry.
- Every candidate bound a contract-role blob and descriptor-role blob into an immutable
  tree and revision.
- Candidate lifecycle progressed through received, quarantined, structurally valid, and
  indexed states without overwriting capsule identity.
- The producer could not self-promote a generated candidate; promotion requires
  independent evidence and a policy decision.
- Public promotion additionally requires verified license evidence.
- Search records retain exact names/digests, lexical text, blocking keys, three
  overlapping LSH input widths, graph calls, and deferred embedding channels.
- Worker jobs used idempotency keys, capability-aware leases, attempt receipts, and
  explicit output references.
- The sample coding-harness session stored only a request digest, progressively resolved
  one candidate, materialized a role-selective pack, and abstained when model and
  verifier integrations were absent.
- The standalone frontend contains its data locally, makes no fetch/XHR calls, and its
  filters and tabs are implemented in plain JavaScript.
- All 89 repository tests passed; Python compilation, generated JavaScript syntax,
  embedded JSON reconciliation, SVG XML parsing, and `git diff --check` also passed.

## Artifact inventory

| Artifact | Purpose |
|---|---|
| `candidates.jsonl` | Immutable primitive candidate records |
| `submissions.jsonl` | Immutable intake submission records |
| `intake-events.jsonl` | Complete append-only candidate state history |
| `search-index.jsonl` | Search descriptor envelopes and projection inputs |
| `candidate-summary.csv` | Human sorting and spreadsheet inspection |
| `graphs/primitive-candidates.graphml` | Complete candidate/call-label graph |
| `graphs/primitive-candidates.mmd` | Bounded readable graph slice |
| `selected-candidate.tcgpack` | Content-addressed selective download |
| `worker-receipts.json` | Idempotent jobs, leases, attempts, and outputs |
| `harness-session.json` | Digest-only retrieval/materialization/abstention trace |
| `registry-console-data.json` | Frontend dataset plus operations/business records |
| `candidate-manifest.json` | Reconciliation and evidence boundary |
| `apps/explorer/registry-console.html` | Interactive product POC |
| `primitive-candidate-kinds.svg` | GitHub-renderable real-data chart |
| `product-operating-model.svg` | GitHub-renderable architecture/business view |

## Evidence boundary

This validates static extraction, data contracts, lifecycle enforcement, selective
transport, and frontend/receipt integration. It does **not** validate behavioral
correctness, safe composition, semantic embedding quality, LLM classification,
production durability, tenant isolation, billing, customer demand, or cost savings.
Those require real providers, sandbox verification, workload evaluations, production
adapters, and design-partner evidence.
