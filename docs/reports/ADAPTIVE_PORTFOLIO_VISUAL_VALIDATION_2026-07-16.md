# Adaptive portfolio, multi-resolution LSH, visuals, and monorepo validation

Date: 2026-07-16
Status: POC validated; production calibration remains open

## Outcome

The atlas refinement fits the existing representation spine without adding wide
entity columns. The POC now includes:

- explicit typed materialization-state and selector-receipt variants;
- a deterministic, budgeted subject-local enrichment planner;
- E0–E6 enrichment depth, separate from D0–D6 context disclosure;
- overlapping narrow/medium/wide SimHash64 and MinHash16 LSH families;
- self-describing LSH keys with width, table, offset, and band plus query receipts;
- a machine-checked monorepo component manifest and extraction scaffold;
- a self-contained interactive HTML architecture explorer;
- five GitHub-renderable SVG/PNG visuals and reproducible CSV/JSON data.

The logical design passes the extensibility challenge. The physical storage and
retrieval quality warnings from the prior PyPDF run remain unresolved and are visible
in the new scale chart.

## Real-package smoke test

The updated code ingested the pinned real wheel
`usaddress-0.5.16-py3-none-any.whl` with SHA-256
`ce2bd73e3a41176fa29f093e9ad153327a87862430f1b0b121f0cb230c182a6a`.

| Measure | Result |
|---|---:|
| Files | 1 |
| Entities | 101 |
| Occurrences | 296 |
| Relations | 614 |
| Representation assertions | 1,883 |
| Representation contents | 744 |
| Generation runs | 2 |
| Lineage assertions | 671 |
| Fact bytes | 7,984,829 |
| SQLite index bytes | 10,129,408 |

The structural query for `usaddress.tag` searched 56 keys: 28 SimHash keys and 28
MinHash keys across narrow, medium, and wide profiles with overlapping offsets. The
top three candidates each matched all 28 SimHash keys:

| Candidate | Kind | Matching bands | Matching profiles |
|---|---|---:|---|
| `usaddress.DIRECTIONS` | Python variable | 28 | SimHash narrow, medium, wide |
| `usaddress.Feature` | Python variable | 28 | SimHash narrow, medium, wide |
| `usaddress.GROUP_LABEL` | Python variable | 28 | SimHash narrow, medium, wide |

This is a useful failure, not evidence that the candidates are equivalent. Their
normalized declaration token views collide exactly, so a wider band cannot restore
information already erased by normalization. Multi-resolution LSH protects operating
regions; it does not cure an insufficient input view.

Making all six profiles independent, lineage-bearing variants also exposed their
physical cost. Relative to the prior usaddress POC, fact bytes grew 17.58% and the
SQLite index grew 25.34%. That is acceptable evidence for an experiment, not a reason
to enable every profile for every subject in production. Profile-level variants make
the required individual-arm and leave-one-out ablations possible; the portfolio policy
must decide which profiles are defaults, on-demand arms, or query-time fallbacks.

The architecture response is the proposed dynamic-depth loop:

1. measure bucket size, entropy, false-positive rate, and repeated query confusion;
2. raise the subject's `candidate_confusion_ppm` receipt;
3. materialize a different independent view—identifier/type context, AST shape,
   MinHash, graph neighborhood, contract, or selected embedding—if marginal value
   justifies cost;
4. apply exact distance, typed filters, evidence, and verification to finalists;
5. retain the successful and failed arms for ablation and future routing.

Raw output: [usaddress LSH smoke data](../../eval/results/adaptive-portfolio-2026-07-16/usaddress-lsh-smoke.json).

## Schema conclusion

The right physical pattern is typed long tables plus specialist projections, not
unbounded wide columns and not untyped EAV:

```text
descriptor_definition
representation_content
generation_run
representation_assertion
lineage_assertion
materialization_state
preferred_view
projection_epoch
```

New license, lineage, hierarchy, scalar, text, vector, graph, or runtime facets are
registered versions and append-only rows. Hot values may be promoted into typed
columns, postings, ANN spaces, adjacency layouts, or policy indexes without changing
the canonical entity record.

## Monorepo conclusion

A monorepo is the right development boundary because schemas, conformance fixtures,
ingestors, analyzers, storage, retrieval, services, and agent contracts need atomic
changes. It should still produce separate libraries and deployables.

The scaffold deliberately does not move the working `src/taedri_codegraph` package.
Each extraction should preserve the CLI, golden tests, security corpus, and real-
package evaluations before the old module is removed.

## Visual and data artifacts

- [Interactive explorer and static visual index](../visuals/README.md)
- [Typed long-table model](../visuals/assets/typed-long-table-model.svg)
- [Adaptive enrichment depth](../visuals/assets/adaptive-enrichment-depth.svg)
- [Multi-resolution LSH collision curves](../visuals/assets/multiresolution-lsh-collision.svg)
- [Real-package storage scale](../visuals/assets/real-package-storage-scale.svg)
- [Monorepo topology](../visuals/assets/monorepo-component-topology.svg)
- [Chart source data](../visuals/data/)

The LSH curve is theoretical single-table probability. The storage chart uses measured
real-package data. The adaptive-depth heatmap is a deterministic policy illustration,
not a learned production policy.

## Validation

- 59 unit, golden, integration, security, and architecture tests passed.
- Python compilation passed for `src`, `tests`, and `tools`.
- JSON, CSV, SVG/XML, and HTML parsed successfully.
- JavaScript syntax checks passed for the architecture explorer.
- All five generated charts were visually inspected.
- The atlas copy differs from the supplied file only by a final newline.

No semantic embedding model, external LLM, or runtime execution of the target package
was used in this slice. The deterministic lexical hash vector remains explicitly
non-semantic.
