# Agent contract

Work from evidence and keep the graph's planes separate.

- Never import or execute analyzed package code in the syntax analyzer.
- Never put an embedding, generated description, confidence score, or mutable path in
  an exact identity key unless the relevant contract explicitly requires it.
- Store the full canonical key behind every digest and validate it on read.
- Preserve parallel assertions and contradictions; do not overwrite them during
  reconciliation.
- Treat missing values as unknown unless a registered descriptor says otherwise.
- Add new semantics through namespaced, versioned descriptors and conformance tests.
- Build search indexes as disposable projections from immutable epoch facts.
- Add golden or poison-corpus coverage with every analyzer or compatibility change.
- Do not add an unbounded all-pairs compatibility operation.

Before handing off a change, run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```
