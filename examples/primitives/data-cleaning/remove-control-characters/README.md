# remove-control-characters primitive

`remove_control_characters(value)` filters characters whose Unicode general category is Cc; format, mark, separator, symbol, punctuation, number, and letter categories remain.

Reference semantics:
- https://docs.python.org/3.12/library/unicodedata.html#unicodedata.category
- https://www.unicode.org/reports/tr44/

This is a complete, dependency-free, deterministic capsule: source, contract, examples, tests, runtime lock, license evidence, provenance, interface graph, and searchable capability labels are all present and independently validated.
