# normalize-null-marker primitive

`normalize_null_marker(value)` matches a small documented set of common missing-value strings after stripping and case folding, returning `None` for matches and preserving every non-marker string exactly.

Reference semantics:
- https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html
- https://docs.python.org/3.12/library/stdtypes.html#str.casefold

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
