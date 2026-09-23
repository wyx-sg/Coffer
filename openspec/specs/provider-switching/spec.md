# Provider Switching

## Purpose
An LLM connection is a credentialed endpoint — a name, a base URL, a detected protocol, an encrypted
credential and a curated set of the models it offers. One connection is used both ways: projected
into the native config file of each agent it reaches, and borrowed as the endpoint Coffer's own
internal engine runs on ([internal-engine](../internal-engine/spec.md)). Claude Code and Codex each
read provider settings from their own native config file (`~/.claude/settings.json`,
`~/.codex/config.toml`) with their own keys and base URLs; switching providers by hand means editing
several files, storing keys in plaintext and losing any record of what changed, and a key configured
for an agent could not be reused by Coffer's own engine. Coffer centralises the connection: configure
once, route it at the agents you mean, mark one as the internal engine's default, audit everything.
Its differentiator over per-tool switching scripts is governance — Fernet-encrypted credentials
([credentials](../credentials/spec.md)), a full audit trail, and one registry that converges across
the user's machines. From a fresh install a user can add a connection, bind a model, switch an agent
onto it, and have that agent pick up the new endpoint.

A connection is an optional override. An agent with nothing projected runs on its own built-in
login, and no surface may block on "no connection" — the chat surface offers the agent's own models
and runs. A connection answers "which gateway account"; which model an agent runs is a property of
the use, not of the account, so the model is chosen at the point of use — the per-agent binding, the
conversation, or the internal engine's own setting.

This capability owns the `provider` resource kind, its credential handling, the projection into
agents' native config, the switch / activate / use-builtin operations, per-connection key
resolution, the internal-engine and speech-to-text default flags, and the curated model set with its
modalities. It relies on [agent-registry](../agent-registry/spec.md) for `AgentType`, `AgentConfig`,
agent CRUD, the per-agent model binding the projection reads, the catalogue of what models an agent
can be put on and the reasoning levels its runtime reports, and the config-file store every
projection write goes through. What the flagged connections are used for — the engine's model, the
speech-to-text model, the unattended passes and the rule that drops a model when a flag moves — is
[internal-engine](../internal-engine/spec.md)'s. Coffer is a single-user tool, so no access control
applies beyond the daemon's `X-Coffer-Token` gate. Out of scope: hot-switching a running Claude Code
or Codex process mid-session; continuously reconciling live native config against the active
connection (the boot self-check is the narrow version that exists); restoring native config beyond
the `.bak` copies projection leaves; proxying, failover chains or anthropic↔openai translation (a
connection reaches an agent only because the user routed it there, and the endpoint must really
speak what that agent sends); curating an agent's own models; and deriving account entitlement
locally.

## Requirements

### Requirement: Register each connection as a provider resource
The system MUST register each managed connection as a Resource of kind `provider`, identified by the
framework's immutable `uid`
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md));
its `name` is a mutable label, validated by `validate_name` and unique within the kind. The `provider`
kind declares `supports_scope`, and its `enabled` switch is the framework's.

#### Scenario: a connection is a provider resource addressed by its uid
- **GIVEN** a running daemon
- **WHEN** the user creates a connection named `acme` and then tries to create a second connection named `acme`
- **THEN** the first is returned with a minted `uid` distinct from its name, and the framework's resource routes report it at that `uid` as kind `provider` labelled `acme`
- **AND** the second create is refused with 409 `RESOURCE_ALREADY_EXISTS` and no second row exists

### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, credential_ref, models, is_active, internal_default, transcribe_default}`,
rejecting any other key. The config MUST NOT carry a model the connection runs (no `model`, no
`fast_model`), nor the agents it reaches — reach is the resource row's per-agent `scope` — nor a
manually chosen wire format or a `wire_api`: the Codex chat/responses choice belongs to the Codex
binding.

