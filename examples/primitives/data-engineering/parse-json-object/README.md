# parse-json-object primitive

`parse_json_object(value)` uses the standard-library JSON decoder with hooks that reject duplicate keys and non-finite constants, then requires a top-level object.

Reference semantics:
- https://docs.python.org/3.12/library/json.html#json.loads

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
