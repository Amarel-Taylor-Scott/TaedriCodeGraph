# Benchmark worker

Owns the isolated evaluation controller that leases `benchmark` jobs, supplies only
lane-authorized context to a frozen model harness, executes outputs in a sandbox,
hands sealed oracles directly to an independent verifier, and emits immutable run
receipts. It must use separate credentials, storage namespaces, and indexes from
production ingestion and retrieval.

The current POC schedules jobs and validates external runner receipts in
`src/taedri_codegraph/benchmarking.py`. The bounded Ollama native adapter emits real
runtime usage receipts and is protocol-tested against a local fake server. A reachable
runtime is still required for real-model evidence; benchmark-suite and isolated sandbox
adapters remain explicit deployment integrations. The checked-in conformance fixture
does not call an external model.

`benchmark_pipeline_catalog()` makes freeze, lane execution, sealed verification,
paired comparison, claim, and promotion stages machine-readable. It labels local report
compilation as working, external model/sandbox execution as contractual, and automatic
representation promotion as planned so orchestration cannot mistake a documented stage
for an available capability.
