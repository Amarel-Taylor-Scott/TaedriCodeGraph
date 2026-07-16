# Taedri CodeGraph working rules

Read `AGENTS.md` first. Keep exact facts, evidence, compatibility assessments,
descriptions, and search projections distinct. Prefer a tested vertical slice over
unconnected scaffolding. Source bodies are resolved only after selection, and target
package code is never executed by the default analyzer.

Use the `taedri-code-search` project skill when `.tcg` is available. Start with
`tcg search` and `tcg context`; add `--source` only for selected candidates. Read
query receipts and representation provenance, and never equate retrieval similarity
with compatibility, correctness, or license suitability.
