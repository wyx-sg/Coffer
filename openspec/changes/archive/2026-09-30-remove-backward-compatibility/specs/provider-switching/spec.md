## MODIFIED Requirements

### Requirement: Delete an owned secret with its connection
On delete, if the connection owns its secret ref (nothing else cites it), the system MUST delete
the vault entry, guarded by `find_secret_citations`. Ownership is decided by citation, not by the
ref spelling the name.

#### Scenario: delete a provider profile cleans up its owned secret
- **GIVEN** a connection whose `secret_ref` is `provider/<uuid4>/key` (owned; nothing else cites it),
- **WHEN** the user deletes it,
- **THEN** the vault entry at that ref is deleted and `resource_deleted` is audited.

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
how de-projection tells Coffer's picker from the user's. For a connection to
a model runtime on this machine it also writes `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

De-projection drops `apiKeyHelper` only when it is Coffer's own — a helper line running the coffer
CLI (by absolute path or bare) with `proxy token` — and leaves a helper the user wrote alone.

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
`auth` table needs Codex 0.155.1 or later. The table MUST name no `env_key`, and the
projection MUST NOT put a provider key into any environment variable Codex passes to the shell
commands the agent runs; the user's own `shell_environment_policy` is left as it is.

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
- **GIVEN** a Codex agent whose `config.toml` carries the user's own `[shell_environment_policy]` with `exclude = ["AWS_*"]`
- **WHEN** the user activates a connection reaching it
- **THEN** `exclude` is still `["AWS_*"]`, the provider block names no `env_key` and authenticates through its `auth` command, and Coffer puts no key into the environment of the Codex processes it starts

#### Scenario: the Codex catalogue carries each model's window and effort levels
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window and the levels `low`, `medium`, `high`, and the agent's effort set to `high`
- **WHEN** the connection is activated
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and `supported_reasoning_levels` low, medium, high
- **AND** `config.toml` carries `model_reasoning_effort = "high"`

### Requirement: Clear an active flag the agent's config contradicts
On every reconcile pass ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), the provider-projection target MUST compare, for each enabled agent an active connection reaches, the keys Coffer's projection would write — base URL, model keys, the key helper command, Codex's provider block and its model catalogue — with the keys the agent's native config carries, by value and not by presence. Where Coffer's keys are present but differ, the connection MUST be projected again. Where they are absent and no agent of that type carries them, the system MUST clear `is_active`, so every surface then says the agent is on its built-in login, and MUST NOT write the projection back, because a flag left from an earlier session is no warrant to re-route a user's agent through a gateway they are not currently using; the exceptions are a pass run for a sync import, which carries the user's explicit switch from another machine, and an item a person applies, both of which project. Where they are absent from one agent of a type while another agent of that type carries them, that agent MUST be projected too. The opposite drift — Coffer's keys present while no active connection reaches the agent — MUST be reported rather than removed, unless the pass runs for a sync import or a person applies
that item. A multi-step switch MUST keep reconcile passes out until its writes and its flags agree. `is_active` is not redundant with `enabled`: `enabled` is the user's switch on the resource, while `is_active` records that this is the connection currently written into the agents it reaches — a claim about a file on disk that the agent's own CLI, other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears an active flag the agent's config does not carry
- **GIVEN** an active connection reaching a registered Claude Code agent whose `settings.json` carries none of Coffer's keys
- **WHEN** a reconcile pass runs at daemon start or on its period
- **THEN** the connection's `is_active` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

#### Scenario: a projection whose values went stale is projected again
- **GIVEN** an active connection projected into a Claude Code agent, whose `settings.json` then carries another base URL or another key helper command than the connection's
- **WHEN** a reconcile pass runs
- **THEN** the pass reports a modification naming the changed keys and writes the connection's projection again, recorded in the audit log with actor `system`

#### Scenario: keys no active connection claims are reported, not removed
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's keys while no connection is active for it
- **WHEN** a reconcile pass runs on its period
- **THEN** the drift is reported and the file is left as it was
- **AND** when the user applies that item, Coffer's keys are removed

#### Scenario: a leftover shell exclude entry is not a Codex projection
- **GIVEN** an active connection reaching a registered Codex agent whose `config.toml` holds only `[shell_environment_policy]` with `exclude = ["COFFER_PROVIDER_KEY"]`
- **WHEN** a reconcile pass runs
- **THEN** the connection's `is_active` is cleared

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` (and `coffer provider builtin <agent_type>`) MUST
remove every key Coffer wrote from every enabled agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model` and `effortLevel`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys and Coffer's `env.NO_PROXY` pair; for Codex the provider table, `model_provider`, `model`,
`model_reasoning_effort`, and the catalogue pointer and file — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` or effort the
user has since changed through `/model` or `/effort` no longer equals the agent's binding, is theirs
and is kept. It also clears the flag of the connection active for it, idempotently — succeeding when
nothing was active — and MUST revert a connection that reaches several agent types as a unit,
because the single `is_active` flag is all-or-nothing. The route and the command take an agent
type; a wire is not accepted, because a connection reaches agents through its scope and no protocol
names an agent.

#### Scenario: switch an agent back to its built-in login
- **GIVEN** a connection is active and projected into Claude Code,
- **WHEN** the user switches Claude Code back to built-in (`POST /providers/use-builtin/claude_code`, or `coffer provider builtin claude_code`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the connection is no longer active; the operation is idempotent (a no-op when nothing is active). A connection is an optional override.

#### Scenario: a wire no longer names an agent to revert
- **GIVEN** the daemon is running
- **WHEN** the user asks to revert `anthropic`, or a type that is not an agent type
- **THEN** the request is refused as `unprocessable_entity` (422) and nothing is written

#### Scenario: switching back removes every key Coffer wrote
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, `effortLevel`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue and an effort
- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer or `model_reasoning_effort` Coffer wrote, and the catalogue file is gone

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
--base-url <url> [--secret <value> | --secret-ref <ref> | --local]` takes no model; `--local`
creates a local runtime connection (see "Configure a local model connection"). No command or route
returns a provider's key: the agents reach a connection through the local model proxy, which injects
the key itself (see "Reach API-key and local connections through the local model proxy"). Reverting is
`coffer provider builtin <agent_type>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation. Which connection the internal engine and speech-to-text
run on is set through `coffer config` (see "Set the internal-engine default" and "Keep an
independent speech-to-text default"), not through a `provider` subcommand.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES group) is
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
- **THEN** only that field is updated, `secret_ref` is unchanged, and `resource_updated` is audited.
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
