## ADDED Requirements

### Requirement: Name the model a default resolves to
Wherever the web UI offers or shows a default model choice — the Agents list's Default model column and Overview › Model's Default model for an agent on its built-in login, and the Change model dialog's Built-in default — it MUST name the model that choice runs on when Coffer can know it, as `Built-in default (<model>)`, and MUST NOT name one it cannot know. The model is, in order: the model the agent's own config names, then the built-in default the agent itself reports (Codex marks it in `model/list`). Claude Code decides its built-in default from its organisation, account tier and entitlements, read from the server at turn time, so nothing on the machine names it and a Claude Code agent whose config names no model shows plain `Built-in default`. Coffer never infers a default from the first catalogue entry or from an alias.

`GET /api/v1/agent-providers/{agent_key}/models` MUST carry `builtin_default` (the model the agent reports as its built-in default, with its label, or null) and `resolved_default` (the config's model, else that built-in default's id, or null). While a connection's catalogue replaces Codex's own list, Codex would only echo the connection's ids, so `builtin_default` is null then.

#### Scenario: a default names the model it resolves to only when known
- **GIVEN** a Codex agent whose `model/list` marks `gpt-5-codex` as its default, and a Claude Code agent, neither config naming a model
- **WHEN** their models are read
- **THEN** Codex's `builtin_default` and `resolved_default` are `gpt-5-codex`, and Claude Code's are both null
- **AND** with `gpt-5` named in Codex's config, `resolved_default` is `gpt-5`

#### Scenario: the built-in default shows its model in the web UI
- **GIVEN** a Codex agent on its built-in login whose config names no model and whose reported default is labelled `GPT-5 Codex`
- **WHEN** the Agents list and the agent's Overview › Model are shown
- **THEN** both read `Built-in default (GPT-5 Codex)`, and a Claude Code agent in the same state reads `Built-in default`

### Requirement: Log an upstream error status without its body
When the upstream a request was relayed to answers with an error status, the model proxy MUST log one metadata line — `model_proxy.upstream_failed` with the agent, the connection, the endpoint, the requested model and the status — so a person can tell an upstream that does not know the model (404) from a refused key or an outage. Like every other proxy log line it MUST NOT contain the response body, which still reaches the agent unchanged ("Reach API-key and local connections through the local model proxy").

#### Scenario: an upstream error status is logged without its body
- **GIVEN** an agent on a connection whose upstream answers 404 with an error body
- **WHEN** the agent sends a request for `m1`
- **THEN** the agent receives the 404 and its body unchanged, and one `model_proxy.upstream_failed` line names `status=404` and `model=m1` without any of the body

### Requirement: Say that a Claude Code switch leaves the Claude desktop app alone
The Change model dialog for Claude Code MUST say, beside its Provider field, that the switch changes the Claude Code CLI only and that the Claude desktop app keeps its own model settings. The desktop app reads gateway routing from its own third-party inference configuration, not from `settings.json` or `ANTHROPIC_BASE_URL`, and Coffer writes nothing there.

#### Scenario: the Change model dialog names what a Claude Code switch reaches
- **GIVEN** a Claude Code agent and a connection reaching it
- **WHEN** the Change model dialog is opened
- **THEN** the Provider hint says the switch changes the Claude Code CLI only and the Claude desktop app keeps its own model settings

### Requirement: Tell Claude Code a provider model's window
When Claude Code is projected onto any connection — remote or local — and the agent's model is not a Claude id and its window resolves on that connection (see "Resolve each provider model's context window"), the projection MUST write `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to that window. Claude Code otherwise assumes 200k for an id its catalog does not describe, warns that it does, and compacts there. A Claude id's window is Claude Code's own and an unknown window is never guessed, so neither writes the key, and a key Coffer wrote earlier is removed. The value is one for the session: a model picked later inside Claude Code with `/model` keeps the window of the model Coffer projected until the next projection.

#### Scenario: a provider model's recorded window reaches Claude Code
- **GIVEN** a Claude Code agent on a remote connection, bound to `agnes-2.5-pro-alpha` whose curated entry records a 1000000-token window
- **WHEN** the agent is switched onto it
- **THEN** `settings.json` carries `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` = `1000000` and no `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`
- **AND** bound to `claude-opus-4-8`, or to a model with no recorded window, the key is absent

### Requirement: Test a connection on the wire the agent speaks

