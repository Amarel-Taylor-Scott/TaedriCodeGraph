# Indexer service

Coordinates acquisition, analysis, primitive candidate generation, adaptive enrichment,
dependency-directed invalidation, projection builds, validation, and atomic epoch
publication. Work is issued through idempotent, capability-aware leases and every
provider, selector, attempt, and build produces a receipt.

The active `src/taedri_codegraph/job_runner.py` slice executes Python AST and polyglot
inventory jobs from an operator-mounted source root. Client payloads can only name a
relative path beneath that root. Completed jobs atomically publish the tenant graph and
store a content-addressed completion receipt; invalid jobs fail visibly or dead-letter.
