# Deployment

Owns local development stacks, database migrations, object-store configuration,
observability, policy integration, backups, and reproducible deployment manifests.
Secrets and runtime policy never belong in committed examples.

[`topology.v1.json`](topology.v1.json) records the staged deployment decision: keep a
modular vertical slice now, use independently scalable process groups before assuming
microservices are necessary, and split deployables only after a measured gate. Machine
volumes and local SQLite remain development/cache options, never the production source
of truth for immutable artifacts or multi-tenant refs.
