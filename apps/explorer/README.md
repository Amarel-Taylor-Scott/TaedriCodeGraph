# Explorer application

The active [`index.html`](index.html) live console connects to the authenticated API,
submits source-analysis and primitive-factory jobs, switches graph mounts, displays
persistent worker/candidate state, runs hybrid search, and shows raw receipts. It
deliberately keeps the API token only in page memory. The
static frontend image can be run independently from the API and worker containers.

The active self-contained [`registry-console.html`](registry-console.html) POC filters
347 real-source primitive candidates, shows selected capsule/search details, worker and
prompt-session receipts, and the machine-readable business-model hypothesis. It makes
no network requests and can be opened directly after cloning the repository.

The broader architecture simulator remains at
[`docs/visuals/architecture-explorer.html`](../../docs/visuals/architecture-explorer.html).

The self-contained [`benchmark-console.html`](benchmark-console.html) shows the
four matched assistance lanes, sealed-evaluation boundary, claim gate, conformance
receipts, real campaign tracks, and failure-inclusive unit-economics contract. Its
embedded run is explicitly a no-model conformance fixture and cannot be read as a
product-quality result.

Production UI work still needs an OIDC/BFF session in place of developer API-token
entry, pagination, virtualized graphs, deeper accessibility testing, and hosted
end-to-end browser verification.
