# Worker runtime

Owns queue-scoped idempotency, capability-aware leases, retry limits, dead letters,
attempt receipts, and worker isolation ports for acquisition, extraction, description,
embedding, indexing, verification, materialization, rendering, and isolated benchmark
execution.

The in-memory semantic reference lives in `src/taedri_codegraph/workers.py`. The active
single-node persistent adapter in `src/taedri_codegraph/saas.py` preserves the same
idempotency, capability, lease-expiry, retry, dead-letter, and append-only event rules
across process restarts. The runner automatically renews long operations; each
heartbeat replaces the lease identity, and pending or leased jobs support idempotent,
cooperative cancellation receipts. PostgreSQL `SKIP LOCKED` conformance remains the
cloud gate.
