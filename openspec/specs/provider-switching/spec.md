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
applies beyond the daemon's `X-Coffer-Token` gate. It also owns the local model proxy every
API-key and local connection is reached through — the per-agent proxy tokens, failover between
connections that serve the same model, and usage metering. Out of scope: hot-switching a running
Claude Code or Codex process mid-session; restoring native config beyond the `.bak` copies
projection leaves; anthropic↔openai protocol translation (a connection reaches an agent only
because the user routed it there, and the endpoint must really speak what that agent sends — the
proxy relays each wire to an upstream of the same wire); curating an agent's own models; and
deriving account entitlement locally.

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
connection reaches no agent whatever its scope says — which is why the wire cannot move under a live
connection (see "Refuse to move the wire of a live connection"). No wire names an agent: each agent
declares the wire protocols its native config speaks, possibly none (see "Keep projection transforms
pure").

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
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
rotated `.bak` ([agent-registry](../agent-registry/spec.md) "Write config files atomically with a backup and an audit entry") and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Reject stale config-file writes by fingerprint") — merging only the managed keys and preserving
everything else. Coffer MERGES into the user's existing file and never replaces it; a file that does
not exist is created with only the managed keys, and activating a connection MUST NOT touch any key
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
launch; the top-level `effortLevel` for the agent's effort; `env.ANTHROPIC_DEFAULT_OPUS_MODEL`,
`env.ANTHROPIC_DEFAULT_SONNET_MODEL`, `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` and, when a Fable tier is
pinned, `env.ANTHROPIC_DEFAULT_FABLE_MODEL`, from "Suggest a model for each Claude Code tier"; and
`modelPicker`, which fills Claude Code's `/model` picker with the connection's curated text models,
replacing the built-in rows on an endpoint that serves no Claude ids and keeping them on one that
does. Every option Coffer writes into `modelPicker` carries the description `via Coffer`, which is
how de-projection tells Coffer's picker from the user's. Every projection write MUST delete
`env.ANTHROPIC_SMALL_FAST_MODEL`, the deprecated background-model key that Claude Code still reads
ahead of the Haiku pin, and an `env.ANTHROPIC_MODEL` an earlier build wrote. For a connection to
a model runtime on this machine it also writes `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

De-projection drops `apiKeyHelper` only when it is Coffer's own — a helper line running the coffer
CLI (by absolute path or bare) with `proxy token`, or the `provider key` form earlier builds wrote —
and leaves a helper the user wrote alone.

Every projection write — this one, the Codex one (see "Project into Codex config without clobbering
it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` printing that agent's proxy token and `env.ANTHROPIC_BASE_URL` naming the proxy's loopback Anthropic route; neither the connection's endpoint nor its key appears in the file, `ANTHROPIC_API_KEY` is absent; and the connection's `is_active` becomes `true`.
#### Scenario: switching preserves unrelated native-config keys and writes a .bak backup
- **GIVEN** `~/.claude/settings.json` contains keys Coffer does not manage (e.g. `theme`, `mcpServers`),
- **WHEN** the user activates a connection reaching that agent,
- **THEN** those keys are preserved byte-for-byte in the updated file, a `.bak` file is written before the update (the previous `.bak` rotating to `.bak.1`, then `.bak.2`; three generations are kept), and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no `.bak` is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

#### Scenario: every write deletes the deprecated background-model key
- **GIVEN** `~/.claude/settings.json` carrying `env.ANTHROPIC_SMALL_FAST_MODEL` and `env.ANTHROPIC_MODEL` from an earlier build
- **WHEN** Coffer projects a connection for an agent bound to a model and a Haiku tier
- **THEN** both keys are gone, the model is in the top-level `model` key, and the Haiku tier is in `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`

### Requirement: Project into Codex config without clobbering it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The `[model_providers.coffer]` table points Codex at the local model
proxy's Responses route, `base_url = "http://127.0.0.1:<proxy port>/openai/v1"`, with
`supports_websockets = false` (pointed at another base URL Codex otherwise tries the Responses
WebSocket transport first and stalls), `requires_openai_auth = false`, and
`auth = {command = "<absolute path to the coffer CLI>", args = ["proxy", "token", "--agent-uid", "<agent uid>"]}`,
so Codex fetches its local proxy token itself — a Codex the user starts in their own terminal needs
nothing exported, and no provider key is in any Codex process's environment. The command-backed
`auth` table needs Codex 0.155.1 or later. The table names no `env_key`, and the
`COFFER_PROVIDER_KEY` entry earlier builds added to `shell_environment_policy.exclude` is removed,
keeping the user's own entries, and the table when nothing else is left in it.

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
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Each
catalogue entry MUST carry the model's context window as `context_window` and `max_context_window`,
`auto_compact_token_limit` at 90% of that window, and — when the model has effort levels —
`supported_reasoning_levels` and `default_reasoning_level`, from what the connection records for
that model (see "Record a context window and effort levels with each curated model"): without the
levels Codex sends no reasoning effort whatever `model_reasoning_effort` says, and without the window
it never compacts. An entry whose window is unknown leaves the three window keys out rather than
guessing. The agent's effort is written as the top-level `model_reasoning_effort`, and only when the
chosen model records that level. Other values Coffer cannot derive for a third-party endpoint take
the least committal value, and `base_instructions` is written empty, so Codex sends no
`instructions` field: Coffer does not author another product's system prompt. For `claude_code` the
counterpart is the `modelPicker` settings key of "Project into Claude Code settings without
clobbering them" (`additionalModelOptionsCache` is Claude Code's own cache and is clobbered, so it is
not used).

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with the proxy's loopback `base_url`, `wire_api = "responses"`, `supports_websockets = false`, `requires_openai_auth = false` and an `auth` command printing the agent's proxy token, and no `env_key`; and the connection's `is_active` becomes `true`.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` carries `[shell_environment_policy]` with `exclude = ["AWS_*", "COFFER_PROVIDER_KEY"]` from an earlier build
- **WHEN** the user activates a connection reaching it
- **THEN** `exclude` is `["AWS_*"]`, the provider block names no `env_key`, and Coffer puts no key into the environment of the Codex processes it starts

