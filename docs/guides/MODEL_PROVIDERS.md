# Model providers, live smokes, and matched evidence

Status: bounded adapters, offline conformance tests, a provider-injected two-condition
campaign library, a dry-run-by-default operator CLI, and sanitized live Mistral/Ollama
pilot receipts are checked in. The checked pilot uses legacy campaign format 1.0.0;
new runs use strict format 2.0.0. Neither is a whole-coding-session efficacy result.

Taedri currently has four non-streaming chat adapters in
`src/taedri_codegraph/model_providers.py`:

| Adapter | Endpoint | Authentication | Provider-reported usage retained |
|---|---|---|---|
| `OllamaChatProvider` | native `POST /api/chat`, local or Ollama Cloud | none for the ordinary local API; optional bearer token for a protected host or direct cloud access | prompt and completion tokens, four Ollama duration fields, model, and finish reason |
| `MistralChatProvider` | `POST https://api.mistral.ai/v1/chat/completions` | bearer API key | prompt and completion tokens, model, and finish reason |
| `OpenRouterChatProvider` | `POST https://openrouter.ai/api/v1/chat/completions` | bearer API key | prompt and completion tokens, model, and normalized finish reason |
| `OpenAICompatibleChatProvider` | caller-supplied `/chat/completions` root | optional bearer token | the compatible response's prompt and completion tokens, model, and finish reason |

The generic compatible adapter is a wire-protocol integration point, not a claim that
every OpenAI-compatible server behaves identically. The Mistral and OpenRouter
subclasses freeze provider identifiers, endpoint defaults, usage-source labels, and
credential requirements. Mistral maps `seed` to its documented `random_seed` field;
the other compatible adapters use `seed`.

Official protocol references:

