# Exported schemas

Generated, consumer-facing JSON Schema, Arrow schema, SQL DDL, protocol, and
compatibility fixtures will be published here from the authoritative definitions in
`packages/shared-schemas`. Generated files are checked for drift; they are not edited
as a second source of truth.

The current hand-authored conformance contracts cover primitive revisions and packs,
candidate submissions, worker jobs, and prompt-session events. They specify portable
records without prescribing a database, queue, object store, Git host, model provider,
or package registry. The Python reference implementations additionally enforce state
transitions that JSON Schema alone cannot express.
