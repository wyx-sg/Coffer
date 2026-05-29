# ADR-004: MCP Capability State — Preferences in DB, List Live-Queried From Upstream

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (User Story 2)

## Context

An MCP server exposes tools, resources, and prompts. The gateway needs to know
what each upstream offers, which the user has chosen to expose, and how to keep
both consistent when upstreams change (upgrade, plugin reload, restart).

The MCP protocol itself signals dynamic capabilities through
`notifications/tools/list_changed`, `notifications/resources/list_changed`, and
`notifications/prompts/list_changed`. Capability discovery is therefore a
**runtime concern**, not a configuration concern.

Two extreme designs frame the choice:

- **Cache everything in the database.** Tool names, schemas, descriptions, plus
  enabled flags, all in a `mcp_capabilities` table. UI renders from the table.
- **Cache nothing.** Every list / call hits the upstream. Enabled/disabled state
  exists only as a list in `mcp_servers.config` JSON.

Both have failure modes. The first fights against the protocol's dynamic model
and accumulates stale schema; the second sacrifices UI responsiveness and
loses meaningful user state when an upstream is offline.

## Decision

**Database stores only user preferences. Capability lists are live-queried.**

- `mcp_capability_preferences (resource_id, capability_type, capability_key,
enabled, first_seen_at, last_seen_at)` — the **only** persisted capability
  state.
- Tool / resource / prompt names, schemas, descriptions are **never** persisted.
  They are fetched live on each `list_*` request, cached in memory per session
  with a 60-second TTL.
- Cache invalidation triggers:
  - TTL expiry.
  - Upstream `notifications/*/list_changed` (which is also forwarded to the
    downstream client).
  - User-initiated refresh (`coffer mcp refresh <name>`).
  - Upstream session restart.
- On every successful list, preferences are reconciled with the live list:
  newly-seen capability keys get a row inserted (enabled per the server's
  `auto_enable_new_capabilities` policy); capability keys that disappear are
  **not** deleted (so the user's choice survives upstream churn).

## Consequences

**Positive**

- No stale-cache class of bugs. UI, gateway list, and upstream are always in
  sync at the boundary of the 60-second cache window.
- No schema-drift class of bugs. Upstream changing a tool's `inputSchema`
  requires zero migration; the next `tools/list` reflects it.
- User intent (enabled/disabled) survives upstream upgrades naturally — keyed
  on capability name, the only stable identity available.
- Aligns with the MCP protocol's dynamic-capability design rather than fighting
  it.

**Negative**

- When an upstream is offline, the UI cannot show schemas or descriptions for
  the user's known capabilities; only names (from `last_seen_at`) and the
  enabled flag are available.
- Every `list_*` through the gateway pays at minimum one round-trip to each
  upstream on cache miss. With multiple registered upstreams this can add tens
  of milliseconds to a single client request — judged acceptable.
- Preferences for capabilities that have permanently disappeared accumulate
  rows in the DB. Cleanup is left to manual / future automation; the volume
  is bounded by the number of capabilities the user has ever seen, which is
  small in single-user scenarios.

## Alternatives Considered

**Cache full capability list in DB with periodic sync.** Rejected.

- Fights against `list_changed` semantics — the protocol expects dynamic.
- Introduces a synchronisation lag observable to the user (schema cache says
  one thing, upstream actually has another).
- Forces schema migrations when upstreams add new fields.
- Provides little benefit over the in-memory cache, which is fast enough.

**Pure live (no cache at all).** Rejected. The latency cost compounds when the
gateway has 5+ registered upstreams and the AI is doing frequent `list_tools`
queries during a multi-turn conversation. The 60-second in-memory cache
captures the common case.

**LLM-based semantic dedup of redundant capabilities.** Rejected. Brittle
(name vs description vs schema), expensive (per-list LLM call), opaque
(user can't predict which of two `read_file` tools survives). The user's
explicit preference toggle is the right control surface.

**Persist schema + description but rely on `notifications/*/list_changed` for
freshness.** Rejected. Many MCP servers don't reliably emit `list_changed` on
restart; we'd accumulate stale schemas anyway. The decision was to remove the
ambiguity entirely.
