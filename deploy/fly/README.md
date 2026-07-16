# Fly.io proof deployment

These manifests make the current SQLite/CAS slice runnable on one Fly Machine and
host the static explorer separately. They are deliberately named **single-node POC**:
the attached volume is not the production source of truth described by
`deploy/topology.v1.json`, and the API must not be horizontally scaled while it uses
this adapter.

## POC sequence

Choose app names at deploy time; none are committed into the reusable manifests.

```bash
fly apps create <api-app>
fly volumes create taedri_data --app <api-app> --region iad --size 10
fly deploy --app <api-app> --config deploy/fly/single-node-poc.fly.toml

fly ssh console --app <api-app> --command \
  "tcg admin bootstrap --control /data/control.sqlite --tenant demo --name Demo --graph-store /data/graph"

fly apps create <frontend-app>
fly deploy --app <frontend-app> --config deploy/fly/frontend.fly.toml
```

The bootstrap command returns the API token once. Put it in a password manager; do
not put it in Git, a Fly manifest, frontend source, or logs. Configure the API's exact
frontend origin with a `--cors-origin` argument before using the browser console.

## Production promotion gate

Do not call this HA or multi-tenant production infrastructure until all of the
following replace the local proof adapters:

- PostgreSQL control-plane implementation using `deploy/postgres/001_control_plane.sql`;
- S3/Tigris-backed immutable CAS and epoch publication with a bounded Machine cache;
- separate API, indexer, evaluator, model-gateway, and sandbox Fly apps;
- OIDC browser sessions and tenant-scoped envelope encryption for provider tokens;
- backups, restore exercises, telemetry, rate limiting, and failure-injection evidence.
