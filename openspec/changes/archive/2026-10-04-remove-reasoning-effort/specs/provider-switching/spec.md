## ADDED Requirements

### Requirement: Project into Codex config without overwriting it
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

### Requirement: Offer every connection operation over REST and in the web UI
Create, switch, revert-to-built-in, rename, edit, enable and disable, scope, order and delete MUST be
available via (a) the REST API and (b) the web surfaces — the Model providers library for create and
delete, the Agent detail page for the switch and the revert, the connection's own page for the
rename, the edit, the scope control and the enabled switch (see "Rename a connection without moving
anything else"). Coffer has no `provider` command group: the list carries no Active column, and a
connection's lifecycle verbs are the ones every kind's page offers. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`, `fallback`) and from its detail page, including correcting the wire.
Creating one (`POST /api/v1/providers` with a name, a protocol, a base URL and an inline secret, a
secret ref or the `local_runtime` detection) takes no model; a local runtime connection is created
without a key (see "Configure a local model connection"). No route returns a provider's key: the
agents reach a connection through the local model proxy, which injects the key itself (see "Reach
API-key and local connections through the local model proxy"). Reverting is
`POST /api/v1/providers/use-builtin/{agent_type}`, offered by the agent's Change model dialog as its
built-in login: a surface that can put an agent onto a Coffer connection and not take it off again is
half an operation. Which connection the internal engine and speech-to-text run on is chosen in
Settings › General (see "Set the internal-engine default" and "Keep an independent speech-to-text
default"), not on the connection's own page.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's Agents group, beside the agents whose models it serves) is
  one page under one header — the title, an Experimental tag, a one-line description and the page's one primary button, **Add provider** — over two tabs, **Providers** and **Usage** ("Show metered usage on a Usage tab of Model providers"). Providers is the connection library: a list of connections beside the open one. It has no view of which agent runs on what and no Coffer's model tab, because an agent's connection is shown and changed in that agent's Overview › Model and Coffer's own is chosen in Settings › General. The page opens on the first connection, and with none it is a welcome panel. Each row shows
  the connection's vendor mark, its name, its protocol and what it offers (its curated model count,
  or all models), and the marks of the agents running on it, read from the agents' `connection_uid`; a filter narrows the list over name,
  title, endpoint and description, and the list's order is the fallback order, labelled "Fallback order" with a help tip (see "Order providers, and fail over in that order"). It has no per-row switch, because activation is per agent, and no
  per-row reach or delete: both are on the open connection's header. A row MUST say what Coffer
  ITSELF uses the connection for: the `internal_default` connection carries a "Coffer · background
  model" badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with
  a hint naming Settings › General as where it is changed, and the connection's Used by repeats
  them. The labels lead with Coffer because a bare "Speech to text" reads as a capability of the
  provider rather than a job Coffer gives it; an agent's mark on a row is a different fact — that
  agent is switched to the connection. The vendor mark is derived from `base_url` by matching the
  preset list (an unmatched endpoint gets Coffer's neutral provider glyph); the name is the user's
  own, and the row links to the detail page by `uid`.
- The add-connection dialog asks for the vendor from a grid of eight equal buttons — Anthropic, OpenAI, Google Gemini, DeepSeek, OpenRouter, Ollama, LM Studio and Custom — which fill in the
  endpoint and protocol (Custom reveals a manual protocol selector), in two steps, Endpoint and then Models. A local runtime (Ollama, LM Studio) asks for no key and,
  until a runtime is chosen or an address is filled in, does not let the user go on to Models; the connection's Name
  appears once a runtime is chosen. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) is one column opened beside the list — Used by, Endpoint, Models — and has no tabs. Its header carries a health pill (Reachable, Key rejected or Unreachable, read from a probe that runs when it opens), the protocol, the host and, when the endpoint answered, how long it took, and the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed — with Test, Edit and a menu holding Delete provider ("Review what deleting a connection changes"). **Used by** is read-only: each agent whose `connection_uid` names the connection (and that the connection still serves),
  with the model it runs, as a link reading "<Agent> › Change model" that opens that agent's page with its Change model dialog already open (`/agents/<type>?change-model=1`); and Coffer's engine and Speech to text
  when the connection is flagged for them, each reading "Settings › General" and opening it. Used by carries no
  switch, activate or revert control, and no row repeats a fault: a connection's fault shows in its header pill and in the section it belongs to (Endpoint for Unreachable or Key rejected, Models for a failed listing).
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model** and **Route** and, with the `models` feature on, carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that reach that agent and narrowed by `enabled`: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model** and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). It carries no
  other model setting — no output-limit, subagent, fallback, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. Picking things in the form is a DRAFT: it writes nothing, and **Review changes** is enabled only once the draft differs from what is applied and names a model. The built-in login needs no model. The agent's Overview reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `secret_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the routes cover create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** a client calls `POST /api/v1/providers`, `GET /api/v1/providers`, `POST /api/v1/providers/{uid}/activate` with an `agent_type` and `POST /api/v1/providers/use-builtin/{agent_type}`,
- **THEN** each operation succeeds and the list answers with the connections as JSON,
- **AND** after the revert the agent's `connection_uid` is empty, so the switch that was made can be undone.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections, marks the one an agent runs on with that agent's mark, and shows the open connection's endpoint and its reach in the header's shared control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per agent in its Change model dialog (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)

#### Scenario: the provider library has no tabs
- **GIVEN** the Model providers page
- **WHEN** it renders
- **THEN** its only tab strip is the page header's Providers | Usage, and the library itself has no view of which agent runs on which connection and no Coffer's model tab (TypeScript acceptance test)

#### Scenario: a provider's used-by list is read-only
- **GIVEN** a connection that Claude Code runs on (its `connection_uid`) with a chosen model, and that is flagged `internal_default`
- **WHEN** its detail page renders
- **THEN** Used by lists Claude Code with its model, as a link "Claude Code › Change model" to `/agents/claude_code?change-model=1`, and Coffer's engine, opening `/settings/general`
- **AND** Used by carries no switch, activate or revert control (TypeScript acceptance test)

#### Scenario: the Change model dialog shows only provider, model and tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection
- **WHEN** each agent's Change model dialog renders
- **THEN** Claude Code's shows Provider, Model and Model per tier, and Codex's shows Provider and Model
- **AND** neither shows an effort, output-limit, subagent, fallback, thinking or fast-mode control

### Requirement: Record a context window with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window**, which the Codex catalogue needs (see "Project into Codex config without overwriting it"). It
travels through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry and is read from
the endpoint where it reports them (the person never chooses a context window); an unknown value is left
out of the stored document rather than guessed.

The add-connection dialog shows each listed model's window where the endpoint reports it and keeps
it on the curated entry; on the web it is not edited after that, only over REST. A curated entry an earlier version wrote with `effort_levels` or `default_effort` is read without them, and the next write drops them.

#### Scenario: a curated model keeps its window
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window for `gpt-x`
- **THEN** the connection reports it on `gpt-x`

## MODIFIED Requirements

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
rotated `.bak` ([agent-registry](../agent-registry/spec.md) "Write config files atomically with a backup and an audit entry") and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Reject stale config-file writes by fingerprint") — merging only the managed keys and preserving
everything else. Coffer MERGES into the user's existing file and never replaces it; a file that does
not exist is created with only the managed keys, and switching an agent onto a connection MUST NOT touch any key
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
launch; `env.ANTHROPIC_DEFAULT_OPUS_MODEL`,
`env.ANTHROPIC_DEFAULT_SONNET_MODEL`, `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` and, when a Fable tier is
pinned, `env.ANTHROPIC_DEFAULT_FABLE_MODEL`, from "Suggest a model for each Claude Code tier"; and
`modelPicker`, which fills Claude Code's `/model` picker with the connection's curated text models,
replacing the built-in rows on an endpoint that serves no Claude ids and keeping them on one that
does. Every option Coffer writes into `modelPicker` carries the description `via Coffer`, which is
how de-projection tells Coffer's picker from the user's. For a connection to
a model runtime on this machine it also writes `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

Coffer writes no reasoning-effort key: an `effortLevel` already in the file is the user's own and is left as it is.

De-projection drops `apiKeyHelper` only when it is Coffer's own — a helper line running the coffer
CLI (by absolute path or bare) with `proxy token` — and leaves a helper the user wrote alone.

Every projection write — this one, the Codex one (see "Project into Codex config without overwriting it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user switches the Claude Code agent onto the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` printing that agent's proxy token and `env.ANTHROPIC_BASE_URL` naming the proxy's loopback Anthropic route; neither the connection's endpoint nor its key appears in the file, `ANTHROPIC_API_KEY` is absent; and the agent's `connection_uid` becomes the connection's uid.
#### Scenario: switching preserves unrelated native-config keys and writes a .bak backup
- **GIVEN** `~/.claude/settings.json` contains keys Coffer does not manage (e.g. `theme`, `mcpServers`),
- **WHEN** the user switches that agent onto a connection reaching it,
- **THEN** those keys are preserved byte-for-byte in the updated file, a `.bak` file is written before the update (the previous `.bak` rotating to `.bak.1`, then `.bak.2`; three generations are kept), and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no `.bak` is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

### Requirement: Take projected model keys from the agent's binding
The model keys MUST come from the AGENT's binding (`AgentConfig.model` and, for Claude
Code, `tier_models`). An unset `model` for
Claude Code MUST leave the key untouched — the agent runs on whatever it was set to, its own default or the user's `/model`
choice. For Codex an unset `model` removes the `model` key instead: the gateway the connection points
at is unlikely to serve the model name the user had pinned for Codex's own login. An unset
tier MUST be unpinned, except that a Claude Code agent storing no tiers is pinned to Coffer's
suggestion (see "Suggest a model for each Claude Code tier"). Projection input is the connection
(endpoint, key, protocol, curated models) plus the agent's binding; a connection carries no model for
any use to fall back to. The surface that SETS that binding is
[agent-registry](../agent-registry/spec.md)'s, since the field is the agent's; this requirement is
about what the projection reads.

