## Why

A review of MCP management and custom tools on 2026-11-06, against the owner's
30 days of real use (9 servers, 2 custom tool groups, 438 calls, all set up by
agents through the CLI), applied the project's rule that Coffer does only what
an agent cannot. It found features nobody needs (OpenAPI import, a
per-environment timeout, a dead `projects` key), real defects (every session
starting every server, failures recorded as a bare class name, four
overlapping hand-off prompts) and a few small gaps. The owner agreed the list
and asked for it in one change. Deferred items went to `docs/TODO.md` (PR #709).

## What Changes

- Remove OpenAPI import, re-import and the import diff; agents add HTTP APIs
  with `coffer custom-tool` commands.
- Check custom tool arguments with the `jsonschema` library (ADR
  `custom-tool-arguments-are-checked-by-the-jsonschema-library`).
- Remove the per-environment timeout and the reach file's `projects` key.
- A custom tool test returns every response header, cookies and secret values
  masked; `diagnostic_headers` is removed.
- A query that spells a tool's name ranks it first (ADR
  `tool-search-puts-an-exact-name-first`).
- An agent's old SSE entries are listed but never imported or adopted (ADR
  `upstreams-speak-stdio-or-streamable-http`).
- Relay an upstream's `elicitation/create` to a client that declared it.
- Record why an upstream failed in Coffer's words: the HTTP failure kind or
  status, or a stdio exit with its last stderr line.
- One hand-off per server and per group, carrying that error; no per-call
  hand-off; the status read drops failing-since, error time and last tool (ADR
  `one-hand-off-per-server-or-group`).
- Sessions list from the saved catalogue and start a server only for a call
  (ADR `session-subprocess-model`, revision 2026-11-06).
- Log fixes: Coffer lines start their own line, a deleted server's log goes,
  the SDK's 404 session-termination warning is dropped, an empty static header
  value is refused on save.
- The mcp-gateway Purpose says call content is recorded by default; the
  `coffer-guide` skill asks agents to pin `npx` and `uvx` versions.

## Impact

- Specs mcp-gateway, web-ui, agent-registry edited directly (scenarios renamed
  and removed, hence `skip_specs`).
- `derived.db` gains `mcp_catalogue`; no migration.
- Removed wire fields: `InvocationOut.handoff`, status `failing_since`,
  `last_error_at`, `last_ok_capability`, response `diagnostic_headers`,
  environment `timeout_seconds`, the OpenAPI import routes and CLI.
