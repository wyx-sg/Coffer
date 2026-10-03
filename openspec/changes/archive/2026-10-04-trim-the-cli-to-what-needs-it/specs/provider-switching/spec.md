## MODIFIED Requirements

### Requirement: Switch one agent at a time
`POST /api/v1/providers/{uid}/activate` with body `{agent_type}` (the agent's Change model dialog calls it) MUST switch THAT agent onto the
connection. The operation:

1. requires the connection to exist, else 404, and the agent of that type to be registered, else 404;
2. refuses with 409 `PROVIDER_DOES_NOT_REACH_AGENT` when the connection or the agent is switched off or
   the connection's scope does not name the agent, and with 409 `PROVIDER_INTERNAL_ONLY` for an
   `ollama` connection;
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
every agent including one registered later, and nothing (`scope = []`) for `ollama`. Re-targeting is a scope edit (`PUT /api/v1/resources/{uid}/scope`, which the
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
login, `POST /api/v1/providers/use-builtin/{agent_type}`). A keyless (`ollama`) connection covers no agent whatever its
scope says (see "Keep ollama connections internal-only").
Moving the wire of a connection an agent runs on would leave the native config Coffer
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

### Requirement: Offer every connection operation on REST, CLI and web
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
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model**, **Effort** and **Route** and, with the `models` feature on, carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that reach that agent and narrowed by `enabled`: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model**, **Effort** — offering the chosen model's own levels and hidden when it has none — and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). A local model whose runtime reports no context window adds a **Context window** field. It carries no
  other model setting — no output-limit, subagent, fallback, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. Picking things in the form is a DRAFT: it writes nothing, and **Review changes** is enabled only once the draft differs from what is applied and names a model. The built-in login needs no model. The agent's Overview reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `secret_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the command line covers create, list, switch and revert
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

#### Scenario: the Change model dialog shows only provider, model, effort, tiers and a context window
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection whose chosen model has no effort levels
- **WHEN** each agent's Change model dialog renders
- **THEN** Claude Code's shows Provider, Model, Effort and Model per tier, and Codex's shows Provider and Model with no Effort
- **AND** neither shows an output-limit, subagent, fallback, thinking or fast-mode control

### Requirement: Set the internal-engine default
`POST /api/v1/providers/{uid}/internal-default` (which Settings › General calls)
MUST set the named connection as the internal-engine default (applying "Keep at most one
internal-engine default"), emit a `provider_internal_default_set` audit event, and return the
updated `ProviderOut`. Which connection carries the flag, or that none does, is read from
`GET /api/v1/providers`. No operation clears the flag without moving it: it moves by naming another
connection.
Setting the internal default MUST notify the engine so it can apply its own drop rule
([internal-engine](../internal-engine/spec.md) "Drop the engine model when its connection moves"); the notification is a port, not an import, so this operation never
reads or writes the engine's own settings row, which lives under `/api/v1/internal-engine-config`. A
connection may be both an agent's connection (projected into that agent) and the internal default — one
key, two uses; an `ollama` connection is only ever the second. The engine picks the model it runs on
the flagged connection from a setting of its own ([internal-engine](../internal-engine/spec.md) "Resolve the engine's connection and model together").

#### Scenario: set a connection as the internal engine default
- **GIVEN** two connections exist and none is the internal default,
- **WHEN** the user sets the second as the internal default,
- **THEN** its `internal_default` becomes true, the other stays false, and a `provider_internal_default_set` audit entry is recorded.

#### Scenario: the command line names the internal engine's connection
- **GIVEN** the daemon is running with two connections, `alpha` flagged as the internal default and `beta` unflagged,
- **WHEN** a client calls `POST /api/v1/providers/{beta uid}/internal-default`, then `GET /api/v1/providers`,
- **THEN** `beta` carries the flag, `alpha` no longer does, and a `provider_internal_default_set` entry names `beta`,
- **AND** the list shows `beta` as the only connection flagged.

### Requirement: Rename a connection without moving anything else
A connection MUST be renamable through the framework's own kind-agnostic route — the `name` field on
`PATCH /api/v1/resources/{uid}` — and from the connection's edit dialog, which calls that
route; this kind MUST NOT serve a rename route of its own. The
operation MUST change the label and NOTHING else: the resource keeps its `uid`, its `secret_ref`
MUST be left where it is (the ref is an opaque address, never derived from the name), the
`audit_log` rows MUST NOT be repointed — they follow the resource by uid and go on spelling the name
each event carried when it happened — and a connection an agent runs on MUST NOT be re-projected, because the
projected `apiKeyHelper` cites the agent's uid. Codex's provider label (`Coffer (<name>)`) is cosmetic and
goes stale until the next projection rewrites it. It MUST record a `resource_renamed` audit event
naming both names. A name another connection already holds MUST be refused with
`RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent connection MUST be a 404;
renaming to the current name MUST be a no-op and MUST record nothing. The optional display title
every resource carries ([resource-framework](../resource-framework/spec.md), set
through the same `PATCH /api/v1/resources/{uid}`) is not a rename and leaves the name alone. On the web, the edit dialog's
Name field submits this rename ahead of the patch, and the page stays where it is, because its route
is the uid.

#### Scenario: rename a connection and keep its secret, audit trail and projection
- **GIVEN** a connection `acme` with an inline secret, which a registered Claude Code agent runs on,
- **WHEN** `PATCH /api/v1/resources/<uid> {"name": "acme-eu"}` is called,
- **THEN** the connection keeps the same `uid` and answers there under the label `acme-eu`, its `secret_ref` is unchanged with the secret still readable at it, the agent's projected `apiKeyHelper` is byte-for-byte what it was (it names the uid), and the whole history — including the rows recorded before the rename, which still spell the old name — comes back when querying the audit log by uid.
#### Scenario: reject a rename onto a name another connection already uses
- **GIVEN** two connections `acme` and `taken`,
- **WHEN** `acme` is renamed to `taken`,
- **THEN** the response is 409 `RESOURCE_ALREADY_EXISTS` and both connections still carry their original labels, each still reachable at its own uid with its secret intact.
#### Scenario: rename a connection from the command line
- **GIVEN** the daemon is running with a connection `acme`,
- **WHEN** a client patches the connection's `name` to `acme-eu` through `PATCH /api/v1/resources/<uid>`, and then patches it to `taken` while another connection is named `taken`,
- **THEN** the first answers under the label `acme-eu` at the same `uid` and records a `resource_renamed` entry naming both names,
- **AND** the second is refused with 409 `RESOURCE_ALREADY_EXISTS`, and the connection is still `acme-eu`.

### Requirement: Keep an independent speech-to-text default
`transcribe_default` MUST be a config field of the same shape as `internal_default`: at most one
connection globally carries it, and `set_transcribe_default` MUST clear it everywhere else before
setting the target, emit `provider_transcribe_default_set`, and notify the engine so it can apply its
own drop rule ([internal-engine](../internal-engine/spec.md) "Drop the speech-to-text model when its connection moves"); what the flagged connection is used for is
[internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model". The two flags MUST move independently — setting one MUST NOT read, write
or clear the other, and neither MUST fall back to the other at resolution time — and one connection
MAY carry both. It is a second flag because the two name different models: a gateway serving chat
completions commonly serves no `/audio/transcriptions` at all, so borrowing the engine's connection
aimed every voice message at a 404. `POST /api/v1/providers/{uid}/transcribe-default`, which Settings › General calls, MUST be the
surface, returning the updated `ProviderOut`. Which connection carries the flag, or that none does,
is read from `GET /api/v1/providers`, and no operation clears the flag without moving it, as for the
internal-engine default (see "Set the internal-engine default").

Like the internal-engine default, the flag is declared in the kind's exclusive flags, so the
vault's validation refuses any document that flags a second connection, and a generic resource
write (`PATCH /api/v1/resources/{uid}`, `POST /api/v1/resources`) that would
set it while another connection holds it MUST be refused before anything is written with 409
`PROVIDER_TRANSCRIBE_DEFAULT_TAKEN`, naming the holder.

#### Scenario: a second speech-to-text default outside the dedicated route is refused
- **GIVEN** connection A is the speech-to-text default
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `transcribe_default` true
- **THEN** the answer is 409 `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN` naming A, and A keeps the flag while B stays unflagged

#### Scenario: marking a speech-to-text default moves only its own flag
- **GIVEN** connection A is both the internal-engine default and the speech-to-text default, and connection B carries neither flag
- **WHEN** the user marks B as the speech-to-text default
- **THEN** B's `transcribe_default` becomes true and A's becomes false, and a `provider_transcribe_default_set` entry is audited
- **AND** A is still the internal-engine default and B still is not

#### Scenario: the command line names the speech-to-text connection
- **GIVEN** the daemon is running with connection A flagged as both the internal-engine and the speech-to-text default, and connection B carrying neither,
- **WHEN** a client calls `POST /api/v1/providers/{B uid}/transcribe-default`, then `GET /api/v1/providers`,
- **THEN** B carries `transcribe_default`, the list shows B as the only one flagged, and a `provider_transcribe_default_set` entry names B,
- **AND** A is still the internal-engine default.

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` MUST
remove every key Coffer wrote from the enabled agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model` and `effortLevel`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys and Coffer's `env.NO_PROXY` pair; for Codex the provider table, `model_provider`, `model`,
`model_reasoning_effort`, and the catalogue pointer and file — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` or effort the
user has since changed through `/model` or `/effort` no longer equals the agent's binding, is theirs
and is kept. Only values Coffer wrote are removed: the `env` keys carry no mark of their own, so they
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
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, `effortLevel`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue and an effort
- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer or `model_reasoning_effort` Coffer wrote, and the catalogue file is gone

#### Scenario: switching back leaves the user's own gateway settings alone
- **GIVEN** a Claude Code `settings.json` with the user's own `env.ANTHROPIC_BASE_URL`, a tier pin and `theme`, and no Coffer `apiKeyHelper`
- **WHEN** the user switches Claude Code back to built-in, or a reconcile pass with a warrant runs
- **THEN** the file is byte-identical afterwards and attention reports no `projection_unclaimed` drift for it

### Requirement: Authenticate each agent to the proxy with its own local token
Each managed agent MUST have its own random 256-bit local proxy token, minted by Coffer on first
use, kept as ciphertext in the secret store under a machine-local ref vault sync never
carries, and printed by `coffer proxy token --agent-uid <uid>` (`GET /api/v1/proxy/tokens/{agent_uid}`)
— the command both agents' projected config runs. The proxy MUST accept a model request only with
one of those tokens, as `Authorization: Bearer` or `x-api-key`, compared in constant time, and MUST
refuse anything else — no token, a claude.ai OAuth token (`sk-ant-oat…`), a provider key — with 401
in the wire's own error shape, forwarding nothing. The token names the agent, which is how usage is
attributed. `POST /api/v1/proxy/tokens/{agent_uid}/rotate` (the agent page's Rotate proxy token) replaces
it; the old token is refused from the moment the rotation answers. For an agent this machine does
not have, the token route answers 404 and the command exits 4 with nothing on stdout, so a stale
helper fails closed. The token keeps browsers and other users' processes off the proxy; it is not a
boundary against a process of the same user. Removing an agent deletes its token. Reading an
existing token pushes nothing to the proxy; only minting or rotating one does.

#### Scenario: a request without a Coffer token is refused
- **GIVEN** the proxy serving an agent's route
- **WHEN** a request arrives with no token, or with an OAuth-shaped `sk-ant-oat` bearer
- **THEN** it is refused with 401 and nothing is forwarded upstream

#### Scenario: a rotated token replaces the old one
- **GIVEN** an agent whose token the proxy accepts
- **WHEN** the token is rotated
- **THEN** the old token is refused with 401 and the new one is accepted

#### Scenario: removing an agent deletes its proxy token
- **GIVEN** a registered agent whose proxy token has been minted
- **WHEN** the agent is removed
- **THEN** the token is gone from the secret store

#### Scenario: the token command prints a local token, never a provider key
- **GIVEN** a registered agent that runs on an API-key connection
- **WHEN** the user runs `coffer proxy token --agent-uid <uid>`
- **THEN** it prints the agent's local token, which is not the connection's key
- **AND** for a uid no agent has it exits 4 with nothing on stdout

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
projection leaves the window out rather than guessing one (see "Record a context window and effort
levels with each curated model"). Neither compatibility key is a field the user sets.

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

### Requirement: Detect a local model runtime without changing it
`POST /api/v1/providers/detect-local` (the Add provider dialog's Detect, with an optional base URL) MUST
report which runtime answers at a loopback URL — or, with none given, at each runtime's default port
(Ollama 11434, LM Studio 1234, llama-server 8080; vLLM's default 8000 is the daemon's own port, so
vLLM is found only on a URL the user gives) — by fingerprint rather than port, with its version, the
wires it serves at that version and, per model, the context window it serves and whether it can
call tools, where the runtime says. Detection MUST be read-only — nothing is pulled, loaded or
downloaded — and MUST refuse a non-loopback URL as 422. A runtime below the minimum version for a
wire (Ollama 0.14.0 for Messages and 0.13.4 for Responses, LM Studio 0.4.1 and 0.3.29, vLLM 0.11.1
and 0.10.0) is not reported as serving it. When nothing answers, the response MUST carry
`handoff`, a prompt the daemon writes (see [skill-manager](../skill-manager/spec.md) "Hand a
required command to an agent with a prompt" for the shape every hand-off takes) asking the
person's agent to set a runtime up on this machine — naming the machine's OS, architecture and,
where it is known, its memory; the runtimes detection probes with their default ports; the
versions from which Ollama and LM Studio serve both wires; that an agent needs a tool-calling
model with a window of at least 64k tokens — preferring Ollama or LM Studio, pulling one
tool-calling chat model that fits, confirming it answers on its default port, and then telling
the person to press Detect; it MUST name no installer or command, and it MUST be `null` once a
runtime answers.
The Add provider dialog's local path MUST offer that prompt beside its note that nothing
answered, and keep typing the address of a runtime that is already running.

#### Scenario: detection reads the runtime, version and served windows
- **GIVEN** an Ollama runtime 0.14.2 on a loopback port serving `qwen3-coder` with a 65536-token window and tool support
- **WHEN** the user runs detection against that URL
- **THEN** it reports `ollama` 0.14.2 serving both wires, and `qwen3-coder` with a 65536-token window and tools

#### Scenario: a runtime below the minimum version serves no wire it lacks
- **GIVEN** an Ollama runtime 0.13.5 on a loopback port
- **WHEN** detection runs
- **THEN** it reports Responses and not Messages

#### Scenario: detection refuses a non-loopback address
- **GIVEN** the daemon is running
- **WHEN** detection is asked to probe `http://example.com:11434`
- **THEN** it is refused as 422 and no request leaves the machine

#### Scenario: nothing found hands setting up a runtime to an agent
- **GIVEN** a loopback port nothing answers on
- **WHEN** detection probes it, and the Add provider dialog shows the result
- **THEN** the response finds nothing and carries a prompt naming this machine, Ollama on 11434, LM Studio on 1234 and llama-server on 8080, preferring Ollama or LM Studio, ending with pressing Detect and the standing rules every hand-off ends with, and naming no install command
- **AND** the dialog says nothing answered, keeps typing a running runtime's address as the other way, and offers Copy prompt with that prompt

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
resolves the same prices for the Models section, each with its source, and the section's **Set
price…** sets or resets the price the user records. Every surface labels cost as estimated. Where
nothing in a cost is priced, the web UI MUST show `—` in its place, never `$0.00`, and MUST say why
and where a price is set in the dash's tooltip and accessible name. Subscription logins do not pass through
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
- **THEN** the section says once where its prices come from — bundled with Coffer, updated <the date of the list in use>, or from the provider — and each priced model shows its input and output price per 1M tokens, marked only when it is the exception: You set
- **AND** the model nothing prices shows `—` with Set price…, and a local runtime's model reads Local · no cost

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model through a connection that records no price for it, whose API reported none, and that the bundled list does not know
- **WHEN** the Usage tab shows that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage tab the dash's tooltip says no price is known for it and that a price is set on its provider, and the Cost tile says "1 model unpriced" once, as a link to that provider's Models section; no other place repeats the count

### Requirement: Report usage by model, agent or day over a range
`GET /api/v1/usage/summary`, taking the range (`today`, `24h`, `7d`, `30d`, `month` or `custom` with a first and last day), the grouping (`model`, `agent` or `day`) and the filters as query parameters,
MUST report, for the range in the machine's local days (today; the last 24 hours up to now, summed from the per-request rows because the window cuts through a local day; the last 7 or 30 days including today;
this calendar month; or an inclusive custom range), one row per model (with the connection that
served it, by uid and name), per agent or per day: requests, the token totals per category, the
estimated cost, how many requests were unpriced or had unknown usage, and the agent types that sent
the row's requests, most requests first. The summary MUST be narrowable to one agent type
(`agent_type`) and to one connection (`connection_uid`); a filtered summary's rows and totals count
only the requests that match every filter. `GET /api/v1/usage/requests`
pages through the per-request detail, newest first. `GET /api/v1/usage/export.csv`
returns the same summary, with the same filters, as CSV, and the Usage tab exports it. The web UI shows the summary as the Usage tab of Model providers ("Show metered usage on a Usage tab of Model providers").

#### Scenario: usage by model names the connection
- **GIVEN** usage of two models over two connections
- **WHEN** the summary is grouped by model
- **THEN** each row names its model and the connection's uid and name, with its requests, tokens and estimated cost

#### Scenario: usage by agent and by day
- **GIVEN** usage by two agents on two days
- **WHEN** the summary is grouped by agent, and then by day
- **THEN** it returns one row per agent, and then one row per day

#### Scenario: usage narrowed to one agent and one provider
- **GIVEN** usage by Claude Code over one connection and by Codex over another
- **WHEN** the summary is narrowed to Codex, then to the first connection, then to both at once
- **THEN** it counts only Codex's requests, then only the first connection's, then nothing
- **AND** each unfiltered row names the agent types that sent its requests, most requests first, and the CSV honours the same filters

#### Scenario: a range resolves in local days
- **GIVEN** a clock on a known local day
- **WHEN** the ranges today, 7d, 30d and this month are resolved
- **THEN** each spans the local days it names, today included

#### Scenario: the last 24 hours is a rolling window
- **GIVEN** requests 2 hours ago, 23 hours ago and 25 hours ago
- **WHEN** the summary is read for the range `24h`
- **THEN** it counts the first two requests and not the third

#### Scenario: export usage as CSV
- **GIVEN** usage in the range
- **WHEN** the user exports it
- **THEN** the CSV has a header row and one line per group with the same totals the summary reports

### Requirement: Order providers, and fail over in that order
The Model providers list MUST have an order the user sets, and that order MUST be the order the
proxy tries fallbacks in: the agent's own connection first, then the other eligible connections in
list order. The order is saved as each connection's position (`PUT /api/v1/providers/order` with
every connection's uid exactly once, else 422); a connection never placed sorts after the placed ones, by name. The list offers a drag
handle on each row, moves with the keyboard, and explains in its help that order is fallback
priority. Each connection MUST carry **Use as fallback for other providers** (`fallback`, on by
default; `PATCH /api/v1/providers/{uid}`): switched
off, it is never tried for another connection's request, though its own agents still fail over from
it. A local runtime is never a fallback and its detail says so. Where an agent's requests go is read from
`GET /api/v1/proxy/routes/{agent_uid}?model=<model>`, and the agent's Overview › Model shows only that its route is through Coffer's proxy, with **Test**; the agent's own proxy token is replaced
from **Rotate proxy token** in the agent page's ⋯ menu, offered only while the agent routes through the proxy. Usage is metered on the
connection that actually answered.

#### Scenario: fallbacks are tried in the Model providers list order
- **GIVEN** an agent on connection A and connections B and C that also offer its model, listed C, A, B
- **WHEN** the proxy's route for the agent is built
- **THEN** it tries A, then C, then B

#### Scenario: a provider switched off as a fallback is never failed over to
- **GIVEN** an agent on connection A and connection B offering the same model with Use as fallback for other providers switched off
- **WHEN** the proxy's route for the agent is built
- **THEN** it holds A only

#### Scenario: Rotate proxy token is offered only while the agent routes through the proxy
- **GIVEN** an agent on a connection and an agent on its built-in login
- **WHEN** each agent's page menu is opened
- **THEN** the first offers Rotate proxy token and the second does not, and choosing it replaces the first agent's token

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
**Refresh model prices** in Settings › General under Coffer's model, `PUT /api/v1/providers/price-list` — and `COFFER_PRICE_REFRESH=off` pins it
off. `GET /api/v1/providers/price-list` says which list is in use, the day its data is from, and
the refresh's state; the Models section's price-source line reads "bundled with Coffer, updated <that day>" for a bundled price.

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
