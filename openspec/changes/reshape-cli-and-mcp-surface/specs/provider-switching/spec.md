## MODIFIED Requirements

### Requirement: Activate a connection into the agents its scope reaches
`POST /api/v1/providers/{uid}/activate` (and `coffer provider switch <name>`) MUST apply the
single-active rule (see "Keep at most one active connection per agent type"), then project into
every ENABLED registered agent the connection's scope reaches. The operation:

1. requires the connection to exist, else 404;
2. projects into each agent its scope reaches, and de-projects the agents the previous connection held
   and this one does not;
3. clears `is_active` on the connections that held those agents, then sets it on the target;
4. emits `provider_switched`;
5. returns `{activated, protocol, projected, skipped}`.

Projection MUST run BEFORE the activation flip, so a failed native-config write aborts the switch
with the registry unchanged. If no agent the connection reaches is registered, it MUST record the
connection active and return a non-empty `skipped` list — NOT an error.

Reach is the framework's per-agent `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)); there is no
`compatible_agents` field in the config, in `ProviderCreate` or in `ProviderPatch`. A new connection
is pre-filled from its wire through the kind's `default_scope` hook — unscoped for a credentialed
wire (including `unknown`, so an inconclusive probe hides nothing and the user decides), which reaches
every agent including one registered later, and nothing (`scope = []`) for `ollama`. Re-targeting is a scope edit (`PUT /api/v1/resources/{uid}/scope`,
`coffer provider scope <name> --agents …`). `scope = []` is dormant: the connection reaches no
agent, so no agent resolves its key. The projection writer MUST be chosen by AGENT type, not by
protocol: a connection reaching `claude_code` writes Claude's `settings.json` in the anthropic shape
and one reaching `codex` writes Codex's `config.toml`, which is how an OpenAI-compatible gateway is
routed to Claude Code. Coffer translates nothing between protocols.

#### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing
- **GIVEN** no Codex agent is registered and a connection reaching only Codex exists,
- **WHEN** the user activates it,
- **THEN** its `is_active` becomes `true`, no config file is written, and the response carries `skipped: ["codex"]` (or empty `projected`).
#### Scenario: route an openai-compatible connection to Claude Code with its scope
- **GIVEN** a Claude Code agent is registered and an `openai`-wire connection is created and then scoped to `["claude_code"]`,
- **WHEN** the user activates that connection,
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "<absolute path to the coffer CLI> provider key --connection-uid <uid>"`, `GET /providers/{uid}/key` returns exactly that connection's key, and the reported agent set follows the scope.

### Requirement: Revert an agent to its built-in login
`POST /api/v1/providers/use-builtin/{wire}` (and `coffer provider builtin <wire>`) MUST remove
Coffer's managed keys from the agent behind that wire and clear the active connection's flag,
idempotently — succeeding when nothing was active — and MUST revert a connection that reaches
several agents as a unit, because the single `is_active` flag is all-or-nothing.

#### Scenario: switch a wire back to the agent built-in login
- **GIVEN** a connection is active and projected into Claude Code,
- **WHEN** the user switches that wire back to built-in (`POST /providers/use-builtin/{wire}`, or `coffer provider builtin <wire>`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the connection is no longer active; the operation is idempotent (a no-op when nothing is active). A connection is an optional override.

### Requirement: Refuse to move the wire of a live connection
A connection's `protocol` MUST be correctable — the probe that guessed the wire can be wrong, and
re-entering the key to fix it is a worse answer than editing it. But the wire is not inert, so
changing it MUST be refused with 409 `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while the connection is
active, with a message that names the way out (`coffer provider builtin <wire>`). Two things key
off it: a keyless (`ollama`) connection covers no agent whatever its scope says (see "Keep ollama
connections internal-only"), and reverting to the built-in login finds the agent to revert through
the wire.
Moving the wire of a connection that is currently projected would leave the native config Coffer
already wrote standing, with nothing left that would ever take it off. Silently de-projecting instead
MUST NOT be the answer: the developer asked to change a field, not to take their agents off a
gateway. Re-sending the wire the connection already has is not a change, so a client that submits a
whole form is never told its unchanged dropdown is a conflict. The refusal MUST be reachable on every
surface that offers the edit — REST, `coffer provider edit`, and the connection's form.

#### Scenario: correcting a mis-probed wire is refused while the connection is live
- **GIVEN** a connection that is switched on and projected into an agent,
- **WHEN** the user patches its `protocol` to a different wire,
- **THEN** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names `coffer provider builtin <wire>` as the way out
- **AND** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (see "Refuse to move the wire of a live connection")

### Requirement: Offer every connection operation on REST, CLI and web
Create, switch, revert-to-built-in, rename and delete MUST be available via (a) the REST API, (b)
`coffer provider list|show|add|edit|rm|enable|disable|scope|switch|builtin|key` with `--json` on
`list` and `show` — the lifecycle verbs being the ones every kind's group offers, and rename being
`coffer provider edit <name> --name <new>` (see "Rename a connection without moving anything
else") — and (c) the web surfaces — the Model providers library for create and delete, the Agent
detail page for the switch, the connection's own page for the rename. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`), over the CLI
(`coffer provider edit <name> [--name <new>] [--title <text>] [--description <text>] [--protocol <wire>] [--base-url <url>] [--secret <value>]`)
and from its detail page, including correcting the wire. `coffer provider add <name> --protocol <p>
--base-url <url> [--secret <value> | --credential-ref <ref>]` takes no model. Reverting is
`coffer provider builtin <wire>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation. Which connection the internal engine and speech-to-text
run on is set through `coffer config` (see "Set the internal-engine default" and "Keep an
independent speech-to-text default"), not through a `provider` subcommand.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES group; the old
  `/settings/models`, `/settings/providers` and `/settings/llm-connections` routes redirect there) is
  the connection library: a table of name / vendor / base URL / reach, an Add action and Delete per
  row. It has no per-row switch, because activation is per agent, and no internal-engine badge. The
  vendor column and its filter are derived from `base_url` by matching the preset list (an unmatched
  endpoint reads as Custom); the name column keeps the user's own name, and the row links to the
  detail page by `uid`.
- The add-connection dialog asks for the protocol rather than detecting it: it offers provider
  presets (OpenAI / Anthropic / Google Gemini / DeepSeek / OpenRouter / Ollama) that fill in the
  endpoint and protocol, plus Custom, which reveals a manual protocol selector; the CLI takes
  `--protocol`. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail page splits into Overview and Models tabs. Its header carries the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed.
- Per-agent connection and model selection lives on the agent detail page's Overview tab, filtered to
  the connections that reach that agent and narrowed by `enabled`. Picking a connection or a model
  there is a DRAFT: it activates nothing and PATCHes nothing. Picking a non-built-in connection
  introspects its endpoint and stages a default model — Claude Code's primary and fast slots and
  Codex's single slot all default to the first model returned. A custom connection MUST pass
  `POST /api/v1/models/test-connection` with the staged model before it can be confirmed; confirm
  stays disabled until the test for the CURRENT draft passes, and changing the connection or the
  model resets the result. Confirming PATCHes the per-agent binding and then activates the
  connection — the only step that writes native config. Switching back to the built-in login needs
  no test.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `credential_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the command line covers create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider builtin <wire>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for its wire, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

### Requirement: Set the internal-engine default
`POST /api/v1/providers/{uid}/internal-default` (and `coffer config set engine.provider <name>`)
MUST set the named connection as the internal-engine default (applying "Keep at most one
internal-engine default"), emit a `provider_internal_default_set` audit event, and return the
updated `ProviderOut`. `coffer config get engine.provider` MUST print the name of the connection
that carries the flag, or that none does. No operation clears the flag without moving it, so
`coffer config unset engine.provider` MUST be refused with a message saying the flag moves by
naming another connection, and nothing is written.
Setting the internal default MUST notify the engine so it can apply its own drop rule
([internal-engine](../internal-engine/spec.md) "Drop the engine model when its connection moves"); the notification is a port, not an import, so this operation never
reads or writes the engine's own settings row, which lives under `/api/v1/internal-engine-config`. A
connection may be both active (projected into the agents it reaches) and the internal default — one
key, two uses; an `ollama` connection is only ever the second. The engine picks the model it runs on
the flagged connection from a setting of its own ([internal-engine](../internal-engine/spec.md) "Resolve the engine's connection and model together").

#### Scenario: set a connection as the internal engine default
- **GIVEN** two connections exist and none is the internal default,
- **WHEN** the user sets the second as the internal default,
- **THEN** its `internal_default` becomes true, the other stays false, and a `provider_internal_default_set` audit entry is recorded.

#### Scenario: the command line names the internal engine's connection
- **GIVEN** the daemon is running with two connections, `alpha` flagged as the internal default and `beta` unflagged,
- **WHEN** the user runs `coffer config set engine.provider beta`, then `coffer config get engine.provider`, then `coffer config unset engine.provider`,
- **THEN** `beta` carries the flag, `alpha` no longer does, a `provider_internal_default_set` entry names `beta`, and `get` prints `beta`,
- **AND** `unset` exits non-zero with a message saying the flag moves by naming another connection, and `beta` still carries it.

### Requirement: Rename a connection without moving anything else
A connection MUST be renamable through the framework's own kind-agnostic route — the `name` field on
`PATCH /api/v1/resources/{uid}` — and from the CLI with `coffer provider edit <name> --name <new>`,
which calls that route; this kind MUST NOT serve a rename route of its own. The
operation MUST change the label and NOTHING else: the resource keeps its `uid`, its `credential_ref`
MUST be left where it is (the ref is an opaque address, never derived from the name), the
`audit_log` rows MUST NOT be repointed — they follow the resource by uid and go on spelling the name
each event carried when it happened — and an active connection MUST NOT be re-projected, because the
projected `apiKeyHelper` cites the uid. Codex's provider label (`Coffer (<name>)`) is cosmetic and
goes stale until the next projection rewrites it. It MUST record a `resource_renamed` audit event
naming both names. A name another connection already holds MUST be refused with
`RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent connection MUST be a 404;
renaming to the current name MUST be a no-op and MUST record nothing. The optional display title
every resource carries ([resource-framework](../resource-framework/spec.md), edited with
`--title`) is not a rename and leaves the name alone. On the web, the edit dialog's
Name field submits this rename ahead of the patch, and the page stays where it is, because its route
is the uid.

#### Scenario: rename a connection and keep its credential, audit trail and projection
- **GIVEN** an active connection `acme` with an inline secret, projected into a registered Claude Code agent,
- **WHEN** `PATCH /api/v1/resources/<uid> {"name": "acme-eu"}` is called,
- **THEN** the connection keeps the same `uid` and answers there under the label `acme-eu`, its `credential_ref` is unchanged with the secret still readable at it, the agent's projected `apiKeyHelper` is byte-for-byte what it was (it names the uid), and the whole history — including the rows recorded before the rename, which still spell the old name — comes back when querying the audit log by uid.
#### Scenario: reject a rename onto a name another connection already uses
- **GIVEN** two connections `acme` and `taken`,
- **WHEN** `acme` is renamed to `taken`,
- **THEN** the response is 409 `RESOURCE_ALREADY_EXISTS` and both connections still carry their original labels, each still reachable at its own uid with its credential intact.
#### Scenario: rename a connection from the command line
- **GIVEN** the daemon is running with a connection `acme`,
- **WHEN** the user runs `coffer provider edit acme --name acme-eu`, and then `coffer provider edit acme-eu --name taken` while another connection is named `taken`,
- **THEN** the first answers under the label `acme-eu` at the same `uid` and records a `resource_renamed` entry naming both names,
- **AND** the second exits non-zero with the `RESOURCE_ALREADY_EXISTS` error the route gives, and the connection is still `acme-eu`.

### Requirement: Keep an independent speech-to-text default
`transcribe_default` MUST be a config field of the same shape as `internal_default`: at most one
connection globally carries it, and `set_transcribe_default` MUST clear it everywhere else before
setting the target, emit `provider_transcribe_default_set`, and notify the engine so it can apply its
own drop rule ([internal-engine](../internal-engine/spec.md) "Drop the speech-to-text model when its connection moves"); what the flagged connection is used for is
[internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model". The two flags MUST move independently — setting one MUST NOT read, write
or clear the other, and neither MUST fall back to the other at resolution time — and one connection
MAY carry both. It is a second flag because the two name different models: a gateway serving chat
completions commonly serves no `/audio/transcriptions` at all, so borrowing the engine's connection
aimed every voice message at a 404. `POST /api/v1/providers/{uid}/transcribe-default` and
`coffer config set transcribe.provider <name>` MUST be the surfaces, the route returning the updated
`ProviderOut`. `coffer config get transcribe.provider` MUST print the name of the connection that
carries the flag, or that none does, and `coffer config unset transcribe.provider` MUST be refused
the way `unset engine.provider` is (see "Set the internal-engine default").

Unlike the internal-engine default, no partial unique index backs this flag yet: a generic resource
update, `coffer provider edit` or an incoming document can still write a second one without passing
through the clear-then-set. The gap is recorded rather than claimed closed, and it wants the same
index.

#### Scenario: marking a speech-to-text default moves only its own flag
- **GIVEN** connection A is both the internal-engine default and the speech-to-text default, and connection B carries neither flag
- **WHEN** the user marks B as the speech-to-text default
- **THEN** B's `transcribe_default` becomes true and A's becomes false, and a `provider_transcribe_default_set` entry is audited
- **AND** A is still the internal-engine default and B still is not

#### Scenario: the command line names the speech-to-text connection
- **GIVEN** the daemon is running with connection A flagged as both the internal-engine and the speech-to-text default, and connection B carrying neither,
- **WHEN** the user runs `coffer config set transcribe.provider B`, then `coffer config get transcribe.provider`,
- **THEN** B carries `transcribe_default`, `get` prints B, and a `provider_transcribe_default_set` entry names B,
- **AND** A is still the internal-engine default.
