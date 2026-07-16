# Exported schemas

Generated, consumer-facing JSON Schema, Arrow schema, SQL DDL, protocol, and
compatibility fixtures will be published here from the authoritative definitions in
`packages/shared-schemas`. Generated files are checked for drift; they are not edited
as a second source of truth.

The first hand-authored conformance contracts are
[`primitive-revision.v1.schema.json`](primitive-revision.v1.schema.json) and
[`primitive-pack.v1.schema.json`](primitive-pack.v1.schema.json). They specify
registry-native revision history and selective content delivery without prescribing a
database, object store, Git host, or package registry.
