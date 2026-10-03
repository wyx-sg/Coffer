## MODIFIED Requirements

### Requirement: Keep an agent on at most one connection
Which connection an agent runs on MUST be one field of the agent record, `AgentConfig.connection_uid`
([agent-registry](../agent-registry/spec.md) "Carry the connection an agent runs on on the agent
record"), so an agent runs on at most one connection by construction: there is no flag on the
connection that could be set on two of them. Switching an agent onto a connection changes that agent's
field and its own native config file and nothing else — another agent of the same type, or one of
another type, that runs on the previous connection stays on it. One pure function,
`connection_for_agent(agent, connections)`, answers which connection an agent is on, and projection,
the proxy's route, the chat model list and the protocol lock all ask it. A
connection SERVES an agent when the agent's `connection_uid` names it, it exists, is enabled, is not
`ollama`, and its scope reaches the agent; a pointer that names a missing, switched-off or
out-of-scope connection means the agent is treated as on its built-in login, and the reconciler reports
the keys left in its file rather than silently routing it elsewhere.

#### Scenario: switching one agent onto a connection moves only that agent
- **GIVEN** a Claude Code agent and a Codex agent that both run on connection A, and a connection B that reaches Claude Code
- **WHEN** the user switches the Claude Code agent onto B
- **THEN** the Claude Code agent's `connection_uid` is B's uid and its `settings.json` carries B's projection
- **AND** the Codex agent still runs on A, with its `config.toml` and `connection_uid` untouched

### Requirement: Resolve each model's price from the provider, its API, or the bundled list
Cost MUST be estimated at ingest, per model and per token category, at the price resolved for the
connection that served the request, in this order: (1) the price the user set on that connection
for the model ("You set" — relays and resellers price differently); (2) a model runtime on this
machine costs nothing; (3) the price the connection's own API reported when its models were last
listed or refreshed (OpenRouter-style `/models` pricing), remembered in a derived store and never
fetched per request; (4) the price list bundled with the release — pydantic/genai-prices (MIT),
provider-scoped by the connection's base URL (an endpoint no provider claims is priced as the
model's vendor), with historical prices by the request's start time, tiered prices by the
request's total input tokens, and cache read and write rates — supplemented by Coffer's own
Anthropic rates for models the list has not caught up with. The bundled snapshot is refreshed at
release time (`make refresh-prices`), and between releases the daemon refreshes it once a day (see
"Refresh the bundled price list in the background"); whichever copy is fresher is used, and no
price is ever looked up over the network per request or while a request is being costed. Each
cost MUST be stored with the label of the price it used (`override:<connection uid>`,
`provider:<connection uid>`, `bundled:<list version>` or `local`) so a later list never rewrites
history. A cache category a price leaves out is charged at its input rate. A model none of them
prices MUST be marked unpriced, never costed at zero. `POST /api/v1/providers/{uid}/prices`
resolves the same prices for the Models section, each with its source; `coffer provider price
<name> [<model> --input <usd> --output <usd> | --reset]` shows them and sets or resets the price
the user records. Every surface labels cost as estimated. Where nothing in a cost is priced, the web
UI and the CLI MUST show `—` in its place, never `$0.00`, and the web UI MUST say why and where a
price is set in the dash's tooltip and accessible name. Subscription logins do not pass through
Coffer and are not metered.

#### Scenario: a known model is priced per category
- **GIVEN** a record for `claude-sonnet-4-6` through `https://api.anthropic.com` with input, cache-write, cache-read and output tokens
- **WHEN** it is priced
- **THEN** each category is charged at that model's own rate from the bundled list

#### Scenario: an unknown model is marked unpriced, never zero
- **GIVEN** a record for a model no connection price, provider API or bundled list prices
- **WHEN** it is priced
- **THEN** it has no cost and is marked unpriced

#### Scenario: stored cost names the price it used
- **GIVEN** one record priced from the bundled list and one from its connection's own price
- **WHEN** both are ingested
- **THEN** each row names the price it was costed with

#### Scenario: a price is taken from the first source that has one
- **GIVEN** a connection with its own price for one model, a price its API reported for a second, the bundled list's price for a third, and a local runtime connection
- **WHEN** each model's price is resolved
- **THEN** the first reads You set, the second From the connection, the third Bundled, and the local runtime's model costs nothing

#### Scenario: each price names where it came from
- **GIVEN** a provider whose models are priced from different sources, and one model nothing prices
- **WHEN** its Models section renders
- **THEN** each priced model shows its input and output price per 1M tokens with You set, From <provider> or Bundled · updated <the date of the list in use>, and the unpriced one shows `—` with Set price…

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model through a connection that records no price for it, whose API reported none, and that the bundled list does not know
- **WHEN** the Usage page and `coffer usage` show that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage tab the dash's tooltip says no price is known for it and that one is set on its provider

### Requirement: Refresh the bundled price list in the background
Besides the snapshot shipped in the build, the daemon MUST refresh the model price list from the
file pydantic/genai-prices publishes — the one its own `UpdatePrices` fetches,
`https://raw.githubusercontent.com/pydantic/genai-prices/refs/heads/main/prices/new_data/v2/data.json`,
a fixed URL Coffer chose, never one a user typed — once shortly after it starts and then every
24 hours. The fetch MUST be a read-only `GET` with a timeout and a size cap that sends nothing about
the user. The payload MUST be validated (a provider array that parses, with Anthropic and OpenAI in
it) before it is kept, and cached atomically at `~/.coffer/derived/genai-prices.json` with when it
was fetched. Pricing MUST use whichever of the cache and the bundled snapshot is fresher, and MUST
never wait on the network: a failed fetch keeps the list in use and is logged once per run of
failures, not on every attempt. The refresh is on by default and is switched per machine —
**Refresh model prices** in Settings › General under Coffer's model, `coffer config set
prices.refresh on|off`, `PUT /api/v1/providers/price-list` — and `COFFER_PRICE_REFRESH=off` pins it
off. `GET /api/v1/providers/price-list` says which list is in use, the day its data is from, and
the refresh's state; a bundled price reads "Bundled · updated <that day>".

#### Scenario: a refreshed list is cached and used
- **GIVEN** the published list prices a model differently from the bundled snapshot
- **WHEN** the refresh runs
- **THEN** the list is cached with when it was fetched, the model is priced from it, and a daemon started later uses the cache without fetching

#### Scenario: a failed refresh keeps the list in use
- **GIVEN** a refreshed list in use
- **WHEN** the next two refreshes fail, one unreachable and one returning something that is not a price list
- **THEN** the list in use and its cache are unchanged, and the failure is logged once

#### Scenario: the fresher of the cache and the bundled list is used
- **GIVEN** a cached list older than the bundled snapshot, and another newer than it
- **WHEN** a price is looked up with each
- **THEN** the older cache gives way to the bundled snapshot and the newer cache is used

#### Scenario: the refresh can be turned off
- **GIVEN** Refresh model prices turned off
- **WHEN** the refresh's schedule comes round
- **THEN** nothing is fetched and prices come from the bundled snapshot

### Requirement: Offer every connection operation on REST, CLI and web
Create, switch, revert-to-built-in, rename and delete MUST be available via (a) the REST API, (b)
`coffer provider list|show|add|edit|rm|enable|disable|scope|switch|builtin|detect-local|order|price` with `--json` on
`list` and `show` (`switch <name> [--agent claude_code|codex]` switches one agent, or with no `--agent` every registered, enabled agent the connection reaches; the list carries no Active column) — the lifecycle verbs being the ones every kind's group offers, and rename being
`coffer provider edit <name> --name <new>` (see "Rename a connection without moving anything
else") — and (c) the web surfaces — the Model providers library for create and delete, the Agent
detail page for the switch, the connection's own page for the rename. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`, `fallback`), over the CLI
(`coffer provider edit <name> [--name <new>] [--title <text>] [--description <text>] [--protocol <wire>] [--base-url <url>] [--secret <value>] [--fallback|--no-fallback]`)
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