The connection test behind the Change model dialog and Overview › Model › Test MUST speak the wire
the agent will use, not the connection's own protocol: Claude Code is tested on the Anthropic wire
on every connection, any other agent on the connection's protocol. An OpenAI-protocol connection
that serves no Messages API at its base URL then fails the test before the switch can be reviewed,
instead of every Claude Code turn failing after it.

#### Scenario: Claude Code tests an OpenAI-protocol connection on the Anthropic wire
- **GIVEN** a connection with protocol `openai` that reaches Claude Code
- **WHEN** the user picks it and a model in Claude Code's Change model dialog
- **THEN** the test is sent with protocol `anthropic`, the connection's base URL and its secret ref

### Requirement: Offer a vendor's Anthropic endpoint as its own connection

A connection is one endpoint: one protocol at one base URL. A vendor that serves the Anthropic wire
at a different root from its OpenAI-compatible one (DeepSeek: `https://api.deepseek.com` and
`https://api.deepseek.com/anthropic`) MUST be reachable from Claude Code as a second connection, not
through a second address on the first. The Add dialog's preset for such a vendor MUST offer both
wires, and picking one fills the base URL that wire is served at; both connections may use the same
stored secret (ADR one-connection-serves-both-wires).

#### Scenario: DeepSeek offers its Anthropic endpoint as a second connection
- **GIVEN** the Add dialog with the DeepSeek preset chosen
- **WHEN** the user picks Anthropic-compatible
- **THEN** the base URL becomes `https://api.deepseek.com/anthropic`
- **AND** picking OpenAI-compatible puts back `https://api.deepseek.com`

### Requirement: Resolve each provider model's context window

A model's context window on a connection MUST resolve in one order, used by the projection (Claude
Code's `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, Codex's model list) and by the Models tab alike: **You set**
(the curated entry's `user_context_window`) → **From the endpoint** (its `context_window`, kept from the
listing) → **Bundled** (the `context_window` the release's price list records for the model at the
provider the endpoint belongs to, found the way a bundled price is) → unknown, in which case nothing
is written and nothing is guessed (ADR context-windows-for-provider-models). A model the connection
does not curate still resolves from the bundled list. `POST /api/v1/providers/{uid}/windows` takes
`{models}` and answers each model's `{model, tokens, source}`; it is read-only and touches no network.

The Models tab shows a **Window** column: the window in compact form ("1M", "128K") with its source
(You set, From the endpoint, Bundled), or "—" with **Set window…**. Either opens a dialog with one field
in tokens (`128000`, `128k`, `1m`, between 1k and 100m) that saves `user_context_window` on the model,
writing an unrestricted connection out first as a price does, and **Reset to default**, offered only
while a window of yours exists, which removes it.

#### Scenario: a model's window comes from you, then the endpoint, then the bundled list
- **GIVEN** a connection whose curated `deepseek-flash` records a 128000 window from the endpoint and a 64000 window you set, whose `endpoint-said` records only 128000 from the endpoint, and a bundled list that records 1000000 for `deepseek-flash`
- **WHEN** their windows are resolved
- **THEN** `deepseek-flash` is 64000 from You set and `endpoint-said` is 128000 from the endpoint
- **AND** on a connection curating nothing `deepseek-flash` is 1000000 from Bundled, and a model nothing records is unknown

#### Scenario: each model's window names where it came from and can be set
- **GIVEN** a provider's Models tab with models whose windows come from you, the endpoint, the bundled list, and nothing
- **WHEN** it shows them
- **THEN** each reads its window and source, and the unknown one reads "—" with Set window…
- **AND** setting 128k there saves `user_context_window` 128000 on that model, keeping every other row offered with the window its endpoint reported