#### Scenario: an agent's model binding drives the projected model
- **GIVEN** a Claude Code agent is registered with a per-agent model binding (`model` and `tier_models`) and a connection reaching it exists,
- **WHEN** the user switches the agent onto the connection,
- **THEN** the projected top-level `model` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins come from the AGENT's binding, and neither `env.ANTHROPIC_MODEL` nor `env.ANTHROPIC_SMALL_FAST_MODEL` is written — the model lives at the point of use, not on the connection.

### Requirement: Review a model change before writing it
An agent's model MUST be changed in two calls, so the person sees the lines before they are written. `POST /api/v1/providers/model-switch/preview` takes `{agent_type, connection_uid, model, tier_models}` — `connection_uid` null is the agent's built-in login, which carries no model or tiers — and answers, per file the change would write, the file's path, whether it would be added, modified or removed, the line counts and diff, and a **fingerprint** of what the file held when it was read, plus the agent and the connection it would run on; it writes nothing, not even a `.bak`. It refuses, as "Switch one agent at a time" does, with 409 when the connection or the agent is switched off or the connection does not reach the agent. `POST /api/v1/providers/model-switch/apply` takes the same body with `seen`, each previewed file's path and fingerprint, and does what the switch of "Switch one agent at a time" and "Revert an agent type to its built-in login" does — records the model binding (`model` and `tier_models`) on the agent, then projects it and sets the connection, putting the binding back if the projection fails — so the preview and the write cannot disagree about the lines. When a file named in `seen` was edited on disk after the preview, nothing is written and the answer is 409 `CONFIG_FILE_STALE`.

