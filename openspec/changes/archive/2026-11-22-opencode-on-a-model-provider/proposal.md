## Why

The owner asked for Cursor, OpenCode and DeepSeek Harness to get as many features as each can take. The first change (2026-11-19) gave them the MCP entry and skills. OpenCode can also take a model connection: a custom provider in `opencode.json` with a base URL. Cursor and Antigravity cannot, because they run only their makers' models.

## What Changes

- OpenCode gets a provider projection, a `provider.coffer` block in `opencode.json`. The block uses the `@ai-sdk/openai` package, so OpenCode sends the Responses API to the proxy's `/openai/v1` route. It also holds the connection's curated models with their windows, and sets the top-level `model` to `coffer/<id>`.
- OpenCode cannot run a command for its key, so the projection names a token file with `{file:…}`. Coffer keeps that file, `~/.coffer/local/proxy-tokens/opencode` with mode `0600`, equal to the agent's proxy token. It rewrites the file on mint and rotate, and deletes it with the agent.
- A connection with an OpenAI address now serves OpenCode. OpenCode's agent page shows the Model section, which follows from `features`.
- Coffer reads OpenCode's default model from its own `model` key. A `coffer/` prefix is shown as the bare id.
- The `agent-cli` CI job ran nothing, because the test harness strips `COFFER_*` variables and its switch was one of them. The switch is now `COFFER_SMOKE_AGENT_CLI`, and every agent's check has been run on a real install. For OpenCode 2.x the MCP check reads the config OpenCode resolved, because its `mcp list` lists no server at all. A new check makes OpenCode call a stand-in proxy with the token read from the file.
- Not in this change: a model connection for DeepSeek Harness (see the ADR), and drivers, sessions, plugins and hooks for the new types.

## Capabilities

### Modified Capabilities

- `provider-switching`: new requirement "Project into OpenCode config without overwriting it". "Authenticate each agent to the proxy with its own local token" and "Derive the agents a connection serves from its addresses" name OpenCode. The main spec is edited directly, so this change carries no delta.

## Impact

Backend provider domain (the OpenCode projection, `token_file` on the request), the proxy token service and a token-file mirror, the projector and its wiring, model discovery, tests, the frontend i18n strings for OpenCode's model section, the ADR `opencode-reads-its-proxy-token-from-a-file`, the docs-site providers and agents guides (en and zh), and the Makefile smoke switch.