#### Scenario: the Codex catalogue carries each model's window and effort levels
- **GIVEN** a Codex agent switched to an API-key connection whose curated model `gpt-x` records a 200000-token window and the levels `low`, `medium`, `high`, and the agent's effort set to `high`
- **WHEN** the connection is activated
- **THEN** the catalogue entry for `gpt-x` carries `context_window` and `max_context_window` 200000, `auto_compact_token_limit` 180000 and `supported_reasoning_levels` low, medium, high
- **AND** `config.toml` carries `model_reasoning_effort = "high"`

### Requirement: Take projected model keys from the agent's binding
The model keys MUST come from the AGENT's binding (`AgentConfig.model`, `effort` and, for Claude
Code, `tier_models`). An unset `model` or `effort` MUST leave the corresponding key untouched — the
agent runs on whatever it was set to, its own default or the user's `/model` choice — and an unset
tier MUST be unpinned, except that a Claude Code agent storing no tiers is pinned to Coffer's
suggestion (see "Suggest a model for each Claude Code tier"). Projection input is the connection
(endpoint, key, protocol, curated models) plus the agent's binding; a connection carries no model for
any use to fall back to. The surface that SETS that binding is
[agent-registry](../agent-registry/spec.md)'s, since the field is the agent's; this requirement is
about what the projection reads.