The files are the agent's own: for Claude Code, `settings.json` — the top-level `model` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins; for Codex, `config.toml` — `model` and `[model_providers.coffer]` — together with Coffer's own model-list file `coffer-model-catalog.json` beside it, so a Codex change reads as two changes. A model the user has since changed with `/model` no longer equals the agent's binding and is theirs. No reasoning effort is written, so none is previewed.

The web UI's **Change model** dialog (Overview › Model › Change…, or `?change-model=1`) is the one form for both agents: Provider, Model and, for Claude Code, Model per tier — Codex has one model per session and no tiers. **Review changes** opens the 1060-wide review of the files from the preview, with a note that only the lines shown change, a `.bak` is kept, and, for Codex, that the model list file is Coffer's own; **Apply** writes them and closes both dialogs. With a provider chosen, Coffer tests the connection with the chosen model while the preview is computed; a failed test is shown as a warning and does not stop the apply. When Apply is refused as stale, the review says which file changed and offers **Reload preview**, and writes nothing. With the built-in login chosen the dialog offers Provider only, with a line saying the agent picks its model itself (`/model`) and that Coffer sets it only for a provider the user adds.

#### Scenario: previewing a model change writes nothing
- **GIVEN** a Claude Code agent on its built-in login and a connection that reaches it
- **WHEN** the user previews switching it onto the connection with a model and tier pins
- **THEN** the answer lists `settings.json` with the diff of the keys it would write and a fingerprint, and no file, `.bak` or agent record has changed
- **AND** previewing onto a connection that does not reach the agent is refused with 409

#### Scenario: a Codex change previews two files
- **GIVEN** a Codex agent and a connection whose chosen model has a context window
- **WHEN** the user previews the change
- **THEN** the answer lists `config.toml` and `coffer-model-catalog.json`, and applying writes both and records the model binding and the connection on the agent

