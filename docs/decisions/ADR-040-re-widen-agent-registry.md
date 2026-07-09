# ADR-040: Re-widen the agent registry (opencode, hermes, cursor; openclaw as a separate track)

> 中文版: [ADR-040-re-widen-agent-registry.zh.md](ADR-040-re-widen-agent-registry.zh.md)

**Status**: Accepted — the openclaw verdict is REVERSED by [ADR-043](ADR-043-openclaw-managed-agent.md) (openclaw IS the sixth managed agent; ADR-042's re-check found three of this ADR's five openclaw capability cells wrong)
**Date**: 2026-07-08
**Deciders**: Yuxing Wu
**Related**: spec `004-agent-registry` (FR-003 + the FR-003a capability matrix); spec `008-agent-chat` (FR-005a agent providers); spec `011-provider-switching` (native-config projection); reverses the data migration `0031_drop_removed_agent_types`; builds on [ADR-032](ADR-032-provider-switching.md) (the `env_key` projection seam) and [ADR-037](ADR-037-rules-runtime-injection.md) (SessionStart injection)

## Context

A June 2026 simplification narrowed Coffer to exactly two managed agent types
(`claude_code`, `codex`) and **deleted** the `cursor` / `opencode` / `openclaw` /
`hermes` enum values that had shipped `enabled=False`. The data migration
`0031_drop_removed_agent_types` removed any persisted rows of those types; there
is **no schema constraint** on the agent `type` (agents live in the generic
`resources` table with `config_json.type`), so the narrowing was code + data
only.

The user now wants Coffer to manage more coding agents — **opencode**, **hermes**,
**cursor** — each with the same capability surface Coffer gives Claude Code and
Codex (chat, MCP injection, session-context/rules injection, provider projection,
native-memory disable, config-file management, discovery). This reverses the
simplification. The registry was built for exactly this: per-type behaviour lives
in the capability manifest (`AGENT_DESCRIPTORS`), and the chat surface reads an
agent-provider registry (spec 008), so adding a product is data plus — when its
wire protocol is new — one chat-provider adapter.

Three facts from surveying the four removed products shape the decision:

1. **opencode, hermes, and cursor are leaf coding CLIs** — like Claude Code and
   Codex, Coffer drives one and manages one config set. They fit the manifest.
2. **Two capability gaps are real and upstream**, not Coffer bugs:
   - **opencode has no shell-command lifecycle hook** — only in-process JS plugin
     callbacks (`session.created` / `session.idle`). Coffer's SessionStart-hook
     injection ([ADR-037](ADR-037-rules-runtime-injection.md)) cannot express a
     JS-plugin file drop; that is a genuinely different mechanism, not a widening
     of `HookInjectionSpec`.
   - **cursor is locked to Cursor's own backend** and exposes no custom LLM base
     URL, so Coffer cannot project its own LLM connections (spec 011) into it.
3. **openclaw is NOT a leaf coding CLI.** It is a peer gateway that itself
   orchestrates Claude Code / Codex / OpenCode, ships its own multi-agent router,
   persistent memory, MCP host, hooks, and channels. Coffer's "inject MCP + inject
   a session hook + drive one turn" model does not map onto it — those layers live
   inside openclaw's own config, which it owns and would conflict with Coffer's.

## Decision

**Re-add `opencode`, `hermes`, and `cursor` as managed agent types**, each as one
`AgentDescriptor` record (config dir, config-file allowlist, MCP injection shape,
and the optional hook / provider-projection / native-memory facets it supports)
plus, where the wire protocol is new, one chat-provider adapter registered in the
same seam as Claude Code / Codex. Delivery is **per-agent vertical slices** (one
agent end-to-end per PR), in ascending adapter risk: opencode → hermes → cursor.

**Capability gaps are modelled as absent descriptor facets, not errors.** A
product that lacks a facet upstream leaves it unset; the service degrades cleanly
(e.g. a native-memory-disable request for opencode returns
`NATIVE_MEMORY_DISABLE_UNSUPPORTED` / 422, and the surface hides the toggle) and
the per-agent support is tabulated in the spec 004 **capability matrix**
(FR-003a). Specifically: opencode ships without session-hook injection (its
plugin-drop is a documented follow-up slice) and without native-memory disable
(it has no cross-session native memory); cursor ships without provider projection
(no custom base URL upstream).

**openclaw is NOT re-added as a managed leaf agent.** It is a peer control plane.
The only coherent integration is to treat its gateway as an OpenAI-compatible
model endpoint (`openclaw gateway` + `POST /v1/chat/completions`,
`model: "openclaw/<agentId>"`), which is an LLM-connection concern, not an
agent-registry one. It is left to a **separate design track** —
[`docs/research/openclaw-gateway-integration.md`](../research/openclaw-gateway-integration.md)
details how it would plug into the LLM-connection registry; this ADR records why
it is out of the agent registry.

No new database migration is required — the agent `type` has no DB-level
constraint, so re-adding the enum values restores acceptance of those types;
`0031`'s row deletion is not un-done (the deleted rows were non-functional and
their config is unrecoverable — same rationale `0031` gave).

## Consequences

- The manifest seam is validated a second time: adding a leaf agent is one
  descriptor record (+ optional chat adapter), with no change to the chat surface,
  persistence, or wire contract (spec 008 SC-007).
- opencode reuses the JSON config machinery; it introduces one new
  `McpEntryStyle` (`TYPED_LOCAL_OBJECT`, opencode's `{type, command[], enabled}`
  shape) and an `opencode.json` `provider`-block projection whose `apiKey`
  references `COFFER_PROVIDER_KEY` — the same env-injection seam Codex uses
  ([ADR-032](ADR-032-provider-switching.md)).
- hermes will introduce YAML config handling (its `config.yaml` holds MCP + hooks
  + memory) and a native-memory disable target; it has the closest hook parity
  (`on_session_start` / `on_session_end`, JSON stdin/stdout, Claude-like).
- cursor ships with a documented parity hole (no provider projection); its chat
  adapter parses Cursor's `stream-json` NDJSON.
- Surfaces must read the capability matrix (an agent lacking a facet hides the
  action). Frontend `Record<AgentType, …>` maps force the new keys to be added.

## Alternatives considered

- **Keep the two-type minimum.** Rejected by the user — they want more managed
  agents with full parity.
- **Per-feature horizontal slices** (register all types first, then add each
  capability layer across all agents). Rejected: nothing is usable until late and
  a broken adapter blocks every agent; per-agent vertical slices deliver a
  working agent per PR and match Coffer's one-spec-per-scope SDD.
- **Treat openclaw as a leaf coding agent.** Rejected: architectural mismatch —
  its MCP/hook/memory layers are its own and would duplicate or conflict with
  Coffer's; driving it as an OpenAI-compatible endpoint is the only coherent path.
- **A new umbrella spec (012-multi-agent).** Rejected: the concerns already have
  owner specs (004 registry/facets, 008 chat, 011 projection); the change is
  distributed into those rather than duplicated in a new one.
