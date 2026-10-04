## MODIFIED Requirements

### Requirement: Review a model change before writing it
An agent's model MUST be changed in two calls, so the person sees the lines before they are written. `POST /api/v1/providers/model-switch/preview` takes `{agent_type, connection_uid, model, tier_models}` — `connection_uid` null is the agent's built-in login, which carries no model or tiers — and answers, per file the change would write, the file's path, whether it would be added, modified or removed, the line counts and diff, and a **fingerprint** of what the file held when it was read, plus the agent and the connection it would run on; it writes nothing, not even a `.bak`. It refuses, as "Switch one agent at a time" does, with 409 when the connection or the agent is switched off or the connection does not reach the agent. `POST /api/v1/providers/model-switch/apply` takes the same body with `seen`, each previewed file's path and fingerprint, and does what the switch of "Switch one agent at a time" and "Revert an agent type to its built-in login" does — records the model binding (`model` and `tier_models`) on the agent, then projects it and sets the connection, putting the binding back if the projection fails — so the preview and the write cannot disagree about the lines. When a file named in `seen` was edited on disk after the preview, nothing is written and the answer is 409 `CONFIG_FILE_STALE`.

The files are the agent's own: for Claude Code, `settings.json` — the top-level `model` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins; for Codex, `config.toml` — `model` and `[model_providers.coffer]` — together with Coffer's own model-list file `coffer-model-catalog.json` beside it, so a Codex change reads as two changes. A model the user has since changed with `/model` no longer equals the agent's binding and is theirs. No reasoning effort is written, so none is previewed.

The web UI's **Change model** dialog (Overview › Model › Change…, or `?change-model=1`) is the one form for both agents: Provider, Model and, for Claude Code, Model per tier — Codex has one model per session and no tiers. **Review changes** opens the 1060-wide review of the files from the preview, with a note that only the lines shown change, a `.bak` is kept, and, for Codex, that the model list file is Coffer's own; **Apply** writes them and closes both dialogs. With a provider and a model chosen, Coffer tests that provider with that model by itself once the draft has rested for a moment (`POST /api/v1/models/test-connection` with the connection's protocol, base URL and stored secret ref — the call of Overview › Model › Test; the page never handles a key), cancels a run the draft has moved past, and shows the result as a line under Model: **Testing connection…**, **Connection OK** with how long it took, or **Connection failed** with the reason and **Retry**. **Review changes** is enabled only when the draft differs from what is applied, names a model, AND the test for exactly this provider and model passed; while it is testing or after a failure it stays off and a line beside it says why. A local runtime connection is tested the same way. The review runs no second test. When Apply is refused as stale, the review says which file changed and offers **Reload preview**, and writes nothing. With the built-in login chosen the dialog offers Provider only, with a line saying the agent picks its model itself (`/model`) and that Coffer sets it only for a provider the user adds.

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

#### Scenario: the built-in login needs no connection test
- **GIVEN** the Change model dialog for an agent on a connection
- **WHEN** the user picks the built-in login
- **THEN** no test runs, no test line is shown and Review changes is on

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
  the tier suggestions for it. Picking things in the form is a DRAFT: it writes nothing, and **Review changes** is enabled only once the draft differs from what is applied, names a model and has passed its connection test ("Review a model change before writing it"). The built-in login needs no model and no test. The agent's Overview reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection.

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
