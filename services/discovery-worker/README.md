# Discovery worker

This process boundary polls approved registries or accepts verified webhook deliveries,
then emits `SourceDiscoveryEvent` records. `SourceDiscoveryRouter` allowlists the source,
retains the source/event identity and payload digest, selects the versioned operation
contract, derives worker capabilities, and enqueues one tenant-scoped idempotent job.

The working reference supports PyPI release and immutable GitHub commit events. A hosted
adapter must verify webhook signatures before constructing the event, deduplicate by the
provider delivery ID, request only subscribed event types, return quickly after durable
enqueue, apply registry rate limits, and never treat arbitrary scraped text as executable
source. Poll cursors and webhook secrets remain deployment state, not primitive facts.
