# chunk-sequence primitive

`chunk_sequence(request)` splits a list into fixed-size contiguous lists with a smaller final batch when necessary and rejects ambiguous request fields.

Reference semantics:
- https://docs.python.org/3.12/library/itertools.html#itertools.batched

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
