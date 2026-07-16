# normalize-column-name primitive

`normalize_column_name(value)` applies Unicode NFKC normalization and case folding, converts runs of non-alphanumeric characters to underscores, and rejects empty results.

Reference semantics:
- https://docs.python.org/3.12/library/unicodedata.html#unicodedata.normalize
- https://pandas.pydata.org/docs/reference/api/pandas.Series.str.normalize.html

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
