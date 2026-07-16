# Storage

Owns content-addressed payload storage, immutable fact epochs, typed long-table
adapters, Parquet/Arrow exports, PostgreSQL control records, migrations, and disposable
projection manifests. Search engines and graph databases are projections, never the
canonical ledger.

Current extraction sources: `storage.py`, `primitives/storage.py`, the persistence
portions of `query.py`, and `deploy/postgres/002_representation_ledger.sql`. The latter
keeps descriptor/content/run/assertion/evidence/lineage rows authoritative while exact,
lexical, scalar, blocking, embedding, and graph tables remain disposable epochs.
