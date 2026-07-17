# Strict v2 live prompt-interception evidence

This directory preserves seven failure-inclusive, sanitized campaign-v2 documents
captured on 2026-07-16 in `America/New_York` (some receipt timestamps fall on
2026-07-17 UTC). The campaigns compare two plain conditions:

- **All descriptions:** the model receives the natural-language request and body-free
  descriptions of all 11 released primitives.
- **Locally selected descriptions:** deterministic local BM25-like text retrieval runs
  before the model call and supplies only positive-scoring descriptions, up to the
  configured maximum of 1, 2, 4, or 8.

The model sees no primitive source body, pack bytes, verifier inputs, expected outputs,
credential, registry primitive/release/pack identifier, or registry/pack location. A
card does include the primitive's human-readable stable name, summary, keywords, and
use cases. The model returns an opaque call-local route handle or abstains. Trusted
local code resolves a selected handle, checks the pack digest, executes the checked
pack, and compares its output with two cases withheld from the model call.

## Result in plain language

The five usage-complete Mistral campaigns produced 100 operator-captured provider-
response receipts across 50 within-campaign matched task-seed observations. Because
the same constructed tasks and seed recur at several description limits, those 50
observations reduce to 23 unique task-and-seed keys after repeated K campaigns are
deduplicated. Ninety-eight calls selected a primitive, and all 196 resulting case
executions passed. The two non-successes were explicit model abstentions in the
all-descriptions condition; no selected primitive failed a case.

Across the 50 pairs for which both conditions returned provider usage, the provider
responses reported 50,369 prompt-plus-completion tokens when all 11 descriptions were
shown and 20,248 when descriptions were selected locally: 30,121 fewer reported
selector-stage tokens, or 59.8007%. This aggregate repeats the same nine-task cohort at
several description limits and includes a two-seed K=4 campaign, so it is an
observation total, not a unique-task population estimate.

The Ollama and OpenRouter campaigns are retained even though all 12 calls failed before
a usage receipt or primitive execution was produced. A separate bounded diagnostic
afterward observed HTTP 429 from the configured Ollama cloud endpoint and HTTP 401 from
OpenRouter. Those HTTP details are operator diagnostics, not fields retroactively added
to the immutable campaign receipts.

## Every campaign

| Provider / requested model | Workload | Seeds | Maximum locally selected descriptions | All-description accepted | Locally selected accepted | All-description reported tokens | Locally selected reported tokens | Observed difference | Executed cases |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Mistral / `mistral-small-2603` | 9 constructed natural tasks | 0 | 1 | 9/9 | 9/9 | 9,063 | 2,111 | 6,952 (76.7075%) | 36/36 passed |
| Mistral / `mistral-small-2603` | 9 constructed natural tasks | 0 | 2 | 9/9 | 9/9 | 9,063 | 2,800 | 6,263 (69.1052%) | 36/36 passed |
| Mistral / `mistral-small-2603` | 9 constructed natural tasks | 0, 1 | 4 | 17/18 | 18/18 | 18,125 | 8,090 | 10,035 (55.3655%) | 70/70 passed |
| Mistral / `mistral-small-2603` | 9 constructed natural tasks | 0 | 8 | 8/9 | 9/9 | 9,062 | 5,068 | 3,994 (44.0742%) | 34/34 passed |
| Mistral / `mistral-small-2603` | 5 external-issue-derived positive tasks | 0 | 4 | 5/5 | 5/5 | 5,056 | 2,179 | 2,877 (56.9027%) | 20/20 passed |
| Ollama / `gpt-oss:20b` | 3-task portability subset | 0 | 4 | 0/3 | 0/3 | unavailable | unavailable | unavailable | no execution |
| OpenRouter / `meta-llama/llama-3.3-70b-instruct:free` | 3-task portability subset | 0 | 4 | 0/3 | 0/3 | unavailable | unavailable | unavailable | no execution |

Human-readable percentages above use conventional round-to-nearest at four decimal
places. The machine summary's integer parts-per-million field deliberately uses floor
division, so its last displayed decimal can be one unit lower.

For the K=4 two-seed campaign, seed 0 alone was 9/9 accepted in both conditions and
reported 9,063 versus 4,045 tokens, a 5,018-token (55.3680%) difference. Seed 1 was
8/9 versus 9/9 and reported 9,062 versus 4,045, a 5,017-token (55.3631%) difference.

