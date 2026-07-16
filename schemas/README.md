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
