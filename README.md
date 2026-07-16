# Taedri CodeGraph

Taedri CodeGraph turns a fixed existing-code snapshot into a language-neutral,
evidence-backed graph that tools and agents can search, trace, and verify without
rereading the whole package.

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
- verified local-wheel ingestion with declared license provenance and distribution/import
  namespace separation;
- registry-native primitive capsules with content-addressed trees, immutable revision
  DAGs, compare-and-swap branches, forks/merges, and selective thin downloads;
- an AST-only primitive factory that turns real functions and methods into candidate
  capsules, contracts, graph neighborhoods, and exact/lexical/blocking/LSH search data;
- append-only candidate intake, worker lease, and privacy-aware prompt-session ledgers
  that prevent generated code from self-promoting;
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
```

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
tags, cross-namespace forks, merges, role-selective packs, and cached-blob omission. Read
the [primitive registry and staged deployment decision](docs/architecture/PRIMITIVE_CAPSULE_REGISTRY_AND_DEPLOYMENT.md)
or inspect the machine-readable [deployment topology](deploy/topology.v1.json). The
[validation report](docs/reports/PRIMITIVE_CAPSULE_VALIDATION_2026-07-16.md) links the
real-source capsule receipt and downloadable pack.

## Primitive factory, product console, and business model

The next vertical slice runs the primitive factory over Taedri's own implementation. It
produced 347 real-source function/method candidates, 1,812 syntax-derived call edges,
1,388 append-only intake events, two successful leased worker jobs, and a digest-only
coding-harness trace. No model or verifier was configured, so the sample session
abstained and zero candidates were promoted.

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

## Project status

Pre-alpha. The current slice proves the identity/evidence/ingestion/publication/query
spine, the universal representation extension mechanism, real-source primitive
candidate generation, append-only operational receipts, and a self-contained frontend.
Remote PyPI/Git acquisition for the factory, semantic cross-language analyzers,
production databases/queues/object storage, real model and embedding providers,
independent sandbox verification, calibrated fusion, tenant authorization, billing, and
compatibility routing remain explicit later milestones.

No project license has been selected yet; all rights are reserved until one is added.
