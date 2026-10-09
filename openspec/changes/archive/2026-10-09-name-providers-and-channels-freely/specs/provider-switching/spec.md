## MODIFIED Requirements

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
naming both names. A name another connection already holds, in any casing, MUST be refused with
`RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent connection MUST be a 404;
renaming to the current name MUST be a no-op and MUST record nothing. A connection's name is free text
([resource-framework](../resource-framework/spec.md) "Name a provider or a channel with free text"), so a rename
that only changes the case of its own name is allowed, and the connection's file, `resources/provider/<uid>.json`,
stays where it is. A connection carries no separate title. On the web, the edit dialog's
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
#### Scenario: rename a connection to free text
- **GIVEN** a connection `acme`
- **WHEN** a client patches its `name` to "Acme (EU) 生产", and then to "acme (eu) 生产"
- **THEN** both are accepted, the connection keeps its `uid`, its `secret_ref` and its file `resources/provider/<uid>.json`, and each rename records a `resource_renamed` entry naming both names
- **AND** a name with a line break, a name over 80 characters and a name starting with `-` are each refused as a validation error

#### Scenario: rename a connection over REST
- **GIVEN** the daemon is running with a connection `acme`,
- **WHEN** a client patches the connection's `name` to `acme-eu` through `PATCH /api/v1/resources/<uid>`, and then patches it to `taken` while another connection is named `taken`,
- **THEN** the first answers under the label `acme-eu` at the same `uid` and records a `resource_renamed` entry naming both names,
- **AND** the second is refused with 409 `RESOURCE_ALREADY_EXISTS`, and the connection is still `acme-eu`.

### Requirement: Converge connections across machines
The `provider` kind MUST be registered into the composition root's kind table like every kind, so each
connection is one vault file, `resources/provider/<uid>.json`, that a sync round merges and checks out
like every resource file ([vault-sync](../vault-sync/spec.md) "Converge resources as their own files"). A connection's reach
(`enabled` / `scope`) MUST NOT travel: it is this machine's reach record, one decision the user makes
per machine, so a connection that already exists keeps the reach it has, and one that has just arrived
takes the kind's own default. Secrets travel as Fernet ciphertext at `secret/<ref>.enc`, only when the
remote is configured to carry them; the master key never enters the repository, and no raw key MUST
appear in the vault's plaintext.

Agents are filed machine-locally, so which connection an agent runs on is this machine's choice and a
switch made on another machine does not travel. Projection is a machine-local side effect too, so
after a round that applied changes, the reconcile pass it runs with the import's warrant
([vault-sync](../vault-sync/spec.md) "Run the reconciler once after a round that applied changes")
MUST re-project every agent that runs on a connection from the connection as it now is — edited
values that arrived reach the agent's file, and keys gone missing are written back — and remove the
keys Coffer left in the file of an agent that runs on none.

#### Scenario: a provider profile round-trips through sync export and import
- **GIVEN** a connection with a secret ref exists on one machine,
- **WHEN** a second machine joins a remote that carries secrets, and the first machine later edits the connection and both run a round,
- **THEN** the connection's file arrives on the second machine byte for byte, the secret ciphertext is present at `secret/<ref>.enc`, and no secret appears in the file's plaintext; the edit arrives the same way, so the second machine ends up with the edited config.

#### Scenario: an import re-projects an edited connection into the agent that runs on it
- **GIVEN** an agent on a connection, and a sync round that brings an edited `base_url` for that connection
- **WHEN** the round's reconcile pass runs with the import's warrant
- **THEN** the agent's file carries the edited projection, and an agent that runs on no connection is left as it was

### Requirement: Offer every connection operation over REST and in the web UI
Create, switch, revert-to-built-in, rename, edit and delete MUST be
available via (a) the REST API and (b) the web surfaces — the Model providers library for create and
delete, the Agent detail page for the switch and the revert, the connection's own page for the
rename and the edit (see "Rename a connection without moving anything else"). A connection has no
scope and no off switch: the agents it serves follow from its addresses. The `coffer provider` and `coffer model` commands call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). The list carries no Active column, and a
connection's lifecycle verbs are the ones every kind's page offers. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `anthropic_base_url` (`""`
clears it), `protocol`, `models`, `secret_value`, `description`) and from its detail page, including
correcting the wire. Creating one (`POST /api/v1/providers` with a name, a protocol, a base URL, an
optional Anthropic address and an inline secret, a secret ref or the `local_runtime` detection) takes no model; a local runtime connection is created
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
  endpoint and description, and the list is sorted by name, with no order heading and no drag handle on a row. It has no per-row switch, because activation is per agent, and no
  per-row delete: it is on the open connection's header. A row MUST say what Coffer
  ITSELF uses the connection for: the `transcribe_default` connection carries a "Coffer · speech to
  text" badge with a hint naming Settings › General as where it is changed, and the connection's Used by repeats
  it. The label leads with Coffer because a bare "Speech to text" reads as a capability of the
  provider rather than a job Coffer gives it; an agent's mark on a row is a different fact — that
  agent is switched to the connection. The vendor mark is derived from `base_url` by matching the
  preset list (an unmatched endpoint gets Coffer's neutral provider glyph); the name is the user's
  own, and the row links to the detail page by `uid`.
- The add-connection dialog asks for the vendor from a grid of equal buttons (see "Offer the
  mainstream vendors as presets"), which fill in the vendor's addresses, in two steps, Endpoint and then
  Models. It asks for addresses, not a protocol (see "Ask for addresses, not a protocol"). A local runtime (Ollama, LM Studio) asks for no key, offers only the wires the detected runtime serves to agents (Anthropic, OpenAI) and,
  until a runtime is detected, does not let the user go on to Models; the connection's Name
  appears once a runtime is chosen. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) is one column opened beside the list — Used by, Endpoint, Models — and has no tabs. Its header carries a health pill (Reachable, Key rejected or Unreachable, read from a probe that runs when it opens), the agents its addresses serve ("For Claude Code, Codex", or that none can use it), the host and, when the endpoint answered, how long it took, with Test, Edit and a menu holding Delete provider ("Review what deleting a connection changes"). **Used by** is read-only: each agent whose `connection_uid` names the connection (and that the connection still serves),
  with the model it runs, as a link reading "<Agent> › Change model" that opens that agent's page with its Change model dialog already open (`/agents/<type>?change-model=1`); and Speech to text
  when the connection is flagged for it, reading "Settings › General" and opening it. Used by carries no
  switch, activate or revert control, and no row repeats a fault: a connection's fault shows in its header pill and in the section it belongs to (Endpoint for Unreachable or Key rejected, Models for a failed listing).
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model** and **Route** and carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that serve that agent: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model** and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). It carries no
  other model setting — no output-limit, subagent, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. Picking things in the form is a DRAFT: it writes nothing, and **Review changes** is enabled only once the draft differs from what is applied, names a model and has passed its connection test ("Review a model change before writing it"). On the built-in login Model is the agent's own model and optional, and no test runs. The agent's Overview reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection.

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
- **GIVEN** the connections page is rendered with two mock connections that serve different agents,
- **WHEN** the page renders,
- **THEN** it lists both connections, marks the one an agent runs on with that agent's mark, and shows the open connection's address and, in its header, the agents it serves, with NO per-row "Switch" action, because activation is per agent in its Change model dialog (TypeScript acceptance test).

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
