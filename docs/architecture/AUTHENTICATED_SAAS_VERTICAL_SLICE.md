# Authenticated SaaS vertical slice

Status: executable single-node proof, production storage ports not yet promoted
Date: 2026-07-16

## Outcome

Taedri now has one complete network path from a tenant request to a searchable,
immutable result:

1. an operator creates a tenant and graph mount;
2. the control plane issues a scoped API token and stores only its salted verifier;
3. an authenticated client submits a content-addressed source-analysis job;
4. a persistent worker selects it by capability and acquires a time-bounded lease;
5. the worker resolves a relative path beneath an operator-mounted source root;
6. the existing no-import Python analyzer builds and validates an immutable epoch;
7. publication atomically advances the tenant's local graph pointer;
8. the worker records output references and a content-addressed completion receipt;
9. the client searches or requests progressively disclosed context through HTTP.

This closes the gap between the existing graph algorithms and a usable service. It
does not claim that SQLite plus a Machine volume is horizontally scalable production
infrastructure.

## Runtime boundaries

| Boundary | Active implementation | State |
|---|---|---|
| Tenant/auth control | `src/taedri_codegraph/saas.py` | Persistent SQLite POC |
| Query/job API | `src/taedri_codegraph/http_api.py` | Dependency-free WSGI |
| Worker executor | `src/taedri_codegraph/job_runner.py` | Python AST and polyglot inventory |
| Canonical graph/CAS | `storage.py` and immutable epoch directories | Existing active local adapter |
| Browser | `apps/explorer/index.html` | Live API console |
| Local deployment | `Dockerfile`, `compose.yaml` | API, worker, frontend |
| Fly proof | `deploy/fly/*.fly.toml` | Explicit single-Machine POC |
| Production SQL contract | `deploy/postgres/001_control_plane.sql` | Schema defined; adapter pending |
| Production object store | S3/Tigris port | Pending |

## Control-plane model

Mutable SaaS records remain outside exact graph identity:

- `Tenant` has a deterministic identity based on its immutable slug.
- `GraphMount` identity contains tenant and logical mount name, not the operational
  filesystem path. Remounting does not rewrite graph identity.
- API tokens use `tcg_<key-id>_<secret>` format. Only PBKDF2 salt, verifier, prefix,
  scopes, and lifecycle timestamps are stored. Revocation is immediate.
- API scopes support exact rights and namespace wildcards. `source:read` is distinct
  from `graph:read`, so selection metadata does not imply body disclosure.
- Audit events form an append-only tenant-local hash chain. Tenant creation, graph
  mounting, key issuance, and key revocation all create events.
- Job payloads are canonical JSON objects addressed by SHA-256 and keyed by tenant.
- Worker rows retain the existing job, lease, attempt, retry, dead-letter, and event
  contracts across API and worker process restarts.

The SQLite adapter starts write transactions with `BEGIN IMMEDIATE`, chooses one
eligible job, inserts the lease and append-only event, and commits before execution.
The PostgreSQL implementation must preserve the same behavior with a short
`SELECT ... FOR UPDATE SKIP LOCKED` transaction.

## HTTP surface

| Method and path | Scope | Purpose |
|---|---|---|
| `GET /healthz` | Public | Process liveness |
| `GET /readyz` | Public | Control-store integrity and migration readiness |
| `GET /openapi.json` | Public | Machine-readable API surface |
| `GET /v1/me` | Authenticated | Tenant, key ID, and granted scopes |
| `GET /v1/epochs` | `graph:read` | Candidate/published/current epoch inventory |
| `GET /v1/search` | `graph:read` | Exact, lexical, blocking, vector, and fused search |
| `GET /v1/context` | `graph:read` | Progressive context; bodies additionally require `source:read` |
| `GET /v1/entities/{id}` | `graph:read` | Exact entity record |
| `GET /v1/entities/{id}/neighbors` | `graph:read` | Typed adjacency |
| `GET /v1/edges` | `graph:read` | Predicate/text edge search |
| `GET /v1/edges/{id}` | `graph:read` | Exact relation assertion |
| `GET /v1/representations` | `graph:read` | Typed representation variants and provenance |
| `POST /v1/jobs` | `jobs:write` | Idempotent, tenant-scoped job submission |
| `GET /v1/jobs[/{id}]` | `jobs:read` | State, lease, attempts, and immutable event history |
| `GET /v1/audit` | `audit:read` | Tenant-local control-plane audit chain |

The server accepts only explicit browser origins, caps JSON bodies, sends no-store and
content-type security headers, emits request IDs, and never returns a stored token.
The frontend keeps its developer token in page memory rather than local storage.

## Worker safety and semantics

The network API currently accepts only `extract` and `index` jobs. The executable
operations are intentionally narrow:

- `analyze_python_path`: full Python syntax graph using the established no-import
  analyzer;
- `inventory_source_path`: language inventory without target-code execution.

Every requested source path must be relative. Absolute paths, `..` traversal, NULs,
and paths resolving outside the operator source mount fail before analysis. Existing
symlink and wheel-path protections remain active inside the analyzers.

The worker records failures rather than losing them. Validation and authorization
errors are terminal; potentially transient operating-system errors may retry until the
declared attempt limit, after which the job dead-letters.

## Local execution

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .

tcg admin bootstrap \
  --control .tcg/control.sqlite \
  --tenant demo \
  --name Demo \
  --graph-store "$(pwd)/.tcg/demo-graph"

tcg serve \
  --control .tcg/control.sqlite \
  --cors-origin http://localhost:8080

tcg worker run \
  --control .tcg/control.sqlite \
  --source-root "$(dirname "$(pwd)")"
```

The bootstrap output contains the only plaintext copy of the new token. The local
Compose stack builds the same boundaries:

```bash
docker compose build
docker compose run --rm api admin bootstrap \
  --control /data/control.sqlite \
  --tenant demo \
  --name Demo \
  --graph-store /data/graph
docker compose up
```

Then open `http://localhost:8080`. The worker's read-only mount exposes the repository
as relative path `taedri-codegraph`.

## Fly.io interpretation

`deploy/fly/single-node-poc.fly.toml` runs API and worker threads inside one Machine so
they can safely share the SQLite database and attached volume. It disables autostop
and must remain at one Machine. The frontend has a separate, scale-to-zero manifest.

This configuration proves image construction, routing, health checks, persistent
restart behavior, and browser-to-API traffic. It does not satisfy the production
topology because a Fly volume is tied to a Machine/region and cannot be the durable,
multi-process truth assumed by horizontal scaling.

## Production promotion gates

The next storage slice must pass the same tests using:

1. PostgreSQL tenant, key, audit, payload, job, lease, and event repositories;
2. atomic lease acquisition with `SKIP LOCKED` and concurrency tests;
3. S3/Tigris immutable epoch upload, validation, and compare-and-swap current pointer;
4. bounded download/cache of only the selected serving epoch;
5. separate API and worker Fly apps with distinct credentials;
6. a separate evaluator store and an ephemeral sandbox with no production credential;
7. managed OIDC browser sessions while retaining scoped machine/API keys;
8. envelope encryption for customer Git, Ollama, and other model-provider credentials;
9. restore drills, rate limits, observability, and failure-injection evidence.

Until those gates pass, the correct description is **working authenticated single-node
SaaS POC**, not production SaaS.
