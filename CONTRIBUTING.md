# Contributing

Changes should preserve the invariants in `AGENTS.md`, add focused tests, and avoid
new runtime dependencies unless measurement justifies them. New entity kinds,
predicates, feature families, compatibility axes, fingerprints, descriptions, or
models must use namespaced versioned descriptors; they must not require nullable
columns in the canonical kernel.

Run the full standard-library test suite before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```