`protocol` says what the endpoint speaks: `anthropic`, `openai`, `ollama` or `unknown`, where
`unknown` means a probe was inconclusive. It drives model introspection and whether a key is
required; it does not choose the agent a connection is written into, but a keyless (`ollama`)
connection reaches no agent whatever its scope says, and `use-builtin <wire>` finds the agent to
revert through the wire — which is why the wire cannot move under a live connection (see "Refuse to
move the wire of a live connection").

#### Scenario: reject a profile with an unknown wire format
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create a connection with `protocol="grpc"`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row is created.

### Requirement: Never return the raw secret in a connection
`ProviderOut` MUST NEVER include the raw secret. `credential_ref`, `compatible_agents` (the
configured reach, read-only), `models`, `enabled`, `is_active`, `internal_default` and
`transcribe_default` MUST be included.

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
- **THEN** both appear in `ProviderOut[]`, none includes the raw secret, and each carries the correct `is_active` flag.

### Requirement: Store an inline secret under a minted opaque ref
On create with `secret_value`, the system MUST store the raw key under a freshly minted opaque ref
(`provider/<uuid4>/key`) in the Fernet vault and persist only that ref — deriving the ref from the
name would make the name a key, which it is not. Supplying `credential_ref` instead reuses an
existing vault entry and creates none. For `anthropic` / `openai` / `unknown`, exactly one of
`secret_value` or `credential_ref` MUST be supplied; both or neither MUST be rejected `422`.

#### Scenario: create an anthropic provider profile with an inline secret
- **GIVEN** no connection named `my-provider` exists,
- **WHEN** the user creates one with `protocol="anthropic"`, a `base_url` and `secret_value` (the raw API key),
- **THEN** it is persisted with a `credential_ref` of the form `provider/<uuid4>/key`, the raw key is stored in the Fernet vault under that ref, `ProviderOut` is returned with no secret field, and `resource_created` is audited.
#### Scenario: create a profile that reuses an existing credential ref
- **GIVEN** a credential already exists under ref `shared/key`,
- **WHEN** the user creates a connection supplying `credential_ref="shared/key"` (no `secret_value`),
- **THEN** it is persisted pointing at the existing ref, no new vault entry is created, and `ProviderOut` reflects the supplied `credential_ref`.
#### Scenario: reject a profile that supplies neither a secret nor a credential ref
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create an **anthropic** connection (the neither-rule applies to anthropic / openai / unknown; ollama legitimately supplies neither) without either `secret_value` or `credential_ref`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row and no vault entry are created.

### Requirement: Rotate a connection's secret in place
On `PATCH` with `secret_value`, the system MUST rotate the stored secret (overwrite the vault entry)
without changing the ref. `credential_ref` itself is immutable on `PATCH`.

#### Scenario: rotate a connection's secret without changing its ref
- **GIVEN** a connection created with an inline secret
- **WHEN** the user patches it with a new `secret_value`
- **THEN** its `credential_ref` is unchanged
- **AND** the vault entry at that ref now holds the new secret, which is what the connection's key resolves to

### Requirement: Delete an owned credential with its connection
On delete, if the connection owns its credential ref (nothing else cites it), the system MUST delete
the vault entry, guarded by `find_credential_citations`. Ownership is decided by citation, not by the
ref spelling the name.

#### Scenario: delete a provider profile cleans up its owned credential
- **GIVEN** a connection whose `credential_ref` is `provider/my-provider/key` (owned; nothing else cites it),
- **WHEN** the user deletes it,
- **THEN** the vault entry at that ref is deleted and `resource_deleted` is audited.

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into `~/.claude/settings.json` through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
rotated `.bak` ([agent-registry](../agent-registry/spec.md) "Uninstall Coffer's MCP server from an agent") and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Carry reasoning-effort levels beside the model id") — merging only the managed keys and preserving
everything else. Coffer MERGES into the user's existing file and never replaces it; a file that does
not exist is created with only the managed keys, and activating a connection MUST NOT touch any key
outside the managed set. The managed key set per agent and the ownership markers that make
de-projection safe are in [data-model.md](data-model.md).

The raw key MUST NOT be written to `settings.json`, `config.toml` or any other native config file;
`ANTHROPIC_API_KEY` MUST NOT be written. Claude Code instead gets
`apiKeyHelper = "coffer provider key --connection-uid <uid>"`, which it invokes to fetch the key
(and re-invokes periodically). De-projection drops `apiKeyHelper` only when it is Coffer's own.

Every projection write — this one, the Codex one (see "Project into Codex config without clobbering
it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` naming that connection, `env.ANTHROPIC_BASE_URL`, and — when the agent's binding names them — `env.ANTHROPIC_MODEL` and `env.ANTHROPIC_SMALL_FAST_MODEL`; `ANTHROPIC_API_KEY` is absent; and the connection's `is_active` becomes `true`.
#### Scenario: switching preserves unrelated native-config keys and writes a .bak backup
- **GIVEN** `~/.claude/settings.json` contains keys Coffer does not manage (e.g. `theme`, `mcpServers`),
- **WHEN** the user activates a connection reaching that agent,
- **THEN** those keys are preserved byte-for-byte in the updated file, a `.bak` file is written before the update (the previous `.bak` rotating to `.bak.1`, then `.bak.2`; three generations are kept), and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no `.bak` is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

### Requirement: Project into Codex config without clobbering it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The key reaches Codex through `env_key = "COFFER_PROVIDER_KEY"` in the
`[model_providers.coffer]` table: Coffer materialises it into the environment of any Codex process it
spawns itself, and a Codex the user starts in their own shell needs the variable exported there,
since Codex offers no helper-command seam. Codex's variable is filled from the connection active for
Codex.

`wire_api = "responses"` is the only accepted value, enforced in `AgentConfig`, so anything else is a
422 at the moment it is set: Codex refuses to load a `config.toml` carrying `wire_api = "chat"`, and
rewriting the value at projection time would leave the stored value, and every `AgentOut`, saying
something other than what Coffer projects.

When the connection curates `text` models the system MUST also write the Coffer-owned model catalogue
next to `config.toml` and point `model_catalog_json` at it, writing the file before the pointer and
dropping the pointer before the file; it MUST drop that pointer only when it names the Coffer-owned
filename. That key replaces Codex's built-in model list, which is what is wanted — the built-in names
are not served by the endpoint the agent now calls. De-projection drops the pointer and retires the
file, so Codex's own models come back; an uncurated connection writes no catalogue. The file is a
wire contract with another program: every field Codex's parser requires MUST be emitted, because a
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Values
Coffer cannot derive for a third-party endpoint take the least committal value, and
`base_instructions` is written empty, so Codex sends no `instructions` field: Coffer does not author
another product's system prompt. Claude Code has no equivalent seam (`additionalModelOptionsCache` is
Claude Code's own cache and is clobbered), so for `claude_code` the Coffer-side surfaces stay the only
places the model is chosen.

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with `base_url`, `wire_api = "responses"` and `env_key = "COFFER_PROVIDER_KEY"`; and the connection's `is_active` becomes `true`.

### Requirement: Take projected model keys from the agent's binding
The model keys MUST come from the AGENT's binding (`AgentConfig.model` / `fast_model`). An unset
`model` or `fast_model` MUST leave the corresponding key out of — or removed from — the native config,
so the agent runs on its own default. Projection input is the connection (endpoint, key, protocol)
plus the agent's binding (model); a connection carries no model for any use to fall back to. The
surface that SETS that binding is [agent-registry](../agent-registry/spec.md)'s, since the field is
the agent's; this requirement is about what the projection reads.

#### Scenario: an agent's model binding drives the projected model
- **GIVEN** a Claude Code agent is registered with a per-agent model binding (`model` + `fast_model`) and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** the projected `env.ANTHROPIC_MODEL` / `env.ANTHROPIC_SMALL_FAST_MODEL` come from the AGENT's binding — the model lives at the point of use, not on the connection. An unbound agent gets no model env written, so it runs on its OWN default model.

### Requirement: Keep projection transforms pure
Domain projection logic MUST be pure (no I/O): the `apply_*` / `remove_*` functions in
`domain/provider/projection.py` (`apply_anthropic_settings`, `apply_codex_provider` and their
inverses) take the existing text and return the new native-config TEXT; `ProviderProjector` performs
the file read and write, refuses a stale write, and owns the Codex catalogue file's lifecycle.

#### Scenario: projection transforms touch no file
- **GIVEN** existing native-config text for Claude Code and for Codex, and file access that fails if attempted
- **WHEN** the anthropic and Codex apply and remove transforms run over that text
- **THEN** each returns new native-config text carrying (or no longer carrying) the managed keys
- **AND** no file is opened, read or written while they run

### Requirement: Keep at most one active connection per agent type
At most one connection per AGENT TYPE MAY have `is_active=true`. Activating a connection MUST clear
`is_active` on the connections holding the agents it reaches, then set the target's, via sequential
`ResourceService.update_config` calls; the single-process daemon serialises requests so switches
never interleave. Activating a connection takes its agents over from any previously active
connection, de-projecting that one from the agents the new one does not cover. Converging a vault
that holds more than one active connection for an agent type MUST normalise deterministically: keep
the most-recently-updated, clear the rest.

#### Scenario: activating a profile deactivates the previous active profile of the same wire format
- **GIVEN** connection A is active for an agent type and connection B reaches the same agent type,
- **WHEN** the user activates B,
- **THEN** B becomes active and A becomes inactive — at most one active connection per AGENT TYPE (the single-process daemon serialises the clear-then-set so switches never interleave).

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
is pre-filled from its wire through the kind's `default_scope` hook — both coding agents for a
credentialed wire (including `unknown`, so an inconclusive probe hides nothing and the user decides),
nothing for `ollama`. Re-targeting is a scope edit (`PUT /api/v1/resources/{uid}/scope`,
`coffer scope set provider <name> --agents …`). `scope = []` is dormant: the connection reaches no
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
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "coffer provider key --connection-uid <uid>"`, `GET /providers/{uid}/key` returns exactly that connection's key, and the reported agent set follows the scope.

### Requirement: Audit every provider switch
The system MUST emit an audit event with value `"provider_switched"` and details
`{from, to, protocol, agents}` for every switch.

#### Scenario: a provider switch is recorded in the audit log
- **GIVEN** a connection is activated,
- **WHEN** the user queries the audit log,
- **THEN** a `provider_switched` entry appears with details `{from, to, protocol, agents}`, a timestamp, and an actor.

### Requirement: Revert an agent to its built-in login
`POST /api/v1/providers/use-builtin/{wire}` MUST remove Coffer's managed keys from the agent behind
that wire and clear the active connection's flag, idempotently — succeeding when nothing was active —
and MUST revert a connection that reaches several agents as a unit, because the single `is_active`
flag is all-or-nothing.

#### Scenario: switch a wire back to the agent built-in login
- **GIVEN** a connection is active and projected into Claude Code,
- **WHEN** the user switches that wire back to built-in (`POST /providers/use-builtin/{wire}`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the connection is no longer active; the operation is idempotent (a no-op when nothing is active). A connection is an optional override.

### Requirement: Clear an active flag the agent's config contradicts at boot
At boot, for each agent type with an active connection reaching it, the system MUST check that the
agent's native config actually carries the projection and MUST clear `is_active` when it does not,
so every surface then says the agent is on its built-in login. It MUST NOT write the projection back,
because a flag left from an earlier session is no warrant to re-route a user's agent through a
gateway they are not currently using; the opposite drift — Coffer's keys present while the registry
says inactive — MUST be reported rather than removed. `is_active` is not redundant with `enabled`:
`enabled` is the user's switch on the resource, while `is_active` records that this is the connection
currently written into the agents it reaches — a claim about a file on disk that the agent's own CLI,
other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears an active flag the agent's config does not carry
- **GIVEN** an active connection reaching a registered Claude Code agent whose `settings.json` carries none of Coffer's keys
- **WHEN** the boot self-check runs
- **THEN** the connection's `is_active` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

### Requirement: Resolve a key for exactly one connection
`coffer provider key --connection-uid <uid>` / `GET /api/v1/providers/{uid}/key` MUST resolve exactly
that connection's credential ref, decrypt via `EncryptedCredentialStore.get(ref)`, and print it to
stdout or return it without logging the value. Keys resolve per CONNECTION, so routing a connection
to the other wire's agent can never resolve a different connection's key; a disabled connection, or
one scoped to no agent, resolves none. This is the one CLI command that takes a uid instead of a
name: its caller is the `apiKeyHelper` line Coffer writes into another tool's config file, so it MUST
keep resolving to the same connection after a rename. The wire-keyed form (`--wire <wire>` /
`GET /api/v1/providers/active-key/{wire}`) MUST remain for back-compat with `settings.json` files
written before, resolving through the connection active for that wire's agent.

#### Scenario: resolve the active provider key for the apiKeyHelper
- **GIVEN** a connection is active with a known secret stored in the vault,
- **WHEN** its key is resolved — `coffer provider key --connection-uid <uid>`, or the legacy `--wire anthropic` form,
- **THEN** the raw key is printed to stdout and the vault key is NOT logged.
#### Scenario: per-agent key routing follows the connection's scope
- **GIVEN** two activated connections told apart only by their scope — one scoped to `claude_code`, one to `codex`,
- **WHEN** each agent's key is resolved,
- **THEN** each resolves its own connection's key; disabling a connection, or scoping it to no agent, makes it resolve none.
#### Scenario: an agent bound to a renamed connection still resolves its key
- **GIVEN** a Claude Code agent running on connection `acme`,
- **WHEN** `acme` is renamed,
- **THEN** `GET /api/v1/providers/<uid>/key` returns the same secret, the uid the projected `apiKeyHelper` cites still resolves to it, and the connection is still active and still reaches that agent.

### Requirement: Converge connections across machines
The `provider` kind MUST be registered into the composition root's kind table so the sync exporter
and the resource applier carry it automatically ([vault-sync](../vault-sync/spec.md)): the exporter
writes each row to `resources/provider/<uid>.yaml`, git three-way-merges the tree against the remote,
and the applier puts the resulting difference back one document at a time. An incoming document MUST
NOT change the local row's reach (`enabled` / `scope`), which is one decision the user makes per
machine: a row that already exists keeps the reach it has, and a row that has just arrived takes the
kind's own default. Credentials travel as Fernet ciphertext at `credentials/<ref>.enc`, only when the
remote is configured to carry them; the master key never enters the repository, and no raw key MUST
appear in the sync tree's plaintext.

Projection is a machine-local side effect, so after a round the kind's post-import hook MUST
re-derive every agent's projection from the converged rows and apply it idempotently: for each agent
type with a registered agent, the active connection whose scope reaches it is projected, and a type
with no active connection is de-projected.

#### Scenario: a provider profile round-trips through sync export and import
- **GIVEN** a connection with a credential ref exists on one machine,
- **WHEN** a converge round runs — the exporter writes the connection into the tree and the resource **applier** puts that document into the second machine's vault,
- **THEN** the row lands there with identical `config` fields, the credential ciphertext is present at `credentials/<ref>.enc`, and no secret appears anywhere in the tree's plaintext. A later edit converges the same way, so the second machine ends up with the edited config and description.

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
- **WHEN** the user switches that connection on, marks one connection the internal-engine default and the other the speech-to-text default
- **THEN** the audit log holds a `provider_switched`, a `provider_internal_default_set` and a `provider_transcribe_default_set` entry, each naming the connection it acted on
- **AND** all four provider event values, `provider_projection_refused` included, are members of `AuditEventType`

### Requirement: Refuse to move the wire of a live connection
A connection's `protocol` MUST be correctable — the probe that guessed the wire can be wrong, and
re-entering the key to fix it is a worse answer than editing it. But the wire is not inert, so
changing it MUST be refused with 409 `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while the connection is
active, with a message that names the way out (`coffer provider use-builtin <wire>`). Two things key
off it: a keyless (`ollama`) connection covers no agent whatever its scope says (see "Keep ollama
connections internal-only"), and `use-builtin <wire>` finds the agent to revert through the wire.
Moving the wire of a connection that is currently projected would leave the native config Coffer
already wrote standing, with nothing left that would ever take it off. Silently de-projecting instead
MUST NOT be the answer: the developer asked to change a field, not to take their agents off a
gateway. Re-sending the wire the connection already has is not a change, so a client that submits a
whole form is never told its unchanged dropdown is a conflict. The refusal MUST be reachable on every
surface that offers the edit — REST, `coffer provider edit`, and the connection's form.

#### Scenario: correcting a mis-probed wire is refused while the connection is live
- **GIVEN** a connection that is switched on and projected into an agent,
- **WHEN** the user patches its `protocol` to a different wire,
- **THEN** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names `coffer provider use-builtin <wire>` as the way out
- **AND** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (see "Refuse to move the wire of a live connection")

### Requirement: Offer every connection operation on REST, CLI and web
Create, switch, revert-to-built-in, rename and delete MUST be available via (a) the REST API, (b)
`coffer provider list|add|show|edit|rm|switch|use-builtin|key|internal-default|transcribe-default`
with `--json` on `list` — rename excepted, which is `coffer resource rename provider <name> <new>`,
the kind-agnostic command — and (c) the web surfaces — the Model providers library for create and
delete, the Agent detail page for the switch, the connection's own page for the rename. Editing a
connection MUST be available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`,
`models`, `secret_value`, `description`), over the CLI
(`coffer provider edit <name> [--protocol <wire>] [--base-url <url>] [--secret <value>]`) and from
its detail page, including correcting the wire. `coffer provider add <name> --protocol <p>
--base-url <url> [--secret <value> | --credential-ref <ref>]` takes no model. Reverting is
`coffer provider use-builtin <wire>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation.

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
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider use-builtin <wire>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for its wire, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

### Requirement: Require a connection or a wire for the key command
The CLI `key` subcommand MUST accept `--connection-uid <uid>` as its primary form and `--wire <wire>`
as the back-compat form, and MUST refuse a call naming neither.

#### Scenario: the key command refuses a call naming neither a connection nor a wire
- **GIVEN** a running daemon with an active connection
- **WHEN** the user runs `coffer provider key` with neither `--connection-uid` nor `--wire`
- **THEN** the command exits non-zero with a usage error
- **AND** no key is printed

### Requirement: Keep ollama connections internal-only
The `ollama` protocol is internal-only: such a connection MUST reach no agent whatever its scope
says, MUST never be `is_active`, and activating it MUST write no native config. It has no key to
write and is used solely by Coffer's internal engine. The rule is enforced in
`application/provider/targets.py::scoped_targets`, which answers `[]` for `ollama` BEFORE the scope
is read — it is a rule about projection, not about the config's shape, and scope lives outside the
config.

#### Scenario: activating an ollama connection writes no native config
- **GIVEN** a registered Claude Code agent and an `ollama` connection whose scope names that agent
- **WHEN** the user activates the connection
- **THEN** no native config file is written and the connection is not `is_active`
- **AND** the connection reports no reachable agent

### Requirement: Make the credential optional only for ollama
`credential_ref` MUST be optional — required for `anthropic` / `openai` / `unknown`, absent for
`ollama`. On create, supplying neither `secret_value` nor `credential_ref` is valid ONLY for
`ollama`, and an `ollama` connection MUST supply neither; elsewhere the exactly-one rule (see "Store
an inline secret under a minted opaque ref") stands.

#### Scenario: create an ollama connection without a credential
- **GIVEN** no connection named `local-llm` exists,
- **WHEN** the user creates one with `protocol="ollama"`, a `base_url`, and neither `secret_value` nor `credential_ref`,
- **THEN** it persists with `credential_ref` null, no vault entry is created, it reaches no agent, and `ProviderOut` shows `internal_default=false`.

### Requirement: Keep at most one internal-engine default
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon). Converging more than one MUST normalise: keep the most-recently-updated.

The invariant MUST be enforced by the database, not only by that method. `internal_default` is an
ordinary config field, so the generic resource-update route, `coffer provider edit`, and an incoming
document all write it without going through the clear-then-set — and a live vault was found holding
two flagged connections, which makes "which connection does the internal engine use?" a question
with no defined answer. A partial unique index restricted to flagged provider rows makes a second
one unrepresentable, whatever writes it.

#### Scenario: setting a new internal default clears the previous one
- **GIVEN** connection A is the internal default,
- **WHEN** the user sets connection B as the internal default,
- **THEN** B's `internal_default` becomes true and A's becomes false (one internal default globally, enforced by the database as well as by the operation).

### Requirement: Set the internal-engine default
`POST /api/v1/providers/{uid}/internal-default` (and `coffer provider internal-default <name>`) MUST
set the named connection as the internal-engine default (applying "Keep at most one internal-engine
default"), emit a `provider_internal_default_set` audit event, and return the updated `ProviderOut`.
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

### Requirement: Introspect an unsaved connection with an inline secret
The endpoint-introspection routes MUST remain available to callers holding a connection that is not
saved yet: `POST /api/v1/models/list-models`, `/test-connection` and `/detect-protocol` each accept an
inline `secret_value` instead of a `credential_ref` and persist nothing. Testing a connection makes a
minimal request to the endpoint and reports success or a humanized failure message.

#### Scenario: test a model connection
- **GIVEN** a connection's protocol, a model id, and (where required) a credential ref,
- **WHEN** the connection is tested,
- **THEN** Coffer makes a minimal request to the endpoint and reports success or a humanized failure message, without persisting anything.
#### Scenario: test or fetch models with an inline unsaved secret
- **GIVEN** the connection dialog is open and neither the connection nor its credential ref has been saved yet,
- **WHEN** the user types a raw API key and triggers test-connection or list-models (`POST /models/test-connection` / `POST /models/list-models` carrying `secret_value` and no `credential_ref`),
- **THEN** the introspection service passes the inline key straight to the endpoint without consulting the credential vault, the probe succeeds, and the fetched models populate the selectable dropdown.

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
`PATCH /api/v1/resources/{uid}` — and this kind MUST NOT serve a rename route of its own. The
operation MUST change the label and NOTHING else: the resource keeps its `uid`, its `credential_ref`
MUST be left where it is (the ref is an opaque address, never derived from the name), the
`audit_log` rows MUST NOT be repointed — they follow the resource by uid and go on spelling the name
each event carried when it happened — and an active connection MUST NOT be re-projected, because the
projected `apiKeyHelper` cites the uid. Codex's provider label (`Coffer (<name>)`) is cosmetic and
goes stale until the next projection rewrites it. It MUST record a `resource_renamed` audit event
naming both names. A name another connection already holds MUST be refused with
`RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent connection MUST be a 404;
renaming to the current name MUST be a no-op and MUST record nothing. On the web, the edit dialog's
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

### Requirement: Introspect the endpoint when the Models tab opens
The Models tab MUST introspect the endpoint when it opens, once per visit, without a user action, and
MUST show that it is doing so; there is no "Fetch models" button, because making the user press one
made "the endpoint offers nothing" and "nothing asked it" indistinguishable. A probe that FAILS MUST
say so on the surface and offer a retry — it MUST NOT fail silently. A failed or empty probe MUST
leave the curated `models` selection unchanged, and the empty-means-unrestricted semantics (see
"Curate the models a connection offers") MUST be unaffected.

The tab is a table with one row per model id — id, type and offered — with search, a Type filter and
an Offered filter. The type is a five-value select pre-filled from what introspection guessed and
correctable in place; a correction on an already-offered row patches the curated set immediately,
while one made on a row not offered yet is held on the surface and travels into the entry when its
switch is turned on.

#### Scenario: the models table lists the endpoint's models when it opens
- **GIVEN** a connection whose endpoint serves a model list,
- **WHEN** the Models tab of its detail page is opened,
- **THEN** the endpoint is introspected without any user action and its model ids fill the table, each with its own offered/not-offered switch — there is no "Fetch models" button.
#### Scenario: a failed model introspection says so and offers a retry
- **GIVEN** a connection whose endpoint refuses the model-list probe,
- **WHEN** the Models tab is opened,
- **THEN** the failure is stated on the surface with a retry control, and the connection's existing curated selection is left exactly as it was.

### Requirement: Store a modality with each curated model
`ProviderConfig.models` MUST be a list of OBJECTS, not of strings: each entry is a `CuratedModel` of
`{id: str, modality: Modality}`, where `Modality` is a `StrEnum` over `text` (the default),
`embedding`, `image`, `video` and `audio`. One endpoint answers for more than chat, and without the
kind an embedding model could be picked as an agent's chat model. The id keeps every property "Curate
the models a connection offers" gives it (opaque, verbatim to the vendor, shape-validated only,
deduplicated preserving order, empty list = no restriction).

The STORED modality is the truth: the system MUST infer a modality in exactly two places — the
one-shot Alembic migration that converts stored plain-string entries, and endpoint introspection
(see "Offer only text models to chat pickers") — both correctable by the user from the connection
editor. There MUST be no load-time shim: reading a stored row MUST NOT re-derive a modality. The
inference rule, identical in both places, operates on the lowercased id: one containing `embed` →
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

Every CHAT model picker MUST narrow the active connection's curated set to modality `text` — the ids
fed to `AgentModelCatalogueService.offered()` / `suggest()` (the web picker, the channel `/model`
card, the turn-time note) and the Codex model catalogue Coffer projects into the agent's native
config. An `embedding`, `image`, `video` or `audio` entry MUST NEVER surface as a chat model. A
connection that curates something but nothing `text` offers no chat model rather than falling back
to the endpoint's whole catalogue; a connection curating nothing MUST still mean no restriction.
`ProviderOut.models`, `ProviderCreateRequest.models`, `ProviderPatchRequest.models` and
`ProviderModelsOut.models` MUST all carry `{id, modality}` objects; patch semantics are unchanged
(`null` leaves the set alone, `[]` clears the restriction).

#### Scenario: list a provider's models
- **GIVEN** a connection being added or edited, with a protocol entered (plus base URL and credential where the endpoint needs them),
- **WHEN** its models are fetched,
- **THEN** Coffer returns the model ids the endpoint exposes for selection, each with an inferred modality, and if none can be listed it returns an empty list with a message so the surface can say what happened.
#### Scenario: a non-text curated model never reaches a chat model picker
- **GIVEN** an active connection curating one `text` model and one `embedding` model,
- **WHEN** the agent's model picker is offered its options (`AgentModelCatalogueService.offered()` / `suggest()`, the channel `/model` card) and the Codex catalogue is projected into the agent's native config,
- **THEN** only the `text` entry appears in any of them — the `embedding` entry is offered nowhere as a chat model — while a connection that curates nothing still means no restriction.

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the active reaching connection's curated `text` ids when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an active connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. An active connection that curates nothing changes nothing, and no active reaching
connection means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Levels MUST survive it — an
id the agent also reports keeps the levels the agent reported, and one the agent has never heard of
reports none, because the turn still runs through the agent's own runtime whatever endpoint it
points at. Every surface that offers a model MUST get this answer from the same place:
`GET /api/v1/agent-providers/{agent_key}/models` serves it, and a channel's `/model` card resolves it
in-process through the same function. No surface may compute its own — a web picker that
introspected the endpoint and offered the union with the agent's catalogue listed ids the endpoint
would reject and disagreed with the same user's `/model` card.

For Claude Code, the system-prompt append Coffer adds on every turn MUST state which model Coffer put
the agent on — or that Coffer set no override — and which ids are available, so the agent does not
confidently name a model it is not running on. Codex's app-server takes no per-thread instructions,
so Codex gets the accurate catalogue instead of the note.

#### Scenario: every surface offers the same models
- **GIVEN** an agent with an active connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the web Chat page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered. A model name
and a reasoning level MUST both be passed to the agent verbatim, with no validation against a list of
Coffer's own: the CLI owns that namespace, so a renamed or added level works the day it ships, and a
level an account cannot run fails where every other unusable choice fails. A model name is still raw
passthrough everywhere the CLI accepts one.

On the built-in login the Agent page offers no model control — those slots bind a connection's
model — and shows only a line saying where the model is chosen instead (per conversation in the Chat
page's picker, or with `/model` in a channel). The reasoning effort is stored per conversation next
to the model in the provider-owned `AgentConfig` blob: `PATCH
/api/v1/chat/conversations/{id}/agent-config` takes `effort` alongside `model`, a body that mentions
one leaves the other alone, and an empty or null value clears the field so the agent runs at its own
default. Codex applies it on the turn (`turn/start {threadId, input, effort}`, omitted when unset).
Both agents get it on every surface that offers a model: the web Chat page's draft bar carries the
effort picker ([channels](../channels/spec.md) "Switch the model and reasoning effort from chat"), and a channel has `/effort`, `/model`'s sibling
([channels](../channels/spec.md) "Switch the model and reasoning effort from chat").

#### Scenario: the agent's model picker offers a fixed list without free-form entry
- **GIVEN** an agent whose model is being chosen — on its detail page or in a conversation,
- **WHEN** the model picker is opened,
- **THEN** it offers a fixed dropdown with no free-text "Custom…" entry and no text input: the agent's own catalogue (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in login, and the active connection's introspected models when one overrides it — never a model field stored on the connection, which carries none (TypeScript acceptance test).

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
`coffer provider transcribe-default <name>` MUST be the surfaces, returning and printing the updated
`ProviderOut`.

Unlike the internal-engine default, no partial unique index backs this flag yet: a generic resource
update, `coffer provider edit` or an incoming document can still write a second one without passing
through the clear-then-set. The gap is recorded rather than claimed closed, and it wants the same
index.

#### Scenario: marking a speech-to-text default moves only its own flag
- **GIVEN** connection A is both the internal-engine default and the speech-to-text default, and connection B carries neither flag
- **WHEN** the user marks B as the speech-to-text default
- **THEN** B's `transcribe_default` becomes true and A's becomes false, and a `provider_transcribe_default_set` entry is audited
- **AND** A is still the internal-engine default and B still is not