- **Model providers** (route `/model-providers`, in the sidebar's Agents group, beside the agents whose models it serves) is
  the connection library: a list of connections beside the open one, and no tabs — no view of which
  agent runs on what and no Coffer's model tab, because an agent's connection is shown and switched on
  that agent's Model tab and Coffer's own is chosen in Settings › General. The page header carries
  Add; the page opens on the first connection, and with none it is a welcome panel. Each row shows
  the connection's vendor mark, its name, its protocol and what it offers (its curated model count,
  or all models), and the marks of the agents running on it, read from the agents' `connection_uid`; a filter narrows the list over name,
  title, endpoint and description, and the list's order is the fallback order (see "Order providers,
  and fail over in that order"). It has no per-row switch, because activation is per agent, and no
  per-row reach or delete: both are on the open connection's header. A row MUST say what Coffer
  ITSELF uses the connection for: the `internal_default` connection carries a "Coffer · background
  model" badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with
  a hint naming Settings › General as where it is changed, and the connection's Used by repeats
  them. The labels lead with Coffer because a bare "Speech to text" reads as a capability of the
  provider rather than a job Coffer gives it; an agent's mark on a row is a different fact — that
  agent is switched to the connection. The vendor mark is derived from `base_url` by matching the
  preset list (an unmatched endpoint gets Coffer's neutral provider glyph); the name is the user's
  own, and the row links to the detail page by `uid`.
- The add-connection dialog asks for the protocol rather than detecting it: it offers provider
  presets (OpenAI / Anthropic / Google Gemini / DeepSeek / OpenRouter / Ollama) that fill in the
  endpoint and protocol, plus Custom, which reveals a manual protocol selector; the CLI takes
  `--protocol`. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail page (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) has no tabs: it is one column — Used by, Endpoint, Models. Its header carries the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed — with Test, Edit and a menu holding Delete. **Used by** is read-only: each agent whose `connection_uid` names the connection (and that the connection still serves),
  with the model it runs, opening that agent's Model tab (`/agents/<type>/model`); and Coffer's engine and Speech to text
  when the connection is flagged for them, each opening `/settings/general`. Used by carries no
  switch, activate or revert control: an agent's connection is switched only on its Model tab.
- Per-agent connection and model selection lives on the agent detail page's Model tab, filtered to
  the connections that reach that agent and narrowed by `enabled`. The tab carries **Provider**
  (the built-in login or a connection), **Model** and **Effort** — for Claude Code, plus a **Model per
  tier** section (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model) while
  the agent is not on its built-in login (see "Suggest a model for each Claude Code tier"). Effort
  offers the chosen model's own levels and is hidden when it has none; on the built-in login the
  Model is the agent's own default, shown rather than offered. It carries no
  other model setting — no context-window, output-limit, subagent, fallback, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. While the agent is on
  a connection, the tab also shows, read-only, which provider is tried next if that connection
  fails (see "Order providers, and fail over in that order") and the last four characters of the
  agent's own proxy token with **Rotate**; the built-in login bypasses the proxy and shows neither. Picking a connection
  or a model there is a DRAFT: it activates nothing and PATCHes nothing. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. A custom connection MUST pass
  `POST /api/v1/models/test-connection` with the staged model before it can be confirmed; confirm
  stays disabled until the test for the CURRENT draft passes, and changing the connection or the
  model resets the result. Confirming PATCHes the per-agent binding and then switches the agent onto the
  connection (`POST /api/v1/providers/{uid}/activate {agent_type}`) — the only step that writes native config. The tab reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection. Switching back to the built-in login needs
  no test.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `secret_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the command line covers create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch <name> --agent <agent_type>` and `coffer provider builtin <agent_type>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the agent's `connection_uid` is empty, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections, marks the one an agent runs on with that agent's mark, and shows the open connection's endpoint and its reach in the header's shared control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the agent's Model tab (TypeScript acceptance test).

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
- **THEN** Used by lists Claude Code with its model, opening Claude Code's Model tab, and Coffer's engine, opening `/settings/general`
- **AND** Used by carries no switch, activate or revert control (TypeScript acceptance test)

#### Scenario: the model tab shows only provider, model, effort and the tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection whose chosen model has no effort levels
- **WHEN** each agent's Model tab renders
- **THEN** Claude Code's shows Provider, Model, Effort and Model per tier, and Codex's shows Provider and Model with no Effort
- **AND** neither shows a context-window, output-limit, subagent, fallback, thinking or fast-mode control

## ADDED Requirements

### Requirement: Show metered usage on a Usage tab of Model providers
The Model providers page MUST carry two tabs under one header — **Providers** and **Usage**. The
header is the title with the Experimental tag, the line "Where your agents’ models come from, and
what requests through Coffer cost." and the primary **Add provider** button, the same on both tabs.
The tab is in the address: `/model-providers` and `/model-providers/<uid>` are Providers,
`/model-providers?tab=usage` is Usage. There MUST be no `/usage` page and no Usage sidebar entry.
The Usage tab shows only what Coffer's proxy metered for API-key requests: a filter row with a
date-only time range (Today, Last 7 days, Last 30 days, This month, or a custom range of days, up to
90 days back), an **Agent** pill, a **Provider** pill, **Clear filters** while one is set and a ghost
**Export CSV** button at the right; five tiles in one row — Cost (estimated), whose "?" holds the
note on which prices costed the range, Input, Output, Cache read and Cache write; a Cost per day
chart in the data colour with today lighter; a segmented By model · By agent · By day over a bordered
table with a Total row, a footer "Cost of priced models only." with **Edit prices**, which switches
to the Providers tab, and, by day, the latest seven days then "Showing 7 of N · Show all". The range,
the filters and the breakdown are in the address. A cost no price covers reads `—`, with the reason
on hover. Before any API-key request has ever been metered the tab is one whole-page empty state —
"No API-key usage yet" and **Open Providers**, which switches to the Providers tab — with no filter
row and no export. Coffer MUST NOT show, read, store or report an agent's own subscription quota
anywhere, nor offer a status-line wrapper for it; the data is Coffer's own, so the tab has no Refresh.

#### Scenario: Usage is a tab of Model providers
- **GIVEN** the Model providers page with a provider
- **WHEN** it renders and the user chooses the Usage tab
- **THEN** the header carries the Experimental tag, the description and Add provider on both tabs, and the address becomes `/model-providers?tab=usage`
- **AND** `/usage` is not a page and the sidebar has no Usage entry

#### Scenario: the Usage tab keeps its range and filters in the address
- **GIVEN** the Usage tab with metered requests
- **WHEN** the user picks Last 30 days, the By agent view and an Agent and a Provider filter
- **THEN** the address carries `range`, `by`, `agent` and `provider` beside `tab=usage`, the summary and the export are asked with the same range, grouping and filters, and a custom range is two days

#### Scenario: the Usage tab has nothing to show before any usage
- **GIVEN** no API-key request has ever been metered
- **WHEN** the Usage tab is opened
- **THEN** it shows "No API-key usage yet" and Open Providers, which switches to the Providers tab, and no time range, filter pills or Export CSV

#### Scenario: Coffer shows no subscription quota
- **GIVEN** agents on their own subscription logins
- **WHEN** the Usage tab is opened
- **THEN** it shows no quota meter, no Refresh and no status-line wrapper, and no `/api/v1/usage/quota` route is asked for

## REMOVED Requirements

### Requirement: Show a subscription's official quota as of when it was seen
**Reason**: Coffer no longer shows, reads or stores an agent's own subscription allowance. It was the vendor's number relayed through a driven session or a short-lived `codex app-server`, it covered only the sessions Coffer drives, and the Usage page it sat on is now the Usage tab of Model providers, which shows only what Coffer metered.
**Migration**: None. `GET /api/v1/usage/quota`, `POST /api/v1/usage/quota/refresh` and `coffer usage quota` are gone; the `quota_snapshots` table is dropped by migration 0140. Read the allowance in the agent itself.

### Requirement: Offer an opt-in statusline wrapper
**Reason**: The wrapper only existed to feed the quota readings.
**Migration**: None. `coffer usage statusline`, `POST /api/v1/usage/quota/statusline` and `coffer usage quota --prompt` are gone. A `statusLine` command a person set to `coffer usage statusline -- <command>` in an agent's `settings.json` stops working; setting it back to the original command is the person's edit.
