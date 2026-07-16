---
name: taedri-code-search
description: Search a Taedri CodeGraph before reading broad source trees. Use when locating reusable code, implementations, contracts, relationships, provenance, or alternatives in a published .tcg epoch, and when a coding task would otherwise require scanning many files or external package docs.
---

# Taedri Code Search

Use the graph for candidate selection and evidence navigation. Similarity is not
proof of compatibility, correctness, licensing suitability, or safe execution.

## Workflow

1. Confirm a published graph exists with `tcg epoch list --store .tcg`.
2. Search broadly with `tcg search "<intent>" --store .tcg --limit 10`.
3. Read each result's `query_receipt`; note the exact, lexical, blocking, and vector
   lanes that contributed. Apply facet filters when language or entity kind matters.
4. Request selection-level context with
   `tcg context "<intent>" --store .tcg --limit 5`.
5. Inspect graph assertions or parallel variants when a candidate matters:
   `tcg edge neighbors <qualified-name> --store .tcg` and
   `tcg representation list <qualified-name> --store .tcg`.
   Search artifact or license variants with
   `tcg representation search "<text>" --subject-kind snapshot --store .tcg`.
6. Only then request bounded implementation text with
   `tcg context "<intent>" --store .tcg --limit 3 --source`.
7. Verify the selected code's contract, version, evidence, and license before reuse.
8. When the harness supports Taedri session receipts, retain request digests, search and
   materialization receipts, model attempts, verification, and acceptance or abstention.
   Do not persist raw prompts or source bodies unless an explicit capture policy allows it.

For MCP-capable harnesses, use `search_code`, `get_code_context`, `get_entity`,
`get_neighbors`, `list_representations`, `search_metadata`, and
`find_structural_candidates` from the Taedri CodeGraph server.

Do not treat a missing representation as false. Do not merge contradictory model
or labeler outputs. Prefer source-backed or verified assertions, and report when a
decision relies only on inferred or similarity-based evidence.
