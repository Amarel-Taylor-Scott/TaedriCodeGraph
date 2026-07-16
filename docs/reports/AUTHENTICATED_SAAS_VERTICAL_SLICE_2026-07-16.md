# Authenticated SaaS vertical-slice validation

Date: 2026-07-16
Branch: `agent/initial-vertical-slice`
Claim class: implementation and conformance evidence, not production availability

## Result

The repository now executes a tenant-authenticated request path from queued source
analysis through worker lease, immutable epoch publication, and HTTP hybrid search.

The new integration fixture uses real Python source bytes rather than synthetic graph
rows. It verifies this sequence:

1. create a tenant and graph mount;
2. issue a scoped API key;
3. submit an idempotent `analyze_python_path` job over HTTP;
4. persist the job and content-addressed payload;
5. lease it to a capability-matched worker;
6. analyze without importing or executing the target module;
7. publish the validated epoch atomically;
8. complete the job with epoch and receipt references;
9. retrieve `normalize_address` with an explainable hybrid-search receipt;
10. deny source disclosure to a valid key lacking `source:read`.

## Verification evidence

| Check | Result |
|---|---|
| Full unit/architecture/security/integration suite | 118 passed |
| Python compile pass | Passed for `src` and `tests` |
| Git whitespace/error check | Passed |
| JSON parsing | All checked-in schemas and manifests passed |
| Fly TOML parsing | Both manifests passed `tomllib` parsing |
| Compose structure parsing | `api`, `worker`, and `frontend` loaded successfully |
| Real socket HTTP smoke | HTTP 200, two candidates, returned epoch matched published epoch |
| Docker image build | Not executed; Docker CLI is unavailable in the verification environment |

The full test command was:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## New active artifacts

- `src/taedri_codegraph/saas.py` — tenant, key, audit, payload, and queue persistence;
- `src/taedri_codegraph/http_api.py` — authenticated WSGI API and OpenAPI document;
- `src/taedri_codegraph/job_runner.py` — safe source-mounted worker execution;
- `apps/explorer/index.html` — live search, ingestion, jobs, and receipt UI;
- `Dockerfile` and `compose.yaml` — local API/worker/frontend stack;
- `deploy/fly/*.fly.toml` — reusable frontend and explicit single-node proof configs;
- `deploy/postgres/001_control_plane.sql` — production relational contract;
- `schemas/tenant.v1.schema.json` and `schemas/job-submission.v1.schema.json`;
- `docs/architecture/AUTHENTICATED_SAAS_VERTICAL_SLICE.md`.

## Boundaries retained

- API-key plaintext is returned once and is not stored in the control database.
- Search access does not imply source-body disclosure.
- Job payloads are tenant scoped and content addressed.
- Source paths cannot be absolute or escape the configured source root.
- Generated descriptions, embeddings, and operational paths do not enter exact graph
  identity.
- Search remains a candidate mechanism rather than compatibility proof.
- The evaluator and hidden benchmark data are not connected to this production query
  path.
- The Fly proof is one Machine by design; no HA or production-scale claim is made.

## Next measured gate

Implement PostgreSQL repositories and S3/Tigris graph-epoch storage behind the same
interfaces, then run the existing tenant, idempotency, lease-expiry, atomic-publication,
and HTTP integration suite against those adapters under concurrent workers. Only after
that passes should API and indexer become independently scaled Fly apps.
