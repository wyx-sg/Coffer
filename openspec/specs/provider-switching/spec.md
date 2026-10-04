# Provider Switching

## Purpose
An LLM connection is a credentialed endpoint — a name, a base URL, a detected protocol, an encrypted
secret and a curated set of the models it offers. One connection is used both ways: projected
into the native config file of each agent it reaches, and borrowed as the endpoint Coffer's own
internal engine runs on ([internal-engine](../internal-engine/spec.md)). Claude Code and Codex each
read provider settings from their own native config file (`~/.claude/settings.json`,
`~/.codex/config.toml`) with their own keys and base URLs; switching providers by hand means editing
several files, storing keys in plaintext and losing any record of what changed, and a key configured
for an agent could not be reused by Coffer's own engine. Coffer centralises the connection: configure
once, route it at the agents you mean, mark one as the internal engine's default, audit everything.
Its differentiator over per-tool switching scripts is governance — Fernet-encrypted secrets
([secret](../secret/spec.md)), a full audit trail, and one registry that converges across
the user's machines. From a fresh install a user can add a connection, bind a model, switch an agent
onto it, and have that agent pick up the new endpoint.

A connection is an optional override. An agent with nothing projected runs on its own built-in
login, and no surface may block on "no connection" — the chat surface offers the agent's own models
and runs. A connection answers "which gateway account"; which model an agent runs is a property of
the use, not of the account, so the model is chosen at the point of use — the per-agent binding, the
conversation, or the internal engine's own setting.

This capability owns the `provider` resource kind, its secret handling, the projection into
agents' native config, the switch / activate / use-builtin operations, per-connection key
resolution, the internal-engine and speech-to-text default flags, and the curated model set with its
modalities. It relies on [agent-registry](../agent-registry/spec.md) for `AgentType`, `AgentConfig`,
agent CRUD, the per-agent model binding the projection reads, the catalogue of what models an agent
can be put on, and the config-file store every
projection write goes through. What the flagged connections are used for — the engine's model, the
speech-to-text model, the unattended passes and the rule that drops a model when a flag moves — is
[internal-engine](../internal-engine/spec.md)'s. Coffer is a single-user tool, so no access control
applies beyond the daemon's `X-Coffer-Token` gate. It also owns the local model proxy every
API-key and local connection is reached through — the per-agent proxy tokens, the relay to
each agent's one connection, and usage metering. Out of scope: hot-switching a running
Claude Code or Codex process mid-session; restoring native config beyond the `.bak` copies
projection leaves; anthropic↔openai protocol translation (a connection reaches an agent only
because the user routed it there, and the endpoint must really speak what that agent sends — the
proxy relays each wire to an upstream of the same wire); curating an agent's own models; and
deriving account entitlement locally.

While the `models` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the models feature's surfaces"), the provider, model, proxy and usage routes answer 404 `FEATURE_DISABLED`, the projection into agents' own config files is withdrawn so each agent runs on its own login, and the local model proxy serves no agent; each agent record keeps its connection choice and the projection returns when the feature is switched on. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Register each connection as a provider resource
The system MUST register each managed connection as a Resource of kind `provider`, identified by the
framework's immutable `uid`
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md));
its `name` is a mutable label, validated by `validate_name` and unique within the kind. The `provider`
kind declares `supports_scope`, and its `enabled` switch is the framework's.

#### Scenario: a connection is a provider resource addressed by its uid
- **GIVEN** a running daemon
- **WHEN** the user creates a connection named `acme` and then tries to create a second connection named `acme`
- **THEN** the first is returned with a minted `uid` distinct from its name, and the framework's resource routes report it at that `uid` as kind `provider` labelled `acme`
- **AND** the second create is refused with 409 `RESOURCE_ALREADY_EXISTS` and no second row exists

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

### Requirement: Never return the raw secret in a connection
`ProviderOut` MUST NEVER include the raw secret. `secret_ref`, `compatible_agents` (the
configured reach, read-only), `models`, `enabled`, `internal_default` and
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
- **WHEN** the user attempts to create an **anthropic** connection (the neither-rule applies to anthropic / openai / unknown; ollama legitimately supplies neither) without either `secret_value` or `secret_ref`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row and no vault entry are created.

### Requirement: Rotate a connection's secret in place
On `PATCH` with `secret_value`, the system MUST rotate the stored secret (overwrite the vault entry)
without changing the ref. A connection's key is bound to its base URL when the connection is registered,
and the new value is stored at once, with no approval
([secret](../secret/spec.md) "Store a secret through the API"). The key still reaches a new
base URL only after that URL is approved.
`secret_ref` itself is immutable on `PATCH`.

#### Scenario: rotate a connection's secret without changing its ref
- **GIVEN** a connection created with an inline secret
- **WHEN** the user patches it with a new `secret_value`
- **THEN** its `secret_ref` is unchanged
- **AND** the vault entry at that ref holds the new secret, which is what the connection's key resolves to

### Requirement: Delete an owned secret with its connection
On delete, if the connection owns its secret ref (nothing else cites it), the system MUST delete
the vault entry, guarded by `find_secret_citations`. Ownership is decided by citation, not by the
ref spelling the name.