#### Scenario: applying refuses a file that changed after the preview
- **GIVEN** a previewed change to a Codex agent's `config.toml`
- **WHEN** the user edits that file and then applies with the fingerprints the preview gave
- **THEN** the apply is refused with 409 `CONFIG_FILE_STALE`, the user's edit survives and the agent's record is unchanged
- **AND** the review says which file changed and offers Reload preview

#### Scenario: the built-in login asks for a provider only
- **GIVEN** the Change model dialog for a Claude Code agent on a connection
- **WHEN** the user picks the built-in login
- **THEN** no Model or tier field is shown, Review changes lists only the removal of the keys Coffer wrote, and applying leaves the agent's `connection_uid` empty

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the curated `text` ids of the connection the agent runs on when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an agent on a connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. A connection that curates nothing changes nothing, and an agent on no connection
means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

Codex's own model picker, inside Codex, is the one surface this answer does not reach when the
connection curates models but none of modality `text`: Coffer's surfaces then offer no chat model,
while the projection writes no model catalogue ("Project into Codex config without overwriting it"
writes one only for curated `text` models), so Codex keeps listing its built-in models.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Every surface that offers a model MUST get this answer from the same place:
`GET /api/v1/agent-providers/{agent_key}/models` serves it, and a channel's `/model` card resolves it
in-process through the same function. No surface may compute its own — a web picker that
introspected the endpoint and offered the union with the agent's catalogue listed ids the endpoint
would reject and disagreed with the same user's `/model` card.