#### Scenario: an agent's model binding drives the projected model
- **GIVEN** a Claude Code agent is registered with a per-agent model binding (`model`, `effort` and `tier_models`) and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** the projected top-level `model` and `effortLevel` and the `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins come from the AGENT's binding, and neither `env.ANTHROPIC_MODEL` nor `env.ANTHROPIC_SMALL_FAST_MODEL` is written — the model lives at the point of use, not on the connection.

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

### Requirement: Keep at most one active connection per agent type
At most one connection per AGENT TYPE MAY have `is_active=true`. Activating a connection MUST clear
`is_active` on the connections holding the agents it reaches, then set the target's, via sequential
`ResourceService.update_config` calls; the single-process daemon serialises requests so switches
never interleave. Activating a connection takes its agents over from any previously active
connection, de-projecting that one from the agents the new one does not cover. Converging a vault
that holds more than one active connection for an agent type MUST project deterministically — the
first of those connections by name wins the agent type — MUST leave every `is_active` flag as it
stands, and MUST report the conflict naming both connections so the user re-activates one. No
last-write rule applies: `updated_at` is machine-local and does not travel with the document.

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
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, the model proxy routes that agent's requests to exactly that connection with that connection's key, and the reported agent set follows the scope.

### Requirement: Audit every provider switch
The system MUST emit an audit event with value `"provider_switched"` for every switch, with details
`{from, to, protocol, agents}` for an activation and `{from, to: null, agent_type, agents}` for a
revert to the built-in login.

#### Scenario: a provider switch is recorded in the audit log
- **GIVEN** a connection is activated,
- **WHEN** the user queries the audit log,
- **THEN** a `provider_switched` entry appears with details `{from, to, protocol, agents}`, a timestamp, and an actor.

### Requirement: Clear an active flag the agent's config contradicts
On every reconcile pass ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), the provider-projection target MUST compare, for each enabled agent an active connection reaches, the keys Coffer's projection would write — base URL, model keys, the key helper command, Codex's provider block and its model catalogue — with the keys the agent's native config carries, by value and not by presence. Where Coffer's keys are present but differ, the connection MUST be projected again. Where they are absent and no agent of that type carries them, the system MUST clear `is_active`, so every surface then says the agent is on its built-in login, and MUST NOT write the projection back, because a flag left from an earlier session is no warrant to re-route a user's agent through a gateway they are not currently using; the exceptions are a pass run for a sync import, which carries the user's explicit switch from another machine, and an item a person applies, both of which project. Where they are absent from one agent of a type while another agent of that type carries them, that agent MUST be projected too. For Codex, the `shell_environment_policy.exclude` entry alone does not count as carrying the projection: it selects no provider. The opposite drift — Coffer's keys present while no active connection reaches the agent — MUST be reported rather than removed, unless the pass runs for a sync import or a person applies
that item. A multi-step switch MUST keep reconcile passes out until its writes and its flags agree. `is_active` is not redundant with `enabled`: `enabled` is the user's switch on the resource, while `is_active` records that this is the connection currently written into the agents it reaches — a claim about a file on disk that the agent's own CLI, other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears an active flag the agent's config does not carry
- **GIVEN** an active connection reaching a registered Claude Code agent whose `settings.json` carries none of Coffer's keys
- **WHEN** a reconcile pass runs at daemon start or on its period
- **THEN** the connection's `is_active` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

#### Scenario: a leftover shell exclude entry is not a Codex projection
- **GIVEN** an active connection reaching a registered Codex agent whose `config.toml` holds only `[shell_environment_policy]` with `exclude = ["COFFER_PROVIDER_KEY"]`
- **WHEN** a reconcile pass runs
- **THEN** the connection's `is_active` is cleared

#### Scenario: a projection whose values went stale is projected again
- **GIVEN** an active connection projected into a Claude Code agent, whose `settings.json` then carries another base URL or another key helper command than the connection's
- **WHEN** a reconcile pass runs
- **THEN** the pass reports a modification naming the changed keys and writes the connection's projection again, recorded in the audit log with actor `system`

#### Scenario: keys no active connection claims are reported, not removed
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's keys while no connection is active for it
- **WHEN** a reconcile pass runs on its period
- **THEN** the drift is reported and the file is left as it was
- **AND** when the user applies that item, Coffer's keys are removed

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

Projection is a machine-local side effect, so after a round applies, the reconcile pass it runs
with the import's warrant MUST re-derive every agent's projection from the converged rows: for each
agent type with a registered agent, the active connection whose scope reaches it is projected, and a
type with no active connection is de-projected — the import carries the user's switch either way.

#### Scenario: a provider profile round-trips through sync export and import
- **GIVEN** a connection with a credential ref exists on one machine,
- **WHEN** a converge round runs — the exporter writes the connection into the tree and the resource **applier** puts that document into the second machine's vault,
- **THEN** the row lands there with identical `config` fields, the credential ciphertext is present at `credentials/<ref>.enc`, and no secret appears anywhere in the tree's plaintext. A later edit converges the same way, so the second machine ends up with the edited config and description.

#### Scenario: an import projects a switch made on another machine
- **GIVEN** a connection activated on another machine, whose row arrives here with `is_active` set while this machine's agent carries none of Coffer's keys
- **WHEN** the round's reconcile pass runs
- **THEN** the connection is projected into the agent rather than its flag being cleared

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
active, with a message that names the way out (`coffer provider builtin <agent_type>` for each
agent type the connection reaches). A keyless (`ollama`) connection covers no agent whatever its
scope says (see "Keep ollama connections internal-only").
Moving the wire of a connection that is currently projected would leave the native config Coffer
already wrote standing, with nothing left that would ever take it off. Silently de-projecting instead
MUST NOT be the answer: the developer asked to change a field, not to take their agents off a
gateway. Re-sending the wire the connection already has is not a change, so a client that submits a
whole form is never told its unchanged dropdown is a conflict. The refusal MUST be reachable on every
surface that offers the edit — REST, `coffer provider edit`, and the connection's form.

#### Scenario: correcting a mis-probed wire is refused while the connection is live
- **GIVEN** a connection that is switched on and projected into an agent,
- **WHEN** the user patches its `protocol` to a different wire,
- **THEN** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names `coffer provider builtin <agent_type>` for the agent types it reaches as the way out
- **AND** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (see "Refuse to move the wire of a live connection")

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

- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES group; the old
  `/settings/models`, `/settings/providers` and `/settings/llm-connections` routes redirect there) is
  the connection library: a table of name / vendor / base URL / reach, an Add action and Delete per
  row. It has no per-row switch, because activation is per agent. A row MUST say what Coffer ITSELF
  uses the connection for: the `internal_default` connection carries a "Coffer · background model"
  badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with a hint
  naming where it is changed, and the connection's detail header repeats them. The labels lead with
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
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider builtin <agent_type>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for that agent type, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)

### Requirement: Keep ollama connections internal-only
The `ollama` protocol is internal-only: such a connection MUST reach no agent whatever its scope
says, MUST never be `is_active`, and activating it MUST write no native config: activation is
refused with `409 PROVIDER_INTERNAL_ONLY` before anything is touched. It has no key to
write and is used solely by Coffer's internal engine. The rule is enforced in
`application/provider/targets.py::scoped_targets`, which answers `[]` for `ollama` BEFORE the scope
is read — it is a rule about projection, not about the config's shape, and scope lives outside the
config.

#### Scenario: activating an ollama connection writes no native config
- **GIVEN** a registered Claude Code agent and an `ollama` connection whose scope names that agent
- **WHEN** the user activates the connection
- **THEN** the activation is refused with `409 PROVIDER_INTERNAL_ONLY`, no native config file is written and the connection is not `is_active`
- **AND** the connection reports no reachable agent

### Requirement: Make the credential optional for ollama and local runtimes
`credential_ref` MUST be optional — required for `anthropic` / `openai` / `unknown` connections to a
remote endpoint, absent for `ollama`, and optional for a local runtime connection (see "Configure a
local model connection"), because LM Studio, vLLM and llama-server may be started with a key or
without one. On create, supplying neither `secret_value` nor `credential_ref` is valid for `ollama`
and for a local runtime, and an `ollama` connection MUST supply neither; elsewhere the exactly-one
rule (see "Store an inline secret under a minted opaque ref") stands.

#### Scenario: create an ollama connection without a credential
- **GIVEN** no connection named `local-llm` exists,
- **WHEN** the user creates one with `protocol="ollama"`, a `base_url`, and neither `secret_value` nor `credential_ref`,
- **THEN** it persists with `credential_ref` null, no vault entry is created, it reaches no agent, and `ProviderOut` shows `internal_default=false`.

### Requirement: Keep at most one internal-engine default
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon); it is the one operation that moves the flag on this machine. A direct write
never makes a second one, and a synced one is settled the same way on every machine:

- **Any other write** that would set the flag while a different connection holds it — the generic
  `PATCH /api/v1/resources/{uid}` or `POST /api/v1/resources` — MUST be refused before anything is
  written with 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN`, naming the connection that holds the flag. The
  holder keeps the flag, the refused write changes nothing, and the answer is never a 500. Writing
  the flag back onto the connection that already holds it is not a second one.