#### Scenario: delete a provider profile cleans up its owned secret
- **GIVEN** a connection whose `secret_ref` is `provider/<uuid4>/key` (owned; nothing else cites it),
- **WHEN** the user deletes it,
- **THEN** the vault entry at that ref is deleted and `resource_deleted` is audited.

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
rotated `.bak` ([agent-registry](../agent-registry/spec.md) "Write config files atomically with a backup and an audit entry") and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Reject stale config-file writes by fingerprint") — merging only the managed keys and preserving
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
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

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
- **THEN** those keys are preserved byte-for-byte in the updated file, a `.bak` file is written before the update (the previous `.bak` rotating to `.bak.1`, then `.bak.2`; three generations are kept), and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no `.bak` is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

### Requirement: Take projected model keys from the agent's binding
The model keys MUST come from the AGENT's binding (`AgentConfig.model` and, for Claude
Code, `tier_models`). An unset `model` for
Claude Code MUST leave the key untouched — the agent runs on whatever it was set to, its own default or the user's `/model`
choice. For Codex an unset `model` removes the `model` key instead: the gateway the connection points
at is unlikely to serve the model name the user had pinned for Codex's own login. An unset
tier MUST be unpinned, except that a Claude Code agent storing no tiers is pinned to Coffer's
suggestion (see "Suggest a model for each Claude Code tier"). Projection input is the connection
(endpoint, key, protocol, curated models) plus the agent's binding; a connection carries no model for
any use to fall back to. The surface that SETS that binding is
[agent-registry](../agent-registry/spec.md)'s, since the field is the agent's; this requirement is
about what the projection reads.

#### Scenario: an agent's model binding drives the projected model
- **GIVEN** a Claude Code agent is registered with a per-agent model binding (`model` and `tier_models`) and a connection reaching it exists,
- **WHEN** the user switches the agent onto the connection,
- **THEN** the projected top-level `model` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins come from the AGENT's binding, and neither `env.ANTHROPIC_MODEL` nor `env.ANTHROPIC_SMALL_FAST_MODEL` is written — the model lives at the point of use, not on the connection.

### Requirement: Keep projection transforms pure
Domain projection logic MUST be pure (no I/O). Each agent that can be put on a connection has a
provider entry in its projection facet ([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)):
it names the allowlisted file it lands in and the wire protocols the agent's native config speaks
(possibly none), and composes the pure `apply_*` / `remove_*` transforms (`apply_anthropic_settings`,
`apply_codex_provider` and their inverses) into a plan — the main file's new TEXT, the files written
before it and the files removed after it — plus the check whether Coffer's keys are present.
`ProviderProjector` performs the plan: it reads and writes the files, refuses a stale write, and
writes a side file (the Codex model catalogue) before the pointer to it and removes it after the
pointer is gone. The writer is the agent's facet, never chosen by a protocol.

#### Scenario: projection transforms touch no file
- **GIVEN** existing native-config text for Claude Code and for Codex, and file access that fails if attempted
- **WHEN** the anthropic and Codex apply and remove transforms run over that text
- **THEN** each returns new native-config text carrying (or no longer carrying) the managed keys
- **AND** no file is opened, read or written while they run

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

### Requirement: Switch one agent at a time
`POST /api/v1/providers/{uid}/activate` with body `{agent_type}` (the agent's Change model dialog calls it) MUST switch THAT agent onto the
connection. The operation:

1. requires the connection to exist, else 404, and the agent of that type to be registered, else 404;
2. refuses with 409 `PROVIDER_DOES_NOT_REACH_AGENT` when the connection is switched off or
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

### Requirement: Audit every provider switch
The system MUST emit an audit event with value `"provider_switched"` for every switch of an agent,
with details `{from, to, protocol, agent_type, agents}` for a switch onto a connection and
`{from, to: null, agent_type, agents}` for a revert to the built-in login, where `agents` names the
agent the switch moved.

#### Scenario: a provider switch is recorded in the audit log
- **GIVEN** an agent is switched onto a connection,
- **WHEN** the user queries the audit log,
- **THEN** a `provider_switched` entry appears with details `{from, to, protocol, agent_type, agents}`, a timestamp, and an actor.

### Requirement: Clear an agent's connection its config contradicts
On every reconcile pass ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), the provider-projection target MUST compare, for each agent that runs on a connection, the keys Coffer's projection would write — base URL, model keys, the key helper command, Codex's provider block and its model catalogue — with the keys the agent's native config carries, by value and not by presence. Where Coffer's keys are present but differ, the connection MUST be projected again. Where they are absent, the system MUST clear that agent's `connection_uid` — only that field of only that agent, writing no file, recorded in the audit log with actor `system` — so every surface then says the agent is on its built-in login, and MUST NOT write the projection back, because a choice left from an earlier session is no warrant to re-route a user's agent through a gateway they are not currently using; the exceptions are a pass run for a sync import and an item a person applies, both of which project. The opposite drift — Coffer's keys present while no connection serves the agent — MUST be reported rather than removed, unless the pass runs for a sync import or a person applies
that item. A switch MUST keep reconcile passes out until its file and its record agree. `connection_uid` is not redundant with `enabled`: `enabled` is the user's switch on the connection, while `connection_uid` records that this is the connection currently written into the agent's file — a claim about a file on disk that the agent's own CLI, other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears a connection the agent's config does not carry
- **GIVEN** an agent whose `connection_uid` names a connection that serves it, whose `settings.json` carries none of Coffer's keys
- **WHEN** a reconcile pass runs at daemon start or on its period
- **THEN** the agent's `connection_uid` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

#### Scenario: a projection whose values went stale is projected again
- **GIVEN** an agent on a connection and projected into it, whose `settings.json` then carries another base URL or another key helper command than the connection's
- **WHEN** a reconcile pass runs
- **THEN** the pass reports a modification naming the changed keys and writes the connection's projection again, recorded in the audit log with actor `system`

