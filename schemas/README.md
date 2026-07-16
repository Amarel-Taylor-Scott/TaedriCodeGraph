# Exported schemas

Generated, consumer-facing JSON Schema, Arrow schema, SQL DDL, protocol, and
compatibility fixtures will be published here from the authoritative definitions in
`packages/shared-schemas`. Generated files are checked for drift; they are not edited
as a second source of truth.

The current hand-authored conformance contracts cover primitive revisions and packs,
candidate submissions, worker jobs, prompt-session events, sealed benchmark tasks,
matched experiments, and terminal benchmark receipts. They specify portable records
without prescribing a database, queue, object store, Git host, model provider, package
registry, benchmark harness, or sandbox. The Python reference implementations
additionally enforce state transitions, progressive-disclosure rights, receipt
reconciliation, and contamination rules that JSON Schema alone cannot express.

The authenticated SaaS slice adds `tenant.v1.schema.json`,
`job-submission.v1.schema.json`, and `primitive-stage.v1.schema.json`. Plaintext API
tokens intentionally have no persistence schema because only salted verifiers may be
stored.

Harnesses use `prompt-session-start.v1.schema.json` and
`prompt-session-append.v1.schema.json`; the append request carries a compare-and-swap
sequence so retries cannot silently duplicate session evidence.

SaaS admission and billing exports use `usage-limit-revision.v1.schema.json` and
`usage-receipt.v1.schema.json`. Limit changes and consumption remain append-only so a
future invoice can be reconciled to the exact policy and receipts that produced it.

The extensibility slice adds `mechanism-waterfall-run.v1.schema.json`,
`pipeline-definition.v1.schema.json`, `search-trigger-signal.v1.schema.json`, and
`subscription-revision.v1.schema.json`. These contracts preserve attempts, capability
skips, explicit abstention, privacy-safe intent digests, provider event lineage, and the
difference between working, contractual, and planned pipeline stages.
