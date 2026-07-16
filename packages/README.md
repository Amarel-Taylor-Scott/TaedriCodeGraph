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

Two active cross-cutting extraction boundaries live under the transitional package:
`mechanisms/` supplies versioned budget/failure/receipt semantics, and `pipelines/`
supplies the operation catalog and replay-safe source-discovery compiler used by both
API admission and worker execution.

`saas-control-plane` is now another active extraction target: its SQLite adapter backs
the authenticated API and worker POC while the PostgreSQL migration fixes the cloud
contract without making local file paths part of graph identity.
