# Primitive capsule and deployment-boundary validation

Date: 2026-07-16
Status: local POC passes; production persistence and transport remain open

## Outcome

The architecture does not require one Git repository or PyPI package per primitive.
Taedri-generated and user-submitted capabilities can begin as registry-native candidate
capsules. Git, PyPI, OCI, npm, Maven, crates.io, and similar systems remain origin and
export adapters for the cases where their native collaboration or distribution behavior
is useful.

The POC adds:

- stable primitive handles separate from revisions and aliases;
- content-addressed blobs and deterministic trees with role-labeled entries;
- immutable revision DAGs with producer, run, evidence, contract, and graph bindings;
- compare-and-swap, fast-forward branch updates;
- immutable release tags;
- cross-namespace fork lineage and two-parent merges;
- role-selective, cached-blob-aware thin packs;
- deterministic compressed pack encoding with bounded decode and digest/size checks;
- public JSON Schemas for primitive revisions and packs;
- a machine-checked modular-monolith/process-group/microservice deployment sequence.

## Real-source capsule

`tools/build_primitive_capsule_demo.py` packages the repository's existing
`src/taedri_codegraph/canonical.py` implementation, its identity tests, a typed contract,
and a reviewed graph neighborhood. It does not invent benchmark code.

| Measure | Result |
|---|---:|
| Primitive handle | `uceg:v1:primitive:2g46dfzdmrdqjyt4ebf6mppg3wsfj5snzghnpqak5o2dij7eox7q` |
| Tree entries | 4 |
| Revisions in history pack | 3 |
| Merge parents | 2 |
| Included payload blobs | 3 |
| Cached source blob omitted | 4,449 bytes |
| Encoded thin pack | 1,835 bytes |
| Pack SHA-256 | `5ed86983ea416915bd676cd7e090f65e2a0071fc5f265d5fa77dbcc4db979126` |

The artifact intentionally has evidence class
`transport-and-history-poc-not-production-authorization`. Existing source and passing
tests make the example concrete, but this run is not a new independent correctness,
security, licensing, usefulness, or production-authorization claim.

Artifacts:

- [JSON receipt](../../eval/results/primitive-capsule-2026-07-16/primitive-capsule-demo.json)
- [Compressed capsule pack](../../eval/results/primitive-capsule-2026-07-16/canonical-identity-encoding.tcgpack)
- [Builder](../../tools/build_primitive_capsule_demo.py)

## Storage decision

The production design uses PostgreSQL for transactional handles, parents, refs, ACLs,
jobs, and projection manifests; S3-compatible immutable storage for bulk code, graph
facts, packs, Parquet, and evidence; and rebuildable specialist serving projections.
Machine-local disks and Fly Volumes may cache data but are not the only durable copy.

OCI is a distribution adapter because its standard already models digest-addressed blobs,
manifests, layers, tags, and non-image artifact types. It is not the canonical Taedri
logical model.

## Deployment decision

The monorepo remains one contract graph with several possible deployables:

1. local vertical slice;
2. one image with independently scaled `web` and `indexer` process groups;
3. separate query, registry, and indexer services only after measured security,
   independent-scaling, failure-domain, runtime/release, ownership, or residency gates.

Isolated execution and verification should eventually become a stronger security
boundary, but the current CodeGraph repository does not pretend that service already
exists.

## Validation

- 71 unit, golden, integration, security, and architecture tests passed.
- Python compilation passed for `src`, `tests`, and `tools`.
- Primitive revision, pack, component, topology, visual-data, and demo JSON parsed.
- The generated pack round-tripped and validated all included bytes.
- The monorepo topology chart was regenerated and visually inspected.

## Remaining gates

- PostgreSQL concurrency, migrations, tenant isolation, backup, restore, and load tests;
- S3-compatible upload/download, pre-signed URL, cache, encryption, and garbage-collection
  evidence;
- OCI mapping and registry conformance;
- pack-size and pull-latency benchmarks across real small, medium, and large portfolios;
- signatures, transparency, SBOM, reproducible build, and vulnerability-policy evidence;
- generated-candidate mutation, independent verification, promotion, revocation, and
  deletion exercises;
- an observed Fly process-group deployment and recovery drill.
