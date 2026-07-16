# Registry API

The modular API now exposes tenant-scoped primitive staging, optimistic branch updates,
immutable tags, content-deduplicated forks, internal exact-revision candidate packs,
released-primitive search/download, append-only review transitions, and release
revocation. SQLite is the tested single-node adapter; the PostgreSQL/object-store
contract is defined but does not yet have a production repository adapter.

The active intake conformance contract keeps candidate lifecycle events append-only,
requires independent evidence and policy for curation, blocks producer self-release,
and requires verified license evidence, executable acceptance, deduplication,
queryability, assurance-tier separation, and explicit authorization before public
release. A staged or curated candidate is not returned by public search, resolution, or
pack endpoints.

The first deployment runs this contract inside the modular API process. It becomes
an independent service only after a security, scaling, failure-domain, or ownership
gate is measured. It never decides whether a primitive is correct or authorized to run.
