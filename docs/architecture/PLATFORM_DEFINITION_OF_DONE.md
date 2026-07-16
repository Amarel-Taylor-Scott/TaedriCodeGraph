# Platform definition of done

Taedri is not considered complete because a directory or service boundary exists. A
component is complete for a declared scope only when it has an executable interface,
durable and idempotent state where needed, security and failure tests, non-synthetic
evidence, inspectable provenance receipts, an operator/recovery path, and passing
acceptance commands.

The machine-readable source of truth is
[`architecture/component-readiness.v1.json`](../../architecture/component-readiness.v1.json).
It covers every component in `architecture/components.json`, points to the current
implementation and evidence, and names the next unpassed gate. The inventory deliberately
distinguishes working local behavior, partial implementations, deterministic conformance
fixtures, bounded POCs, and documentation-only scaffolds.

Run the readiness validator with:

```bash
PYTHONPATH=src python -m unittest tests.architecture.test_component_readiness -v
tcg components --root .
```

## Execution order

1. Preserve the working local source-to-search path while introducing replaceable ports.
2. Add safe PyPI and immutable Git acquisition as persistent worker jobs.
3. Persist registry, session, compatibility, and metering state behind tenant boundaries.
4. Connect MCP and coding harnesses to the authenticated API with D0-D6 disclosure.
5. Run matched real-model lanes in an isolated evaluation environment.
6. Prove PostgreSQL, object storage, containers, Fly deployment, observability, backup,
   restore, and failure recovery before calling the hosted system production-ready.

External secrets are gates, not source configuration. They belong in scoped GitHub,
deployment, or evaluation environments and must never be committed or sent in chat.