## MODIFIED Requirements

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
timestamped backup and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Back up and compare-and-swap every write Coffer makes to an agent's config") — merging only the managed keys and preserving
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
runtimes reject Claude Code's beta request fields). For any connection whose chosen model is not a
Claude id and records a window, it writes `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to that window
(see "Tell Claude Code a provider model's window").

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
- **THEN** those keys are preserved byte-for-byte in the updated file, a timestamped copy of the prior file is written under `~/.coffer/config-backups/` before the update, and nothing is written next to it, and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no backup is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

### Requirement: Record a context window with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window**, which the Codex catalogue needs (see "Project into Codex config without overwriting it"). It
travels through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry and is read from
the endpoint where it reports them as `context_window`, and the window the person sets on the Models tab
is recorded beside it as `user_context_window` (see "Resolve each provider model's context window"); an
unknown value is left out of the stored document rather than guessed. A remote endpoint reports a window in its `/models`
entry as Anthropic's `max_input_tokens`, OpenRouter's `context_length` (or its `top_provider`'s), or the
`context_window` / `max_model_len` spellings gateways and vLLM use; most OpenAI-compatible endpoints
report none.

The add-connection dialog and the Models tab keep each listed model's reported window on the curated
entry when the model is switched on. A curated entry an earlier version wrote with `effort_levels` or `default_effort` is read without them, and the next write drops them.

#### Scenario: a curated model keeps its window
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window for `gpt-x`
- **THEN** the connection reports it on `gpt-x`

#### Scenario: a window the endpoint reports is kept
- **GIVEN** an endpoint whose `/models` lists `claude-x` with `max_input_tokens` 1000000, `or/x` with `context_length` 163840, and `gpt-x` with no window
- **WHEN** its models are listed for the add-connection dialog
- **THEN** `claude-x` and `or/x` carry those windows and `gpt-x` carries none

### Requirement: Review a model change before writing it
An agent's model MUST be changed in two calls, so the person sees the lines before they are written. `POST /api/v1/providers/model-switch/preview` takes `{agent_type, connection_uid, model, tier_models, native_model, clear_native_model}` — `connection_uid` null is the agent's built-in login, which carries no tiers and whose model is the agent's own: `native_model` sets the top-level `model` key of the agent's own config (Codex `config.toml`, Claude Code `settings.json`), `clear_native_model` removes it (the agent's built-in default), and neither leaves it as it is; the two are exclusive and are refused (422) together or beside a `connection_uid` — and answers, per file the change would write, the file's path, whether it would be added, modified or removed, the line counts and diff, and a **fingerprint** of what the file held when it was read, plus the agent and the connection it would run on; it writes nothing, not even a backup. It refuses, as "Switch one agent at a time" does, with 409 when the connection or the agent is switched off or the connection does not reach the agent. `POST /api/v1/providers/model-switch/apply` takes the same body with `seen`, each previewed file's path and fingerprint, and does what the switch of "Switch one agent at a time" and "Revert an agent type to its built-in login" does — for a connection, records the model binding (`model` and `tier_models`) on the agent, then projects it and sets the connection, putting the binding back if the projection fails; for the built-in login, takes Coffer's keys out, writes or removes the agent's own `model` key in the same file write, and only then clears the binding on the agent's record — so the preview and the write cannot disagree about the lines. When a file named in `seen` was edited on disk after the preview, nothing is written and the answer is 409 `CONFIG_FILE_STALE`.

The files are the agent's own: for Claude Code, `settings.json` — the top-level `model` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins; for Codex, `config.toml` — `model` and `[model_providers.coffer]` — together with Coffer's own model-list file `coffer-model-catalog.json` beside it, so a Codex change reads as two changes. A model the user has since changed with `/model` no longer equals the agent's binding and is theirs. No reasoning effort is written, so none is previewed.

The web UI's **Change model** dialog (Overview › Model › Change…, or `?change-model=1`) is the one form for both agents: Provider, Model and, for Claude Code, Model per tier — Codex has one model per session and no tiers. **Review changes** opens the 1060-wide review of the files from the preview, with a note that only the lines shown change, a backup copy is kept in Coffer's own folder, and, for Codex, that the model list file is Coffer's own; **Apply** writes them and closes both dialogs. With a provider and a model chosen, Coffer tests that provider with that model by itself once the draft has rested for a moment (`POST /api/v1/models/test-connection` with the protocol the agent speaks (see "Test a connection on the wire the agent speaks"), the connection's base URL and stored secret ref — the call of Overview › Model › Test; the page never handles a key), cancels a run the draft has moved past, and shows the result as a line under Model: **Testing connection…**, **Connection OK** with how long it took, or **Connection failed** with the reason and **Retry**. **Review changes** is enabled only when the draft differs from what is applied, names a model, AND the test for exactly this provider and model passed; while it is testing or after a failure it stays off and a line beside it says why. A local runtime connection is tested the same way. The review runs no second test. When Apply is refused as stale, the review says which file changed and offers **Reload preview**, and writes nothing. With the built-in login chosen the dialog offers **Model** with no tier section: **Built-in default** (the agent's config names no model), then the agent's own built-in models — the label shown, the id stored — preselected with what the agent's config names now (a configured id the list lacks still reads as its id); when the agent runs on a connection the field starts at Built-in default, and the list is the agent's own, asked of `GET /api/v1/agent-providers/{agent_key}/models?source=builtin` (see "Serve one model list to every surface"), so it never shows the connection's curated set. Choosing one sends `native_model`, Built-in default sends `clear_native_model`, and no connection test runs.

A change written into an agent's config files is read when that agent starts: Codex (App and CLI) reads `config.toml` at startup, and nothing in Coffer establishes that a running Claude Code re-reads `settings.json`, so both are treated as needing a restart. After a successful **Apply** the web UI MUST show a notice naming the agent by its display name — "Restart <agent> to use this change — sessions already open keep the old setting." — at the moment of the change; sessions already open are not touched.

#### Scenario: previewing a model change writes nothing
- **GIVEN** a Claude Code agent on its built-in login and a connection that reaches it
- **WHEN** the user previews switching it onto the connection with a model and tier pins
- **THEN** the answer lists `settings.json` with the diff of the keys it would write and a fingerprint, and no file, backup or agent record has changed
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

#### Scenario: the built-in login offers the agent's own models and no tiers
- **GIVEN** the Change model dialog for a Claude Code agent on a connection
- **WHEN** the user picks the built-in login
- **THEN** the Model field offers Built-in default and the agent's own models, no tier field is shown, and the models are asked of the agent's own catalogue rather than the connection's curated set
- **AND** with Built-in default kept, Review changes lists only the removal of the keys Coffer wrote, and applying leaves the agent's `connection_uid` empty

#### Scenario: choosing a model on the built-in login sets the agent's own model
- **GIVEN** the Change model dialog for an agent on its built-in login whose config names a model
- **WHEN** the dialog opens
- **THEN** Model is preselected with that model and Review changes is off
- **AND** choosing another model enables it and previews `{connection_uid: null, native_model}`; choosing Built-in default previews `clear_native_model`

#### Scenario: a model chosen on the built-in login is written to the agent's own config
- **GIVEN** a Claude Code agent and a Codex agent on their built-in login
- **WHEN** a model is applied to each with `native_model`
- **THEN** Claude Code's `settings.json` carries the top-level `model` and Codex's `config.toml` carries `model`, every other key and comment kept, and applying again with the same model previews no file
- **AND** `clear_native_model` removes the key again, and a file edited since the preview refuses the apply with 409 `CONFIG_FILE_STALE`

#### Scenario: leaving a connection for the built-in login clears the binding
- **GIVEN** a Claude Code agent on a connection with a bound model and tiers
- **WHEN** the user applies the built-in login with a model
- **THEN** Coffer's keys leave `settings.json`, the chosen `model` is the file's top-level model, and the agent's record has no `model` and no `tier_models`

#### Scenario: a model change is tested before it can be reviewed
- **GIVEN** the Change model dialog for an agent with an enabled connection that reaches it
- **WHEN** the user picks a model on the connection
- **THEN** Coffer tests the connection with that model without being asked, the line under Model reads "Testing connection…" and Review changes is off
- **AND** when the test passes the line reads "Connection OK" with its duration and Review changes is on

#### Scenario: a failed connection test keeps Review changes off and offers Retry
- **GIVEN** a draft naming a connection and a model whose test fails
- **WHEN** the test answers
- **THEN** the line under Model reads "Connection failed" with the reason and a **Retry** button, Review changes stays off and a hint says why
- **AND** choosing Retry tests again and, when it passes, turns Review changes on

#### Scenario: applying a model change says the agent must be restarted
- **GIVEN** the Change model review for a Codex agent with a passed connection test
- **WHEN** the user applies the change and it succeeds
- **THEN** a notice reads "Restart Codex to use this change" and says sessions already open keep the old setting

#### Scenario: a model set on the built-in login is not Coffer's to report or remove
- **GIVEN** an agent on its built-in login whose config names a model Coffer did not project
- **WHEN** a reconcile pass runs, including one a person asks for
- **THEN** it reports and removes nothing and the file is unchanged

#### Scenario: the built-in login needs no connection test
- **GIVEN** the Change model dialog for an agent on a connection
- **WHEN** the user picks the built-in login
- **THEN** no test runs, no test line is shown and Review changes is on
