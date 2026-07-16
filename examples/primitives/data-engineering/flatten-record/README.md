# flatten-record primitive

`flatten_record(request)` turns nested JSON objects into flat path-keyed records, keeps lists as leaf values, and fails rather than overwriting colliding keys.

Reference semantics:
- https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
