## MODIFIED Requirements

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

The raw key MUST NOT be written to `settings.json`, `config.toml` or any other native config file;
`ANTHROPIC_API_KEY` MUST NOT be written. Claude Code instead gets
`apiKeyHelper = "<absolute path to the coffer CLI> provider key --connection-uid <uid>"`, which it
invokes to fetch the key (and re-invokes periodically). The path is absolute because Claude Code
runs the helper with its own `PATH`, which need not contain the directory the CLI is installed in.
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
CLI by absolute path, or the bare `coffer provider key` form written by earlier builds — and leaves
a helper the user wrote alone.

Every projection write — this one, the Codex one (see "Project into Codex config without clobbering
it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` naming that connection and `env.ANTHROPIC_BASE_URL`; `ANTHROPIC_API_KEY` is absent; and the connection's `is_active` becomes `true`.
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
with only the managed keys. The key reaches Codex through `env_key = "COFFER_PROVIDER_KEY"` in the
`[model_providers.coffer]` table: Coffer materialises it into the environment of any Codex process it
spawns itself, and a Codex the user starts in their own shell needs the variable exported there.
Codex's variable is filled from the connection active for
Codex. Codex passes its whole environment to the shell commands the agent runs unless told otherwise
(its built-in filter of names containing `KEY`, `SECRET` or `TOKEN` is off by default), so the
projection MUST also add `COFFER_PROVIDER_KEY` to `shell_environment_policy.exclude`, keeping the
user's own entries and other policy keys; de-projection MUST remove only that entry, and the table
when nothing else is left in it.

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
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with `base_url`, `wire_api = "responses"` and `env_key = "COFFER_PROVIDER_KEY"`; and the connection's `is_active` becomes `true`.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` already has `[shell_environment_policy]` with `exclude = ["AWS_*"]`,
- **WHEN** the user activates a connection reaching it, and later switches the agent back to its built-in login,
- **THEN** after activation `exclude` is `["AWS_*", "COFFER_PROVIDER_KEY"]`, so a shell command the agent runs does not see the key,
- **AND** after the switch back `exclude` is `["AWS_*"]` again.

#### Scenario: the Codex catalogue carries each model's window and effort levels
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window and the levels `low`, `medium`, `high`, and the agent's effort set to `high`
- **WHEN** the connection is activated
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and `supported_reasoning_levels` low, medium, high
- **AND** `config.toml` carries `model_reasoning_effort = "high"`

### Requirement: Take projected model keys from the agent's binding
The model keys MUST come from the AGENT's binding (`AgentConfig.model`, `effort` and, for Claude
Code, `tier_models`). An unset `model` or `effort` MUST leave the corresponding key untouched — the
agent runs on whatever it was set to, its own default or the user's `/model` choice — and an unset
tier MUST be unpinned, except that a Claude Code agent storing no tiers is pinned to Coffer's
suggestion (see "Suggest a model for each Claude Code tier"). Projection input is the connection
(endpoint, key, protocol, curated models) plus the agent's binding; a connection carries no model for
any use to fall back to. The surface that SETS that binding is
[agent-registry](../agent-registry/spec.md)'s, since the field is the agent's; this requirement is
about what the projection reads.

#### Scenario: an agent's model binding drives the projected model
- **GIVEN** a Claude Code agent is registered with a per-agent model binding (`model`, `effort` and `tier_models`) and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** the projected top-level `model` and `effortLevel` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins come from the AGENT's binding, and neither `env.ANTHROPIC_MODEL` nor `env.ANTHROPIC_SMALL_FAST_MODEL` is written — the model lives at the point of use, not on the connection.

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` (and `coffer provider builtin <agent_type>`) MUST
remove every key Coffer wrote from every enabled agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model` and `effortLevel`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys, and any `env.ANTHROPIC_SMALL_FAST_MODEL` or
`env.ANTHROPIC_MODEL`; for Codex the provider table, `model_provider`, `model`,
`model_reasoning_effort`, the catalogue pointer and file, and the shell-environment exclusion — so no
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

## ADDED Requirements

### Requirement: Suggest a model for each Claude Code tier
Claude Code asks for models by tier — Opus, Sonnet, Haiku (which also runs its background tasks) and
Fable — and a tier left unpinned on an endpoint that does not serve Claude ids sends a Claude id and
fails. So while a Claude Code agent is on a connection rather than its built-in login, Coffer MUST
have a model for every tier, and suggests one: on a connection whose models are not Claude ids, and
on a local model connection, every tier is the agent's model; on a gateway serving Claude ids, each
tier is the curated model whose name carries it (`opus`, `sonnet`, `haiku`, `fable`), the agent's
model where none does. Fable is suggested only when the connection lists a Fable model. The agent's
own `tier_models`, when it stores any, are projected instead of the suggestion. The tiers are
projected as `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` (see "Project into Claude Code settings without
clobbering them"); on the built-in login no pin is written.

#### Scenario: a non-Claude connection pins every tier to the model
- **GIVEN** a Claude Code agent bound to `kimi-k3` and a connection whose curated models are `kimi-k3` and `kimi-k3-mini`
- **WHEN** Coffer suggests the tiers
- **THEN** Opus, Sonnet and Haiku are `kimi-k3`, and no Fable tier is suggested

#### Scenario: a Claude-id gateway matches each tier by name
- **GIVEN** a connection whose curated models are `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5` and `claude-fable-1`
- **WHEN** Coffer suggests the tiers for a Claude Code agent on it
- **THEN** Opus, Sonnet, Haiku and Fable are the model whose name carries that tier

### Requirement: Record a context window and effort levels with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window** and its **effort levels**, with the level used when an agent names
none, which the Codex catalogue needs (see "Project into Codex config without clobbering it"). They
travel through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry, are read from
the endpoint where it reports them, and are otherwise entered by the user; an unknown value is left
out of the stored document rather than guessed.

#### Scenario: a curated model keeps its window and levels
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window and the levels low, medium and high for `gpt-x`
- **THEN** the connection reports them on `gpt-x`
