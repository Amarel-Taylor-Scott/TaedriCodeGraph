# Services

Independently deployable orchestration and serving processes. Services consume
versioned package contracts and never redefine shared wire semantics. A folder marks
an ownership/deployment boundary, not a requirement to deploy a microservice on day one.

`worker-runtime` defines the active leased-job conformance contract. The first hosted
topology keeps it in the indexer process group; it becomes independently deployable only
after a measured isolation or scaling gate.

`benchmark-worker` is a deliberate trust-boundary exception: even in the first hosted
topology it runs as a separately credentialed evaluator so hidden tests, gold patches,
and cold holdouts cannot flow into production ingestion or retrieval.

The executable worker split is now explicit:

- `discovery-worker` normalizes allowlisted registry polls and verified webhooks;
- `ingestion-worker` acquires bounded immutable artifacts and publishes graph epochs;
- `primitive-worker` creates reviewable candidates and descriptors; and
- `benchmark-worker` evaluates frozen matched lanes behind a sealed-oracle boundary.

They share `src/taedri_codegraph/pipelines` operation contracts. Separate folders do not
require separate deployment until a trust, secret, scaling, or failure-domain gate does.
