# Shared kernel

Owns canonical encoding, content addressing, exact sidecar identity, typed value
envelopes, subject references, generation attempts, assertions, and lineage
primitives. It must not depend on analyzers, databases, services, or agent harnesses.

Current extraction sources: `canonical.py`, `identity.py`, and the generic records in
`contracts.py`.