## Fidelity and the two model abstentions

Every successful route selected the expected released primitive and every executed
case passed. The two retained Mistral non-successes were both for
`customer_ingest.deduplicate_rows` in the all-descriptions condition:

| Campaign | Seed | Outcome | Why no case ran |
|---|---:|---|---|
| K=4, two-seed | 1 | `teacher_abstained_no_suitable_candidate` | The model explicitly abstained, so fail-closed code resolved and executed nothing. |
| K=8 | 0 | `teacher_abstained_no_suitable_candidate` | The model explicitly abstained, so fail-closed code resolved and executed nothing. |

In the K=4 seed-1 pair, `stable-deduplicate` was present among all 11 descriptions at
rank 3, but the model abstained. In the paired locally selected call it was ranked first
among four descriptions, selected, and passed 2/2 cases. That is the immediate observed
difference; it does not prove that reduced context generally improves quality.

The seed-0 all-description request for this same deduplication task had the same
provider request digest, requested model, temperature, and seed in the K=1, K=2, K=4,
and K=8 campaigns. It selected the expected primitive in the first three observations
and abstained in K=8. This observed provider-response nondeterminism is why these rows
must not be read as deterministic K-specific fidelity results and why a broader
campaign needs repeated seeds and runs.

## Why v2 matters

Every campaign here passes the strict v2 parser. It validates:

- the exact task manifest and complete task × seed × two-condition matrix;
- one and only one arm for every declared task, seed, and condition;
- complete matched-pair coverage and exact content-addressed identity chains;
- unique provider-response receipts when both conditions completed;
- condition-, attempt-, task-, seed-, provider-, model-, policy-, and case-bound
  verifier occurrences rather than cloned generic verifier records;
- the same concrete reported provider deployment across a comparable pair;
- frozen prompt, harness, retrieval, execution, provider-bound, and endpoint policies.

Legacy v1 files remain readable, but they cannot detect omission of an entire undeclared
task or prove arm-specific verifier occurrence identity. They are therefore excluded
from strict-v2 counts and remain non-claimable observations.

Three separate version axes appear in the files. Campaign `format_version: 2.0.0` is
the strict campaign document described here. The `uceg:v1:` prefix is the version of
the content-addressed identity namespace, not a legacy campaign marker. Generated
measurement files currently use token-measurement schema `format_version: 1.0.0` and
`measurement_kind: prompt_interception_provider_native_v1`; each measurement records
the source campaign's `2.0.0` version under `campaign_validation`. Legacy evidence
means only a source campaign whose own `format_version` is `1.0.0`.

## External-issue workload scope

The five positive tasks were manually derived from public issues in pandas,
more-itertools, and scikit-learn. Source URLs, short source excerpts, normalized source
digests, derivation scope, and independently authored cases are in
`fixtures/prompt-interception/external-github-issues-positive-v1.json`.

This workload is more realistic than a task written solely from the primitive catalog,
but it remains a small, manually bounded positive-only retrieval set. It contains no
must-abstain negative cases, no repository modification, and no full coding trajectory.
It cannot establish recall, false-positive rate, or production distribution quality.

The checked fixture validates the issue URLs, retained excerpts, normalized source
digests, and derivation notes, but that provenance is adjacent evidence rather than a
field in the campaign manifest. The campaign itself binds each model-visible request
and hidden-case set; it does not bind a digest of the issue-source manifest. Therefore
“external-issue-derived” is a fixture-and-commit-level attribution, not a provenance
claim proven by the campaign receipt alone.

This five-task run is also not arm-order balanced. Every task has step index zero and
the campaign uses one seed, so the locally selected condition ran first in all five
pairs. The general runner counterbalances by step and seed-attempt parity, but a future
external workload needs mixed parity or additional seeds to balance execution order.

## Exact prompt contract

The system message was:

```text
Select at most one released primitive whose stated capability best satisfies the task. Route handles are opaque and primitive cards are metadata only. Reply with one JSON object, no markdown or extra keys. Select using {"selected_route_handle":"<candidate route_handle>","reason_code":"capability_match"}, or abstain using {"selected_route_handle":null,"reason_code":"no_suitable_candidate"}.
```