- [Ollama chat API](https://docs.ollama.com/api/chat),
  [authentication](https://docs.ollama.com/api/authentication),
  [Cloud guide](https://docs.ollama.com/cloud), and
  [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility);
- [Mistral Chat API](https://docs.mistral.ai/api);
- [OpenRouter API overview](https://openrouter.ai/docs/api_reference/overview) and
  [authentication](https://openrouter.ai/docs/api_reference/authentication).

## Bounded request and receipt contract

All four adapters require a positive timeout and response-byte limit, disable
streaming, validate message roles, and allow an explicit seed, temperature, and maximum
completion-token count. The defaults are a 300-second timeout and a 16 MiB response
limit; a smoke should normally choose smaller values. An HTTP error reports the
provider and status, not the remote response body. Transport errors report only their
exception class.

Every non-loopback provider origin must use HTTPS. Plain HTTP is accepted only for
`localhost`, an IPv4 loopback address, or an IPv6 loopback address so a developer can
use a local Ollama or compatible server. The shared authenticated transport does not
follow redirects: this prevents an API or provider origin from forwarding an
`Authorization` header to another host or downgrading an authenticated request. A 3xx
response is terminal and must be handled without replaying the credential.

`ModelUsageReceipt` is a content-addressed, secret-free record containing:

- provider, provider API, usage source, endpoint origin, requested model, and reported
  model;
- digests of the canonical request, canonical response, and assistant content;
- start/completion timestamps and measured wall time;
- provider-reported prompt and completion tokens;
- finish reason and, for Ollama, its native nanosecond phase durations.

The request prompt and assistant text are not copied into the receipt. A credential is
added only to the HTTP header after request bytes are canonicalized, so it cannot enter
the request digest. Credentials are also excluded from receipts, object
representations, and adapter-generated errors. The returned `ChatResult` still contains
assistant content for the caller; receipt-only runners must avoid printing or
persisting that field.

"Provider-reported" is deliberately narrower than "independently verified." Ollama
reports its native `prompt_eval_count` and `eval_count`. Mistral reports usage on its
own chat response. OpenRouter normalizes upstream responses and documents that its
token counts use the selected model's native tokenizer. Taedri does not recompute these
figures with a local tokenizer, and a usage receipt does not prove output correctness.

## Credential input: environment or interactive stdin

Prefer a deployment secret manager that injects a narrowly scoped environment
variable into only the provider worker. For an interactive local smoke, read a key from
the terminal's stdin with echo disabled, export it only for the child process, and
unset it immediately afterward:

```bash
IFS= read -r -s TAEDRI_PROVIDER_KEY
printf '\n'
export TAEDRI_PROVIDER_KEY
# Run exactly one explicitly selected smoke here.
unset TAEDRI_PROVIDER_KEY
```

Map that short-lived value to the provider-specific variable used by the runner, such
as `TAEDRI_OLLAMA_TOKEN`, `TAEDRI_MISTRAL_API_KEY`, or
`TAEDRI_OPENROUTER_API_KEY`. A custom runner may instead read one line from stdin and
pass the value directly to `api_key=` without placing it in the environment; it must
not log, serialize, echo, or retain the value.

Never place a key in a prompt, command argument, URL, committed `.env` file, benchmark
record, artifact handle, receipt, exception message, or model-visible tool result.
Environment variables are convenient, not a durable secret store; keep the worker
scope and lifetime small. No credential value belongs in this repository or in a
campaign evidence bundle.

## Ollama: local and cloud

### Local model

The committed smoke tool makes one native chat call, uses seed `0` and temperature
`0`, caps the completion, and can emit only the receipt:

```bash
export TAEDRI_LIVE_MODEL_SMOKE=1
export TAEDRI_OLLAMA_URL=http://127.0.0.1:11434
export TAEDRI_OLLAMA_MODEL='<pinned-local-model-id>'
if [ "${TAEDRI_LIVE_MODEL_SMOKE:-0}" != 1 ]; then exit 2; fi
python tools/smoke_ollama_provider.py \
  --receipt-only \
  --max-completion-tokens 64
```

The ordinary local API requires a reachable Ollama server but no API key. Pin the
installed model bytes or deployment identity outside the friendly model alias if the
receipt will be used in a matched campaign.

### Ollama Cloud through the local host

Ollama can offload a cloud model while the client continues to call the local
`http://127.0.0.1:11434/api/chat` endpoint. Authenticate the Ollama installation with
the official `ollama signin` flow, select a current cloud model, and run the same smoke.
In this mode Taedri does not need the cloud key because the local Ollama process owns
authentication. The receipt's endpoint still identifies the local origin, so the
campaign must separately freeze and attest the cloud model/deployment identity.

### Direct Ollama Cloud API

For direct access, use the official `https://ollama.com` origin and inject an API key
as the smoke tool's optional bearer token:

```bash
export TAEDRI_LIVE_MODEL_SMOKE=1
export TAEDRI_OLLAMA_URL=https://ollama.com
export TAEDRI_OLLAMA_MODEL='<pinned-cloud-model-id>'
IFS= read -r -s TAEDRI_OLLAMA_TOKEN
printf '\n'
export TAEDRI_OLLAMA_TOKEN
if [ "${TAEDRI_LIVE_MODEL_SMOKE:-0}" != 1 ]; then exit 2; fi
python tools/smoke_ollama_provider.py \
  --receipt-only \
  --max-completion-tokens 64
unset TAEDRI_OLLAMA_TOKEN
```

Ollama Cloud aliases and availability can change. Record the model returned by the
provider, the request model, time, endpoint, and an independently captured deployment
or model revision when the provider exposes one. A seed is a requested control, not a
promise that separate hosted calls are byte-identical.

## Mistral and OpenRouter

There is not yet a dedicated one-call smoke CLI for these two adapters. The following
is a receipt-only example for an operator who has deliberately opted in. It refuses to
run without an explicit provider, model, key, and live-smoke flag; it caps wall wait,
response bytes, and generated tokens:

```bash
export TAEDRI_LIVE_MODEL_SMOKE=1
export TAEDRI_PROVIDER=mistral  # or: openrouter
export TAEDRI_MODEL_ID='<exact-provider-model-id>'
IFS= read -r -s TAEDRI_PROVIDER_KEY
printf '\n'
export TAEDRI_PROVIDER_KEY

python - <<'PY'
import json
import os

from taedri_codegraph.model_providers import (
    ChatMessage,
    MistralChatProvider,
    OpenRouterChatProvider,
)

if os.environ.get("TAEDRI_LIVE_MODEL_SMOKE") != "1":
    raise SystemExit("live smoke is not enabled")

name = os.environ["TAEDRI_PROVIDER"]
key = os.environ["TAEDRI_PROVIDER_KEY"]
common = {"api_key": key, "timeout_seconds": 60, "max_response_bytes": 1_048_576}
if name == "mistral":
    provider = MistralChatProvider(**common)
elif name == "openrouter":
    provider = OpenRouterChatProvider(**common)
else:
    raise SystemExit("provider must be mistral or openrouter")

result = provider.chat(
    os.environ["TAEDRI_MODEL_ID"],
    (ChatMessage("user", "Return exactly TAEDRI_PROVIDER_SMOKE_OK."),),
    seed=0,
    temperature="0",
    max_completion_tokens=64,
)
print(json.dumps({"receipt": result.receipt.to_dict()}, sort_keys=True))
PY

unset TAEDRI_PROVIDER_KEY
```

This example intentionally does not print the assistant content. The operator may
compare its content digest with the expected smoke output, but that is still a narrow
protocol check, not a coding-quality test. For OpenRouter, freeze the exact model slug
and routing policy needed by the campaign; an unpinned upstream fallback can destroy a
same-model comparison even if the public model slug is unchanged.

## What each evidence level proves

| Level | Real network/model? | Independent task oracle? | Permitted conclusion |
|---|---:|---:|---|
| Offline adapter/unit conformance | No | No | Request shaping, bounds, response validation, receipt serialization, and secret exclusion behave as tested. |
| Live provider smoke | Yes | No | One selected endpoint accepted one bounded request and returned a parseable provider usage receipt. |
| Live campaign attempt | Yes | Possibly | A task ran; it is not an efficacy result until its complete matched block and independent verifier join resolve. |
| Claimable matched proof | Yes | Yes | Only the exact frozen comparison named by the proof may support a correctness-preserving token result. |

"Live" describes where bytes went. It is not a proof class and does not imply quality,
determinism, security, privacy, savings, or unit economics. Provider conformance tests
use simulated transports. The existing benchmark-worker bundle under
`eval/results/benchmark-worker-2026-07-16` is also a conformance fixture with provider
`deterministic-contract-fixture` and model `not-a-model`; its zero deltas are not model
results.

The exact token-evidence classes in `src/taedri_codegraph/token_savings.py` are:

- `conformance_fixture`: synthetic or replay evidence may prove receipt wiring and
  fail-closed validation, but `savings_claimable` is always false;
- `reported_historical`: totals without raw attempt and verifier receipts support
  arithmetic only; attempt completeness, correctness preservation, and savings remain
  unverified;
- `verified_real_model`: the only class eligible for an efficacy claim. The label alone
  is insufficient: both arms must have the same frozen context, all attempts and both
  independent verifier receipts must resolve, both outputs must be accepted, and the
  baseline total must exceed the treatment total.

### What strict campaign format 2.0.0 does and does not prove

Format 2.0.0 fails closed on the serialized evidence shape. It content-addresses the
campaign, its terminal arms, pairs, provider-response usage receipts, verifier
receipts, and arm-specific verification occurrences. It declares the complete task
manifest in advance and requires the exact task × seed × condition matrix. Every arm
must appear in exactly one pair; provider receipts, verifier receipts, and occurrences
cannot be reused. Each occurrence binds the task and hidden-case digest, A/B condition,
attempt/order, provider, requested model, seed, completion cap, and execution-policy
digest. A matched pair also has to bind the same concrete reported deployment.

Those checks prove that a well-formed v2 document is internally complete and has not
been edited by simple omission, substitution, or receipt cloning without breaking its
identities. They do **not** prove that the provider counters are provider-signed, the
runtime told the truth, hidden cases were secret before the call, the verifier ran in a
separate security boundary, the deployment was immutable behind its reported name, the
cohort represents real coding work, or retrieval/verification/repair/infrastructure
costs are complete. The validator field named `claimable_independent_execution` means
that distinct verifier occurrences and concrete provider receipts are structurally
bound; it is not a runtime-isolation attestation and is not itself a savings claim.

Legacy format 1.0.0 remains readable so earlier observations are not discarded, but it
has no declared task manifest and no arm-specific verifier occurrence. Therefore an
entire omitted task or a transplanted deterministic verifier result cannot be ruled out
from the serialized document alone. Every v1 campaign is non-claimable even when its
arithmetic and checked outputs look favorable.

The campaign-to-token measurement adapter never grants trust from JSON. A v2 provider-
response measurement still emits `savings_claimable=false` until a separately trusted
runtime resolves an attestation bound to the exact source and terminal receipts, and a
separately configured keyed trust root authenticates it. The resolver cannot provide
its own root, and neither a CLI flag nor a serialized evidence-class label can promote
the record. Complete failure-inclusive overhead receipts and paired acceptance are
still required after that trust check.

The proof evaluator can be exercised without a network call:

```bash
python tools/prove_token_savings.py \
  fixtures/token-savings/synthetic-conformance.json \
  --compact
python tools/prove_token_savings.py \
  fixtures/token-savings/reported-historical-137485-to-85954.json \
  --compact
```

Both commands must emit non-claimable proofs for different reasons. They are schema
and policy checks, not substitutes for real provider receipts.

### Live-campaign activation and hard bounds

`run_prompt_interception_campaign` in
`src/taedri_codegraph/prompt_interception.py` is a committed provider-injected library
runner. In plain language, condition A shows the model descriptions of all 11 released
primitives; condition B first ranks descriptions locally and shows the model only the
top K positive matches. The machine-readable names are `full_catalog` for A and
`deterministic_shortlist` for B. The runner freezes the same requested model, seed, and
output cap inside each pair, then resolves and executes a selected checked pack against
cases withheld from the model. It retains accepted and failed conditions. This verifier
path creates a distinct bound receipt, but the current local runner does not place that
verifier in a separately attested isolation boundary. The library does not read
credentials. Its committed wrapper,
`tools/run_prompt_interception_campaign.py`, defaults to emitting a dry-run schedule
without constructing a provider or reading a credential. A dry run is safe to inspect:

```bash
python tools/run_prompt_interception_campaign.py \
  --provider openrouter \
  --model '<exact-provider-model-id>' \
  --task-id customer_ingest.collapse_spacing \
  --max-provider-calls 2 \
  --compact
```

Network execution requires either `--execute-live` or
`TAEDRI_LIVE_MODEL_CAMPAIGN=1`. Mistral and OpenRouter credentials must arrive through
one named environment variable or exactly one stdin line; Ollama and a generic
compatible endpoint accept the same channels when authentication is required. For
example, this shape keeps the value out of arguments and output:

```bash
IFS= read -r -s TAEDRI_OPENROUTER_API_KEY
printf '\n'
export TAEDRI_OPENROUTER_API_KEY
python tools/run_prompt_interception_campaign.py \
  --provider openrouter \
  --model '<exact-provider-model-id>' \
  --task-id customer_ingest.collapse_spacing \
  --seed 0 \
  --max-completion-tokens 128 \
  --timeout-seconds 60 \
  --max-response-bytes 1048576 \
  --max-provider-calls 2 \
  --api-key-env TAEDRI_OPENROUTER_API_KEY \
  --execute-live \
  --output '<approved-receipt-path>.json'
unset TAEDRI_OPENROUTER_API_KEY
```

Before provider construction, the wrapper computes `tasks × seeds × 2` and rejects a
schedule above `--max-provider-calls`. It also bounds each provider wait to at most 300
seconds, each response to at most 16 MiB, and each requested completion to at most
4,096 tokens; defaults are 60 seconds, 1 MiB, and 128 tokens. The two disclosure
conditions are fixed, the local maximum K must be smaller than all 11 available
descriptions, and no retry or
tool-call lane exists. The emitted campaign contains secret-free usage and verification
receipts, not the credential or raw natural requests.

Those controls make a bounded operator-run campaign possible; they are not yet the
complete hosted admission system. A production credential-taking worker must also
supply positive hard limits for:

- tasks, repetitions, lanes, attempts per lane, and total provider calls;
- prompt, completion, aggregate accounted tokens, tool calls, and disclosed bytes;
- per-call and whole-campaign wall time plus verifier CPU time;
- provider spend, infrastructure spend, and shadow/strong-model spend;
- retained artifact bytes and campaign expiry.

Hosted admission reserves the worst-case allowed spend; it must stop before starting a
call that could cross the remaining campaign or tenant ceiling. That future worker
must record a plan digest, dry-run schedule, operator identity, explicit activation,
start/stop reason, and every terminal attempt. Credentials arrive separately through
the provider worker's stdin/environment secret path and never enter the plan. A manual
cancellation or exhausted bound is retained as campaign evidence, not dropped as an
incomplete row.

## Current strict-v2 live evidence

Seven failure-inclusive format-2.0.0 campaign documents are checked in under
`eval/results/prompt-interception-live-v2-2026-07-16/`. Five completed Mistral
campaigns cover the nine-task constructed cohort at locally selected description
limits 1, 2, 4, and 8, a second K=4 seed, and five positive tasks derived from public
GitHub issues. Across the successful strict-v2 campaigns, 98/100 model calls selected
a checked pack and all 196 resulting case executions passed. Both retained model
abstentions occurred when all 11 descriptions were shown.

Across 50 provider-usage-complete pairs, the responses reported 50,369
prompt-plus-completion tokens with all descriptions and 20,248 with locally selected
descriptions, a 30,121-token (59.8006%) selector-stage difference. The two-seed K=4
campaign alone reports 18,125→8,090 (55.3655%); its locally selected condition accepted
18/18 calls versus 17/18 for all descriptions. The five external-issue-derived positive
tasks report 5,056→2,179 (56.9026%), 5/5 accepted in both conditions, and 20/20 case
executions passed.

Fresh Ollama and OpenRouter portability campaigns are retained even though all 12 calls
ended in provider failures before usage or execution. No comparison is manufactured for
them. Strict v2 proves complete declared task/seed/condition matrices, unique provider
receipts, exact identity chains, and arm-bound verifier occurrences. It still does not
provide provider-signed usage, a separately trusted isolated-runtime attestation,
complete overhead accounting, sealed tests, or a full coding trajectory. The generated
`*.measurement.json` files therefore correctly retain `savings_claimable=false`.

See the [plain-language strict-v2 report](../../eval/results/prompt-interception-live-v2-2026-07-16/README.md),
its exact campaign JSON, summary JSON/CSV, and proof-tool measurements.

## Legacy checked pilot and future claimable campaign

Status: a constructed in-catalog live pilot is checked in; the rights-cleared, sealed,
end-to-end coding-session campaign described below has not yet run. Pilot numbers are
operator-captured provider-response selector/context observations from legacy campaign
format 1.0.0, not promoted product-wide savings percentages.

The planned claimable cohort follows
`eval/results/benchmark-worker-2026-07-16/campaign-plan.json`: sealed cold-holdout,
accepted and rejected product tasks from at least three consenting design-partner
teams, with immutable repository snapshots and executable independent oracles. A pilot
estimates paired outcome discordance and cost variance; the main-run sample size is
then powered and frozen. No sample count is invented before that pilot. Rights-reviewed
evaluation-only harness adapters may form separately reported cohorts, but fixture
tasks, replays, and conformance receipts never enter the real-model efficacy stratum.

The primary comparison answers a narrow question: for the same task and model, does
local retrieval followed by smaller, relevance-ordered capability disclosure preserve
checked execution outcomes while using fewer model tokens than showing every available
description? The locally retrieved condition also has condition-local opaque handles;
this is not a pure card-count ablation.

| Condition | Model-visible input | Purpose |
|---|---|---|
| A — all descriptions (`full_catalog` in machine JSON) | natural task request and all 11 released body-free primitive descriptions in canonical order | Implemented comparison condition for selection and prompt cost when the model receives every in-scope description. |
| B — locally retrieved descriptions (`deterministic_shortlist` in machine JSON) | the same task request and up to the top `K` positive-scoring descriptions in BM25 relevance order, with condition-local opaque handles | Implemented reduced-and-reordered context condition; local retrieval and verification overhead remain attributable to it. |
| `from_scratch` | the same task without any Taedri card or pack | Planned secondary quality/cost reference; the current campaign runner does not implement this lane. |
| stronger-model A/B | the same implemented pair repeated with one separately pinned stronger model | Supported secondary block. The first bounded Mistral Large smoke produced two retained provider failures and no usage comparison. |

The checked pilot ran Mistral `mistral-small-2603` over nine tasks at K=1, 2, 4,
and 8. Condition B selected packs that passed every executed check in all four runs.
Provider-response prompt-plus-completion totals were 9,062→2,111, 9,062→2,800,
9,063→4,045, and 9,062→5,068. The all-description condition abstained on the same
deduplication task in three runs; the locally selected condition passed it. A separate
three-task Ollama `gpt-oss:20b` run passed both conditions and measured 3,166→1,587.
All non-successes, including two bounded Mistral Large provider failures, are retained
in `eval/results/prompt-interception-live-pilot-2026-07-16/`. The cohort is constructed
and in-catalog, and the public fixture is hidden from model calls rather than
cryptographically sealed, so these are descriptive selector/context measurements.

The checked catalog, primitive-card schema, canonical primitive-ID order, `K`,
shortlister version, and maximum disclosed bytes are frozen before any outcome is
observed. The implemented shortlist uses integer-only BM25-like scoring with fixed
generic stopwords and fixed field weights, breaks ties by primitive ID, and excludes
zero-score cards. Cards contain compact names, summaries, keywords, use cases, and
opaque per-prompt route handles; source bodies, pack locations, registry identifiers,
and hidden cases do not enter the teacher prompt. If the complete eligible catalog
cannot fit the pre-registered context budget, the task is ineligible. The current
runner has no paging lane, so it must not silently truncate the baseline.

For every pair, freeze the same:

- immutable natural task/request digest, checked catalog digest, and hidden-case-set
  digest or sealed oracle reference;
- provider, requested and reported model/deployment identity, model configuration,
  seed schedule, and counterbalanced lane order;
- system prompt, harness, deterministic executor, runtime image, network policy, and
  policy digest;
- prompt, completion, total-token, tool-call, wall-time, and verifier-CPU budgets;
- sealed oracle reference and independent verifier configuration.

Only the disclosure intervention differs inside a pair. The optional strong-model
block must repeat both disclosure lanes with that strong model. A future `from_scratch`
comparison becomes a separate pair with its own pre-registered estimand; neither
planned lane weakens the same-model invariant.

Hidden tests, cases, gold patches, grader logic, expected outputs, and answer-derived
features never enter a model prompt, provider request, catalog, shortlist, retrieval
index, teacher request, tool result, or repair turn. The model-side job knows only an
opaque sealed-oracle reference. A separate verifier resolves that reference after the
model terminates and joins its receipt to the exact output digest and complete ordered
set of model-attempt receipt digests.

Every scheduled task, repetition, and lane remains in the denominator. Retain initial
failures and retries, rejected outputs, abstentions, policy blocks, budget exhaustion,
timeouts, provider errors, build/test failures, verifier failures, infrastructure
errors, human intervention, and detected or unknown contamination. A later successful
retry does not erase earlier tokens, time, or cost. The proof loader rejects missing,
duplicate, unassigned, non-contiguous, cross-run, or selectively omitted attempt
receipts.

The implemented campaign receipt retains `accepted`, `verification_failed`,
`teacher_rejected`, `provider_failed`, `interceptor_failed`, and `verifier_failed`
terminal arms and embeds provider usage when a response exists. Its claim scope is
intentionally limited to operator-captured provider counters and checked hidden-case
outcomes; it says that causal savings still require the separate token-savings
integrity evaluator. `fixtures/prompt-interception/natural-tasks.json` supplies natural
requests and cases that are withheld from model calls. It contains no live provider
output; exact sanitized provider outputs are stored under
`eval/results/prompt-interception-live-pilot-2026-07-16/`.

The current proof schema is pairwise (`baseline` versus `reuse`). Emit one proof input
mapping condition A to `baseline` and condition B to `reuse` for each
frozen matched context. Emit separate inputs for any future `from_scratch` or
strong-model estimand; never place different models in the same `MatchedRunContext`.
Aggregate only complete task-matched blocks and publish failures and uncertainty
alongside any point estimate.

Promotion from a live campaign to `verified_real_model` requires real provider usage,
complete receipts, independent acceptance of both conditions, a clean contamination
stratum, exact context equality, a trusted runtime resolver that returns an attestation
bound to the exact source and terminal receipts, and a separately configured keyed
trust root that authenticates that attestation. Neither a resolver alone nor serialized
JSON or CLI input can self-promote. A token-savings claim additionally requires the
failure-inclusive baseline total to exceed the treatment total. Provider tokens alone
are not the whole economic result: report retrieval, selector, tool, verification,
repair, infrastructure, and failed-attempt costs separately and in total.

The server-side premium/teacher experiment, including advisory artifact handles and
the stronger-model shadow block, is specified in
`docs/architecture/PREMIUM_PROMPT_INTERCEPTION_AND_TEACHER_DISTILLATION.md`.
