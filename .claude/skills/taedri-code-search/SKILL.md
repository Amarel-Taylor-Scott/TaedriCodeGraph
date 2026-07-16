---
name: taedri-code-search
description: Search Taedri CodeGraph for reusable code, contracts, relationships, provenance, and bounded implementation context before scanning source trees or package documentation.
---

# Taedri Code Search

Use `tcg search "<intent>" --store .tcg`, inspect its query receipts, then use
`tcg context "<intent>" --store .tcg` for summaries and graph links. Fetch source
only for selected candidates with `tcg context "<intent>" --store .tcg --source`.

Inspect exact variants with `tcg representation list <qualified-name> --store .tcg`
and graph assertions with `tcg edge neighbors <qualified-name> --store .tcg`.
Search package/license metadata with `tcg representation search "<text>"
--subject-kind snapshot --store .tcg`.
Similarity proposes candidates; it does not prove compatibility, correctness,
license suitability, or safety. Preserve parallel and contradictory assertions.
