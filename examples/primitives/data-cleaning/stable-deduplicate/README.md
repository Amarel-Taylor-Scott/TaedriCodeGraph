# stable-deduplicate primitive

`stable_deduplicate(values)` removes repeated finite JSON values by canonical representation while retaining each first occurrence and its original value.

Reference semantics:
- https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html
- https://docs.python.org/3.12/library/json.html#json.dumps

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
