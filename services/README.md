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
