# Model provider testing

The first executable provider adapter uses Ollama's native `POST /api/chat` endpoint
with streaming disabled. The response's prompt/completion counts and nanosecond phase
durations become an immutable `ModelUsageReceipt`; raw prompts are represented in the
receipt only by digest. See the official [Ollama chat API](https://docs.ollama.com/api/chat)
and [OpenAI-compatibility reference](https://docs.ollama.com/api/openai-compatibility).

Run a bounded smoke call with a local or remote Ollama runtime:

```bash
export TAEDRI_OLLAMA_URL=http://127.0.0.1:11434
export TAEDRI_OLLAMA_MODEL=qwen3:8b
python tools/smoke_ollama_provider.py --receipt-only
```

If the endpoint requires authentication, inject `TAEDRI_OLLAMA_TOKEN` through the
shell's secret facility, a GitHub environment, or the deployment secret manager. Never
put it in a prompt, command argument, committed `.env`, benchmark record, or model-visible
tool result. A local Ollama runtime normally needs a reachable server rather than an API
key.

This smoke establishes protocol and usage-receipt integrity only. A product-quality
claim still requires frozen matched lanes, the same exact model and budgets, sealed
non-synthetic tasks, isolated execution, independent tests/policy checks, retained
failures, and contamination analysis.
