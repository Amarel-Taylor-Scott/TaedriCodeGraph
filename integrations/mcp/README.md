# MCP integration

Owns versioned MCP tools/resources for hybrid and adaptive primitive search, entity
context, representations, neighbors, structural candidates, metadata, and provenance.
Results use bounded progressive disclosure and preserve query or escalation receipts.

`mcp_server.py` supports both a local immutable graph store and the authenticated remote
API through the dependency-free `api_client.py`. Remote credentials are accepted only
through an operator-named environment variable, never a command-line flag.

`tests/integration/test_mcp_protocol.py` boots the stdio server as a subprocess,
negotiates a real MCP session, lists the declared tools, and performs a structured
search round trip against an immutable graph. Hosted harness evaluation and automatic
OIDC harness identity remain explicit promotion gates.

Remote harnesses may pass `--session-id` (or `TAEDRI_PROMPT_SESSION_ID`). Search and
context tools then append request and search receipts with compare-and-swap sequencing.
Only query/response digests, tool identity, and result counts are retained; configured
recording fails closed if the session cannot accept evidence.
