# Packages

Reusable, versioned libraries live here. The current executable code remains under
`src/taedri_codegraph` while it is extracted behind conformance tests. See
[`architecture/components.json`](../architecture/components.json) for ownership and
allowed dependencies. Primitive capsules are registry-native objects; they are not
automatically separate Python packages or Git repositories.

The current extraction targets include `primitive-factory` for source-backed candidate
creation, `session-ledger` for coding-harness receipts, and `benchmarking` for frozen
matched-lane experiments and claim-aware reports. Their tested reference code remains
in the transitional `src/taedri_codegraph` package until package boundaries are
published independently.