The user message was compact canonical JSON in this shape:

```json
{"primitive_cards":[{"keywords":["<keyword>","..."],"name":"<stable primitive name>","route_handle":"c001","summary":"<released summary>","use_cases":["<use case>","..."]}],"schema_version":"1.0.0","task_request":"<exact request from the checked fixture>"}
```

The only experimental change was which descriptions were disclosed and their
condition-local rank/handle assignment. All-description mode supplied all 11 in
canonical order. Locally selected mode supplied only positive local matches in BM25
relevance order, up to the configured maximum.

## Evidence and claim boundary

These campaigns support a narrow statement: local retrieval materially reduced
operator-captured, provider-response-reported selector prompt-plus-completion tokens in
the usage-complete Mistral runs without an observed selected-pack case failure.

They do **not** support a general, trusted, end-to-end token-savings claim. The proof
tool intentionally returns `savings_claimable=false` because the campaign files lack a
separately trusted runtime attestation and complete failure-inclusive overhead receipts.
Unresolved categories include provider-specific cached/reasoning counters and any model
tokens used for retrieval, selection outside this call, verification, tools, repair, or
later coding. Local CPU, storage, network, and verifier work are separate resource
measures. The cases were withheld from model calls but are public in the repository,
not cryptographically sealed. This is selector/context-stage evidence, not a complete
coding session or organic production traffic.

At the published Mistral Small 4 (26.03) list-price snapshot of $0.15 per million input
tokens and $0.60 per million output tokens, the K=4 two-seed receipt counters convert
arithmetically to $0.00286410 for all descriptions and $0.00135930 for locally selected
descriptions, $0.00150480 less. This is illustrative arithmetic, not an invoice or
provider-signed billing record. Source: <https://docs.mistral.ai/models/model-cards/mistral-small-4-0-26-03>.

## Reproduction

Regenerate the summaries and validate the principal K=4 campaign:

```bash
PYTHONPATH=src python tools/summarize_prompt_interception_evidence.py \
  --summary eval/results/prompt-interception-live-v2-2026-07-16/summary.json \
  --csv eval/results/prompt-interception-live-v2-2026-07-16/summary.csv \
  eval/results/prompt-interception-live-v2-2026-07-16/*.campaign.json

PYTHONPATH=src python tools/prove_token_savings.py \
  --campaign eval/results/prompt-interception-live-v2-2026-07-16/mistral-small-2603-k4-seeds0-1.campaign.json
```

`summary.json` is the detailed machine-readable index; `summary.csv` is its compact
campaign table. Each usage-complete Mistral campaign also has a generated
`*.measurement.json` file. Those files are the proof tool's exact fail-closed output:
they reconcile the serialized receipts and observed token differences while retaining
`savings_claimable=false`. The two provider-failure campaigns correctly cannot produce
a token measurement because they contain no provider usage.

The campaign files are immutable sanitized outputs. Their exact SHA-256 values are:

| File | SHA-256 |
|---|---|
| `mistral-small-2603-k1-seed0.campaign.json` | `8e95e4994d282e356d02e0df4187db51f53242fabb3ea81df2ee55875213002f` |
| `mistral-small-2603-k2-seed0.campaign.json` | `45ef08f5d15b8320000de76e5d49357dae00988e0927bc5829d2364b4b8e68fe` |
| `mistral-small-2603-k4-seeds0-1.campaign.json` | `4d01252103dedfa20a000e5de719ee1e3bb296ecd97e5447a42428b9e03d4ab6` |
| `mistral-small-2603-k8-seed0.campaign.json` | `46018cee85ce2273cc0dce905803bdcc1ce3f567a2a36510d3ab7dd63daa8a78` |
| `mistral-small-2603-external-issues-k4-seed0.campaign.json` | `43620a414eae7c191856c01744a97cad7d174186b5289a99887e7fc7b4e585b9` |
| `ollama-gpt-oss-20b-k4-3tasks-seed0.campaign.json` | `f5565bb6dda9e63a4a366ff4b3c82e6527d68c72ec76b8821967f480397b178f` |
| `openrouter-llama-3.3-70b-k4-3tasks-seed0.campaign.json` | `f207a9379c923bc50fdb15687a35361b5176f4ba2cc61e772f79f9c0e0448c7e` |
