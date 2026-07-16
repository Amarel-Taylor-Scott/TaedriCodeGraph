# Coding-agent harness guide

Taedri's agent surface is deliberately small: search first, inspect provenance and graph
context, then disclose bounded source for selected entities.

## Build and publish a graph

```bash
python -m pip install -e '.[agents]'

# A trusted local source tree
tcg analyze path ./src --package my-package --store .tcg --publish

# A downloaded wheel; verifies RECORD and never imports/builds/executes it
tcg analyze wheel ./dist/example-1.2.3-py3-none-any.whl --store .tcg --publish

# Language-neutral inventory for a polyglot checkout
tcg analyze inventory . --package my-repository --store .tcg --publish
```

Remote acquisition is intentionally outside these commands. Resolve a GitHub ref or PyPI
artifact to immutable bytes first, then analyze the local receipt.

## Progressive disclosure

```bash
tcg search "parse an address into components" --store .tcg --limit 10
tcg search "HTTP response JSON" --filter uceg.label.language=uceg.language.python --store .tcg
tcg context "parse an address into components" --store .tcg --limit 5
tcg representation list usaddress.parse --store .tcg
tcg representation search "MIT" --subject-kind snapshot --store .tcg
tcg edge neighbors usaddress.parse --store .tcg --direction both
tcg entity similar usaddress.parse --store .tcg
tcg context "parse an address into components" --store .tcg --limit 2 --source
```

`search` returns a query receipt with lane ranks and fusion policy. `entity similar` returns
LSH candidates and explicitly marks them non-proving. `context --source` reads only the
selected entity range from the content-addressed source store and applies a byte limit.

## MCP server

Start the optional stdio server with:

```bash
tcg mcp --store .tcg
```

It exposes:

- `search_code`;
- `get_code_context`;
- `get_entity`;
- `get_neighbors`;
- `list_representations`;
- `find_structural_candidates`;
- `search_metadata`;
- `taedri://entity/{identifier}` resources.

The server writes no diagnostic output to stdout because stdio is the protocol channel.

### Codex project configuration

After installing the optional dependency, a trusted repository can add the following to
`.codex/config.toml`:

```toml
[mcp_servers.taedri]
enabled = true
required = false
command = "python"
args = ["-m", "taedri_codegraph", "mcp", "--store", ".tcg"]
cwd = ".."
startup_timeout_sec = 20.0
tool_timeout_sec = 60.0
```

Project configuration is loaded only for trusted repositories. Keep credentials out of
the file; the current server needs none. The repository skill lives at
`.agents/skills/taedri-code-search/SKILL.md`, and `AGENTS.md` contains the durable rule to
use it before broad source reads.

### Claude Code project configuration

Claude Code can use the repository skill at
`.claude/skills/taedri-code-search/SKILL.md`. A project `.mcp.json` can launch the same
server:

```json
{
  "mcpServers": {
    "taedri": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "taedri_codegraph", "mcp", "--store", ".tcg"]
    }
  }
}
```

`CLAUDE.md` remains concise and points to the skill; procedural detail belongs in the
skill so it loads only when relevant.

## Hooks and enforcement

Skills and instruction files guide model behavior. They do not enforce it. A controlled
environment may add a deterministic pre-tool hook that:

1. observes a request to read a large source file or recursively search a source tree;
2. checks whether `.tcg/CURRENT` exists;
3. returns additional context asking the agent to run `search_code` first, or denies the
   operation under a strict policy;
4. records the policy version and decision.

Do not enable such a hook by default in a public repository: it can surprise contributors,
depends on harness-specific tool names, and project-local hooks are executable code. Keep
the hook in a separately reviewed policy package, pin it by digest, and have it emit a
router/policy receipt when the harness supports that path.

## Provider integration

The Python API supports deterministic labelers, NLP pipelines, local models, remote LLMs,
and embedding services through the same contract:

```python
from taedri_codegraph.providers import (
    CallbackProvider,
    ProviderDescriptor,
    ProviderInput,
    ProviderOutput,
    run_provider,
)
```

A provider must declare every output representation descriptor. Callers supply a unique
attempt key and a canonical model configuration. Nondeterministic retries remain separate
generation runs even when they emit identical content. Network access, credentials,
execution, rate limits, and retries are caller policy—not implicit graph behavior.

## Agent decision rule

Use a candidate only after checking the evidence needed for the task:

| Task | Minimum checks |
|---|---|
| Read for understanding | Source-backed location and snapshot |
| Copy/adapt code | Version, license assertions, source, tests, dependencies |
| Call an API | Signature/contract, environment, error/effect evidence |
| Compose components | Compatibility judgment or explicit adapter/test receipt |
| Execute package code | Separate sandbox policy and execution receipt |

Retrieval similarity alone satisfies none of the last four rows.