- **A converge round** ([vault-sync](../vault-sync/spec.md)) applying a document that sets the flag on
  a connection other than the local holder MUST NOT fail the round and MUST NOT hold the path for
  retry. When the tree the round applies also clears the flag on the local holder, the flag was
  moved on another machine, and the holder MUST be released first so the move lands whatever order
  the two documents apply in. Otherwise two machines each flagged a different connection, and the
  connection whose uid sorts first (lexicographically) MUST keep the flag — a tie-break every machine
  computes the same way, so the fleet converges on one default instead of each machine keeping its
  own and then receiving a clear for it. If that is the incoming connection, the local holder MUST
  be released and the document applied as written; if it is the local holder, the document MUST be
  applied with `internal_default` false and everything else as written — whether the connection
  already exists here or is new — and the path MUST be reported among the round's failures, naming
  the holder. A release runs only once the incoming document has passed its gate, just before its
  write, and is reverted if that write fails, so a document that cannot land leaves this machine its
  internal default.

The invariant MUST be enforced by the database as well. `internal_default` is an ordinary config
field, and a live vault was found holding two flagged connections, which makes "which connection
does the internal engine use?" a question with no defined answer. A partial unique index restricted
to flagged provider rows makes a second one unrepresentable, whatever writes it; the refusal and the
normalisation above keep every write from reaching it.

