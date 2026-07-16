# Retrieval

Owns query compilation, exact/lexical/facet/scalar lanes, multi-resolution LSH, vector
space adapters, graph candidates, calibrated fusion, progressive disclosure, and
explainable receipts. Candidate scores do not establish compatibility.

Current extraction sources: `query.py`, `primitives/search.py`, `discovery/triggers.py`,
`fingerprints.py`, `representations.py`, and `portfolio.py`. The authenticated API and
MCP bridge expose adaptive search explicitly while preserving the existing hybrid
ranking as the backward-compatible SDK default.
