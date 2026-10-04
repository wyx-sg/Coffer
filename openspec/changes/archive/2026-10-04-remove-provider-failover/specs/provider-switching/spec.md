## REMOVED Requirements

### Requirement: Fail over only before the first content byte
**Reason**: A request is relayed to the one connection the agent is on; the agent's own retries handle transient errors.

### Requirement: Order providers, and fail over in that order
**Reason**: The list is sorted by name and the proxy route is the agent's own connection; the route read-out and the Rotate proxy token scenario move to "Reach API-key and local connections through the local model proxy".

### Requirement: Log every failover in Activity
**Reason**: No request moves between connections, so there is nothing to log.

## MODIFIED Requirements

### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, secret_ref, models, internal_default, transcribe_default, local_runtime}`,
rejecting any other key. The config MUST NOT carry a model the connection runs (no `model`, no
`fast_model`), nor the agents it reaches — reach is the resource row's per-agent `scope` — nor a
manually chosen wire format or a `wire_api`: Codex loads only `responses`, so the Codex block writes that
fixed value and nothing stores it.

`protocol` says what the endpoint speaks: `anthropic`, `openai`, `ollama` or `unknown`, where
`unknown` means a probe was inconclusive. It drives model introspection and whether a key is
required; it does not choose the agent a connection is written into, but a keyless (`ollama`)
connection reaches no agent whatever its scope says — which is why the wire cannot move under a live
connection (see "Refuse to move the wire of a live connection"). The config carries no flag saying a
connection is switched on: which agent runs on which connection is a field of the agent record (see
"Keep an agent on at most one connection"). No wire names an agent: each agent
declares the wire protocols its native config speaks, possibly none (see "Keep projection transforms
pure").

#### Scenario: reject a profile with an unknown wire format
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create a connection with `protocol="grpc"`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row is created.

### Requirement: Offer every connection operation on REST and the web
Create, switch, revert-to-built-in, rename, edit, enable and disable, scope and delete MUST be
available via (a) the REST API and (b) the web surfaces — the Model providers library for create and
delete, the Agent detail page for the switch and the revert, the connection's own page for the
rename, the edit, the scope control and the enabled switch (see "Rename a connection without moving
anything else"). Coffer has no `provider` command group: the list carries no Active column, and a
connection's lifecycle verbs are the ones every kind's page offers. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`) and from its detail page, including correcting the wire.
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
  title, endpoint and description, and the list is sorted by name, with no order heading and no drag handle on a row. It has no per-row switch, because activation is per agent, and no
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
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model**, **Effort** and **Route** and, with the `models` feature on, carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that reach that agent and narrowed by `enabled`: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model**, **Effort** — offering the chosen model's own levels and hidden when it has none — and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). It carries no
  other model setting — no output-limit, subagent, thinking or fast-mode
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

#### Scenario: the Change model dialog shows only provider, model, effort and tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection whose chosen model has no effort levels
- **WHEN** each agent's Change model dialog renders
- **THEN** Claude Code's shows Provider, Model, Effort and Model per tier, and Codex's shows Provider and Model with no Effort
- **AND** neither shows an output-limit, subagent, thinking or fast-mode control

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
body, prompt, completion or secret. Each agent's requests go to exactly one connection, the one the agent is on; the proxy never moves a request to another connection. When that upstream answers, whatever it answers — an error status included — reaches the agent as sent, so the agent's own retries handle transient errors; when it cannot be reached the proxy answers 502. The agent's Overview › Model shows only that its route is through Coffer's proxy, with **Test**; the agent's own proxy token is replaced from **Rotate proxy token** in the agent page's ⋯ menu, offered only while the agent runs on a provider. Everything else it is asked for is 404. The decision is
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

#### Scenario: an upstream error reaches the agent as sent
- **GIVEN** an agent on a connection whose upstream answers 503
- **WHEN** the agent sends a request
- **THEN** the agent receives the 503 and its body unchanged, and no other connection is contacted

#### Scenario: an unreachable upstream is answered with 502
- **GIVEN** an agent on a connection whose endpoint cannot be reached
- **WHEN** the agent sends a request
- **THEN** the proxy answers 502

#### Scenario: Rotate proxy token is offered only while the agent routes through the proxy
- **GIVEN** an agent on a connection and an agent on its built-in login
- **WHEN** each agent's page menu is opened
- **THEN** the first offers Rotate proxy token and the second does not, and choosing it replaces the first agent's token

### Requirement: Meter every proxied request
The local model proxy MUST record one usage record per Messages or Responses
request: when it started, the agent (from its local token), the
session and request class where the agent sends them, the connection, the endpoint, the requested
model, the status, the outcome (`completed`, `error_event`, `truncated`, `client_cancel`,
`upstream_error`, `connect_error`), the time to first token, the duration, and the tokens in
disjoint categories — uncached input, 5-minute and 1-hour cache writes, cache reads, output (with
reasoning as a part of output), and web-search requests. On the Anthropic wire the last value of each
field wins and `message_delta` overrides `message_start`; on the Responses wire the terminal event
carries them and cached tokens are split out of `input_tokens`; a non-streamed body is read the same
way. A stream cut before its terminal event MUST be recorded with usage unknown — never dropped and
never guessed. The proxy opens no database: it spools records to `~/.coffer/proxy-usage/`, and the
daemon ingests completed files into its database with `source = "proxy"` and a de-duplication key
(the upstream's request id, else the proxy's attempt id), deleting a file only after its rows are
committed, so a repeated ingest writes nothing twice. No record carries a body, a prompt, a
completion or a secret. How the proxy reads the stream is
[The local model proxy](../../../docs-site/architecture/model-proxy.md).

#### Scenario: a streamed request is recorded with its tokens by category
- **GIVEN** an agent's Responses request whose stream reports 1000 input tokens of which 600 cached, and 90 output tokens of which 40 reasoning
- **WHEN** the proxy relays it
- **THEN** the record carries 400 uncached input, 600 cache-read and 90 output tokens with 40 reasoning, the agent, the connection, the upstream's request id as its de-duplication key and the outcome `completed`

#### Scenario: the final message_delta overrides message_start
- **GIVEN** an Anthropic stream whose `message_delta` restates larger input and cache totals than its `message_start`
- **WHEN** its usage is read
- **THEN** the record carries the `message_delta` totals

#### Scenario: a stream cut short is recorded as unknown
- **GIVEN** an Anthropic stream that ends before `message_stop`
- **WHEN** its usage is read
- **THEN** the usage is marked unknown and no token count is invented

#### Scenario: nothing stored carries a body or a key
- **GIVEN** a request whose prompt and whose connection key are known strings
- **WHEN** the proxy relays and spools it
- **THEN** neither string appears in the spooled record

#### Scenario: replaying a spool file writes nothing twice
- **GIVEN** a spool file the daemon has ingested
- **WHEN** the same records are ingested again
- **THEN** no usage row or daily total changes