#### Scenario: keys no connection claims are reported, not removed
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's keys while its `connection_uid` is empty
- **WHEN** a reconcile pass runs on its period
- **THEN** the drift is reported and the file is left as it was
- **AND** when the user applies that item, Coffer's keys are removed

### Requirement: Converge connections across machines
The `provider` kind MUST be registered into the composition root's kind table like every kind, so each
connection is one vault file, `resources/provider/<name>.json`, that a sync round merges and checks out
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

### Requirement: Record provider operations as their own audit events
`PROVIDER_SWITCHED` (`"provider_switched"`), `PROVIDER_INTERNAL_DEFAULT_SET`
(`"provider_internal_default_set"`), `PROVIDER_TRANSCRIBE_DEFAULT_SET`
(`"provider_transcribe_default_set"`) and `PROVIDER_PROJECTION_REFUSED`
(`"provider_projection_refused"`) MUST be in `AuditEventType` and emitted from the switch, the
internal-default operation, the speech-to-text-default operation and a refused projection.
`resource_created` / `resource_updated` / `resource_deleted` / `resource_renamed` are emitted
automatically by `ResourceService` with kind-redacted config; the provider kind declares no redactor,
because its config holds no secret.

#### Scenario: each provider operation records its own audit event
- **GIVEN** two connections and a registered Claude Code agent one of them reaches
- **WHEN** the user switches that agent onto the connection, marks one connection the internal-engine default and the other the speech-to-text default
- **THEN** the audit log holds a `provider_switched`, a `provider_internal_default_set` and a `provider_transcribe_default_set` entry, each naming the connection it acted on
- **AND** all four provider event values, `provider_projection_refused` included, are members of `AuditEventType`

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

