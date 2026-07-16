# Primitive generation worker

`generate_primitive_candidates` is the working AST-only operation for source-mounted
Python. It creates source and contract capsules, descriptors, fingerprints, graph
neighborhoods, candidate submissions, provenance, and an immutable generation receipt.
Generation ends at `indexed_candidate`; no generated candidate is publicly searchable
or downloadable.

`verify_primitive_release` is the separate working acceptance operation. A worker must
be started with the explicit `primitive-release-v1` capability before it can lease that
job. The current verifier accepts complete Python 3.12 capsules from trusted source,
materializes the digest-bound pack in a temporary directory, denies network and child
process calls through the Python audit hook, executes every declared example and test
vector with a timeout, and records normalized outputs and proof digests. The release
transaction then independently checks capsule completeness, source deduplication,
queryability, assurance-tier identity separation, and authorization.

This is not a hostile-code sandbox. Untrusted execution requires a separately isolated
runtime with no secrets, read-only inputs, egress denial, resource limits, and a signed
result handoff. Other languages may be inventoried today, but release fails closed until
a real verifier for that language/runtime is registered.

Future deterministic labelers, classifiers, model descriptions, behavioral probes, and
embeddings register as versioned mechanisms. Dynamic depth activates them only when
cheap representations cannot distinguish a candidate or when a requested decision needs
their facet. No model output can overwrite exact facts or silently release a primitive.
