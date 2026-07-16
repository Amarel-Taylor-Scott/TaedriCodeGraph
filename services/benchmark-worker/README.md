# Benchmark worker

Owns the isolated evaluation controller that leases `benchmark` jobs, supplies only
lane-authorized context to a frozen model harness, executes outputs in a sandbox,
hands sealed oracles directly to an independent verifier, and emits immutable run
receipts. It must use separate credentials, storage namespaces, and indexes from
production ingestion and retrieval.

The current POC schedules jobs and validates external runner receipts in
`src/taedri_codegraph/benchmarking.py`. Provider, benchmark-suite, and sandbox adapters
remain explicit deployment integrations; no external model is called by the
conformance fixture.
