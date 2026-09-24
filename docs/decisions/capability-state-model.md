# MCP Capability State — Preferences in the Database, Lists Live-Queried From Upstream

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [Session Subprocess Model](session-subprocess-model.md),
[Resource Reach Is Machine-Local](resource-reach-is-machine-local.md),
spec mcp-gateway "Forward tools, resources and prompts",
spec mcp-gateway "Toggle individual capabilities",
spec mcp-gateway "Preserve capability decisions",
spec mcp-gateway "Enable newly discovered capabilities",
research note [MCP gateways](../research/mcp-gateways.md)

## Context

An upstream MCP server exposes tools, resources and prompts. The gateway needs
to know what each upstream offers, which of those the user has chosen to
expose, and how to keep both straight when an upstream is upgraded, reloads a
plugin or restarts.

The MCP protocol treats capabilities as dynamic: a server announces changes
with `notifications/tools/list_changed`, `notifications/resources/list_changed`
and `notifications/prompts/list_changed`. What a server offers is therefore a
runtime fact, not configuration. The user's choice to hide one of those
capabilities is the opposite — durable intent that must survive the server
changing underneath it. The only stable identity a capability has is its name
(or URI) within its server.

## Options Considered

### Option A — persist only preferences; query lists live with a short in-memory cache (chosen)

`mcp_capability_preferences (resource_id, capability_type, capability_key,
enabled, first_seen_at, last_seen_at)` is the only persisted capability state
(`infrastructure/mcp/persistence.py`). Names, schemas and descriptions are
never persisted: `CapabilityDiscovery` (`application/mcp/discovery.py`) fetches
them from the upstream and caches each `(server, capability type)` slice in
memory for 60 seconds. Each gateway session builds its own
`CapabilityDiscovery` over its own supervisor
([Session Subprocess Model](session-subprocess-model.md)); a separate
process-wide instance over a process-wide supervisor serves the management
routes — the capability tabs and refresh — so the UI never borrows an agent's
session (`surfaces/http/app_mcp_composition.py`).

The cache slice is dropped on TTL expiry, on an upstream `list_changed`
notification (which is also forwarded to the downstream client), on an explicit
refresh (`coffer mcp refresh <name>` / `POST …/{uid}/refresh`), and when a
server that failed to list recovers. Every successful list reconciles
preferences in one batch: a newly seen key gets a row, enabled; an existing
key's `last_seen_at` is touched; a key that disappeared is **not** deleted, so
a disable survives an upstream that briefly drops the tool. Preference rows are
read fresh on every list, so a toggle takes effect immediately regardless of
the cache.

Pros: no stale-schema bugs and no migrations when an upstream changes a
tool's `inputSchema`; aligned with the protocol's dynamic model; user intent
survives upgrades because it is keyed on the name. Cons: with an upstream
offline the UI can show only the names it has preference rows for, not
schemas or descriptions; a cache miss costs a round-trip per upstream; rows for
capabilities that are gone for good accumulate (bounded by what one user has
ever seen).

### Option B — cache the full capability list in the database, refreshed periodically

A `mcp_capabilities` table with names, schemas, descriptions and flags; the UI
renders from it. Pros: the UI works fully with an upstream offline; no
round-trip on read. Cons: fights `list_changed` semantics; introduces a
visible lag between what the table says and what the upstream does; forces
schema migrations when upstreams add fields; offers little over the in-memory
cache. Lost.

### Option C — persist schemas and descriptions, rely on `list_changed` for freshness

Pros: full offline UI with protocol-driven freshness. Cons: many servers do
not emit `list_changed` on restart, so stale schemas would accumulate anyway.
Lost: it removes none of Option B's ambiguity.

### Option D — no cache at all; preferences as a disabled-list inside the server's config

Every list hits every upstream; the disabled set lives in the server's
resource config (`resources.config`). Pros: nothing to invalidate; one row per
server. Cons: latency compounds with five or more upstreams and an agent
listing tools every turn; and folding the disabled set into config makes a
toggle a config write — re-validated, audited as a config change and
reconciled as one — while a capability that disappears and returns has no
first/last-seen record to show. Lost on both counts; the 60-second cache
captures the common case.

### Option E — automatic semantic dedup of overlapping capabilities

An LLM decides which of two similar `read_file` tools to expose. Pros: less
noise with no user effort. Cons: brittle (name vs description vs schema),
costs a model call per list, and the user cannot predict which tool survives.
Lost: an explicit per-capability toggle is the right control.

## Decision

The database stores only the user's per-capability preference and when the
capability was first and last seen. Capability lists are always queried from
the upstream, cached in memory per session (and in one process-wide instance
for management routes) for 60 seconds, invalidated by TTL, `list_changed`,
explicit refresh and recovery. Newly seen capabilities are enabled by default;
vanished ones keep their row.

## Consequences

- An upstream upgrade that changes a schema needs no migration; the next list
  reflects it.
- The discovery path heals a stale reused connection the same way the call
  path does: a failed `list_*` — other than `METHOD_NOT_FOUND`, a legitimate
  "no such capability", or a timeout — evicts the connection and retries once
  on a fresh one, and a failing retry surfaces as `UPSTREAM_UNAVAILABLE` (503)
  rather than a 500. Before that, a connection that had died idle kept serving
  empty lists to the management page until the daemon restarted.
- The capability tabs must distinguish "could not load" from "the upstream
  offers nothing".
- Preference rows are keyed on the local `resources.id`; what converges
  between machines is each server's disabled set, exported as a shared state
  area keyed by the server's uid (`application/mcp/sync_state.py`).
- Pruning preferences for permanently vanished capabilities is left undone;
  the volume is small for one user.
