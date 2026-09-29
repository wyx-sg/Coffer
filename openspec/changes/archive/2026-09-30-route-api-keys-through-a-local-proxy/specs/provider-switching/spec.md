## MODIFIED Requirements

### Requirement: Make the credential optional for ollama and local runtimes
`credential_ref` MUST be optional — required for `anthropic` / `openai` / `unknown` connections to a
remote endpoint, absent for `ollama`, and optional for a local runtime connection (see "Configure a
local model connection"), because LM Studio, vLLM and llama-server may be started with a key or
without one. On create, supplying neither `secret_value` nor `credential_ref` is valid for `ollama`
and for a local runtime, and an `ollama` connection MUST supply neither; elsewhere the exactly-one
rule (see "Store an inline secret under a minted opaque ref") stands.

#### Scenario: create an ollama connection without a credential
- **GIVEN** no connection named `local-llm` exists,
- **WHEN** the user creates one with `protocol="ollama"`, a `base_url`, and neither `secret_value` nor `credential_ref`,
- **THEN** it persists with `credential_ref` null, no vault entry is created, it reaches no agent, and `ProviderOut` shows `internal_default=false`.

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
rotated `.bak` ([agent-registry](../agent-registry/spec.md) "Write config files atomically with a backup and an audit entry") and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Reject stale config-file writes by fingerprint") — merging only the managed keys and preserving
everything else. Coffer MERGES into the user's existing file and never replaces it; a file that does
not exist is created with only the managed keys, and activating a connection MUST NOT touch any key
outside the managed set. The managed key set per agent and the ownership markers that make
de-projection safe are in [data-model.md](data-model.md).

No provider key reaches Claude Code at all: `env.ANTHROPIC_BASE_URL` is the local model proxy's
Anthropic route, `http://127.0.0.1:<proxy port>/anthropic`, and the agent authenticates to the proxy
with its own local token (see "Authenticate each agent to the proxy with its own local token"),
which the proxy exchanges for the connection's key upstream. `ANTHROPIC_API_KEY` MUST NOT be
written. Claude Code gets
`apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, which it
invokes to fetch that token (and re-invokes periodically); the path is absolute because Claude Code
runs the helper with its own `PATH`. `env.NO_PROXY` gains `127.0.0.1,localhost`, appended to the
user's own entries, so a corporate `HTTPS_PROXY` never captures the loopback leg; de-projection
takes back only that appended pair. Because the file names the proxy rather than the connection,
switching the agent from one API-key connection to another changes the proxy's route and leaves
`settings.json` as it is.
The model keys Coffer writes for Claude Code are these and no others (see "Take projected model keys
from the agent's binding"): the top-level `model` key for the agent's model — never
`env.ANTHROPIC_MODEL`, which outranks `model` and would undo the user's own `/model` choice at every
launch; the top-level `effortLevel` for the agent's effort; `env.ANTHROPIC_DEFAULT_OPUS_MODEL`,
`env.ANTHROPIC_DEFAULT_SONNET_MODEL`, `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` and, when a Fable tier is
pinned, `env.ANTHROPIC_DEFAULT_FABLE_MODEL`, from "Suggest a model for each Claude Code tier"; and
`modelPicker`, which fills Claude Code's `/model` picker with the connection's curated text models,
replacing the built-in rows on an endpoint that serves no Claude ids and keeping them on one that
does. Every option Coffer writes into `modelPicker` carries the description `via Coffer`, which is
how de-projection tells Coffer's picker from the user's. Every projection write MUST delete
`env.ANTHROPIC_SMALL_FAST_MODEL`, the deprecated background-model key that Claude Code still reads
ahead of the Haiku pin, and an `env.ANTHROPIC_MODEL` an earlier build wrote. For a connection to
a model runtime on this machine it also writes `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

De-projection drops `apiKeyHelper` only when it is Coffer's own — a helper line running the coffer
CLI (by absolute path or bare) with `proxy token`, or the `provider key` form earlier builds wrote —
and leaves a helper the user wrote alone.

Every projection write — this one, the Codex one (see "Project into Codex config without clobbering
it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` printing that agent's proxy token and `env.ANTHROPIC_BASE_URL` naming the proxy's loopback Anthropic route; neither the connection's endpoint nor its key appears in the file, `ANTHROPIC_API_KEY` is absent; and the connection's `is_active` becomes `true`.
#### Scenario: switching preserves unrelated native-config keys and writes a .bak backup
- **GIVEN** `~/.claude/settings.json` contains keys Coffer does not manage (e.g. `theme`, `mcpServers`),
- **WHEN** the user activates a connection reaching that agent,
- **THEN** those keys are preserved byte-for-byte in the updated file, a `.bak` file is written before the update (the previous `.bak` rotating to `.bak.1`, then `.bak.2`; three generations are kept), and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no `.bak` is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

#### Scenario: every write deletes the deprecated background-model key
- **GIVEN** `~/.claude/settings.json` carrying `env.ANTHROPIC_SMALL_FAST_MODEL` and `env.ANTHROPIC_MODEL` from an earlier build
- **WHEN** Coffer projects a connection for an agent bound to a model and a Haiku tier
- **THEN** both keys are gone, the model is in the top-level `model` key, and the Haiku tier is in `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`

### Requirement: Project into Codex config without clobbering it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The `[model_providers.coffer]` table points Codex at the local model
proxy's Responses route, `base_url = "http://127.0.0.1:<proxy port>/openai/v1"`, with
`supports_websockets = false` (pointed at another base URL Codex otherwise tries the Responses
WebSocket transport first and stalls), `requires_openai_auth = false`, and
`auth = {command = "<absolute path to the coffer CLI>", args = ["proxy", "token", "--agent-uid", "<agent uid>"]}`,
so Codex fetches its local proxy token itself — a Codex the user starts in their own terminal needs
nothing exported, and no provider key is in any Codex process's environment. The command-backed
`auth` table needs Codex 0.155.1 or later. The table names no `env_key`, and the
`COFFER_PROVIDER_KEY` entry earlier builds added to `shell_environment_policy.exclude` is removed,
keeping the user's own entries, and the table when nothing else is left in it.

`wire_api = "responses"` is the only accepted value, enforced in `AgentConfig`, so anything else is a
422 at the moment it is set: Codex refuses to load a `config.toml` carrying `wire_api = "chat"`, and
rewriting the value at projection time would leave the stored value, and every `AgentOut`, saying
something other than what Coffer projects.

When the connection curates `text` models the system MUST also write the Coffer-owned model catalogue
next to `config.toml` and point `model_catalog_json` at it, writing the file before the pointer and
dropping the pointer before the file; it MUST drop that pointer only when it names the Coffer-owned
filename. That key replaces Codex's built-in model list, which is what is wanted — the built-in names
are not served by the endpoint the agent now calls. De-projection drops the pointer and retires the
file, so Codex's own models come back; an uncurated connection writes no catalogue. The file is a
wire contract with another program: every field Codex's parser requires MUST be emitted, because a
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Each
catalogue entry MUST carry the model's context window as `context_window` and `max_context_window`,
`auto_compact_token_limit` at 90% of that window, and — when the model has effort levels —
`supported_reasoning_levels` and `default_reasoning_level`, from what the connection records for
that model (see "Record a context window and effort levels with each curated model"): without the
levels Codex sends no reasoning effort whatever `model_reasoning_effort` says, and without the window
it never compacts. An entry whose window is unknown leaves the three window keys out rather than
guessing. The agent's effort is written as the top-level `model_reasoning_effort`, and only when the
chosen model records that level. Other values Coffer cannot derive for a third-party endpoint take
the least committal value, and `base_instructions` is written empty, so Codex sends no
`instructions` field: Coffer does not author another product's system prompt. For `claude_code` the
counterpart is the `modelPicker` settings key of "Project into Claude Code settings without
clobbering them" (`additionalModelOptionsCache` is Claude Code's own cache and is clobbered, so it is
not used).

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with the proxy's loopback `base_url`, `wire_api = "responses"`, `supports_websockets = false`, `requires_openai_auth = false` and an `auth` command printing the agent's proxy token, and no `env_key`; and the connection's `is_active` becomes `true`.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` carries `[shell_environment_policy]` with `exclude = ["AWS_*", "COFFER_PROVIDER_KEY"]` from an earlier build
- **WHEN** the user activates a connection reaching it
- **THEN** `exclude` is `["AWS_*"]`, the provider block names no `env_key`, and Coffer puts no key into the environment of the Codex processes it starts

#### Scenario: the Codex catalogue carries each model's window and effort levels
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window and the levels `low`, `medium`, `high`, and the agent's effort set to `high`
- **WHEN** the connection is activated
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and `supported_reasoning_levels` low, medium, high
- **AND** `config.toml` carries `model_reasoning_effort = "high"`

### Requirement: Offer every connection operation on REST, CLI and web
Create, switch, revert-to-built-in, rename and delete MUST be available via (a) the REST API, (b)
`coffer provider list|show|add|edit|rm|enable|disable|scope|switch|builtin|detect-local` with `--json` on
`list` and `show` — the lifecycle verbs being the ones every kind's group offers, and rename being
`coffer provider edit <name> --name <new>` (see "Rename a connection without moving anything
else") — and (c) the web surfaces — the Model providers library for create and delete, the Agent
detail page for the switch, the connection's own page for the rename. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`), over the CLI
(`coffer provider edit <name> [--name <new>] [--title <text>] [--description <text>] [--protocol <wire>] [--base-url <url>] [--secret <value>]`)
and from its detail page, including correcting the wire. `coffer provider add <name> --protocol <p>
--base-url <url> [--secret <value> | --credential-ref <ref> | --local]` takes no model; `--local`
creates a local runtime connection (see "Configure a local model connection"). No command or route
returns a provider's key: the agents reach a connection through the local model proxy, which injects
the key itself (see "Reach API-key and local connections through the local model proxy"). Reverting is
`coffer provider builtin <agent_type>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation. Which connection the internal engine and speech-to-text
run on is set through `coffer config` (see "Set the internal-engine default" and "Keep an
independent speech-to-text default"), not through a `provider` subcommand.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES group; the old
  `/settings/models`, `/settings/providers` and `/settings/llm-connections` routes redirect there) is
  the connection library: a table of name / vendor / base URL / reach, an Add action and Delete per
  row. It has no per-row switch, because activation is per agent. A row MUST say what Coffer ITSELF
  uses the connection for: the `internal_default` connection carries a "Coffer · background model"
  badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with a hint
  naming where it is changed, and the connection's detail header repeats them. The labels lead with
  Coffer because a bare "Speech to text" reads as a capability of the provider rather than a job
  Coffer gives it; the "Active" badge is a different fact — an agent is switched to the connection —
  and its hint says so. The
  vendor column and its filter are derived from `base_url` by matching the preset list (an unmatched
  endpoint reads as Custom); the name column keeps the user's own name, and the row links to the
  detail page by `uid`.
- The add-connection dialog asks for the protocol rather than detecting it: it offers provider
  presets (OpenAI / Anthropic / Google Gemini / DeepSeek / OpenRouter / Ollama) that fill in the
  endpoint and protocol, plus Custom, which reveals a manual protocol selector; the CLI takes
  `--protocol`. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail page splits into Overview and Models tabs. Its header carries the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed.
- Per-agent connection and model selection lives on the agent detail page's Overview tab, filtered to
  the connections that reach that agent and narrowed by `enabled`. Picking a connection or a model
  there is a DRAFT: it activates nothing and PATCHes nothing. Picking a non-built-in connection
  introspects its endpoint and stages a default model — Claude Code's primary and fast slots and
  Codex's single slot all default to the first model returned. A custom connection MUST pass
  `POST /api/v1/models/test-connection` with the staged model before it can be confirmed; confirm
  stays disabled until the test for the CURRENT draft passes, and changing the connection or the
  model resets the result. Confirming PATCHes the per-agent binding and then activates the
  connection — the only step that writes native config. Switching back to the built-in login needs
  no test.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `credential_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the command line covers create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider builtin <agent_type>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for that agent type, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)

## RENAMED Requirements

- FROM: `### Requirement: Make the credential optional only for ollama`
- TO: `### Requirement: Make the credential optional for ollama and local runtimes`

## REMOVED Requirements

### Requirement: Resolve a key for exactly one connection
**Reason**: The agents reach a connection through the local model proxy, which injects the key itself; no route or command returns a provider key any more (ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new).
**Migration**: The projection writes `coffer proxy token --agent-uid <uid>` in place of the key helper; files an earlier build wrote are re-projected by the reconciler.

### Requirement: Require a connection or a wire for the key command
**Reason**: `coffer provider key` is removed with the key route.
**Migration**: `coffer proxy token --agent-uid <uid>` prints an agent's local proxy token.

## ADDED Requirements

### Requirement: Reach API-key and local connections through the local model proxy
An agent on a connection MUST send its model requests to the local model proxy, never to the
connection's endpoint directly, and the proxy MUST relay each request to an upstream of the same
wire — Anthropic Messages (`POST /anthropic/v1/messages`, `/messages/count_tokens`,
`GET /anthropic/v1/models`) to an Anthropic-shaped endpoint, OpenAI Responses
(`POST /openai/v1/responses`) to a Responses endpoint — with no protocol translation. The request
body is forwarded byte for byte; every request header is forwarded except hop-by-hop headers,
`host`, `content-length`, the client's credentials (`authorization`, `x-api-key`, cookies) and
`accept-encoding`, so `anthropic-*` headers and body fields travel as an open list. The proxy
injects the connection's key for the upstream (`x-api-key` and `Authorization: Bearer` on the
Anthropic wire, `Authorization: Bearer` on the Responses wire), and none for a keyless local runtime.
Status, headers and body chunks go back as received — pings and comments included, error bodies
verbatim, never buffered and never compressed. What the proxy logs or stores is metadata only: no
body, prompt, completion or credential. Everything else it is asked for is 404. The decision is
[API-Key Providers Are Reached Through a Separate Local Model Proxy](../../../docs/decisions/api-key-providers-are-reached-through-a-separate-local-model-proxy.md);
how it works is [The local model proxy](../../../docs-site/architecture/model-proxy.md).

#### Scenario: the proxy relays a stream byte for byte
- **GIVEN** an agent on a connection whose upstream streams a recorded Messages response with pings and comments
- **WHEN** the agent sends a streaming request through the proxy
- **THEN** the agent receives exactly the bytes the upstream sent, in order

#### Scenario: unknown anthropic headers and body fields reach the upstream untouched
- **GIVEN** a request carrying an `anthropic-beta` value and a body field Coffer has never seen
- **WHEN** the proxy forwards it
- **THEN** the upstream receives both unchanged, receives the connection's key and not the agent's token

#### Scenario: a keyless local runtime gets no key
- **GIVEN** an agent on a local runtime connection that carries no key
- **WHEN** the agent sends a request through the proxy
- **THEN** the upstream receives no `authorization` and no `x-api-key` header

### Requirement: Authenticate each agent to the proxy with its own local token
Each managed agent MUST have its own random 256-bit local proxy token, minted by Coffer on first
use, kept as ciphertext in the credential store under a machine-local ref vault sync never
carries, and printed by `coffer proxy token --agent-uid <uid>` (`GET /api/v1/proxy/tokens/{agent_uid}`)
— the command both agents' projected config runs. The proxy MUST accept a model request only with
one of those tokens, as `Authorization: Bearer` or `x-api-key`, compared in constant time, and MUST
refuse anything else — no token, a claude.ai OAuth token (`sk-ant-oat…`), a provider key — with 401
in the wire's own error shape, forwarding nothing. The token names the agent, which is how usage is
attributed. `coffer proxy rotate <agent>` (`POST /api/v1/proxy/tokens/{agent_uid}/rotate`) replaces
it; the old token is refused from the moment the rotation answers. For an agent this machine does
not have, the token route answers 404 and the command exits 4 with nothing on stdout, so a stale
helper fails closed. The token keeps browsers and other users' processes off the proxy; it is not a
boundary against a process of the same user.

#### Scenario: a request without a Coffer token is refused
- **GIVEN** the proxy serving an agent's route
- **WHEN** a request arrives with no token, or with an OAuth-shaped `sk-ant-oat` bearer
- **THEN** it is refused with 401 and nothing is forwarded upstream

#### Scenario: a rotated token replaces the old one
- **GIVEN** an agent whose token the proxy accepts
- **WHEN** the token is rotated
- **THEN** the old token is refused with 401 and the new one is accepted

#### Scenario: the token command prints a local token, never a provider key
- **GIVEN** a registered agent and an active API-key connection reaching it
- **WHEN** the user runs `coffer proxy token --agent-uid <uid>`
- **THEN** it prints the agent's local token, which is not the connection's key
- **AND** for a uid no agent has it exits 4 with nothing on stdout

### Requirement: Refuse a foreign Host or any Origin at the proxy
The proxy MUST bind `127.0.0.1` only, on a fixed port (`proxy_port` in `daemon-config.json`, 8001
by default), and MUST refuse with 403 a request whose `Host` is not a loopback name on the port it
arrived on, and any request that carries an `Origin` header — no browser page is a client of it.

#### Scenario: a foreign Host or an Origin is refused
- **GIVEN** the proxy running
- **WHEN** a request names a foreign `Host`, or carries any `Origin`
- **THEN** it is refused with 403 before authentication, and nothing is forwarded

### Requirement: Fail over only before the first content byte
When a request fails before the first content byte reaches the agent — a connect, TLS or DNS
error, a 5xx, 529 or 429 status, a 401 or 403, a first-byte timeout, or an error event before the
first content event (the proxy holds the response until then, bounded to a few kilobytes and
seconds) — the proxy MUST move it to the next member of the agent's route: another enabled
connection that reaches the same agent type, speaks the same protocol and lists the requested model
among its curated models. Failover MUST never change the model, never try the same member twice for
one request, and never happen after the first content byte: an error or truncation after it goes to
the agent, whose own retry lands on a healthy member. A 429 with `retry-after` cools that member for
that long; 401 or 403 disables it until its key changes; 400, 404 and 413 are relayed and never
fail over. A local runtime connection has no fallback members. A session stays on one member until
that member fails.

#### Scenario: a failure before the first byte moves to another connection serving the model
- **GIVEN** an agent's active connection answering 503, and another connection reaching the agent that lists the requested model
- **WHEN** the agent sends a request
- **THEN** the agent receives the second connection's response and never sees the 503

#### Scenario: an error after the first content byte is passed to the agent
- **GIVEN** an active connection whose stream fails after its first content event
- **WHEN** the agent sends a streaming request
- **THEN** the agent receives the partial stream and the error, and no other connection is tried

#### Scenario: a request problem is never failed over
- **GIVEN** an active connection answering 400
- **WHEN** the agent sends a request
- **THEN** the 400 and its body reach the agent unchanged and no other connection is tried

#### Scenario: failover never changes the model
- **GIVEN** an active connection answering 529, a second connection that does not list the requested model, and a third that does
- **WHEN** the agent sends a request
- **THEN** the second connection is never tried, and the third receives the request with the model the agent asked for

### Requirement: Configure a local model connection
A local model connection — one whose endpoint is a model runtime on this machine (Ollama, LM
Studio, vLLM, llama.cpp's `llama-server`) speaking the agent's own protocol — MUST be creatable
without a key (`coffer provider add <name> --protocol <wire> --base-url <loopback url> --local`, or
`POST /api/v1/providers` with the `local_runtime` detection returned), MUST point at a loopback
address, and is reached through the proxy like any other connection. There is no protocol
translation: a runtime that serves neither Anthropic Messages nor OpenAI Responses natively
(`mlx_lm.server`) is not a supported upstream. `--local` curates the runtime's models that it does
not report as unable to call tools, each with the context window the runtime serves it with. For
Claude Code, Coffer sets `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` and
`CLAUDE_CODE_MAX_CONTEXT_TOKENS` to the chosen model's window, and pins every tier to the one model;
for Codex the window goes into the catalogue entry. Coffer never runs Codex with `--oss`, which can
pull models.

#### Scenario: create a keyless local runtime connection
- **GIVEN** an Ollama runtime answering on a loopback port
- **WHEN** the user runs `coffer provider add ollama --protocol anthropic --base-url http://127.0.0.1:11434 --local`
- **THEN** the connection persists with no credential, records the runtime, version and wires it serves, and curates its tool-capable models with their served windows

#### Scenario: a local connection sets Claude Code's compatibility key
- **GIVEN** a Claude Code agent switched to a local model connection whose model records a 131072-token window
- **WHEN** the connection is activated
- **THEN** `settings.json` carries `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` = `1` and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` = `131072`, with every tier pinned to the local model

#### Scenario: a local runtime connection must be on this machine
- **GIVEN** the daemon is running
- **WHEN** a connection is created with a `local_runtime` and a non-loopback base URL
- **THEN** it is refused as 422

### Requirement: Detect a local model runtime without changing it
`POST /api/v1/providers/detect-local` and `coffer provider detect-local [--base-url <url>]` MUST
report which runtime answers at a loopback URL — or, with none given, at each runtime's default port
(Ollama 11434, LM Studio 1234, llama-server 8080; vLLM's default 8000 is the daemon's own port, so
vLLM is found only on a URL the user gives) — by fingerprint rather than port, with its version, the
wires it serves at that version and, per model, the context window it serves and whether it can
call tools, where the runtime says. Detection MUST be read-only — nothing is pulled, loaded or
downloaded — and MUST refuse a non-loopback URL as 422. A runtime below the minimum version for a
wire (Ollama 0.14.0 for Messages and 0.13.4 for Responses, LM Studio 0.4.1 and 0.3.29, vLLM 0.11.1
and 0.10.0) is not reported as serving it.

#### Scenario: detection reads the runtime, version and served windows
- **GIVEN** an Ollama runtime 0.14.2 on a loopback port serving `qwen3-coder` with a 65536-token window and tool support
- **WHEN** the user runs detection against that URL
- **THEN** it reports `ollama` 0.14.2 serving both wires, and `qwen3-coder` with a 65536-token window and tools

#### Scenario: a runtime below the minimum version serves no wire it lacks
- **GIVEN** an Ollama runtime 0.13.5 on a loopback port
- **WHEN** detection runs
- **THEN** it reports Responses and not Messages

#### Scenario: detection refuses a non-loopback address
- **GIVEN** the daemon is running
- **WHEN** detection is asked to probe `http://example.com:11434`
- **THEN** it is refused as 422 and no request leaves the machine
