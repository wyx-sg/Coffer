## MODIFIED Requirements

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

- **Model providers** (route `/model-providers`, in the sidebar's AGENTS group, beside the agents whose models it serves; the old
  `/settings/models`, `/settings/providers` and `/settings/llm-connections` routes redirect there) is
  the connection library: one table of name / vendor / base URL / reach, an Add action and Delete per
  row, and no tabs — no view of which agent runs on what and no Coffer's model tab, because an
  agent's connection is shown and switched on that agent's Model tab and Coffer's own is chosen in
  Settings › General. It has no per-row switch, because activation is per agent. A row MUST say what Coffer ITSELF
  uses the connection for: the `internal_default` connection carries a "Coffer · background model"
  badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with a hint
  naming Settings › General as where it is changed, and the connection's detail header repeats them. The labels lead with
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
- The connection detail page (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) splits into Overview and Models (`/model-providers/<uid>/models`) tabs. Its header carries the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed. Overview carries a read-only **Used by** list: each agent switched to the connection,
  with the model it runs, opening that agent's Model tab (`/agents/<type>/model`); and Coffer's engine and Speech to text
  when the connection is flagged for them, each opening `/settings/general`. Used by carries no
  switch, activate or revert control: an agent's connection is switched only on its Model tab.
- Per-agent connection and model selection lives on the agent detail page's Model tab, filtered to
  the connections that reach that agent and narrowed by `enabled`. The tab carries **Provider**
  (the built-in login or a connection), **Model** and **Effort** — for Claude Code, plus a **Model per
  tier** section (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model) while
  the agent is not on its built-in login (see "Suggest a model for each Claude Code tier"); for
  Codex, Effort offers the chosen model's own levels and is hidden when it has none. It carries no
  other model setting — no context-window, output-limit, subagent, fallback, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. Picking a connection
  or a model there is a DRAFT: it activates nothing and PATCHes nothing. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. A custom connection MUST pass
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
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the agent's Model tab (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)

#### Scenario: the provider library has no tabs
- **GIVEN** the Model providers page
- **WHEN** it renders
- **THEN** it shows the connection table only, with no tab strip, no view of which agent runs on which connection and no Coffer's model tab (TypeScript acceptance test)

#### Scenario: a provider's used-by list is read-only
- **GIVEN** a connection that Claude Code is switched to with a chosen model, and that is flagged `internal_default`
- **WHEN** its detail page's Overview renders
- **THEN** Used by lists Claude Code with its model, opening Claude Code's Model tab, and Coffer's engine, opening `/settings/general`
- **AND** Used by carries no switch, activate or revert control (TypeScript acceptance test)

#### Scenario: the model tab shows only provider, model, effort and the tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection whose chosen model has no effort levels
- **WHEN** each agent's Model tab renders
- **THEN** Claude Code's shows Provider, Model, Effort and Model per tier, and Codex's shows Provider and Model with no Effort
- **AND** neither shows a context-window, output-limit, subagent, fallback, thinking or fast-mode control

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

On the agent's Model tab the tiers are a **Model per tier** section — Fable only when the connection
lists a Fable model — prefilled with the suggestion, each editable from the connection's models, with
**Reset to suggested** putting every tier back to the prefill; confirming stores them as the agent's
`tier_models`. On the built-in login the section is hidden.

#### Scenario: a non-Claude connection pins every tier to the model
- **GIVEN** a Claude Code agent bound to `kimi-k3` and a connection whose curated models are `kimi-k3` and `kimi-k3-mini`
- **WHEN** Coffer suggests the tiers
- **THEN** Opus, Sonnet and Haiku are `kimi-k3`, and no Fable tier is suggested

#### Scenario: a Claude-id gateway matches each tier by name
- **GIVEN** a connection whose curated models are `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5` and `claude-fable-1`
- **WHEN** Coffer suggests the tiers for a Claude Code agent on it
- **THEN** Opus, Sonnet, Haiku and Fable are the model whose name carries that tier

#### Scenario: an edited tier resets to the suggestion
- **GIVEN** the Model per tier section with Haiku changed by the user
- **WHEN** the user chooses Reset to suggested
- **THEN** every tier returns to Coffer's prefill, and confirming writes those pins

#### Scenario: the built-in login shows no tiers
- **GIVEN** a Claude Code agent on its built-in login
- **WHEN** its Model tab renders
- **THEN** it shows Provider, Model and Effort and no Model per tier section, and no tier pin is in `settings.json`

### Requirement: Record a context window and effort levels with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window** and its **effort levels**, with the level used when an agent names
none, which the Codex catalogue needs (see "Project into Codex config without clobbering it"). They
travel through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry, are read from
the endpoint where it reports them, and are otherwise entered by the user; an unknown value is left
out of the stored document rather than guessed.

The connection's Models tab shows and edits them.

#### Scenario: a curated model keeps its window and levels
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window and the levels low, medium and high for `gpt-x`
- **THEN** the connection reports them on `gpt-x`

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

When the runtime does not report a chosen model's window, the Model tab MUST show a required
**Context window** field before the choice can be confirmed, and it MUST warn when the window is
below 64k tokens, which agents' own compaction and tools cannot work well within. Neither
compatibility key is a field the user sets.

#### Scenario: create a keyless local runtime connection
- **GIVEN** an Ollama runtime answering on a loopback port
- **WHEN** the user runs `coffer provider add ollama --protocol anthropic --base-url http://127.0.0.1:11434 --local`
- **THEN** the connection persists with no secret, records the runtime, version and wires it serves, and curates its tool-capable models with their served windows

#### Scenario: a local connection sets Claude Code's compatibility key
- **GIVEN** a Claude Code agent switched to a local model connection whose model records a 131072-token window
- **WHEN** the connection is activated
- **THEN** `settings.json` carries `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` = `1` and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` = `131072`, with every tier pinned to the local model

#### Scenario: a local runtime connection must be on this machine
- **GIVEN** the daemon is running
- **WHEN** a connection is created with a `local_runtime` and a non-loopback base URL
- **THEN** it is refused as 422

#### Scenario: a local model's window is read from the runtime
- **GIVEN** a local model connection whose runtime serves `qwen-coder` with a 131072-token window
- **WHEN** a Codex agent is switched to it with that model
- **THEN** the catalogue entry carries a 131072-token window with compaction at 90% of it, and no Context window field is shown

#### Scenario: an unreadable window asks for one and warns when small
- **GIVEN** a local model connection whose runtime does not report the window
- **WHEN** the user picks it on the Model tab and enters 32000
- **THEN** confirm stays disabled until a window is entered, and the tab warns that 32000 is below 64k
- **AND** confirming writes that window

