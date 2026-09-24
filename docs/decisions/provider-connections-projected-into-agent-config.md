# LLM Connections Are Projected Into Each Agent's Own Config File

**Status**: Accepted
**Date**: 2026-09-11
**Deciders**: Yuxing Wu
**Related**: [Provider Keys Never Land in Native Config](provider-keys-never-land-in-native-config.md), [Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md), [Writing Agent Native Config Safely](writing-agent-native-config-safely.md), [Internal Engine Settings](internal-engine-settings.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md), [Kind Plugin Contract](kind-plugin-contract.md), [Vault Sync](vault-sync.md), spec provider-switching "Project into Claude Code settings without clobbering them", spec provider-switching "Project into Codex config without clobbering it", spec provider-switching "Keep at most one active connection per agent type", spec provider-switching "Activate a connection into the agents its scope reaches", spec provider-switching "Revert an agent to its built-in login", spec provider-switching "Clear an active flag the agent's config contradicts at boot", spec provider-switching "Converge connections across machines", research note [provider switching](../research/provider-switching.md), PR #165, PR #187, PR #202, PR #309, PR #320

## Context

Claude Code and Codex each decide which LLM endpoint they call from their own
config file: Claude Code from `env` and `apiKeyHelper` in `~/.claude/settings.json`,
Codex from `model_provider` and a `[model_providers.<id>]` table in
`~/.codex/config.toml`. A user who routes an agent through a third-party gateway
edits those files by hand, in two formats, with the key pasted in as plaintext,
and does it again on every machine.

Coffer already stores credentials encrypted, syncs resources across machines and
audits every change. The question is how a gateway account the user registers in
Coffer becomes the endpoint an agent actually calls, in a way that survives:

- the agents being started by Coffer (chat, channels) **and** by the user in
  their own terminal;
- the agent's own CLI and the user rewriting the same file;
- a switch made on one machine arriving on another through sync;
- the user wanting the agent's own login back.

Two constraints narrow the field. Claude Code speaks only the Anthropic Messages
wire, so its endpoint must present that wire, natively or through a translating
gateway. Codex speaks only the OpenAI Responses wire; Codex 0.139.0 refuses to
load a `config.toml` whose provider says `wire_api = "chat"`.

## Options Considered

### Option A — A connection resource projected into the agent's native file (chosen)

A connection is a `kind='provider'` resource whose config is
`ProviderConfig` (`domain/provider/config.py`): `protocol` (`anthropic`,
`openai`, `ollama` or `unknown`), `base_url`, an optional `credential_ref`, the
curated `models` it offers, and three flags — `is_active`, `internal_default`,
`transcribe_default`. The protocol is chosen from provider presets in the add
dialog or set explicitly (`coffer provider add --protocol`). It carries no model
to run: the model is chosen where it is used, on the agent record
(`AgentConfig.model`, `.fast_model`, `.wire_api`), the conversation, or the
engine settings.

Which agents a connection may reach is its framework-level `scope`
([Per-Agent Resource Scope](per-agent-resource-scope.md)). A credentialed
connection starts unscoped, reaching every agent; a keyless `ollama` connection
starts scoped to no agent and never projects (`_provider_default_scope` in
`application/provider/kind.py`). `application/provider/targets.py` resolves a
scope's agent uids to agent types and intersects them with `enabled`.

Activating a connection projects it into every agent type its scope reaches.
The writer is chosen by the agent type, not by the protocol
(`domain/provider/projection.py`): Claude Code gets `apiKeyHelper` plus
`env.ANTHROPIC_BASE_URL`, and `ANTHROPIC_MODEL` / `ANTHROPIC_SMALL_FAST_MODEL`
from the agent's binding; Codex gets `model_provider = "coffer"`, a
`[model_providers.coffer]` table with `base_url`, `wire_api` and `env_key`,
and, when the connection curates models, `model_catalog_json` pointing at a
Coffer-owned catalogue file so Codex's own picker offers them. At most one
connection is active per agent type. Projection runs before the flag flips, so
a failed or refused write leaves the registry unchanged
(`application/provider/switch_ops.py`). `POST /api/v1/providers/use-builtin/{wire}`
removes Coffer's keys and clears the flag, returning the agent to its own
login. The switch is audited as `provider_switched` with
`{from, to, protocol, agents}`.

Two reconcilers keep the flag honest against a file Coffer does not own.
After a converge round, `application/provider/sync_reconcile.py` re-derives
each agent type's projection from the converged rows, because writing a native
file is a machine-local side effect no synced document can carry. At boot,
`application/provider/boot_reconcile.py` clears `is_active` when the
projection is no longer in the file. It never re-projects: the agent's file is
the ground truth for what the agent runs on, and re-routing a user's agent on
the strength of a stale flag would be a surprise (PR #320, after an agent ran
on its built-in login for weeks while every surface reported a Coffer
connection active).

