# Worker runtime

Owns queue-scoped idempotency, capability-aware leases, retry limits, dead letters,
attempt receipts, and worker isolation ports for acquisition, extraction, description,
embedding, indexing, verification, materialization, and rendering.

The active in-memory conformance implementation lives in
`src/taedri_codegraph/workers.py`; PostgreSQL/queue adapters remain a deployment gate.
