## MODIFIED Requirements

### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, secret_ref, models, transcribe_default, local_runtime}`,
rejecting any other key. The one retired key, `internal_default`, is accepted and ignored
(see "Ignore a stored internal-default flag"). The config MUST NOT carry a model the connection runs (no `model`, no
`fast_model`), nor the agents it reaches — reach is the resource row's per-agent `scope` — nor a
manually chosen wire format or a `wire_api`: Codex loads only `responses`, so the Codex block writes that
fixed value and nothing stores it.

`protocol` says what the endpoint speaks: `anthropic`, `openai` or `unknown`, where
`unknown` means a probe was inconclusive. A fourth value, `ollama`, is retired: it is never offered and
a stored one is only read (see "Stop offering the ollama protocol"). The protocol drives model
introspection and whether a key is required; it does not choose the agent a connection is written into,
but the wire cannot move under a live connection (see "Refuse to move the wire of a live connection"). The config carries no flag saying a
connection is switched on: which agent runs on which connection is a field of the agent record (see
"Keep an agent on at most one connection"). No wire names an agent: each agent
declares the wire protocols its native config speaks, possibly none (see "Keep projection transforms
pure").

#### Scenario: reject a profile with an unknown wire format
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create a connection with `protocol="grpc"`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row is created.

### Requirement: Store an inline secret under a minted opaque ref
On create with `secret_value`, the system MUST store the raw key under a freshly minted opaque ref
(`provider/<uuid4>/key`) in the Fernet vault and persist only that ref — deriving the ref from the
name would make the name a key, which it is not. Supplying `secret_ref` instead reuses an
existing vault entry and creates none. For `anthropic` / `openai` / `unknown`, exactly one of
`secret_value` or `secret_ref` MUST be supplied; both or neither MUST be rejected `422`.

#### Scenario: create an anthropic provider profile with an inline secret
- **GIVEN** no connection named `my-provider` exists,
- **WHEN** the user creates one with `protocol="anthropic"`, a `base_url` and `secret_value` (the raw API key),
- **THEN** it is persisted with a `secret_ref` of the form `provider/<uuid4>/key`, the raw key is stored in the Fernet vault under that ref, `ProviderOut` is returned with no secret field, and `resource_created` is audited.
#### Scenario: create a profile that reuses an existing secret ref
- **GIVEN** a secret already exists under ref `shared/key`,
- **WHEN** the user creates a connection supplying `secret_ref="shared/key"` (no `secret_value`),
- **THEN** it is persisted pointing at the existing ref, no new vault entry is created, and `ProviderOut` reflects the supplied `secret_ref`.
#### Scenario: reject a profile that supplies neither a secret nor a secret ref
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create an **anthropic** connection (the neither-rule applies to anthropic / openai / unknown; only a local runtime connection may supply neither) without either `secret_value` or `secret_ref`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row and no vault entry are created.

### Requirement: Keep an agent on at most one connection
Which connection an agent runs on MUST be one field of the agent record, `AgentConfig.connection_uid`
([agent-registry](../agent-registry/spec.md) "Carry the connection an agent runs on on the agent
record"), so an agent runs on at most one connection by construction: there is no flag on the
connection that could be set on two of them. Switching an agent onto a connection changes that agent's
field and its own native config file and nothing else — another agent of the same type, or one of
another type, that runs on the previous connection stays on it. One pure function,
`connection_for_agent(agent, connections)`, answers which connection an agent is on, and projection,
the proxy's route, the chat model list and the protocol lock all ask it. A
connection SERVES an agent when the agent's `connection_uid` names it, it exists, is enabled, is not a
stored `ollama` connection, and its scope reaches the agent; a pointer that names a missing, switched-off or
out-of-scope connection means the agent is treated as on its built-in login, and the reconciler reports
the keys left in its file rather than silently routing it elsewhere.

#### Scenario: switching one agent onto a connection moves only that agent
- **GIVEN** a Claude Code agent and a Codex agent that both run on connection A, and a connection B that reaches Claude Code
- **WHEN** the user switches the Claude Code agent onto B
- **THEN** the Claude Code agent's `connection_uid` is B's uid and its `settings.json` carries B's projection
- **AND** the Codex agent still runs on A, with its `config.toml` and `connection_uid` untouched

### Requirement: Switch one agent at a time
`POST /api/v1/providers/{uid}/activate` with body `{agent_type}` (the agent's Change model dialog calls it) MUST switch THAT agent onto the
connection. The operation:

1. requires the connection to exist, else 404, and the agent of that type to be registered, else 404;
2. refuses with 409 `PROVIDER_DOES_NOT_REACH_AGENT` when the connection is switched off or
   the connection's scope does not name the agent, and with 422 `PROVIDER_PROTOCOL_RETIRED` for a
   stored `ollama` connection;
3. projects the connection into that agent's native config file, recording the file's prior content;
4. sets the agent's `connection_uid` to the connection's uid;
5. emits `provider_switched`;
6. returns `{activated, protocol, agent_type, agent}`.

The projection MUST run before the agent record is written, and a failure at any step MUST put the
file back and leave the record unchanged, so the agent is never left pointed at the proxy with no
connection behind it. The operation writes no other agent's file and no other agent's record.

Reach is the framework's per-agent `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)); there is no
`compatible_agents` field in the config, in `ProviderCreate` or in `ProviderPatch`. A new connection
is pre-filled from its wire through the kind's `default_scope` hook — unscoped for a credentialed
wire (including `unknown`, so an inconclusive probe hides nothing and the user decides), which reaches
every agent including one registered later; a stored `ollama` connection with no reach record reads as nothing (`scope = []`). Re-targeting is a scope edit (`PUT /api/v1/resources/{uid}/scope`, which the
connection's scope control calls). `scope = []` is dormant: the connection reaches no
agent, so no agent resolves its key. The projection writer MUST be chosen by AGENT type, not by
protocol: a connection reaching `claude_code` writes Claude's `settings.json` in the anthropic shape
and one reaching `codex` writes Codex's `config.toml`, which is how an OpenAI-compatible gateway is
routed to Claude Code. Coffer translates nothing between protocols.

#### Scenario: a switch whose write fails puts the file back
- **GIVEN** a Codex agent whose `config.toml` the user edits between Coffer's read and its write
- **WHEN** the user switches the agent onto a connection and the write is refused as stale
- **THEN** the switch fails with `config_file_stale`, the user's Codex edit survives, and the agent's `connection_uid` is unchanged

#### Scenario: a connection the agent is not reached by is refused
- **GIVEN** a registered Codex agent and a connection scoped to `["claude_code"]`
- **WHEN** the user switches the Codex agent onto it
- **THEN** the switch is refused with 409 `PROVIDER_DOES_NOT_REACH_AGENT`, no file is written and the agent's `connection_uid` is unchanged

#### Scenario: route an openai-compatible connection to Claude Code with its scope
- **GIVEN** a Claude Code agent is registered and an `openai`-wire connection is created and then scoped to `["claude_code"]`,
- **WHEN** the user switches the Claude Code agent onto that connection,
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, and the model proxy routes that agent's requests to exactly that connection with that connection's key.

### Requirement: Refuse to move the wire of a live connection
A connection's `protocol` MUST be correctable — the probe that guessed the wire can be wrong, and
re-entering the key to fix it is a worse answer than editing it. But the wire is not inert, so
changing it MUST be refused with 409 `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while an agent runs on
the connection, with a message that names the way out (switching each agent that runs on it back to its built-in
login, `POST /api/v1/providers/use-builtin/{agent_type}`). Moving the wire of a connection an agent runs on would leave the native config Coffer
already wrote standing, with nothing left that would ever take it off. Silently de-projecting instead
MUST NOT be the answer: the developer asked to change a field, not to take their agents off a
gateway. Re-sending the wire the connection already has is not a change, so a client that submits a
whole form is never told its unchanged dropdown is a conflict. The refusal MUST be reachable on every
surface that offers the edit — REST and the connection's form.

#### Scenario: correcting a mis-probed wire is refused while the connection is live
- **GIVEN** a connection that an agent runs on and is projected into,
- **WHEN** the user patches its `protocol` to a different wire,
- **THEN** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names switching each agent running on it back to its built-in login (`POST /api/v1/providers/use-builtin/{agent_type}`) as the way out
- **AND** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (see "Refuse to move the wire of a live connection")

### Requirement: Offer every connection operation over REST and in the web UI
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
half an operation. Which connection speech-to-text runs on is chosen in
Settings › General (see "Keep an independent speech-to-text
default"), not on the connection's own page.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's Agents group, beside the agents whose models it serves) is
  one page under one header — the title, an Experimental tag, a one-line description and the page's one primary button, **Add provider** — over two tabs, **Providers** and **Usage** ("Show metered usage on a Usage tab of Model providers"). Providers is the connection library: a list of connections beside the open one. It has no view of which agent runs on what and no Coffer's model tab, because an agent's connection is shown and changed in that agent's Overview › Model and the speech-to-text connection is chosen in Settings › General. The page opens on the first connection, and with none it is a welcome panel. Each row shows
  the connection's vendor mark, its name, its protocol and what it offers (its curated model count,
  or all models), and the marks of the agents running on it, read from the agents' `connection_uid`; a filter narrows the list over name,
  title, endpoint and description, and the list is sorted by name, with no order heading and no drag handle on a row. It has no per-row switch, because activation is per agent, and no
  per-row reach or delete: both are on the open connection's header. A row MUST say what Coffer
  ITSELF uses the connection for: the `transcribe_default` connection carries a "Coffer · speech to
  text" badge with a hint naming Settings › General as where it is changed, and the connection's Used by repeats
  it. The label leads with Coffer because a bare "Speech to text" reads as a capability of the
  provider rather than a job Coffer gives it; an agent's mark on a row is a different fact — that
  agent is switched to the connection. The vendor mark is derived from `base_url` by matching the
  preset list (an unmatched endpoint gets Coffer's neutral provider glyph); the name is the user's
  own, and the row links to the detail page by `uid`.
- The add-connection dialog asks for the vendor from a grid of eight equal buttons — Anthropic, OpenAI, Google Gemini, DeepSeek, OpenRouter, Ollama, LM Studio and Custom — which fill in the
  endpoint and protocol (Custom reveals a manual protocol selector), in two steps, Endpoint and then Models. A local runtime (Ollama, LM Studio) asks for no key, offers only the wires the detected runtime serves to agents (Anthropic, OpenAI) and,
  until a runtime is detected, does not let the user go on to Models; the connection's Name
  appears once a runtime is chosen. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) is one column opened beside the list — Used by, Endpoint, Models — and has no tabs. Its header carries a health pill (Reachable, Key rejected or Unreachable, read from a probe that runs when it opens), the protocol, the host and, when the endpoint answered, how long it took, and the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed — with Test, Edit and a menu holding Delete provider ("Review what deleting a connection changes"). **Used by** is read-only: each agent whose `connection_uid` names the connection (and that the connection still serves),
  with the model it runs, as a link reading "<Agent> › Change model" that opens that agent's page with its Change model dialog already open (`/agents/<type>?change-model=1`); and Speech to text
  when the connection is flagged for it, reading "Settings › General" and opening it. Used by carries no
  switch, activate or revert control, and no row repeats a fault: a connection's fault shows in its header pill and in the section it belongs to (Endpoint for Unreachable or Key rejected, Models for a failed listing).
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model** and **Route** and, with the `models` feature on, carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that reach that agent and narrowed by `enabled`: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model** and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). It carries no
  other model setting — no output-limit, subagent, thinking or fast-mode
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
- **GIVEN** connection A is the speech-to-text default, and connection B carries no flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · speech to text" badge and B's row carries none (TypeScript acceptance test)

#### Scenario: the provider library has no tabs
- **GIVEN** the Model providers page
- **WHEN** it renders
- **THEN** its only tab strip is the page header's Providers | Usage, and the library itself has no view of which agent runs on which connection and no Coffer's model tab (TypeScript acceptance test)

#### Scenario: a provider's used-by list is read-only
- **GIVEN** a connection that Claude Code runs on (its `connection_uid`) with a chosen model, and that is flagged `transcribe_default`
- **WHEN** its detail page renders
- **THEN** Used by lists Claude Code with its model, as a link "Claude Code › Change model" to `/agents/claude_code?change-model=1`, and Speech to text, opening `/settings/general`
- **AND** Used by carries no switch, activate or revert control (TypeScript acceptance test)

#### Scenario: the Change model dialog shows only provider, model and tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection
- **WHEN** each agent's Change model dialog renders
- **THEN** Claude Code's shows Provider, Model and Model per tier, and Codex's shows Provider and Model
- **AND** neither shows an effort, output-limit, subagent, thinking or fast-mode control

## REMOVED Requirements

### Requirement: Keep ollama connections internal-only
**Reason**: The `ollama` protocol is no longer offered, and the internal engine it served is gone.
**Migration**: See "Stop offering the ollama protocol".

### Requirement: Make the secret optional for ollama and local runtimes
**Reason**: Only a local runtime connection is keyless now; the `ollama` protocol is no longer offered.
**Migration**: See "Configure a local model connection", which creates a local runtime connection without a key.

## ADDED Requirements

### Requirement: Stop offering the ollama protocol
The `ollama` protocol (the Ollama-native API) is retired. Creating a connection with it
(`POST /api/v1/providers`) and moving a connection onto it (`PATCH /api/v1/providers/{uid}` with
`protocol="ollama"` for a connection that does not already hold it) MUST be refused with `422
PROVIDER_PROTOCOL_RETIRED` before anything is stored. The message names the way on: a local Ollama
runtime is added on its Anthropic or OpenAI wire. A stored connection that already holds `ollama`
MUST stay readable and listed, MUST reach no agent whatever its scope says, MUST be refused with the
same code when an agent is switched onto it, and MUST remain deletable; its other fields stay
editable, and re-sending its stored protocol is not a move. The add-connection dialog MUST NOT offer
`ollama`: a detected local runtime offers only the wires it serves to agents, and a stored
`ollama` connection still renders on the list and its detail page. The local Ollama runtime itself is
unaffected: it is reached over its Anthropic and OpenAI wires.

#### Scenario: refuse to create a connection on the ollama protocol
- **GIVEN** the daemon is running,
- **WHEN** the user creates a connection with `protocol="ollama"`,
- **THEN** the request is refused `422` `PROVIDER_PROTOCOL_RETIRED` and no connection is stored

#### Scenario: refuse to move a connection onto the ollama protocol
- **GIVEN** a connection on the `anthropic` protocol,
- **WHEN** the user patches its `protocol` to `ollama`,
- **THEN** the request is refused `422` `PROVIDER_PROTOCOL_RETIRED` and the stored protocol is unchanged

#### Scenario: a stored ollama connection stays readable and deletable
- **GIVEN** a stored connection whose protocol is `ollama`,
- **WHEN** the user lists connections, reads it, re-sends its protocol in a patch and deletes it,
- **THEN** it is listed with no reachable agent, the patch succeeds, and the delete removes it

#### Scenario: activating an ollama connection writes no native config
- **GIVEN** a registered Claude Code agent and a stored `ollama` connection whose scope names that agent
- **WHEN** the user switches the agent onto the connection
- **THEN** the switch is refused with `422 PROVIDER_PROTOCOL_RETIRED`, no native config file is written and the agent's `connection_uid` is unchanged
- **AND** the connection reports no reachable agent