Pros: the agent runs on the connection whether Coffer or the user started it,
because the file is where the agent looks; no resident component is on the
request path; the connection gets encryption, sync, audit, rename and delete
from the resource framework; `use-builtin` is a clean undo. Cons: Coffer writes
into files it shares with another program and with the user
([Writing Agent Native Config Safely](writing-agent-native-config-safely.md));
a running agent process does not reload, so a switch reaches it on its next
start; the flag can drift from the file and needs the boot check. It wins
because the native file is the only place both Coffer-driven and user-driven
agent processes read.

### Option B — A local proxy the agents always call

Point both agents once at a Coffer-hosted endpoint (the claude-code-router /
LiteLLM shape). The proxy forwards to whichever connection is active, and can
translate wires and fail over.

Pros: switching is instant, even for running processes; one endpoint could serve
both agents through wire translation; failover and usage metering come for
free. Cons: a resident component on every model call, adding latency and a new
failure mode (daemon down means both agents dead, including in the user's own
terminal); the proxy sees every prompt and completion, a much larger trust
surface than a config writer; wire translation between Anthropic Messages and
OpenAI Responses is a product of its own that lags both vendors. It loses on
blast radius: Coffer would become a dependency of every agent call the user
makes, not only the ones Coffer starts.

### Option C — Whole-file profile swap (the cc-switch shape)

Keep complete copies of `settings.json` / `config.toml` per profile and swap
the file on switch.

Pros: simple to implement; any key the user put in a profile comes along. Cons:
the swap overwrites everything else the user and the agent's own CLI wrote to
that file since the profile was saved — MCP servers, hooks, plugins, permissions
— and Coffer itself manages several of those; profiles hold the key in
plaintext; nothing converges across machines. It loses because Coffer is one of
several writers of those files and cannot own the whole of either.

### Option D — Environment variables at launch only

Leave the files alone; inject `ANTHROPIC_BASE_URL`, the key and so on into the
agent processes Coffer spawns.

Pros: no file writes at all; no drift between flag and file. Cons: an agent the
user starts in their own terminal — the common case — never sees the
connection. The same connection would behave differently depending on who
started the agent. It loses on that split. Coffer does use launch-time
injection for the one thing that must not be written down, the Codex key
([Provider Keys Never Land in Native Config](provider-keys-never-land-in-native-config.md)).

### Option E — One protocol per connection, projected by wire, one active per wire

The first shipped shape (PR #165): the connection's `wire_format` picked its
single target agent, and "active" was per wire. The connection also carried the
model.

Pros: simple mapping. Cons: the wire was never the thing being taken over; a
gateway that serves both wires needed two records; and an OpenAI-compatible
endpoint routed to Claude Code through a translating gateway had no way to
express itself. It was replaced by scope-driven reach and per-agent-type
activation, with the writer chosen by agent type.

## Decision

An LLM connection is a `provider` resource — endpoint, protocol, key reference,
curated model set and three flags — with no model of its own. Activating it
writes Coffer-managed keys into the native config file of each agent type its
scope reaches, chosen by agent type, with at most one active connection per
type. The agent's file is the ground truth: boot clears a flag the file
contradicts and never re-projects, while a converge round re-projects the
switch it just carried. `use-builtin` removes the keys and gives the agent back
its own login.

Rules that follow:

- Projection writes only the keys listed above, merged into the existing file,
  and never a raw key.
- A new agent type needs a projection writer in `domain/provider/projection.py`;
  scope decides reach, not the protocol.
- `ollama` connections are internal-only: they start dormant, activation is
  refused (`ProviderInternalOnly`), and they serve only the internal engine.
- Changing a live connection's protocol is refused
  (`PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`) until it is switched off.

## Consequences

- Surfaces: `/api/v1/providers` (CRUD, `/{uid}/activate`,
  `/use-builtin/{wire}`, the two default flags), `coffer provider …`, and the
  connections page. `POST /api/v1/models/detect-protocol` survives as a probe;
  the add dialog uses presets instead.
- A running agent keeps its old endpoint until restarted. Claude Code re-invokes
  `apiKeyHelper` periodically, so a key rotation reaches it sooner than a
  switch does.
- Every projection write goes through the shared native-config writer, with its
  backup, fingerprint check and refusal event (`provider_projection_refused`).
- The same flag may disagree with the file on another machine until its next
  converge round or boot; both reconcilers are idempotent.
