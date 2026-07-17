# Live prompt-interception pilot evidence

This directory preserves six sanitized live-provider campaigns run on
2026-07-16 in `America/New_York` (their receipt timestamps cross into
2026-07-17 UTC). The experiment measures the **model-selection and context
stage only**. It does not measure the tokens for a complete coding session.

## What the two conditions mean

Each task was sent to the same requested provider/model under two conditions:

- **A — all descriptions:** the model sees descriptions of all 11 available
  primitives.
- **B — locally selected descriptions:** before the model call, deterministic
  local retrieval selects up to the top K descriptions and the model sees only
  those descriptions.

BM25 is the local, deterministic keyword-ranking method used to score how well
the task text matches each primitive description. Here, K is a maximum: the
model can see fewer than K descriptions when fewer eligible local matches are
returned. The exact candidate-count distributions are in `summary.json`.

After the model selected a route handle, the harness resolved the corresponding
checked `.tcgpack`, executed it, and checked its output against two cases that
were not included in the model call.

## Observed selector-stage results

Token counts below are the providers' native prompt plus completion counts.
“Difference” is A minus B for these selector calls; the percentage uses A as
the denominator. It is a descriptive observation, not a promoted token-savings
claim.

| Provider / requested model | Tasks | Max K | A: all 11 descriptions | B: locally selected descriptions | Observed difference | Accepted selections, A / B | Executed checks passed, A / B |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mistral / `mistral-small-2603` | 9 | 1 | 9,062 | 2,111 | 6,951 (76.70%) | 8/9 / 9/9 | 16/16 / 18/18 |
| Mistral / `mistral-small-2603` | 9 | 2 | 9,062 | 2,800 | 6,262 (69.10%) | 8/9 / 9/9 | 16/16 / 18/18 |
| Mistral / `mistral-small-2603` | 9 | 4 | 9,063 | 4,045 | 5,018 (55.37%) | 9/9 / 9/9 | 18/18 / 18/18 |
| Mistral / `mistral-small-2603` | 9 | 8 | 9,062 | 5,068 | 3,994 (44.07%) | 8/9 / 9/9 | 16/16 / 18/18 |
| Ollama / `gpt-oss:20b` | 3 | 4 | 3,166 | 1,587 | 1,579 (49.87%) | 3/3 / 3/3 | 6/6 / 6/6 |

The four Mistral rows are independent live campaigns over the same nine-task
cohort at K=1, 2, 4, and 8. The Ollama row is a separate three-task subset.
Totals across rows therefore count repeated task observations and should not be
read as a unique-task population estimate. The sixth campaign was a failed
bounded portability smoke and is deliberately excluded from the comparison
table because it returned no provider usage receipts.

## Every non-success

No failure was discarded. Three model-selection calls in condition A returned
an explicit abstention on the same deduplication task in three independently
executed K campaigns. Condition B selected and verified a working checked pack
for that task in each campaign.

A separate one-task portability smoke requested `mistral-large-latest` with a
60-second harness call bound. Neither condition returned a usable provider
result within that contract. Both calls are retained as `provider_failed` with
`provider_modelprovidererror`; neither produced a usage receipt or reached pack
execution. No fidelity or token comparison is possible for this campaign, and
it was not retried.

| Campaign | Task | Condition | Status | Error code | Call receipt |
|---|---|---|---|---|---|
| Mistral K=1 | `customer_ingest.deduplicate_rows` | A — all 11 descriptions | `teacher_rejected` | `teacher_abstained_no_suitable_candidate` | `uceg:v1:prompt_interception_campaign_arm_receipt:gam7zajwup22da56w44ix6aela6sygrvaxpcy7nyvq4cezsdnkmq` |
| Mistral K=2 | `customer_ingest.deduplicate_rows` | A — all 11 descriptions | `teacher_rejected` | `teacher_abstained_no_suitable_candidate` | `uceg:v1:prompt_interception_campaign_arm_receipt:ofs7huhxkramduqxo4iwo7lqljup4mvxnyoq6ngwzbinjaxzmfba` |
| Mistral K=8 | `customer_ingest.deduplicate_rows` | A — all 11 descriptions | `teacher_rejected` | `teacher_abstained_no_suitable_candidate` | `uceg:v1:prompt_interception_campaign_arm_receipt:75tastbp6faafwb3rjybna2n44zfs3bb2ftp3it4cc7xoy5xw3xa` |
| Mistral Large bounded smoke | `warehouse_load.flatten_events` | A — all 11 descriptions | `provider_failed` | `provider_modelprovidererror` | `uceg:v1:prompt_interception_campaign_arm_receipt:poutmhoeajpjpjkrglgtlnpvwcjswqw73gx5b2y2p33c2b4rfxtq` |
| Mistral Large bounded smoke | `warehouse_load.flatten_events` | B — locally selected descriptions, max K=4 | `provider_failed` | `provider_modelprovidererror` | `uceg:v1:prompt_interception_campaign_arm_receipt:cizvciwvgoh5jtdyjpd63zmchti6tqblzqyabgiy4qxzw4wovfpq` |

