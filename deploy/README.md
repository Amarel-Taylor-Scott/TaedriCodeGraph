# Deployment

Owns local development stacks, database migrations, object-store configuration,
observability, policy integration, backups, and reproducible deployment manifests.
Secrets and runtime policy never belong in committed examples.

[`topology.v1.json`](topology.v1.json) records the staged deployment decision: keep a
modular vertical slice now, use independently scalable process groups before assuming
microservices are necessary, and split deployables only after a measured gate. Machine
volumes and local SQLite remain development/cache options, never the production source
of truth for immutable artifacts or multi-tenant refs.

The repository now includes a hardened three-service `compose.yaml`, reusable backend
and frontend Dockerfiles, the PostgreSQL control-plane migration contract, and an
explicitly single-Machine Fly proof manifest under `deploy/fly`. The Fly POC is useful
for demonstrations but is intentionally prevented from masquerading as HA: production
promotion requires PostgreSQL plus S3/Tigris epoch storage and separate evaluator and
sandbox credentials.

Backend images install the optional `server` extra and run the WSGI application under
Gunicorn's bounded threaded worker pool with graceful timeout and request recycling.
The dependency-free `wsgiref` server remains available for local development only.
`tools/smoke_production_server.py` boots the real process manager, exercises liveness
and readiness over a loopback socket, and is part of hosted CI.

`.github/workflows/ci.yml` runs the complete Python suite on 3.12 and 3.13, applies the
PostgreSQL DDL twice to catch non-idempotent migrations, verifies all 42 declared
tables, and builds both backend and explorer images without publishing them. The first
green hosted run is still an acceptance gate; a committed workflow is not evidence
that GitHub runners or registry permissions work.