### Requirement: Review what deleting a connection changes
Deleting a connection that agents run on MUST put each of those agents back on its built-in login first — the same de-projection "Revert an agent type to its built-in login" performs, audited the same way — and only then delete the connection, its owned secret and the engine settings that named it; a de-projection refused because a file was edited on disk aborts the delete and keeps the connection. `GET /api/v1/providers/{uid}/delete-preview` MUST answer, per agent running on the connection, which of its files the delete would change and exactly the lines it would remove or the file it would remove, and write nothing; it is a 404 for a connection that does not exist. On the web, deleting a connection nothing uses asks once and returns to the list; deleting one in use is not blocked but opens a review — what will happen to each user of the connection (an agent goes back to its own login, Coffer's engine pauses, speech to text turns off, the key is deleted) beside the daemon's own lines for each agent file — and **Delete** applies it. The lines shown are the daemon's dry run, never drawn by the page.

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
write and is used solely by Coffer's internal engine. The rule is enforced in
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
- **THEN** it persists with `secret_ref` null, no vault entry is created, it reaches no agent, and `ProviderOut` shows `internal_default=false`.

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

#### Scenario: the internal engine's connection is named over REST
- **GIVEN** the daemon is running with two connections, `alpha` flagged as the internal default and `beta` unflagged,
- **WHEN** a client calls `POST /api/v1/providers/{beta uid}/internal-default`, then `GET /api/v1/providers`,
- **THEN** `beta` carries the flag, `alpha` no longer does, and a `provider_internal_default_set` entry names `beta`,
- **AND** the list shows `beta` as the only connection flagged.

### Requirement: Introspect an unsaved connection with an inline secret
The endpoint-introspection routes MUST remain available to callers holding a connection that is not
saved yet: `POST /api/v1/models/list-models` and `/test-connection` each accept an
inline `secret_value` instead of a `secret_ref` and persist nothing. Testing a connection makes a
minimal request to the endpoint and reports success or a humanized failure message.

#### Scenario: test a model connection
- **GIVEN** a connection's protocol, a model id, and (where required) a secret ref,
- **WHEN** the connection is tested,
- **THEN** Coffer makes a minimal request to the endpoint and reports success or a humanized failure message, without persisting anything.
#### Scenario: test or fetch models with an inline unsaved secret
- **GIVEN** the connection dialog is open and neither the connection nor its secret ref has been saved yet,
- **WHEN** the user types a raw API key and triggers test-connection or list-models (`POST /models/test-connection` / `POST /models/list-models` carrying `secret_value` and no `secret_ref`),
- **THEN** the introspection service passes the inline key straight to the endpoint without consulting the secret vault, the probe succeeds, and the fetched models populate the selectable dropdown.

### Requirement: Curate the models a connection offers
`ProviderConfig` MUST carry `models` — the set of model ids the connection OFFERS downstream (refined
into a list of `{id, modality}` objects by "Store a modality with each curated model"). A gateway
account frequently serves dozens of models of which its owner uses two or three; `models` records
which. An EMPTY list MUST mean no restriction (every model the endpoint serves) and MUST be the
default. The field MUST NOT be read as a chosen model: the choice stays at the point of use. Ids MUST
be validated for shape only — non-blank, deduplicated preserving order, at most 200 ids of at most
200 characters — passed verbatim to the vendor, and MUST NEVER be checked against a list of model
names Coffer writes down, so an id the endpoint stops serving is a stale menu entry, not a config
error. The user curates from live introspection on the connection's own detail page, and a picker
offering this connection's models offers exactly the curated set when it is non-empty.

#### Scenario: curate which of a connection's models are offered downstream
- **GIVEN** a connection created with `models: ["opus", "sonnet", "opus"]`,
- **WHEN** it is read back, then patched with `models: ["haiku"]`, then patched on an unrelated field,
- **THEN** the create response, `GET /api/v1/providers/{uid}` and the list route all report `["opus", "sonnet"]` (stored verbatim, deduplicated, in the order chosen); the patch REPLACES the whole set with `["haiku"]`; the unrelated patch leaves it alone; and the change is visible in the `resource_updated` audit entry the update already emits — no audit event of its own.

### Requirement: Carry the curated set through create and patch
`ProviderCreate.models` (`null` ⇒ empty) and `ProviderPatch.models` MUST carry the set;
`ProviderOut.models` MUST return it. A `PATCH` MUST replace the whole value — `null` leaves it
unchanged, `[]` clears the restriction — and MUST NOT require a route of its own. A change MUST ride
the `resource_updated` audit event provider updates already emit.

#### Scenario: a connection with no curated models offers every model the endpoint serves
- **GIVEN** a connection created without `models` (the default, and what every connection made before the curated set existed carries),
- **WHEN** it is read back, then curated with `models: ["opus"]`, then patched with `models: []`,
- **THEN** it reports `[]` — no restriction, the endpoint's whole catalogue — both at creation and after the `[]` patch, which clears the curated set.

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
#### Scenario: rename a connection over REST
- **GIVEN** the daemon is running with a connection `acme`,
- **WHEN** a client patches the connection's `name` to `acme-eu` through `PATCH /api/v1/resources/<uid>`, and then patches it to `taken` while another connection is named `taken`,
- **THEN** the first answers under the label `acme-eu` at the same `uid` and records a `resource_renamed` entry naming both names,
- **AND** the second is refused with 409 `RESOURCE_ALREADY_EXISTS`, and the connection is still `acme-eu`.

### Requirement: Introspect the endpoint when the Models tab opens
A connection's Models section MUST introspect the endpoint when the connection opens, once per visit, without a user action, and
MUST show that it is doing so; there is no "Fetch models" button, because making the user press one
made "the endpoint offers nothing" and "nothing asked it" indistinguishable. A probe that FAILS MUST
say so on the surface — in the section's title ("Listing failed · last listed <date>") and in a box naming what failed — and leave **Refresh**, which sits in the section's title, as the one way to try again; the box carries no Retry of its own, and the failure shows only in the Models section, not on the Used by rows. It MUST NOT fail silently. A failed or empty probe MUST
leave the curated `models` selection unchanged, and the empty-means-unrestricted semantics (see
"Curate the models a connection offers") MUST be unaffected.

The section lists one row per model id — its switch (offered or not), id, what uses it, its price and its type — with a search and a Type filter. The one sentence under the section title says where prices come from once ("bundled with Coffer, updated <date>", or from the provider), so a row marks only the exception: **You set**, **Set price…** or **Local · no cost**. The type is a five-value select, shown as plain text with a chevron that opens its menu, pre-filled from what introspection guessed and
correctable in place; a correction on an already-offered row patches the curated set immediately,
while one made on a row not offered yet is held on the surface and travels into the entry when its
switch is turned on.

The section's toolbar also carries **Turn all on** and **Turn all off**, which switch every row the search and Type filter currently
match (not only the rows shown before "Show more") in one write, keeping the prices and types of the rows that stay. Turning rows on
from an unrestricted provider writes the explicit list first, as a single switch does. **Turn all off** MUST NOT write a selection that
would leave no model on, because an empty selection means "no restriction"; it is disabled, with a tooltip saying at least one model
must stay on, and it is also disabled when no matched row is on. **Turn all on** is disabled when every matched row is already on.

#### Scenario: the models table lists the endpoint's models when it opens
- **GIVEN** a connection whose endpoint serves a model list,
- **WHEN** the connection's detail is opened,
- **THEN** the endpoint is introspected without any user action and its model ids fill the table, each with its own offered/not-offered switch — there is no "Fetch models" button.
#### Scenario: a failed model introspection says so, with Refresh in the title
- **GIVEN** a connection whose endpoint refuses the model-list probe,
- **WHEN** the connection is opened,
- **THEN** the Models section's title reads "Listing failed" with Refresh beside it and a box says the endpoint's models could not be listed, with no Retry in the box, and the connection's existing curated selection is left exactly as it was.
#### Scenario: turn the matched models all on or all off in one write
- **GIVEN** a connection whose endpoint serves `a-chat`, `b-chat` and `c-embed`, with `a-chat` and `b-chat` offered,
- **WHEN** Turn all on is pressed, and then, with the search `b-` typed, Turn all off is pressed,
- **THEN** the first press writes all three models in one PATCH, with each model's type, and the second writes only the rows that did not match the search,
- **AND** Turn all off is disabled, with a tooltip, whenever it would leave no model on, and nothing is written.

### Requirement: Store a modality with each curated model
`ProviderConfig.models` MUST be a list of OBJECTS, not of strings: each entry is a `CuratedModel` of
`{id: str, modality: Modality}`, where `Modality` is a `StrEnum` over `text` (the default),
`embedding`, `image`, `video` and `audio`. One endpoint answers for more than chat, and without the
kind an embedding model could be picked as an agent's chat model. The id keeps every property "Curate
the models a connection offers" gives it (opaque, verbatim to the vendor, shape-validated only,
deduplicated preserving order, empty list = no restriction).

