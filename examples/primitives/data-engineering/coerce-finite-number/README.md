# coerce-finite-number primitive

`coerce_finite_number(value)` strips surrounding whitespace, preserves integer syntax with int, parses other accepted syntax with float, and rejects every non-finite result.

Reference semantics:
- https://docs.python.org/3.12/library/functions.html#float
- https://docs.python.org/3.12/library/math.html#math.isfinite

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
