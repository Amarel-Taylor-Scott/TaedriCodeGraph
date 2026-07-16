# Storage

Owns content-addressed payload storage, immutable fact epochs, typed long-table
adapters, Parquet/Arrow exports, PostgreSQL control records, migrations, and disposable
projection manifests. Search engines and graph databases are projections, never the
canonical ledger.

Current extraction sources: `storage.py` and the persistence portions of `query.py`.
