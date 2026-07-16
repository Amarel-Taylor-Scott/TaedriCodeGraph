# Ingestion worker

The active implementation is the `tcg worker run` process backed by `JobRunner` and the
versioned `platform_pipeline_catalog`. It executes only cataloged operations, requires a
matching job kind and capabilities, bounds network acquisition, verifies artifact
digests, analyzes target code without import or execution, writes a candidate epoch, and
publishes it atomically only after validation.

Network-enabled workers should be isolated from source-mounted workers in hosted
deployments. PyPI and GitHub credentials are optional acquisition secrets and must not be
available to query or browser processes.
