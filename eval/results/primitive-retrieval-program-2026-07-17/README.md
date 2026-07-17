# Primitive retrieval program benchmark

Status: **passed**

This deterministic benchmark compares the legacy integer BM25 shortlister with
`taedri.retrieval.primitive_cards@1.0.0` over 31 checked body-free catalog
requests (26 positive and 5
unsupported). It made zero model and semantic calls.

| Measure | Legacy BM25 | Retrieval program |
|---|---:|---:|
| Positive rank-1 hits | 25 / 26 | 26 / 26 |
| Positive hits at K=4 | 26 / 26 | 26 / 26 |
| Unsupported abstentions | 3 / 5 | 5 / 5 |
| Returned candidates | 83 | 34 |

The program returned 49 fewer candidates
(59.04% on this fixture) while improving rank-1 selection by
1 case and grounded abstention by
2 cases. Exact-name requests stop after the hot
exact path; broader requests spend additional deterministic cost only as needed. Every
path attempt, skip, candidate contribution, query digest, and program digest is retained
in `executions.jsonl`.

This is a small constructed retrieval benchmark. It does not establish corpus-wide
ranking quality, semantic-model quality, end-to-end coding success, or token/cost
savings.
