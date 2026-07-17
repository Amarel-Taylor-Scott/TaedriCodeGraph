# normalize-iso-datetime primitive

`normalize_iso_datetime(value)` parses a timezone-aware ISO 8601 timestamp with the Python 3.12 standard library, converts it to UTC, and emits seconds or six-digit microseconds with a trailing `Z`.

Reference semantics:
- https://docs.python.org/3.12/library/datetime.html#datetime.datetime.fromisoformat
- https://www.rfc-editor.org/rfc/rfc3339

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
