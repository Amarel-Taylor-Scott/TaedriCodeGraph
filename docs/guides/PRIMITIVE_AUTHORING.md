# Author and release one primitive at a time

Taedri does not create public placeholder primitives. A Git directory is either a
complete release-grade capsule or it remains ordinary source/candidate material.

## Directory contract

Start from a real, useful function with a narrow contract. A complete v1 directory has
one `primitive.json` manifest declaring every file and all 12 roles:

| Role | Required content |
|---|---|
| `source` | Executable implementation; no generated pseudocode |
| `contract` | Named input schemas, output schema, errors, and effects |
| `descriptor` | Summary, keywords, use cases, and explicit limitations |
| `runtime` | Language, exact runtime, entrypoint, dependency-lock digest, network policy |
| `dependency_lock` | Complete dependency closure or an explicit no-dependency lock |
| `example` | Positive, boundary, and negative executable vectors |
| `test` | Additional executable vectors |
| `verifier` | Independent oracle identity and comparison rule |
| `license` | SPDX expression, verified state, evidence path, and matching digest |
| `provenance` | Producer, source URI, immutable source revision, and source digest |
| `graph_delta` | Evidence-bound nodes, edges, ports, groups, and compatibility dimensions |
| `documentation` | Human-usable behavior and integration guidance |

The graph schema is intentionally composition-grade. It requires:

- exactly one runtime entrypoint node;
- a node for every contract, port, example set, test set, and runtime target used;
- directional namespaced edges with modality, quantifier, confidence, and capsule-bound
  evidence digests;
- one typed port per contract input and exactly one output port, with canonical schema
  digests and declared transports;
- explicit language/runtime, call style, execution model, purity, determinism, network,
  effects, and required compatibility dimensions; and
- at least one evidence-backed capability group with searchable labels.

The working repository cohort contains 23 complete primitives:

- `examples/primitives/normalize-text`
- `examples/primitives/casefold-text`
- `examples/primitives/data-cleaning/*`
- `examples/primitives/data-engineering/*`
- `examples/primitives/data-science/*`

The 21 data utilities are generated from strict typed specifications by
`tools/generate_data_primitive_capsules.py`. The compiler in
`src/taedri_codegraph/primitives/authoring.py` reduces repetitive metadata work but
rejects placeholders, undeclared imports, invalid cases, missing description facets,
and incomplete evidence. The normal bundle inspector remains an independent gate.

Regenerate and then execute the whole current cohort with:

```bash
PYTHONPATH=src python tools/generate_data_primitive_capsules.py
PYTHONPATH=src python tools/generate_data_primitive_capsules.py --check
PYTHONPATH=src python tools/run_data_primitive_cohort.py
```

The `--check` form is read-only: it recompiles every declared file in memory and fails
on any missing, unexpected, symlinked, or byte-drifted capsule content.

## Validate without executing

```bash
tcg primitive validate examples/primitives/casefold-text
```

This command rejects missing/undeclared files, symlinks, stale digests, incomplete
roles, dangling edges, mismatched contract ports, unknown compatibility dimensions,
unverified licensing, mutable provenance, or an unpinned runtime. It prints
`code_executed: false` and a normalized interface assessment.

## Release one trusted-source primitive locally

Create a tenant once:

```bash
tcg admin bootstrap \
  --control .tcg/control.sqlite \
  --tenant local-authoring \
  --name "Local authoring" \
  --graph-store "$(pwd)/.tcg/local-authoring"
```

Then stage, execute, release, search, and pack exactly one directory:

```bash
tcg primitive release-local examples/primitives/casefold-text \
  --control .tcg/control.sqlite \
  --tenant local-authoring \
  --authorizer-id person:local-release-manager \
  --allow-trusted-code-execution
```

`--allow-trusted-code-execution` is mandatory because the local verifier is a real
bounded subprocess but not a hostile-code sandbox. Arbitrary customer code belongs in
the separately isolated verifier deployment gate.

The command succeeds only after all executable acceptance proofs, source-body
deduplication, assurance-tier identity separation, queryability, and authorization pass.
Public primitive search and packs remain empty until that transaction commits.

## A disciplined one-at-a-time queue

For each proposed primitive:

1. Pick one measured reuse gap or repeated implementation—not a speculative name.
2. Write the smallest useful implementation and exact contract.
3. Add examples before descriptions; add counterexamples and failure behavior.
4. Bind every interface edge and group to exact capsule evidence.
5. Run `tcg primitive validate` until the whole directory is release-grade.
6. Review source, contract, license, provenance, and oracle identities.
7. Run `release-local` for trusted code or enqueue `verify_primitive_release` on the
   isolated worker path.
8. Search and download the released pack from a fresh client.
9. Add the primitive to a real task or deterministic route and retain its result receipt.
10. Keep it only if measured use, correctness, or differentiation justifies its storage
    and indexing cost; otherwise revoke without deleting history.

Do not bulk-convert the 347 static factory candidates. They are useful discovery input,
but they lack enough behavioral, license, runtime, and interface evidence to be public
primitives.
