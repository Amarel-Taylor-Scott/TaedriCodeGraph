# SaaS control plane

Owns tenant identity, scoped API-key verification, graph mounts, append-only audit
chains, content-addressed job payloads, transactional persistent worker leases, and
immutable usage/quota receipts. It also owns the provider-neutral plan catalog,
append-only subscription revisions, replay-safe billing events, and active entitlement
snapshots used by the public portal.

The active single-node adapter is `src/taedri_codegraph/saas.py`. It stores only a
PBKDF2 verifier for each API key and returns plaintext tokens once at issuance. The
metering repository atomically enforces fixed-window limits, retains every policy
revision, and exposes tenant-scoped `/v1/usage` and `/v1/limits` APIs. It is an
operational ledger, not an invoice or an invented pricing model. The
production PostgreSQL contracts are `deploy/postgres/001_control_plane.sql` and
`deploy/postgres/002_representation_ledger.sql`; implementing
that adapter and an S3/Tigris epoch store is the promotion gate from the runnable POC
to horizontally scalable cloud service.