The system context Coffer adds on every turn — Claude Code's system-prompt append and Codex's
`developerInstructions` on `thread/start` and `thread/resume` — MUST state which model Coffer put the
agent on — or that Coffer set no override — and which ids are available, so the agent does not
confidently name a model it is not running on ([chat](../chat/spec.md) "Tell the agent which model it
is on").

#### Scenario: every surface offers the same models
- **GIVEN** an agent running on a connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the Conversations page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered, so a connection
an agent runs on that curates models, none of them `text`, offers none. The per-conversation picker also
always carries a **Default** option that clears the conversation's model, so the agent runs its
projected default ([chat](../chat/spec.md) "Offer models from a fixed dropdown that keeps the
current value"). A model name MUST be passed to the agent verbatim, with no validation against a list of
Coffer's own: the CLI owns that namespace, so a renamed or added model works the day it ships, and one an
account cannot run fails where every other unusable choice fails. A model name is still raw
passthrough everywhere the CLI accepts one. Coffer offers no reasoning-effort control on any surface: the agent runs at the effort its own configuration names.

On the built-in login the Change model dialog offers no model control — those slots bind a connection's
model — and says where the model is chosen instead (the agent's own `/model`, per conversation in the Chat
page's picker, or with `/model` in a channel); the agent's Overview › Model still shows the model its own configuration names, read-only. The model is stored per conversation in the provider-owned `AgentConfig` blob: `PATCH
/api/v1/chat/conversations/{id}/agent-config` takes `model`, and an empty or null value clears it so the agent runs at its own
default.

#### Scenario: the agent's model picker offers a fixed list without free-form entry
- **GIVEN** an agent whose model is being chosen — on its detail page or in a conversation,
- **WHEN** the model picker is opened,
- **THEN** it offers a fixed dropdown with no free-text "Custom…" entry and no text input: the agent's own catalogue (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in login, and, when a connection overrides it, that connection's curated `text` ids served by the same route — never a model field stored on the connection, which carries none (TypeScript acceptance test).

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` MUST
remove every key Coffer wrote from the agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys and Coffer's `env.NO_PROXY` pair; for Codex the provider table, `model_provider`, `model`, and the catalogue pointer and file — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` the
user has since changed through `/model` no longer equals the agent's binding, is theirs
and is kept. An `effortLevel` or `model_reasoning_effort` that an earlier version wrote carries no mark of its own, so it is the user's and is kept too. Only values Coffer wrote are removed: the `env` keys carry no mark of their own, so they
count as Coffer's only while Coffer's `apiKeyHelper` is in the file ([data-model.md](data-model.md)
"What is Coffer's"); a user's own `ANTHROPIC_BASE_URL` or tier pins beside no Coffer helper are left
untouched and are not reported as drift. It also clears that agent's `connection_uid`, idempotently — succeeding when
the agent was on no connection — and touches only that agent: another agent that runs on the same
connection stays on it. The route takes an agent
type; a wire is not accepted, because a connection reaches agents through its scope and no protocol
names an agent.

#### Scenario: switch an agent back to its built-in login
- **GIVEN** the Claude Code agent runs on a connection and is projected into it,
- **WHEN** the user switches Claude Code back to built-in (`POST /providers/use-builtin/claude_code`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the agent's `connection_uid` is empty; the operation is idempotent (a no-op when the agent is on no connection). Another agent running on the same connection is untouched. A connection is an optional override.

#### Scenario: a wire no longer names an agent to revert
- **GIVEN** the daemon is running
- **WHEN** the user asks to revert `anthropic`, or a type that is not an agent type
- **THEN** the request is refused as `unprocessable_entity` (422) and nothing is written

#### Scenario: switching back removes every key Coffer wrote
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue

- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer Coffer wrote, and the catalogue file is gone

#### Scenario: switching back leaves the user's own gateway settings alone
- **GIVEN** a Claude Code `settings.json` with the user's own `env.ANTHROPIC_BASE_URL`, a tier pin and `theme`, and no Coffer `apiKeyHelper`
- **WHEN** the user switches Claude Code back to built-in, or a reconcile pass with a warrant runs
- **THEN** the file is byte-identical afterwards and attention reports no `projection_unclaimed` drift for it

### Requirement: Configure a local model connection
A local model connection — one whose endpoint is a model runtime on this machine (Ollama, LM
Studio, vLLM, llama.cpp's `llama-server`) speaking the agent's own protocol — MUST be creatable
without a key (`POST /api/v1/providers` with the `local_runtime` detection returned, from the Add provider
dialog's local path), MUST point at a loopback
address, and is reached through the proxy like any other connection. There is no protocol
translation: a runtime that serves neither Anthropic Messages nor OpenAI Responses natively
(`mlx_lm.server`) is not a supported upstream. A local connection curates the runtime's models that it does
not report as unable to call tools, each with the context window the runtime serves it with. For
Claude Code, Coffer sets `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` and
`CLAUDE_CODE_MAX_CONTEXT_TOKENS` to the chosen model's window, and pins every tier to the one model;
for Codex the window goes into the catalogue entry. Coffer never runs Codex with `--oss`, which can
pull models.

When the runtime does not report a model's window, the curated entry records none and the
projection leaves the window out rather than guessing one (see "Record a context window with each curated model"). Neither compatibility key is a field the user sets, and neither is a model's context window.

#### Scenario: create a keyless local runtime connection
- **GIVEN** an Ollama runtime answering on a loopback port
- **WHEN** the user creates a connection `ollama` through `POST /api/v1/providers` with protocol `anthropic`, base URL `http://127.0.0.1:11434` and the detected `local_runtime`
- **THEN** the connection persists with no secret, records the runtime, version and wires it serves, and curates its tool-capable models with their served windows

#### Scenario: a local connection sets Claude Code's compatibility key
- **GIVEN** a Claude Code agent switched to a local model connection whose model records a 131072-token window
- **WHEN** the agent is switched onto it
- **THEN** `settings.json` carries `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` = `1` and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` = `131072`, with every tier pinned to the local model

#### Scenario: a local runtime connection must be on this machine
- **GIVEN** the daemon is running
- **WHEN** a connection is created with a `local_runtime` and a non-loopback base URL
- **THEN** it is refused as 422

#### Scenario: a local model's window is read from the runtime
- **GIVEN** a local model connection whose runtime serves `qwen-coder` with a 131072-token window
- **WHEN** a Codex agent is switched to it with that model
- **THEN** the catalogue entry carries a 131072-token window with compaction at 90% of it

#### Scenario: an unreported window is left out of the catalogue
- **GIVEN** a local model connection whose runtime does not report the window of `qwen-coder`
- **WHEN** a Codex agent is switched to it with that model
- **THEN** the catalogue entry for `qwen-coder` carries no window and no compaction limit

## REMOVED Requirements

### Requirement: Project into Codex config without clobbering it
**Reason**: Renamed: one of its scenarios no longer mentions effort levels, and a scenario cannot be renamed in place.
**Migration**: Read "Project into Codex config without overwriting it".

### Requirement: Offer every connection operation on REST and the web
**Reason**: Renamed: one of its scenarios no longer mentions effort, and a scenario cannot be renamed in place.
**Migration**: Read "Offer every connection operation over REST and in the web UI".

### Requirement: Record a context window and effort levels with each curated model
**Reason**: Renamed: connections no longer record effort levels.
**Migration**: Read "Record a context window with each curated model".

