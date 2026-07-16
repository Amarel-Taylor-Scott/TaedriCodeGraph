# Applications

Human-facing applications consume the query API and shared schemas. They do not read
mutable analyzer internals or own canonical facts.

- `explorer/` is the authenticated graph, ingestion, primitive, and operations console.
- `portal/` is the public plan catalog and tenant subscription/entitlement surface.
