# Agent integrations

Owns Codex and Claude instructions, skills, optional hooks, tool policies, and harness
examples. Harnesses search first, resolve source late, and verify contracts,
provenance, and licensing before reuse.

Current sources: `AGENTS.md`, `CLAUDE.md`, `.agents/skills`, and `.claude/skills`.

The active prompt-session contract records digest-only request capture, search,
selection, selective materialization, model attempts, verification, acceptance,
abstention, and closure. Digest-only mode refuses raw prompt, message, and source-body
fields; an accepted result requires an earlier verification receipt.
