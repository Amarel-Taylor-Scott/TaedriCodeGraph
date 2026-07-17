# l2-normalize primitive

`l2_normalize(values)` validates finite numeric values, computes the Euclidean norm with fsum, divides nonzero vectors by that norm, and preserves zero vectors.

Reference semantics:
- https://docs.python.org/3.12/library/math.html#math.fsum
- https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.normalize.html

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