The three abstentions are model-level selection outcomes, not transport or API
failures. The two bounded-smoke failures are provider-call outcomes. The
original campaign files retain the complete sanitized records, including
status, errors, available usage receipts, route decisions, pack handles, and
verification receipts.

## Evidence manifest

The campaign JSON files are byte-for-byte copies of the sanitized campaign
outputs. SHA-256 values below are computed over the copied files in this
directory.

| File | Campaign receipt | SHA-256 |
|---|---|---|
| `mistral-small-2603-k1-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:upf5wjctfw4l6rrdnewnywzuwmhsbygsqv47pkw6xqv6pmommrca` | `474c86311aec470eb3120bd8006dae62fadd8d9285bb10139a4e64b5b151c6fb` |
| `mistral-small-2603-k2-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:jrkaqpwra2yylf2h2ciu3dim42cswexsre2cyaeyvmmnqlod2jjq` | `9cb70c802d91bfb9e26b1d90f98e1ae2f7b7fa099e98c2b4a5d2e2159ff92ac2` |
| `mistral-small-2603-k4-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:cr7z5tpvenpwkjudfur5c27gc2ulqpm3f3rniio2q7g2fs46ucta` | `a2dac5e227077ca80058640a05e01acb154d21779b81bae174dc51f26b976ce2` |
| `mistral-small-2603-k8-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:kxw2wiexams3x4zocp2smjv75aasdwqnvz2to22xugbn2at66eyq` | `b0bd08dc8d80bc09c4ca031a55b24f27066e4a0288671679a64ccdd83787c139` |
| `mistral-large-latest-k4-1task-bounded-smoke-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:kdqgjsbajlbhan2jfexyidy5ptgwfbzlj4j6arqfj44v5hl72peq` | `f7e8cc77ed5fca18ef3cace1e8f5768e35ee4f5f9aba21dea8057d0d32787c31` |
| `ollama-gpt-oss-20b-k4-3tasks-seed0.campaign.json` | `uceg:v1:prompt_interception_campaign_receipt:3cxsb6bvw5ejf22ujnrgv44muuo5v3waudndjit2mfuzgw4tbz5q` | `9a0cfe60578707d29f49ee3d05a19736a325dddb0811976fd280d44719a1ad58` |

`summary.json` is the machine-readable index, and `summary.csv` is its compact
campaign-level view. Both are derived from the campaign JSON by:

```bash
python tools/summarize_prompt_interception_evidence.py \
  eval/results/prompt-interception-live-pilot-2026-07-16/*.campaign.json \
  --summary eval/results/prompt-interception-live-pilot-2026-07-16/summary.json \
  --csv eval/results/prompt-interception-live-pilot-2026-07-16/summary.csv
```

## Scope and proof boundary

This is a constructed, in-catalog cohort of plausible natural-language tasks,
not organic production traffic. The two verification cases per successful
selection were hidden from the model call, but they are stored in a public
fixture and are not cryptographically sealed. Execution is real checked-pack
execution, and token accounting comes from provider-native response fields.

These receipts do **not** by themselves establish a causal or generally
applicable reduction, and they do not make a verified `token_savings` claim.
Only the separate token-savings integrity evaluator, supplied with its trusted
evidence resolver and exact receipt bindings, can promote an eligible result.
