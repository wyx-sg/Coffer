## ADDED Requirements

### Requirement: Ignore a stored internal-default flag
The system MUST accept a connection whose stored config still carries
`internal_default` and MUST ignore it: the key changes no behaviour, raises no
validation error, appears in no `ProviderOut`, and is dropped from the file by
the connection's next write. A file holding `internal_default` on several
connections MUST be accepted the same way, because the key means nothing.

#### Scenario: ignore a stored internal-default flag when a connection is read
- **GIVEN** a connection file whose config carries `internal_default: true` beside valid fields,
- **WHEN** the connection is listed with `GET /api/v1/providers`,
- **THEN** it is returned with its valid fields and no `internal_default` field, and no validation error is raised.

#### Scenario: drop a stored internal-default flag on the next write
- **GIVEN** a connection file whose config carries `internal_default: true`,
- **WHEN** the connection is edited with `PATCH /api/v1/providers/{uid}`,
- **THEN** the rewritten file carries no `internal_default` key and the edited field is as patched.

#### Scenario: accept two connection files that both carry the retired flag
- **GIVEN** two connection files that both carry `internal_default: true`,
- **WHEN** the vault is read and a sync round checks out a tree holding both,
- **THEN** neither file is refused and the round does not stop on them.

## MODIFIED Requirements

### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, secret_ref, models, transcribe_default, local_runtime}`,
rejecting any other key. The one retired key, `internal_default`, is accepted and ignored
(see "Ignore a stored internal-default flag"). The config MUST NOT carry a model the connection runs (no `model`, no
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

### Requirement: Never return the raw secret in a connection
`ProviderOut` MUST NEVER include the raw secret. `secret_ref`, `compatible_agents` (the
configured reach, read-only), `models`, `enabled` and
`transcribe_default` MUST be included. `ProviderOut` carries no switched-on flag: which agents run on
a connection is read from the agents' `connection_uid` ([agent-registry](../agent-registry/spec.md)
"Carry the connection an agent runs on on the agent record"), and `AgentOut` carries it.

`enabled` narrows the projection and only the projection: a disabled connection projects into
nothing and resolves no key, but `compatible_agents` MUST still report the CONFIGURED reach without
that narrowing, because the two answer different questions and one field cannot carry both —
folding `enabled` in made switching a connection off look like it erased its agent list. `enabled`
travels on the same payload, so a client that wants the intersection takes it, and the two clients
that offer a connection to act on now — the agent's connection picker and the chat model picker —
MUST take it.

#### Scenario: list provider profiles
- **GIVEN** two connections exist (one anthropic, one openai),
- **WHEN** the user lists all connections,
- **THEN** both appear in `ProviderOut[]`, none includes the raw secret, and neither carries an `is_active` field.

### Requirement: Record provider operations as their own audit events
`PROVIDER_SWITCHED` (`"provider_switched"`), `PROVIDER_TRANSCRIBE_DEFAULT_SET`
(`"provider_transcribe_default_set"`) and `PROVIDER_PROJECTION_REFUSED`
(`"provider_projection_refused"`) MUST be in `AuditEventType` and emitted from the switch, the
speech-to-text-default operation and a refused projection. `PROVIDER_INTERNAL_DEFAULT_SET`
(`"provider_internal_default_set"`) MUST stay a member, though nothing emits it, so an audit row
written earlier keeps rendering.
`resource_created` / `resource_updated` / `resource_deleted` / `resource_renamed` are emitted
automatically by `ResourceService` with kind-redacted config; the provider kind declares no redactor,
because its config holds no secret.

#### Scenario: each provider operation records its own audit event
- **GIVEN** two connections and a registered Claude Code agent one of them reaches
- **WHEN** the user switches that agent onto the connection, marks one connection the speech-to-text default
- **THEN** the audit log holds a `provider_switched` and a `provider_transcribe_default_set` entry, each naming the connection it acted on
- **AND** the three emitted provider event values, `provider_projection_refused` included, and `provider_internal_default_set` are members of `AuditEventType`

### Requirement: Review what deleting a connection changes
Deleting a connection that agents run on MUST put each of those agents back on its built-in login first — the same de-projection "Revert an agent type to its built-in login" performs, audited the same way — and only then delete the connection, its owned secret and the speech-to-text model chosen for it; a de-projection refused because a file was edited on disk aborts the delete and keeps the connection. `GET /api/v1/providers/{uid}/delete-preview` MUST answer, per agent running on the connection, which of its files the delete would change and exactly the lines it would remove or the file it would remove, and write nothing; it is a 404 for a connection that does not exist. On the web, deleting a connection nothing uses asks once and returns to the list; deleting one in use is not blocked but opens a review — what will happen to each user of the connection (an agent goes back to its own login, speech to text turns off, the key is deleted) beside the daemon's own lines for each agent file — and **Delete** applies it. The lines shown are the daemon's dry run, never drawn by the page.

#### Scenario: deleting a provider an agent runs on is a review of its config diff, and Delete applies it
- **GIVEN** a connection a Codex agent runs on, with Coffer's model, provider table and catalogue pointer in its `config.toml`
- **WHEN** the user chooses Delete provider
- **THEN** a review lists what will happen and the lines the delete removes from `config.toml`, and nothing has been removed yet
- **AND** choosing Delete puts the agent back on its built-in login, removes the connection and its owned secret, and leaves the user's own lines in the file

