# ADR-026 — Per-Agent MCP Server Scoping at the Gateway

> 中文版: [ADR-026-per-agent-mcp-scoping.zh.md](./ADR-026-per-agent-mcp-scoping.zh.md)

- **Status:** Reverted (2026-06-20) — see the revert note below
- **Date:** 2026-06-19
- **Deciders:** Yuxing Wu
- **Spec:** 001-mcp-gateway and 004-agent-registry (both spec.md updated before implementation)
- **Amends:** [ADR-007](./ADR-007-everything-is-a-resource-kind.md) (the agent kind now carries a scope) and [ADR-018](./ADR-018-tool-retrieval-for-overload.md) / [ADR-024](./ADR-024-builtin-agent-is-internal-capability.md) (`coffer__search_tools` ranking is now scope-aware)
- **Related:** [ADR-004](./ADR-004-capability-state-model.md) (capability preferences in DB), [ADR-005](./ADR-005-session-subprocess-model.md) (per-session upstream subprocesses)

> **⚠️ Reverted (2026-06-20, simplification 1.6).** Per-agent MCP server scoping is removed — the gateway serves every enabled server to every agent again, with no per-agent identity or allowlist. The decision below is retained for history.

## Context

Coffer aggregates many upstream MCP servers behind one endpoint and re-exposes
them to whichever agent connects through the shim. Today that surface is
**global**: every agent that runs the shim reaches the same set of enabled
servers, because the gateway has no idea _which_ agent is on the other end of a
session. The enabled/disabled curation from [ADR-004](./ADR-004-capability-state-model.md)
is gateway-wide, not per-agent.

This is the one capability the competitive landscape unanimously has and Coffer
lacked. The MCP-ecosystem survey (`docs/research/mcp-ecosystem.md`) found —
**confirmed, unanimous** — that every comparable gateway lets each client see a
different curated subset of servers/tools: ContextForge's **virtual servers**,
MetaMCP's **namespaces**, MCPJungle's **tool groups**, Docker's **profiles**.
Coffer was the lone "whole gateway per agent." As a user registers more servers,
handing all of them to every agent both wastes the downstream model's context
and exposes tools an agent has no business calling.

The blocker has been identity: a gateway session carries no agent identity, so
there is nothing to scope _on_. Spec 004 already writes a `coffer` MCP entry into
each agent's config (the one-click install), which is the natural place to stamp
that identity.

## Decision

Add **per-agent server scoping**, enforced at the gateway. Four moves.

### 1. Agent identity travels with the session

The installed `coffer` MCP entry carries the agent's name as an `--agent <name>`
argument. The shim forwards it as an `X-Coffer-Agent` request header; the gateway
attributes the session to that agent. A session that presents **no** identity —
e.g. the in-process built-in agent behind `coffer__ask`
([ADR-024](./ADR-024-builtin-agent-is-internal-capability.md)) — is treated as
**unscoped (full access)**, so every existing client keeps working unchanged.

### 2. Two scope modes, with new-server semantics

Each agent has a scope **mode**:

- **`auto`** (the default, and current behavior) — the agent sees every enabled
  MCP server. New agents default here, so the feature is fully backward
  compatible.
- **`selected`** — the agent sees only an explicit allowlist of servers.

A newly added server **automatically** appears for `auto` agents but **never**
joins a `selected` agent's allowlist on its own — opting into a smaller surface
stays a deliberate choice the new server can't silently widen.

### 3. Effective scope enforced at list **and** search **and** call

An agent's **effective scope** = enabled servers, intersected with its allowlist
when `selected`. The gateway applies it everywhere a capability could surface:
`tools/list`, `resources/list`, `prompts/list`, and `coffer__search_tools`
ranking (so out-of-scope tools never even rank). Crucially it also rejects a
**direct** `tools/call` / `resources/read` / `prompts/get` to an out-of-scope
server — even when the capability name is supplied directly. List-time hiding
alone is a security gap: a model that already knows a `<server>__<tool>` name
could otherwise call it. The call path is the real boundary.

### 4. Data model — two cascade tables

`agent_mcp_scope` holds one row per agent (its `mode`, FK to the agent resource).
`agent_mcp_scope_server` holds the `selected` allowlist as `(agent, server)`
rows, each an FK to a resource. Both FKs are `ON DELETE CASCADE`: deleting the
agent drops its scope and allowlist; deleting a server drops it from every
allowlist that named it (the owning agent's scope survives, now without that
server). No name-keyed strings, no orphan rows. Migration `0023`.

## Alternatives considered

A — **Per-tool, not per-server granularity.** Scope individual `<server>__<tool>`
capabilities per agent, not whole servers. **Rejected.** ADR-004 already gives
gateway-wide per-tool curation; per-agent _server_ scope is the coarse knob the
competitors ship and what users actually reason about ("this agent gets the
GitHub server"). Per-agent-per-tool is a large allowlist nobody wants to
maintain; revisit only if a real need appears.

B — **Secure-by-default deny (new servers hidden until allowed).** Make `selected`
the default and hide every newly added server from everyone until explicitly
granted. **Rejected.** It breaks backward compatibility (every existing agent
would go dark) and inverts the zero-config promise. `auto` default + auto-include
for `auto` agents keeps the easy path easy; `selected` is the opt-in.

C — **Reusable named scope profiles** shared across agents (à la ContextForge
virtual servers). **Rejected for now (YAGNI).** A single user with a handful of
agents doesn't need a profile registry; per-agent mode + allowlist covers it. A
named-profile layer can be added later without changing the enforcement seam if
sharing across agents becomes real.

D — **Name-keyed scope tables without FK cascade** (store agent/server names as
strings). **Rejected.** It would leave orphan allowlist rows when a server or
agent is deleted and re-introduce the rename/identity drift that
[ADR-003](./ADR-003-resource-identifier-format.md)'s surrogate ids exist to
avoid. FK cascade keeps integrity automatic.

## Consequences

- **Closes the one unanimous competitive gap.** Coffer now matches ContextForge /
  MetaMCP / MCPJungle / Docker on per-client curated subsets, keyed to the agent
  identity the shim already could carry.
- **Backward compatible by construction.** `auto` default + unscoped-on-no-identity
  means every existing shim session and the in-process built-in agent behave
  exactly as before until a user opts an agent into `selected`.
- **Search is now scope-aware** (amends ADR-018/ADR-024): `coffer__search_tools`
  ranks only the calling agent's effective scope, so retrieval can't surface a
  tool the agent then can't call.
- **The call path is the security boundary, not the list.** Out-of-scope calls
  are rejected at `tools/call` / `resources/read` / `prompts/get`, so hiding at
  list time is a UX convenience, not the gate.
- **New surface:** spec 004 gains `GET`/`PUT /agents/{name}/mcp-scope`, an agent
  detail-page control, and the `--agent` argument in the install writer; spec 001
  gains the gateway enforcement and migration `0023` (two cascade tables). No
  change for agents left on the default.