#### Scenario: setting a new internal default clears the previous one
- **GIVEN** connection A is the internal default,
- **WHEN** the user sets connection B as the internal default,
- **THEN** B's `internal_default` becomes true and A's becomes false (one internal default globally, enforced by the database as well as by the operation).
#### Scenario: a second internal default outside the dedicated route is refused
- **GIVEN** connection A is the internal default,
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `internal_default` true, or `POST /api/v1/resources` creates a provider with it true,
- **THEN** the answer is 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN` naming A, A keeps the flag, B stays unflagged and no connection is created,
- **AND** `POST /api/v1/providers/{B}/internal-default` still moves the flag to B.
#### Scenario: a synced second internal default is dropped, not fatal
- **GIVEN** connection A is the internal default on this machine, its document in the tree still flags it, and A's uid sorts before B's,
- **WHEN** a converge round applies a document flagging connection B — an existing connection or a new one — with other edits beside the flag,
- **THEN** the round completes and its pointer advances, A keeps the flag, B is applied with every other field as written and `internal_default` false,
- **AND** the round's failures name B's path and A, and the path is not held for retry.
#### Scenario: a synced internal default whose uid sorts first takes the flag
- **GIVEN** connection A is the internal default on this machine, its document in the tree still flags it, and B's uid sorts before A's,
- **WHEN** a converge round applies a document flagging connection B,
- **THEN** B holds the flag, A's is cleared, and the round reports no failure for it.
#### Scenario: two machines that each set a different internal default converge on one
- **GIVEN** two machines in sync, and within one sync interval machine 1 sets connection X as the internal default and machine 2 sets connection Y,
- **WHEN** both machines run converge rounds until they settle,
- **THEN** both machines hold exactly one internal default, the same one on each, and it is whichever of X and Y has the smaller uid.

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

Codex's own model picker, inside Codex, is the one surface this answer does not reach when the
connection curates models but none of modality `text`: Coffer's surfaces then offer no chat model,
while the projection writes no model catalogue ("Project into Codex config without clobbering it"
writes one only for curated `text` models), so Codex keeps listing its built-in models.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Levels MUST survive it — an
id the agent also reports keeps the levels the agent reported, and one the agent has never heard of
reports none, because the turn still runs through the agent's own runtime whatever endpoint it
points at. Every surface that offers a model MUST get this answer from the same place:
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
- **GIVEN** an agent with an active connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the web Chat page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered, so an active
connection that curates models, none of them `text`, offers none. The per-conversation picker also
always carries a **Default** option that clears the conversation's model, so the agent runs its
projected default ([chat](../chat/spec.md) "Offer models from a fixed dropdown that keeps the
current value"). A model name
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

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` (and `coffer provider builtin <agent_type>`) MUST
remove every key Coffer wrote from every enabled agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model` and `effortLevel`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys, and any `env.ANTHROPIC_SMALL_FAST_MODEL` or
`env.ANTHROPIC_MODEL`; for Codex the provider table, `model_provider`, `model`,
`model_reasoning_effort`, the catalogue pointer and file, and the shell-environment exclusion — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` or effort the
user has since changed through `/model` or `/effort` no longer equals the agent's binding, is theirs
and is kept. It also clears the flag of the connection active for it, idempotently — succeeding when
nothing was active — and MUST revert a connection that reaches several agent types as a unit,
because the single `is_active` flag is all-or-nothing. The route and the command take an agent
type; a wire is not accepted, because a connection reaches agents through its scope and no protocol
names an agent.

