# Query API

Serves authenticated search, provenance, neighborhood, representation, edge, job, and
D0–D6 context operations. Policy filtering occurs before retrieval, and source bodies
are resolved only for credentials carrying the separate `source:read` scope.

The active dependency-free WSGI implementation is
`src/taedri_codegraph/http_api.py`. It exposes liveness/readiness and OpenAPI documents,
enforces exact CORS origins, caps request bodies, keeps API tokens out of responses and
logs, and resolves every graph through the authenticated tenant's control-plane mount.
The hosted container selects the optional Gunicorn process-manager boundary and adds
atomic tenant request admission plus append-only usage/limit APIs. Hosted load,
distributed tracing and PostgreSQL repository evidence remain promotion gates. Search
pagination uses tamper-evident opaque cursors bound to the exact immutable epoch,
query, lanes, and filters; cursors fail closed when an epoch or query changes.