The STORED modality is the truth: the system MUST infer a modality in exactly one place —
endpoint introspection (see "Offer only text models to chat pickers") — correctable by the user
from the connection editor. Reading a stored row MUST NOT re-derive a modality. The inference rule
operates on the lowercased id: one containing `embed` →
`embedding`; containing `dall`, `image`, `imagen` or `flux`, or carrying a token `sd` / `sd<digits>` →
`image`; containing `video` or `sora`, or a token `veo` / `veo<digits>` → `video`; containing
`whisper` or `audio`, or a token `tts` / `tts<digits>` → `audio`; everything else → `text`. The long
names MUST match as substrings and the short ones (`sd`, `veo`, `tts`) as whole tokens (the id split
on non-alphanumerics), so an unrelated id is not mis-tagged.

#### Scenario: curate an embedding model alongside chat models on one connection
- **GIVEN** a connection whose endpoint serves chat and embedding models alike,
- **WHEN** it is created with `models: [{"id": "gpt-4o"}, {"id": "text-embedding-3-large", "modality": "embedding"}]`, read back, and its endpoint introspected via `POST /api/v1/models/list-models`,
- **THEN** the stored set keeps both entries with their modalities — `gpt-4o` as `text` (the default) and `text-embedding-3-large` as `embedding` — every read returns the modality that was STORED rather than one re-derived at read time, and the introspection response carries an inferred modality beside each discovered id so the editor can pre-fill it (an id containing `embed` comes back as `embedding`, an unrelated id as `text`).

### Requirement: Offer only text models to chat pickers
`POST /api/v1/models/list-models` MUST return an inferred modality alongside each discovered id (by
the rule in "Store a modality with each curated model"), so the connection editor pre-fills a
sensible value the user can correct; the value it returns is a suggestion, never a stored fact. When
no model can be listed it returns an empty list with a message so the surface can say what happened.

Every CHAT model picker MUST narrow the agent's connection's curated set to modality `text` — the ids
fed to `AgentModelCatalogueService.offered()` / `suggest()` (the web picker, the channel `/model`
card, the turn-time note) and the Codex model catalogue Coffer projects into the agent's native
config. An `embedding`, `image`, `video` or `audio` entry MUST NEVER surface as a chat model. A
connection that curates something but nothing `text` offers no chat model rather than falling back
to the endpoint's whole catalogue; a connection curating nothing MUST still mean no restriction.
`ProviderOut.models`, `ProviderCreateRequest.models`, `ProviderPatchRequest.models` and
`ProviderModelsOut.models` MUST all carry `{id, modality}` objects; patch semantics are unchanged
(`null` leaves the set alone, `[]` clears the restriction).

#### Scenario: list a provider's models
- **GIVEN** a connection being added or edited, with a protocol entered (plus base URL and secret where the endpoint needs them),
- **WHEN** its models are fetched,
- **THEN** Coffer returns the model ids the endpoint exposes for selection, each with an inferred modality, and if none can be listed it returns an empty list with a message so the surface can say what happened.
#### Scenario: a non-text curated model never reaches a chat model picker
- **GIVEN** a connection that an agent runs on, curating one `text` model and one `embedding` model,
- **WHEN** the agent's model picker is offered its options (`AgentModelCatalogueService.offered()` / `suggest()`, the channel `/model` card) and the Codex catalogue is projected into the agent's native config,
- **THEN** only the `text` entry appears in any of them — the `embedding` entry is offered nowhere as a chat model — while a connection that curates nothing still means no restriction.

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the curated `text` ids of the connection the agent runs on when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an agent on a connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. A connection that curates nothing changes nothing, and an agent on no connection
means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

Codex's own model picker, inside Codex, is the one surface this answer does not reach when the
connection curates models but none of modality `text`: Coffer's surfaces then offer no chat model,
while the projection writes no model catalogue ("Project into Codex config without overwriting it"
writes one only for curated `text` models), so Codex keeps listing its built-in models.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Every surface that offers a model MUST get this answer from the same place:
`GET /api/v1/agent-providers/{agent_key}/models` serves it, and a channel's `/model` card resolves it
in-process through the same function. No surface may compute its own — a web picker that
introspected the endpoint and offered the union with the agent's catalogue listed ids the endpoint
would reject and disagreed with the same user's `/model` card.

