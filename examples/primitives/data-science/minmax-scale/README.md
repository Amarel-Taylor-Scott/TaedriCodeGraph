# minmax-scale primitive

`minmax_scale(values)` validates a finite vector, fits its observed minimum and maximum, and maps the values linearly into `[0.0, 1.0]`, with constants mapped to zero.

Reference semantics:
- https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.MinMaxScaler.html

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
