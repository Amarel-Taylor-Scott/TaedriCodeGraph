# Deployment

Owns local development stacks, database migrations, object-store configuration,
observability, policy integration, backups, and reproducible deployment manifests.
Secrets and runtime policy never belong in committed examples.

[`topology.v1.json`](topology.v1.json) records the staged deployment decision: keep a
modular vertical slice now, use independently scalable process groups before assuming
microservices are necessary, and split deployables only after a measured gate. Machine
volumes and local SQLite remain development/cache options, never the production source
of truth for immutable artifacts or multi-tenant refs.

The repository now includes a four-service local `compose.yaml` (API, worker, explorer,
and portal), reusable backend and frontend Dockerfiles, the PostgreSQL control-plane
migration contract, and an explicitly single-Machine Fly proof manifest under
`deploy/fly`. The Fly POC is useful
for demonstrations but is intentionally prevented from masquerading as HA: production
promotion requires PostgreSQL plus S3/Tigris epoch storage and separate evaluator and
sandbox credentials.

The Compose services run as non-root users, drop Linux capabilities, set
`no-new-privileges`, use read-only filesystems, and bound temporary filesystems. These
are useful baseline container controls. They are not a hostile-code sandbox, a tenant
isolation boundary, a multi-node topology, or proof that a hosted deployment is secure.

Backend images install the optional `server` extra and run the WSGI application under
Gunicorn's bounded threaded worker pool with graceful timeout and request recycling.
The dependency-free `wsgiref` server remains available for local development only.
`tools/smoke_production_server.py` boots the selected production process manager and
exercises liveness and readiness over a loopback socket. Its name describes the server
mode; the smoke does not prove a production deployment. Today `/readyz` checks SQLite
integrity and reports the tenant count. It does not check PostgreSQL, object storage,
provider connectivity, evaluator isolation, billing, or backup recoverability.

`.github/workflows/ci.yml` installs, compiles, and runs the cross-version-safe Python
suite on 3.12 and 3.13. Exact checked-cohort execution and campaign-proof tests run
only on their declared Python 3.12 worker runtime; Python 3.13 skips those tests rather
than fabricating 3.12 execution evidence. CI also applies the PostgreSQL DDL twice to
catch non-idempotent migrations, verifies all 44 declared tables, and builds both
backend and explorer images without publishing them. A green hosted run is a release
gate; a committed workflow alone is not evidence that runners or registry permissions
work.

## Deployment truth

| Environment | Supported claim | Not yet supported |
|---|---|---|
| Local developer stack | Four processes can exercise the authenticated SQLite/local-store path. | Public tenancy, durable multi-node operation, or an isolation guarantee. |
| Controlled private alpha | One operator can run capped workloads for known participants on one controlled host, with manual recovery. | Self-service paid launch, unknown tenants, or contractual availability. |
| Production SaaS | Not reached. | PostgreSQL runtime repositories and concurrency evidence; S3/Tigris runtime wiring; isolated untrusted execution; OIDC/RBAC; real billing/webhook reconciliation and entitlement enforcement; telemetry and alerts; full backup/restore, retention/deletion, incident, load/SLO, staging, rollback, and supply-chain evidence. |
