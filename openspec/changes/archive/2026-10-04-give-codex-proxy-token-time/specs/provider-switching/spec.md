## MODIFIED Requirements

### Requirement: Project into Codex config without overwriting it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The `[model_providers.coffer]` table points Codex at the local model
proxy's Responses route, `base_url = "http://127.0.0.1:<proxy port>/openai/v1"`, with
`supports_websockets = false` (pointed at another base URL Codex otherwise tries the Responses
WebSocket transport first and stalls), `requires_openai_auth = false`, and
`auth = {command = "<absolute path to the coffer CLI>", args = ["proxy", "token", "--agent-uid", "<agent uid>"], timeout_ms = 30000}`,
so Codex fetches its local proxy token itself — a Codex the user starts in their own terminal needs
nothing exported, and no provider key is in any Codex process's environment. `timeout_ms` is
written because Codex gives the command 5 seconds unless told otherwise, and a cold start (the
frozen CLI unpacking itself, the daemon still starting, Codex launching its MCP servers at the same
time) can exceed that, which leaves Codex's first turn hanging; a `config.toml` written without it is
a difference the reconcile pass repairs. The command-backed
`auth` table needs Codex 0.155.1 or later. The table MUST name no `env_key`, and the
projection MUST NOT put a provider key into any environment variable Codex passes to the shell
commands the agent runs; the user's own `shell_environment_policy` is left as it is.

The provider block's `wire_api` is always `"responses"`: Codex refuses to load a `config.toml`
carrying any other value, so it is fixed in the projection and no agent or connection field holds it.

When the connection curates `text` models the system MUST also write the Coffer-owned model catalogue
next to `config.toml` and point `model_catalog_json` at it, writing the file before the pointer and
dropping the pointer before the file; it MUST drop that pointer only when it names the Coffer-owned
filename. That key replaces Codex's built-in model list, which is what is wanted — the built-in names
are not served by the endpoint the agent now calls. De-projection drops the pointer and retires the
file, so Codex's own models come back; an uncurated connection writes no catalogue. The file is a
wire contract with another program: every field Codex's parser requires MUST be emitted, because a
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Each
catalogue entry MUST carry the model's context window as `context_window` and `max_context_window`,
`auto_compact_token_limit` at 90% of that window and an empty `supported_reasoning_levels` list, from what the connection records for
that model (see "Record a context window with each curated model"): Codex's parser requires the list, Coffer offers no reasoning levels, and without the window
it never compacts. An entry whose window is unknown leaves the three window keys out rather than
guessing. Coffer writes no `model_reasoning_effort` and no `default_reasoning_level`: a `model_reasoning_effort` already in `config.toml` is the user's own and is left as it is. Other values Coffer cannot derive for a third-party endpoint take
the least committal value, and `base_instructions` is written empty, so Codex sends no
`instructions` field: Coffer does not author another product's system prompt. For `claude_code` the
counterpart is the `modelPicker` settings key of "Project into Claude Code settings without
clobbering them" (`additionalModelOptionsCache` is Claude Code's own cache and is clobbered, so it is
not used).

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user switches the Codex agent onto the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with the proxy's loopback `base_url`, `wire_api = "responses"`, `supports_websockets = false`, `requires_openai_auth = false` and an `auth` command printing the agent's proxy token, and no `env_key`; and the agent's `connection_uid` becomes the connection's uid.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` carries the user's own `[shell_environment_policy]` with `exclude = ["AWS_*"]`
- **WHEN** the user switches that agent onto a connection reaching it
- **THEN** `exclude` is still `["AWS_*"]`, the provider block names no `env_key` and authenticates through its `auth` command, and Coffer puts no key into the environment of the Codex processes it starts

#### Scenario: the Codex catalogue carries each model's window
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window
- **WHEN** the agent is switched onto the connection
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and an empty `supported_reasoning_levels`
- **AND** `config.toml` carries no `model_reasoning_effort` written by Coffer

#### Scenario: the Codex auth table carries a timeout so a cold token command is not cut off
- **GIVEN** a Codex agent switched onto a connection, whose `auth` table Codex would otherwise limit to its 5 second default
- **WHEN** the projection is written
- **THEN** the `auth` table carries `timeout_ms = 30000`
- **AND** a `config.toml` whose `auth` table lacks `timeout_ms` is re-projected on the next reconcile pass