The system context Coffer adds on every turn — Claude Code's system-prompt append and Codex's
`developerInstructions` on `thread/start` and `thread/resume` — MUST state which model Coffer put the
agent on — or that Coffer set no override — and which ids are available, so the agent does not
confidently name a model it is not running on ([chat](../chat/spec.md) "Tell the agent which model it
is on").

#### Scenario: every surface offers the same models
- **GIVEN** an agent running on a connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the Conversations page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered, so a connection
an agent runs on that curates models, none of them `text`, offers none. The per-conversation picker also
always carries a **Default** option that clears the conversation's model, so the agent runs its
projected default ([chat](../chat/spec.md) "Offer models from a fixed dropdown that keeps the
current value"). A model name MUST be passed to the agent verbatim, with no validation against a list of
Coffer's own: the CLI owns that namespace, so a renamed or added model works the day it ships, and one an
account cannot run fails where every other unusable choice fails. A model name is still raw
passthrough everywhere the CLI accepts one. Coffer offers no reasoning-effort control on any surface: the agent runs at the effort its own configuration names.

On the built-in login the Change model dialog offers no model control — those slots bind a connection's
model — and says where the model is chosen instead (the agent's own `/model`, per conversation in the Chat
page's picker, or with `/model` in a channel); the agent's Overview › Model still shows the model its own configuration names, read-only. The model is stored per conversation in the provider-owned `AgentConfig` blob: `PATCH
/api/v1/chat/conversations/{id}/agent-config` takes `model`, and an empty or null value clears it so the agent runs at its own
default.

#### Scenario: the agent's model picker offers a fixed list without free-form entry
- **GIVEN** an agent whose model is being chosen — on its detail page or in a conversation,
- **WHEN** the model picker is opened,
- **THEN** it offers a fixed dropdown with no free-text "Custom…" entry and no text input: the agent's own catalogue (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in login, and, when a connection overrides it, that connection's curated `text` ids served by the same route — never a model field stored on the connection, which carries none (TypeScript acceptance test).

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

#### Scenario: the speech-to-text connection is named over REST
- **GIVEN** the daemon is running with connection A flagged as both the internal-engine and the speech-to-text default, and connection B carrying neither,
- **WHEN** a client calls `POST /api/v1/providers/{B uid}/transcribe-default`, then `GET /api/v1/providers`,
- **THEN** B carries `transcribe_default`, the list shows B as the only one flagged, and a `provider_transcribe_default_set` entry names B,
- **AND** A is still the internal-engine default.

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` MUST
remove every key Coffer wrote from the agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys and Coffer's `env.NO_PROXY` pair; for Codex the provider table, `model_provider`, `model`, and the catalogue pointer and file — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` the
user has since changed through `/model` no longer equals the agent's binding, is theirs
and is kept. An `effortLevel` or `model_reasoning_effort` that an earlier version wrote carries no mark of its own, so it is the user's and is kept too. Only values Coffer wrote are removed: the `env` keys carry no mark of their own, so they
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
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue

- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer Coffer wrote, and the catalogue file is gone

#### Scenario: switching back leaves the user's own gateway settings alone
- **GIVEN** a Claude Code `settings.json` with the user's own `env.ANTHROPIC_BASE_URL`, a tier pin and `theme`, and no Coffer `apiKeyHelper`
- **WHEN** the user switches Claude Code back to built-in, or a reconcile pass with a warrant runs
- **THEN** the file is byte-identical afterwards and attention reports no `projection_unclaimed` drift for it

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

In the Change model dialog the tiers are a **Model per tier** section — Fable only when the connection
lists a Fable model — prefilled with the suggestion and each editable from the connection's models; applying the change stores them as the agent's
`tier_models` and writes the pins ("Review a model change before writing it"). Codex has no tiers. On the built-in login the section is hidden.

#### Scenario: a non-Claude connection pins every tier to the model
- **GIVEN** a Claude Code agent bound to `kimi-k3` and a connection whose curated models are `kimi-k3` and `kimi-k3-mini`
- **WHEN** Coffer suggests the tiers
- **THEN** Opus, Sonnet and Haiku are `kimi-k3`, and no Fable tier is suggested

#### Scenario: a Claude-id gateway matches each tier by name
- **GIVEN** a connection whose curated models are `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5` and `claude-fable-1`
- **WHEN** Coffer suggests the tiers for a Claude Code agent on it
- **THEN** Opus, Sonnet, Haiku and Fable are the model whose name carries that tier

#### Scenario: an edited tier is written as the user chose it
- **GIVEN** the Model per tier section prefilled by Coffer, with Haiku changed by the user
- **WHEN** the user reviews and applies the change
- **THEN** the preview shows the Haiku pin the user chose beside the other prefilled tiers, and the agent's `tier_models` records them

#### Scenario: the built-in login shows no tiers
- **GIVEN** a Claude Code agent on its built-in login
- **WHEN** its Change model dialog is open
- **THEN** it shows Provider only and no Model per tier section, and no tier pin is in `settings.json`

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

### Requirement: Refuse a foreign Host or any Origin at the proxy
The proxy MUST bind `127.0.0.1` only, on a fixed port (`proxy_port` in `daemon-config.json`, 38471
by default), and MUST refuse with 403 a request whose `Host` is not a loopback name on the port it
arrived on, and any request that carries an `Origin` header — no browser page is a client of it.

#### Scenario: a foreign Host or an Origin is refused
- **GIVEN** the proxy running
- **WHEN** a request names a foreign `Host`, or carries any `Origin`
- **THEN** it is refused with 403 before authentication, and nothing is forwarded

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
projection leaves the window out rather than guessing one (see "Record a context window with each curated model"). Neither compatibility key is a field the user sets, and neither is a model's context window.

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
(Ollama 11434, LM Studio 1234, llama-server 8080; vLLM's default 8000 is shared by many development servers, so
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

### Requirement: Keep usage detail for the invocation window and daily totals for a year
Per-request usage rows MUST follow the MCP invocation log's retention policy (`mcp_invocations`,
30 days by default): they have no policy of their own, and changing that window changes theirs.
Daily totals — per day, agent, connection and model — MUST be kept for 365 days under their own
policy. Both are pruned on the retention cadence.

#### Scenario: request detail follows the MCP calls window
- **GIVEN** usage rows older and newer than the MCP invocation window
- **WHEN** retention prunes
- **THEN** the older rows are gone, the newer remain, and the daily totals are untouched

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
pages through the per-request detail, newest first. The web UI shows the summary as the Usage tab of Model providers ("Show metered usage on a Usage tab of Model providers").

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
- **AND** each unfiltered row names the agent types that sent its requests, most requests first

#### Scenario: a range resolves in local days
- **GIVEN** a clock on a known local day
- **WHEN** the ranges today, 7d, 30d and this month are resolved
- **THEN** each spans the local days it names, today included

#### Scenario: the last 24 hours is a rolling window
- **GIVEN** requests 2 hours ago, 23 hours ago and 25 hours ago
- **WHEN** the summary is read for the range `24h`
- **THEN** it counts the first two requests and not the third

### Requirement: Push the proxy an approved key without a restart
The model proxy MUST hold a connection's key only once the key may go to the connection's base
URL ([secret](../secret/spec.md) "Hold a secret for a new destination until a person
approves it"). While a new key for a key in use waits for approval, the proxy MUST keep sending the
old key; while a new base URL waits, the proxy MUST NOT hold the key for that connection and MUST
send nothing to the new URL. When the approval is applied in the desktop app, the daemon MUST push
the proxy its state again, so the next request carries the new key or reaches the new URL, with no
restart of the daemon or the proxy.

#### Scenario: an approved key reaches the running proxy
- **GIVEN** an agent on a connection served by a running proxy, sending with the connection's key
- **WHEN** the key is replaced, then approved in the desktop app, and the connection's base URL is then moved and that change approved too
- **THEN** until each approval the proxy keeps sending the old key and sends nothing to the new URL
- **AND** after each approval the next requests carry the new key and reach the new URL, with neither process restarted

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

### Requirement: Keep at most one internal default connection
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon); it is the one operation that moves the flag on this machine. Nothing else
makes a second one:

- **Any other write** that would set the flag while a different connection holds it — the generic
  `PATCH /api/v1/resources/{uid}` or `POST /api/v1/resources` — MUST be refused before anything is
  written with 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN`, naming the connection that holds the flag. The
  holder keeps the flag, the refused write changes nothing, and the answer is never a 500. Writing
  the flag back onto the connection that already holds it is not a second one.
- **A sync round** whose merged tree would flag a connection other than the one flagged here MUST
  NOT check that tree out: the vault's validation refuses a tree holding two flagged connections,
  so the round stops on the file and the person answers it like any other
  ([vault-sync](../vault-sync/spec.md) "Stop the round on any conflict") — keeping this machine's
  version or taking the other machine's. A tree that moves the flag, clearing it on one connection
  and setting it on another, holds one and is checked out like any change. No tie-break picks one
  silently: which connection Coffer's own model borrows is the person's decision.

The invariant MUST be enforced by the vault's validation as well. `internal_default` is an ordinary
config field, and a live vault was found holding two flagged connections, which makes "which
connection does the internal engine use?" a question with no defined answer. The rule over the
provider files ([vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path")
makes a second one unrepresentable in the vault, whatever writes it — a surface, a hand edit or a
round; the refusal above keeps every surface write from reaching it.

#### Scenario: setting a new internal default clears the previous one
- **GIVEN** connection A is the internal default,
- **WHEN** the user sets connection B as the internal default,
- **THEN** B's `internal_default` becomes true and A's becomes false (one internal default globally, enforced by the vault's validation as well as by the operation).

#### Scenario: a second internal default outside the dedicated route is refused
- **GIVEN** connection A is the internal default,
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `internal_default` true, or `POST /api/v1/resources` creates a provider with it true,
- **THEN** the answer is 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN` naming A, A keeps the flag, B stays unflagged and no connection is created,
- **AND** `POST /api/v1/providers/{B}/internal-default` still moves the flag to B.

#### Scenario: a file flagging a second internal default is refused by the vault
- **GIVEN** a connection file that flags `internal_default` in the vault
- **WHEN** a second connection file flagging it is written, and separately a change clears the first file's flag while setting the second's
- **THEN** the second file alone is refused as an invalid config naming the file that already holds the flag
- **AND** the change that moves the flag is accepted

#### Scenario: two machines that each set a different internal default stop the round
- **GIVEN** two machines in sync, and within one sync interval machine 1 sets connection X as the internal default and machine 2 sets connection Y
- **WHEN** machine 1's round pushes and machine 2's round then merges
- **THEN** machine 2's round stops on the connection files instead of checking out a tree with two internal defaults
- **AND** machine 2's vault is left as it was, holding only its own flag, until the person answers

### Requirement: Show metered usage on a Usage tab of Model providers
The Model providers page MUST carry two tabs under one header — **Providers** and **Usage**. The
header is the title with the Experimental tag, the line "Where your agents’ models come from, and
what requests through Coffer cost." and the primary **Add provider** button, the same on both tabs.
The tab is in the address: `/model-providers` and `/model-providers/<uid>` are Providers,
`/model-providers?tab=usage` is Usage. There MUST be no `/usage` page and no Usage sidebar entry.
The Usage tab shows only what Coffer's proxy metered for API-key requests: a filter row with a
date-only time range (Today, Last 7 days, Last 30 days, This month, or a custom range of days, up to
90 days back), an **Agent** pill, a **Provider** pill and **Clear filters** while one is set; five tiles in one row — Cost (estimated), whose "?" holds the
note on which prices costed the range, with the request count under it and, when a model in the
range has no known price, "N model(s) unpriced" as a link to that model on its provider
(`/model-providers?provider=<uid>&model=<id>`) — the one place the count appears — then Input,
Output, Cache read and Cache write; a Cost per day chart in the data colour with today lighter; a
segmented By model · By agent · By day over a bordered table whose second column is headed Agent,
with a Total row and, by day, the latest seven days then "Showing 7 of N · Show all". The range,
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
- **THEN** the address carries `range`, `by`, `agent` and `provider` beside `tab=usage`, the summary is asked with that range, grouping and filters, and a custom range is two days

#### Scenario: the Usage tab has nothing to show before any usage
- **GIVEN** no API-key request has ever been metered
- **WHEN** the Usage tab is opened
- **THEN** it shows "No API-key usage yet" and Open Providers, which switches to the Providers tab, and no time range or filter pills

#### Scenario: Coffer shows no subscription quota
- **GIVEN** agents on their own subscription logins
- **WHEN** the Usage tab is opened
- **THEN** it shows no quota meter, no Refresh and no status-line wrapper, and no `/api/v1/usage/quota` route is asked for

### Requirement: Project into Codex config without overwriting it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The `[model_providers.coffer]` table points Codex at the local model
proxy's Responses route, `base_url = "http://127.0.0.1:<proxy port>/openai/v1"`, with
`supports_websockets = false` (pointed at another base URL Codex otherwise tries the Responses
WebSocket transport first and stalls), `requires_openai_auth = false`, and
`auth = {command = "<absolute path to the coffer CLI>", args = ["proxy", "token", "--agent-uid", "<agent uid>"], timeout_ms = 30000}`,
so Codex fetches its local proxy token itself — a Codex the user starts in their own terminal needs
nothing exported, and no provider key is in any Codex process's environment. `timeout_ms` is
written because Codex gives the command 5 seconds unless told otherwise, and a cold start (the
frozen CLI unpacking itself, the daemon still starting, Codex launching its MCP servers at the same
time) can exceed that, which leaves Codex's first turn hanging; a `config.toml` written without it is
a difference the reconcile pass repairs. The command-backed
`auth` table needs Codex 0.155.1 or later. The table MUST name no `env_key`, and the
projection MUST NOT put a provider key into any environment variable Codex passes to the shell
commands the agent runs; the user's own `shell_environment_policy` is left as it is.

The provider block's `wire_api` is always `"responses"`: Codex refuses to load a `config.toml`
carrying any other value, so it is fixed in the projection and no agent or connection field holds it.

When the connection curates `text` models the system MUST also write the Coffer-owned model catalogue
next to `config.toml` and point `model_catalog_json` at it, writing the file before the pointer and
dropping the pointer before the file; it MUST drop that pointer only when it names the Coffer-owned
filename. That key replaces Codex's built-in model list, which is what is wanted — the built-in names
are not served by the endpoint the agent now calls. De-projection drops the pointer and retires the
file, so Codex's own models come back; an uncurated connection writes no catalogue. The file is a
wire contract with another program: every field Codex's parser requires MUST be emitted, because a
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Each
catalogue entry MUST carry the model's context window as `context_window` and `max_context_window`,
`auto_compact_token_limit` at 90% of that window and an empty `supported_reasoning_levels` list, from what the connection records for
that model (see "Record a context window with each curated model"): Codex's parser requires the list, Coffer offers no reasoning levels, and without the window
it never compacts. An entry whose window is unknown leaves the three window keys out rather than
guessing. Coffer writes no `model_reasoning_effort` and no `default_reasoning_level`: a `model_reasoning_effort` already in `config.toml` is the user's own and is left as it is. Other values Coffer cannot derive for a third-party endpoint take
the least committal value, and `base_instructions` is written empty, so Codex sends no
`instructions` field: Coffer does not author another product's system prompt. For `claude_code` the
counterpart is the `modelPicker` settings key of "Project into Claude Code settings without
clobbering them" (`additionalModelOptionsCache` is Claude Code's own cache and is clobbered, so it is
not used).

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user switches the Codex agent onto the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with the proxy's loopback `base_url`, `wire_api = "responses"`, `supports_websockets = false`, `requires_openai_auth = false` and an `auth` command printing the agent's proxy token, and no `env_key`; and the agent's `connection_uid` becomes the connection's uid.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` carries the user's own `[shell_environment_policy]` with `exclude = ["AWS_*"]`
- **WHEN** the user switches that agent onto a connection reaching it
- **THEN** `exclude` is still `["AWS_*"]`, the provider block names no `env_key` and authenticates through its `auth` command, and Coffer puts no key into the environment of the Codex processes it starts

#### Scenario: the Codex catalogue carries each model's window
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window
- **WHEN** the agent is switched onto the connection
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and an empty `supported_reasoning_levels`
- **AND** `config.toml` carries no `model_reasoning_effort` written by Coffer

#### Scenario: the Codex auth table carries a timeout so a cold token command is not cut off
- **GIVEN** a Codex agent switched onto a connection, whose `auth` table Codex would otherwise limit to its 5 second default
- **WHEN** the projection is written
- **THEN** the `auth` table carries `timeout_ms = 30000`
- **AND** a `config.toml` whose `auth` table lacks `timeout_ms` is re-projected on the next reconcile pass

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
- **AND** neither shows an effort, output-limit, subagent, thinking or fast-mode control

### Requirement: Record a context window with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window**, which the Codex catalogue needs (see "Project into Codex config without overwriting it"). It
travels through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry and is read from
the endpoint where it reports them (the person never chooses a context window); an unknown value is left
out of the stored document rather than guessed.

The add-connection dialog shows each listed model's window where the endpoint reports it and keeps
it on the curated entry; on the web it is not edited after that, only over REST. A curated entry an earlier version wrote with `effort_levels` or `default_effort` is read without them, and the next write drops them.

#### Scenario: a curated model keeps its window
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window for `gpt-x`
- **THEN** the connection reports it on `gpt-x`
