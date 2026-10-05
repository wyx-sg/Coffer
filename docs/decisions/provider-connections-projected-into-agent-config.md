# LLM Connections Are Projected Into Each Agent's Own Config File

**Status**: Accepted
**Date**: 2026-09-11
**Deciders**: Yuxing Wu
**Related**: [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [The Model Catalogue Is Read Back From the Installed Agent](model-catalogue-read-from-the-agent.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [Speech-to-Text Settings](internal-engine-settings.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md), [Kind Plugin Contract](kind-plugin-contract.md), [Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), spec provider-switching "Project into Claude Code settings without clobbering them", spec provider-switching "Project into Codex config without overwriting it", spec provider-switching "Keep an agent on at most one connection", spec provider-switching "Switch one agent at a time", spec provider-switching "Revert an agent type to its built-in login", spec provider-switching "Clear an agent's connection its config contradicts", spec provider-switching "Converge connections across machines", spec agent-registry "Carry the connection an agent runs on on the agent record", research note [provider switching](../research/provider-switching.md), PR #165, PR #187, PR #202, PR #309, PR #320

## Context

Claude Code and Codex each decide which LLM endpoint they call from their own
config file: Claude Code from `env` and `apiKeyHelper` in `~/.claude/settings.json`,
Codex from `model_provider` and a `[model_providers.<id>]` table in
`~/.codex/config.toml`. A user who routes an agent through a third-party gateway
edits those files by hand, in two formats, with the key pasted in as plaintext,
and does it again on every machine.

Coffer already stores secrets encrypted, syncs resources across machines and
audits every change. The question is how a gateway account the user registers in
Coffer becomes the endpoint an agent actually calls, in a way that survives:

- the agents being started by Coffer (chat, channels) **and** by the user in
  their own terminal;
- the agent's own CLI and the user rewriting the same file;
- a switch made on one machine not being mistaken for a switch on another;
- the user wanting the agent's own login back.

Two constraints narrow the field. Claude Code speaks only the Anthropic Messages
wire, so its endpoint must present that wire, natively or through a translating
gateway. Codex speaks only the OpenAI Responses wire; it refuses to load a
`config.toml` whose provider says `wire_api = "chat"`.

## Options Considered

### Option A — A connection resource, projected into the agent's native file, with the agent recording which connection it runs on (chosen)

A connection is a `kind='provider'` resource whose config is `ProviderConfig`
(`domain/provider/config.py`): `protocol` (`anthropic`, `openai` or
`unknown`; a stored `ollama` is retired, read and never offered), `base_url`, an optional `secret_ref`, the curated `models` it offers,
`local_runtime`, and one default flag,
`transcribe_default`. The protocol is chosen from provider
presets in the add dialog or set explicitly (`coffer provider add --protocol`). It
carries no model to run and no flag saying it is switched on: the model is chosen
where it is used, on the agent record (`AgentConfig.model` and
`tier_models`), the conversation, or the speech-to-text setting; and which connection an
agent runs on is **one field of the agent record**, `AgentConfig.connection_uid`.

Which agents a connection may reach is its framework-level `scope`
([Per-Agent Resource Scope](per-agent-resource-scope.md)). A credentialed
connection starts unscoped, reaching every agent; a stored, retired `ollama` connection
never projects (it has no wire to project onto). `application/provider/targets.py` resolves a
scope's agent uids to agent types and intersects them with `enabled`. One pure
function, `connection_for_agent`, answers which connection an agent is on, and
projection, the proxy's route, the chat model list and the
protocol lock all ask it. A pointer that names a missing, switched-off or
out-of-scope connection means the agent is treated as on its built-in login.

Switching an agent onto a connection (`POST /api/v1/providers/{uid}/activate`
with an `agent_type`, `coffer provider switch`) projects it into **that agent's**
native file and sets that agent's `connection_uid`; it touches no other agent's
file or record. The writer is the agent's own provider projection
(`domain/provider/agent_projection.py`, composed from the pure transforms in
`domain/provider/projection.py` and `codex_projection.py`), chosen by agent type
and never by protocol: a connection reaching `claude_code` writes Claude's
`settings.json` in the anthropic shape, which is how an OpenAI-compatible gateway
is routed to Claude Code. Projection runs before the record is written, so a
failed or refused write puts the file back and leaves the record unchanged
(`application/provider/switch_ops.py`). `POST /api/v1/providers/use-builtin/{agent_type}`
removes the keys Coffer wrote and clears that agent's field, returning the agent to
its own login. The switch is audited as `provider_switched` with
`{from, to, protocol, agent_type, agents}`.

What is written is the proxy form, not the upstream endpoint. An API-key or local
connection is reached through a local model proxy
([API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)):
Claude Code gets `env.ANTHROPIC_BASE_URL` naming the proxy, an `apiKeyHelper` that
prints the agent's local proxy token, and `NO_PROXY` for the loopback leg; Codex
gets `model_provider = "coffer"` and a `[model_providers.coffer]` table with the
proxy's `base_url`, `wire_api = "responses"` (fixed, since Codex loads nothing
else), `supports_websockets = false`, `requires_openai_auth = false` and a
command-backed `auth` that prints the same token, and, when the connection curates
models, `model_catalog_json` pointing at a Coffer-owned catalogue file so Codex's
own picker offers them. The file names the proxy, not the connection, so moving an
agent between two API-key connections changes the proxy's route and leaves the
file alone. The model keys written come from the agent's binding: the top-level
`model`, the `ANTHROPIC_DEFAULT_<TIER>_MODEL` pins and
`modelPicker` for Claude Code, `model` and the catalogue
for Codex; no reasoning-effort key, because the agent decides its own effort and a key an earlier version wrote is left as the user's; never `ANTHROPIC_MODEL` or `ANTHROPIC_SMALL_FAST_MODEL`, which outrank
the user's own `/model` choice. No provider key and no `env_key` appears in either
file, and the user's own `shell_environment_policy` is left as it is.

The provider-projection target of the unified reconciler
([One Level-Triggered Reconciler](one-level-triggered-reconciler-compares-parameters.md))
keeps the pointer honest against a file Coffer does not own. After a converge
round, the import's pass re-derives each agent's projection from the converged
rows, because writing a native file is a machine-local side effect no synced
document can carry. On every other pass it clears an agent's `connection_uid`
when Coffer's keys are no longer in its file, and re-projects one whose values
went stale. It never writes a missing projection back: the agent's file is the
ground truth for what the agent runs on, and re-routing a user's agent on the
strength of a stale pointer would be a surprise (PR #320, after an agent ran on its
built-in login for weeks while every surface reported a Coffer connection
active). The opposite drift — Coffer's keys present while no connection serves the
agent — is reported, not removed.

Pros: the agent runs on the connection whether Coffer or the user started it,
because the file is where the agent looks; the key never enters the agent's file or
environment; the connection gets encryption, sync, audit, rename and delete from
the resource framework; an agent runs on at most one connection by construction;
`use-builtin` is a clean undo. Cons: Coffer writes into files it shares with
another program and with the user
([Writing Agent Native Config Safely](writing-agent-native-config-safely.md));
a running agent process does not reload, so a switch between a login and a
connection reaches it on its next start; the pointer can drift from the file and
needs the boot check. It wins because the native file is the only place both
Coffer-driven and user-driven agent processes read.

### Option B — A local proxy the agents always call, with no file switching

Point both agents once at a Coffer-hosted endpoint (the claude-code-router /
LiteLLM shape). The proxy forwards to whichever connection is chosen, and can
translate wires.

Pros: switching is instant, even for running processes; one endpoint could serve
both agents through wire translation; usage metering comes for free.
Cons: a resident component on every model call, adding latency and a new failure
mode; the proxy sees every prompt and completion, a much larger trust surface than
a config writer; wire translation between Anthropic Messages and OpenAI Responses
is a product of its own that lags both vendors; and an agent on its own
subscription login would have to route through it, which Anthropic's credential
policy forbids a third party to intermediate. It was first rejected on blast
radius alone.

It is **adopted in part**: API-key and local connections are reached through a
separate supervised proxy that translates nothing, and the file projection above
is what points the agent at it. Subscription logins never go through it, so a
switch between a login and a connection is still a file write.

### Option C — Whole-file profile swap (the cc-switch shape)

Keep complete copies of `settings.json` / `config.toml` per profile and swap the
file on switch.

Pros: simple to implement; any key the user put in a profile comes along. Cons:
the swap overwrites everything else the user and the agent's own CLI wrote to that
file since the profile was saved — MCP servers, hooks, plugins, permissions — and
Coffer itself manages several of those; profiles hold the key in plaintext; nothing
converges across machines. It loses because Coffer is one of several writers of
those files and cannot own the whole of either.

### Option D — Environment variables at launch only

Leave the files alone; inject `ANTHROPIC_BASE_URL` and the credential into the agent
processes Coffer spawns.

Pros: no file writes at all; no drift between pointer and file. Cons: an agent the
user starts in their own terminal — the common case — never sees the connection.
The same connection would behave differently depending on who started the agent.
It loses on that split.

### Option E — One protocol per connection, projected by wire, one active per wire

The first shipped shape (PR #165): the connection's `wire_format` picked its
single target agent, and "active" was per wire. The connection also carried the
model.

Pros: simple mapping. Cons: the wire was never the thing being taken over; a
gateway that serves both wires needed two records; and an OpenAI-compatible
endpoint routed to Claude Code through a translating gateway had no way to express
itself. It was replaced by scope-driven reach, with the writer chosen by agent
type.

### Option F — An `is_active` flag on the connection, one per agent type

The shape that followed: scope-driven reach, but "which connection is on" kept as
a flag on each connection, at most one per agent type.

Pros: one place to read what is switched on; the connection list could show it
directly. Cons: the flag is a property of the connection that is really a fact
about an agent, so two agents of the same type could not run on different
connections, "at most one per type" had to be enforced across rows rather than
holding by construction, and the flag travelled with the connection through sync
although the file it describes is machine-local, so the same flag disagreed with
the file on another machine until its next reconcile.

Why it lost: moving the choice onto the agent record makes the invariant
structural, lets each agent have its own connection, and keeps a machine-local fact
(what an agent's file says) off a document that converges.

## Decision

An LLM connection is a `provider` resource — endpoint, protocol, secret
reference, curated model set and the speech-to-text default flag — with no model of its own and
no flag saying it is on. Which connection an agent runs on is the agent record's
`connection_uid`; switching an agent writes Coffer-managed keys into that agent's
native config file, chosen by agent type, and sets the field, with the key
reaching the agent only as a local proxy token. The agent's file is the ground
truth: boot clears a pointer the file contradicts and never re-projects, while a
converge round re-projects the switch it just carried. `use-builtin` removes the
keys and gives the agent back its own login.

Rules that follow:

- Projection writes only the keys listed above, merged into the existing file,
  and never a raw provider key.
- A new agent type needs a provider projection in its facet; scope decides reach,
  not the protocol.
- The `ollama` protocol is retired: creating or editing a connection onto it is
  refused (`PROVIDER_PROTOCOL_RETIRED`), a stored one stays readable and
  deletable, switching an agent onto it is refused, and it is never written into
  an agent's config.
- Changing a live connection's protocol is refused
  (`PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`) while an agent runs on it.
- A connection's reach and an agent's `connection_uid` are machine-local choices
  and never travel in a sync round; the connection document does.

## Consequences

- Surfaces: `/api/v1/providers` (CRUD, `/{uid}/activate`,
  `/use-builtin/{agent_type}`, the speech-to-text default flag),
  `coffer provider …`, and the connections page.
- A running agent keeps its old endpoint until restarted. Claude Code re-invokes
  `apiKeyHelper` periodically; moving between two API-key connections changes only
  the proxy's route, so it takes effect for the next session without a restart.
- Every projection write goes through the shared native-config writer, with its
  backup, fingerprint check and refusal event (`provider_projection_refused`).
- After a sync round that applied changes, the reconcile pass re-projects every
  agent that runs on a connection from the connection as it now is, and removes
  the keys Coffer left in the file of an agent that runs on none; both
  reconcilers are idempotent.
