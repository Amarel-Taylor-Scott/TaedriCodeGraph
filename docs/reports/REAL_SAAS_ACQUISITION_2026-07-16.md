# Real authenticated SaaS acquisition — 2026-07-16

This run used the official `usaddress==0.5.16` wheel and the immutable GitHub
commit `aa7699b53a0843fc443f9e87285b88cbd9eaf50a`. Both were acquired over the network through the same
allowlisted worker operations exposed by the authenticated API. Target code was
inspected with AST/ZIP logic and was never imported, installed, built, or executed.

## Result

- 2 persistent tenant jobs succeeded.
- 2 independently versioned graph mounts were published and searched together.
- 2 acquisition receipts retain registry/API metadata and artifact digests.
- 2 graph epochs round-tripped into content-addressed backup manifests.
- Every search result identifies its graph mount, exact epoch, local query receipt, and federation receipt.

## Published graph metrics

| Graph | Files | Entities | Relations | Representations | Store bytes |
|---|---:|---:|---:|---:|---:|
| `pypi-usaddress` | 1 | 101 | 614 | 1,886 | 18,231,398 |
| `git-usaddress` | 10 | 417 | 2,282 | 8,075 | 78,543,275 |

## Retrieval probes

| Query | Graph | Expected | Rank@10 | Latency ms |
|---|---|---|---:|---:|
| parse a street address into labeled components | `pypi-usaddress` | `usaddress.parse` | 1 | 58.903 |
| tag address components and determine address type | `pypi-usaddress` | `usaddress.tag` | 1 | 45.277 |
| tokenize an address string | `pypi-usaddress` | `usaddress.tokenize` | 1 | 46.165 |
| parse a street address into labeled components | `git-usaddress` | `usaddress.parse` | 5 | 53.858 |
| tag address components and determine address type | `git-usaddress` | `usaddress.tag` | 2 | 50.257 |
| tokenize an address string | `git-usaddress` | `usaddress.tokenize` | 1 | 53.451 |
| parse a street address into labeled components | `all` | `usaddress.parse` | 1 | 57.564 |
| tag address components and determine address type | `all` | `usaddress.tag` | 1 | 53.652 |
| tokenize an address string | `all` | `usaddress.tokenize` | 1 | 51.913 |

These are transparent probes, not an efficacy claim. The corpus contains two
representations of one project, and no external LLM was used. Retrieval proposes
candidates; compatibility, licensing, policy, and independent verification still decide.

## Artifacts

- `eval/results/saas-real-acquisition-2026-07-16/run.json`
- `eval/results/saas-real-acquisition-2026-07-16/acquisitions.jsonl`
- `eval/results/saas-real-acquisition-2026-07-16/query-results.csv`
- `eval/results/saas-real-acquisition-2026-07-16/graphs/` as JSON, Mermaid, and GraphML
- `eval/results/saas-real-acquisition-2026-07-16/charts/` as SVG and PNG
- `apps/explorer/real-acquisition-console.html` as a self-contained dashboard