#### Scenario: switch an agent back to its built-in login
- **GIVEN** a connection is active and projected into Claude Code,
- **WHEN** the user switches Claude Code back to built-in (`POST /providers/use-builtin/claude_code`, or `coffer provider builtin claude_code`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the connection is no longer active; the operation is idempotent (a no-op when nothing is active). A connection is an optional override.

#### Scenario: a wire no longer names an agent to revert
- **GIVEN** the daemon is running
- **WHEN** the user asks to revert `anthropic`, or a type that is not an agent type
- **THEN** the request is refused as `unprocessable_entity` (422) and nothing is written

#### Scenario: switching back removes every key Coffer wrote
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, `effortLevel`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue and an effort
- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer or `model_reasoning_effort` Coffer wrote, and the catalogue file is gone

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

#### Scenario: a non-Claude connection pins every tier to the model
- **GIVEN** a Claude Code agent bound to `kimi-k3` and a connection whose curated models are `kimi-k3` and `kimi-k3-mini`
- **WHEN** Coffer suggests the tiers
- **THEN** Opus, Sonnet and Haiku are `kimi-k3`, and no Fable tier is suggested

#### Scenario: a Claude-id gateway matches each tier by name
- **GIVEN** a connection whose curated models are `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5` and `claude-fable-1`
- **WHEN** Coffer suggests the tiers for a Claude Code agent on it
- **THEN** Opus, Sonnet, Haiku and Fable are the model whose name carries that tier

### Requirement: Record a context window and effort levels with each curated model
Each curated model of a connection (see "Store a modality with each curated model") MUST be able to
record its **context window** and its **effort levels**, with the level used when an agent names
none, which the Codex catalogue needs (see "Project into Codex config without clobbering it"). They
travel through `POST` / `PATCH /api/v1/providers` with the rest of the curated entry, are read from
the endpoint where it reports them, and are otherwise entered by the user; an unknown value is left
out of the stored document rather than guessed.

#### Scenario: a curated model keeps its window and levels
- **GIVEN** a connection whose curated model `gpt-x` records no window
- **WHEN** the user patches its curated models with a 200000-token window and the levels low, medium and high for `gpt-x`
- **THEN** the connection reports them on `gpt-x`

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
body, prompt, completion or credential. Everything else it is asked for is 404. The decision is
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

### Requirement: Authenticate each agent to the proxy with its own local token
Each managed agent MUST have its own random 256-bit local proxy token, minted by Coffer on first
use, kept as ciphertext in the credential store under a machine-local ref vault sync never
carries, and printed by `coffer proxy token --agent-uid <uid>` (`GET /api/v1/proxy/tokens/{agent_uid}`)
— the command both agents' projected config runs. The proxy MUST accept a model request only with
one of those tokens, as `Authorization: Bearer` or `x-api-key`, compared in constant time, and MUST
refuse anything else — no token, a claude.ai OAuth token (`sk-ant-oat…`), a provider key — with 401
in the wire's own error shape, forwarding nothing. The token names the agent, which is how usage is
attributed. `coffer proxy rotate <agent>` (`POST /api/v1/proxy/tokens/{agent_uid}/rotate`) replaces
it; the old token is refused from the moment the rotation answers. For an agent this machine does
not have, the token route answers 404 and the command exits 4 with nothing on stdout, so a stale
helper fails closed. The token keeps browsers and other users' processes off the proxy; it is not a
boundary against a process of the same user.

#### Scenario: a request without a Coffer token is refused
- **GIVEN** the proxy serving an agent's route
- **WHEN** a request arrives with no token, or with an OAuth-shaped `sk-ant-oat` bearer
- **THEN** it is refused with 401 and nothing is forwarded upstream

#### Scenario: a rotated token replaces the old one
- **GIVEN** an agent whose token the proxy accepts
- **WHEN** the token is rotated
- **THEN** the old token is refused with 401 and the new one is accepted

#### Scenario: the token command prints a local token, never a provider key
- **GIVEN** a registered agent and an active API-key connection reaching it
- **WHEN** the user runs `coffer proxy token --agent-uid <uid>`
- **THEN** it prints the agent's local token, which is not the connection's key
- **AND** for a uid no agent has it exits 4 with nothing on stdout

### Requirement: Refuse a foreign Host or any Origin at the proxy
The proxy MUST bind `127.0.0.1` only, on a fixed port (`proxy_port` in `daemon-config.json`, 8001
by default), and MUST refuse with 403 a request whose `Host` is not a loopback name on the port it
arrived on, and any request that carries an `Origin` header — no browser page is a client of it.

#### Scenario: a foreign Host or an Origin is refused
- **GIVEN** the proxy running
- **WHEN** a request names a foreign `Host`, or carries any `Origin`
- **THEN** it is refused with 403 before authentication, and nothing is forwarded

### Requirement: Fail over only before the first content byte
When a request fails before the first content byte reaches the agent — a connect, TLS or DNS
error, a 5xx, 529 or 429 status, a 401 or 403, a first-byte timeout, or an error event before the
first content event (the proxy holds the response until then, bounded to 64 KiB and 5 seconds) — the proxy MUST move it to the next member of the agent's route: another enabled
connection that reaches the same agent type, speaks the same protocol and lists the requested model
among its curated models. Failover MUST never change the model, never try the same member twice for
one request, and never happen after the first content byte: an error or truncation after it goes to
the agent, whose own retry lands on a healthy member. A 429 with `retry-after` cools that member for
that long; 401 or 403 disables it until its key changes; 400, 404 and 413 are relayed and never
fail over. A local runtime connection has no fallback members. A session stays on one member until
that member fails.

#### Scenario: a failure before the first byte moves to another connection serving the model
- **GIVEN** an agent's active connection answering 503, and another connection reaching the agent that lists the requested model
- **WHEN** the agent sends a request
- **THEN** the agent receives the second connection's response and never sees the 503

#### Scenario: an error after the first content byte is passed to the agent
- **GIVEN** an active connection whose stream fails after its first content event
- **WHEN** the agent sends a streaming request
- **THEN** the agent receives the partial stream and the error, and no other connection is tried

#### Scenario: a request problem is never failed over
- **GIVEN** an active connection answering 400
- **WHEN** the agent sends a request
- **THEN** the 400 and its body reach the agent unchanged and no other connection is tried

#### Scenario: failover never changes the model
- **GIVEN** an active connection answering 529, a second connection that does not list the requested model, and a third that does
- **WHEN** the agent sends a request
- **THEN** the second connection is never tried, and the third receives the request with the model the agent asked for

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

#### Scenario: create a keyless local runtime connection
- **GIVEN** an Ollama runtime answering on a loopback port
- **WHEN** the user runs `coffer provider add ollama --protocol anthropic --base-url http://127.0.0.1:11434 --local`
- **THEN** the connection persists with no credential, records the runtime, version and wires it serves, and curates its tool-capable models with their served windows

#### Scenario: a local connection sets Claude Code's compatibility key
- **GIVEN** a Claude Code agent switched to a local model connection whose model records a 131072-token window
- **WHEN** the connection is activated
- **THEN** `settings.json` carries `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` = `1` and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` = `131072`, with every tier pinned to the local model

#### Scenario: a local runtime connection must be on this machine
- **GIVEN** the daemon is running
- **WHEN** a connection is created with a `local_runtime` and a non-loopback base URL
- **THEN** it is refused as 422

### Requirement: Detect a local model runtime without changing it
`POST /api/v1/providers/detect-local` and `coffer provider detect-local [--base-url <url>]` MUST
report which runtime answers at a loopback URL — or, with none given, at each runtime's default port
(Ollama 11434, LM Studio 1234, llama-server 8080; vLLM's default 8000 is the daemon's own port, so
vLLM is found only on a URL the user gives) — by fingerprint rather than port, with its version, the
wires it serves at that version and, per model, the context window it serves and whether it can
call tools, where the runtime says. Detection MUST be read-only — nothing is pulled, loaded or
downloaded — and MUST refuse a non-loopback URL as 422. A runtime below the minimum version for a
wire (Ollama 0.14.0 for Messages and 0.13.4 for Responses, LM Studio 0.4.1 and 0.3.29, vLLM 0.11.1
and 0.10.0) is not reported as serving it.

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

### Requirement: Meter every proxied request
The local model proxy MUST record one usage record per upstream attempt of a Messages or Responses
request, failed-over attempts included: when it started, the agent (from its local token), the
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
completion or a credential. How the proxy reads the stream is
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

### Requirement: Price usage from a bundled snapshot and per-connection prices
Cost MUST be estimated at ingest, per model and per token category, from a versioned price snapshot
shipped with the release, unless the connection records its own price for that model (relays and
resellers price differently), and stored with the price it used (`snapshot:<version>` or
`override:<connection uid>`) so a later snapshot never rewrites history. A cache category an
override leaves out is charged at its input rate. A model neither prices MUST be marked unpriced,
never costed at zero. The snapshot carries Anthropic's first-party rates only. It carries no OpenAI
(Codex) rates, because Coffer has no verified source for them, and it MUST NOT carry a rate that
is not from the vendor's own published pricing; other vendors' models are unpriced until the user
sets a price on the connection. Every surface labels cost as estimated. Where nothing in a cost is
priced, the web UI and the CLI MUST show `—` in its place, never `$0.00`, and the web UI MUST say
why and where a price is set in the dash's tooltip and accessible name.

#### Scenario: a known model is priced per category
- **GIVEN** a record for `claude-opus-5-5` with input, cache-write, cache-read and output tokens
- **WHEN** it is priced
- **THEN** each category is charged at that model's own rate

#### Scenario: an unknown model is marked unpriced, never zero
- **GIVEN** a record for a model no snapshot or connection prices
- **WHEN** it is priced
- **THEN** it has no cost and is marked unpriced

#### Scenario: stored cost names the price it used
- **GIVEN** one record priced from the snapshot and one from its connection's own price
- **WHEN** both are ingested
- **THEN** each row names the price it was costed with

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model from a vendor other than Anthropic — a Codex model, or a gateway’s own — through a connection that records no price for it
- **WHEN** the Usage page and `coffer usage` show that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage page the dash's tooltip says Coffer ships Anthropic's rates only and a price is set on the connection in Model providers

### Requirement: Report usage by model, agent or day over a range
`GET /api/v1/usage/summary` and `coffer usage [--range today|7d|30d|month|custom] [--from <day> --to <day>] [--by model|agent|day] [--json]`
MUST report, for the range in the machine's local days (today; the last 7 or 30 days including today;
this calendar month; or an inclusive custom range), one row per model (with the connection that
served it, by uid and name), per agent or per day: requests, the token totals per category, the
estimated cost, and how many requests were unpriced or had unknown usage. `GET /api/v1/usage/requests`
and `coffer usage requests` page through the per-request detail, newest first.
`GET /api/v1/usage/export.csv` and `coffer usage --csv` return the same summary as CSV.

#### Scenario: usage by model names the connection
- **GIVEN** usage of two models over two connections
- **WHEN** the summary is grouped by model
- **THEN** each row names its model and the connection's uid and name, with its requests, tokens and estimated cost

#### Scenario: usage by agent and by day
- **GIVEN** usage by two agents on two days
- **WHEN** the summary is grouped by agent, and then by day
- **THEN** it returns one row per agent, and then one row per day

#### Scenario: a range resolves in local days
- **GIVEN** a clock on a known local day
- **WHEN** the ranges today, 7d, 30d and this month are resolved
- **THEN** each spans the local days it names, today included

#### Scenario: export usage as CSV
- **GIVEN** usage in the range
- **WHEN** the user exports it
- **THEN** the CSV has a header row and one line per group with the same totals the summary reports

### Requirement: Show a subscription's official quota as of when it was seen
For an agent on its own subscription login, Coffer MUST show only the vendor's own remaining
allowance, never an estimate, each window with its used percentage, its length and when it resets,
labelled with when its source produced it. Codex's comes from `codex app-server`'s
`account/rateLimits/read` — on request (`POST /api/v1/usage/quota/refresh`, `coffer usage quota
--refresh`), and in the background no more often than every five minutes while a Codex agent is on its
own login — and from `account/rateLimits/updated` notifications of the sessions Coffer drives.
Claude Code's comes from the `rate_limit_event` of the sessions Coffer drives, preferring its
both-windows field and degrading to the top-level window when that is absent. Coffer MUST NOT read
another application's OAuth token or credential file and MUST NOT call an undocumented quota
endpoint. `GET /api/v1/usage/quota` and `coffer usage quota` report the latest window per agent type;
with no value, or a window whose reset has passed, they say so and show no number.

#### Scenario: Codex quota comes from its app-server
- **GIVEN** a `codex app-server` that answers `account/rateLimits/read` with a primary and a secondary window
- **WHEN** Coffer reads Codex's quota
- **THEN** both windows are stored with their used percentage, length, reset time and when they were seen

#### Scenario: Claude Code quota comes from a driven session's rate-limit event
- **GIVEN** a Claude Code session Coffer drives that emits a `rate_limit_event`
- **WHEN** the event arrives
- **THEN** its windows are stored as Claude Code's quota, and the turn is unaffected

#### Scenario: no fresh value shows no number
- **GIVEN** an agent type no source has reported for, and a window whose reset time has passed
- **WHEN** the quota is read
- **THEN** the first says no value has been seen and the second shows no percentage

#### Scenario: Codex is not read more often than every five minutes
- **GIVEN** a Codex quota read a minute ago
- **WHEN** the background loop asks again, and then a manual refresh asks within thirty seconds
- **THEN** neither reaches the app-server

### Requirement: Offer an opt-in statusline wrapper
`coffer usage statusline -- <the user's own statusLine command>` MUST forward the `rate_limits`
object of the statusline JSON Claude Code writes to its stdin to
`POST /api/v1/usage/quota/statusline`, with a timeout of at most one second and never starting a
daemon, then run the user's own command with the same stdin and print its output and exit code —
even when the daemon is down. Coffer never installs it: the user opts in by setting it as their
`statusLine` command, which covers the Claude Code sessions they run in their own terminal.

#### Scenario: the user's statusline command still runs with the daemon down
- **GIVEN** no daemon running
- **WHEN** Claude Code runs the wrapper with the user's own statusline command
- **THEN** the user's command runs with the same stdin and its output is printed

### Requirement: Push the proxy an approved key without a restart
The model proxy MUST hold a connection's key only once the key may go to the connection's base
URL ([credentials](../credentials/spec.md) "Hold a secret for a new destination until a person
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