#### Scenario: the delete preview writes nothing
- **GIVEN** a connection two agents run on
- **WHEN** a client reads `GET /api/v1/providers/{uid}/delete-preview`
- **THEN** it lists each agent with its files and the lines the delete would remove, and every file, record and the connection are unchanged afterwards

### Requirement: Keep ollama connections internal-only
The `ollama` protocol is internal-only: such a connection MUST reach no agent whatever its scope
says, MUST never be an agent's connection, and switching an agent onto it MUST write no native config: the switch is
refused with `409 PROVIDER_INTERNAL_ONLY` before anything is touched. It has no key to
write and is never written into an agent's config. The rule is enforced in
`application/provider/targets.py::scoped_targets`, which answers `[]` for `ollama` BEFORE the scope
is read — it is a rule about projection, not about the config's shape, and scope lives outside the
config.

#### Scenario: activating an ollama connection writes no native config
- **GIVEN** a registered Claude Code agent and an `ollama` connection whose scope names that agent
- **WHEN** the user switches the agent onto the connection
- **THEN** the switch is refused with `409 PROVIDER_INTERNAL_ONLY`, no native config file is written and the agent's `connection_uid` is unchanged
- **AND** the connection reports no reachable agent

### Requirement: Make the secret optional for ollama and local runtimes
`secret_ref` MUST be optional — required for `anthropic` / `openai` / `unknown` connections to a
remote endpoint, absent for `ollama`, and optional for a local runtime connection (see "Configure a
local model connection"), because LM Studio, vLLM and llama-server may be started with a key or
without one. On create, supplying neither `secret_value` nor `secret_ref` is valid for `ollama`
and for a local runtime, and an `ollama` connection MUST supply neither; elsewhere the exactly-one
rule (see "Store an inline secret under a minted opaque ref") stands.

#### Scenario: create an ollama connection without a secret
- **GIVEN** no connection named `local-llm` exists,
- **WHEN** the user creates one with `protocol="ollama"`, a `base_url`, and neither `secret_value` nor `secret_ref`,
- **THEN** it persists with `secret_ref` null, no vault entry is created, it reaches no agent, and `ProviderOut` shows `transcribe_default=false`.

### Requirement: Keep an independent speech-to-text default
At most one connection globally MUST carry the config field `transcribe_default`, and
`set_transcribe_default` MUST clear it everywhere else before
setting the target, emit `provider_transcribe_default_set`, and notify the engine settings so they can apply their
own drop rule ([internal-engine](../internal-engine/spec.md) "Drop the speech-to-text model when its connection moves"); what the flagged connection is used for is
[internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model". It is a connection of its own because a gateway serving chat
completions commonly serves no `/audio/transcriptions` at all, so no chat connection is borrowed for speech.
`POST /api/v1/providers/{uid}/transcribe-default`, which Settings › General calls, MUST be the
surface, returning the updated `ProviderOut`. Which connection carries the flag, or that none does,
is read from `GET /api/v1/providers`, and no operation clears the flag without moving it.

The flag is declared in the kind's exclusive flags, so the
vault's validation refuses any document that flags a second connection, and a generic resource
write (`PATCH /api/v1/resources/{uid}`, `POST /api/v1/resources`) that would
set it while another connection holds it MUST be refused before anything is written with 409
`PROVIDER_TRANSCRIBE_DEFAULT_TAKEN`, naming the holder.

#### Scenario: a second speech-to-text default outside the dedicated route is refused
- **GIVEN** connection A is the speech-to-text default
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `transcribe_default` true
- **THEN** the answer is 409 `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN` naming A, and A keeps the flag while B stays unflagged

#### Scenario: marking a speech-to-text default moves only its own flag
- **GIVEN** connection A is the speech-to-text default, and connection B carries no flag
- **WHEN** the user marks B as the speech-to-text default
- **THEN** B's `transcribe_default` becomes true and A's becomes false, and a `provider_transcribe_default_set` entry is audited
- **AND** no other connection carries the flag

#### Scenario: the speech-to-text connection is named over REST
- **GIVEN** the daemon is running with connection A flagged as the speech-to-text default, and connection B carrying no flag,
- **WHEN** a client calls `POST /api/v1/providers/{B uid}/transcribe-default`, then `GET /api/v1/providers`,
- **THEN** B carries `transcribe_default`, the list shows B as the only one flagged, and a `provider_transcribe_default_set` entry names B,
- **AND** A no longer carries the flag.

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
  endpoint and protocol (Custom reveals a manual protocol selector), in two steps, Endpoint and then Models. A local runtime (Ollama, LM Studio) asks for no key and,
  until a runtime is chosen or an address is filled in, does not let the user go on to Models; the connection's Name
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

### Requirement: Set the internal-engine default
**Reason**: Coffer runs no pass over a model of its own, so no connection is the internal engine's default.
**Migration**: None. A stored `internal_default` key is ignored and dropped, see "Ignore a stored internal-default flag".

### Requirement: Keep at most one internal default connection
**Reason**: The flag no longer exists, so there is no invariant over it and a vault holding it on several connections is accepted.
**Migration**: None. The speech-to-text default keeps its own at-most-one rule, "Keep an independent speech-to-text default".
