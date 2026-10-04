# MCP Capability State: Preferences in the Vault, Lists Live-Queried From Upstream

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [Session Subprocess Model](session-subprocess-model.md),
[Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md),
[Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md),
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

The only persisted capability state is the person's switches and this machine's
observation times (`infrastructure/mcp/persistence.py`). The switches are a
vault state document per server, `state/mcp-preferences/<server name>.json`,
holding `{server_uid, format_version, disabled: {capability_type: [key, …]}}`;
only switched-off capabilities are listed, and a server with nothing switched
off has no file. When this machine first and last saw each capability is an
observation it can make again, so those times are the `mcp_capability_seen`
table in `derived/derived.db`, never committed. Names, schemas and descriptions
are never persisted: `CapabilityDiscovery` (`application/mcp/discovery.py`) fetches
them from the upstream and caches each `(server, capability type)` slice in
memory for 60 seconds. Each gateway session builds its own
`CapabilityDiscovery` over its own supervisor
([Session Subprocess Model](session-subprocess-model.md)); a separate
process-wide instance over a process-wide supervisor serves the management
routes — the capability tabs and refresh — so the UI never borrows an agent's
session (`surfaces/http/app_mcp_composition.py`).

The cache slice is dropped on TTL expiry, on an upstream `list_changed`
notification (which is also forwarded to the downstream client), on an explicit
refresh (`coffer mcp test <name>` / `POST …/{uid}/refresh`), and when a
server that failed to list recovers. Every successful list reconciles
preferences in one batch: a newly seen key is recorded in `mcp_capability_seen`
and is enabled, which writes nothing into the vault; an existing key's
`last_seen_at` is touched; a key that disappeared is **not** deleted, so a
disable survives an upstream that briefly drops the tool. The switch document
is read fresh on every list, so a toggle takes effect immediately regardless of
the cache.

Pros: no stale-schema bugs and no migrations when an upstream changes a
tool's `inputSchema`; aligned with the protocol's dynamic model; user intent
survives upgrades because it is keyed on the name, and it travels between
machines because it is a vault file while the machine-specific observations
stay behind. Cons: with an upstream offline the UI can show only the names it
has preference or seen rows for, not schemas or descriptions; a cache miss
costs a round-trip per upstream; entries for capabilities that are gone for
good accumulate (bounded by what one user has ever seen).

### Option B — cache the full capability list in the database, refreshed periodically

A `mcp_capabilities` table (in `runs.db` or `derived.db`) with names, schemas, descriptions and flags; the UI
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
resource file under `config`. Pros: nothing to invalidate; one file per
server and no second document to keep alongside it. Cons: latency compounds with five or more upstreams and an agent
listing tools every turn; and folding the disabled set into config makes a
toggle a config write — re-validated, audited as a config change and
reconciled as one — while a capability that disappears and returns has no
first/last-seen record to show. Lost on both counts; the 60-second cache
captures the common case.

### Option F — preferences as rows in a database table

A `mcp_capability_preferences` table with `(server, capability type,
capability key, enabled, first_seen_at, last_seen_at)`, one row per capability
ever seen. This is the design the vault document replaced. Pros: one place for
the switch and the seen-times; a toggle is one row update. Cons: the table is
local to a machine, so a switch made on one machine does not reach another, and
a database row cannot be diffed, restored or hand-edited the way a vault file
can; it also mixes a person's intent (which should travel) with an observation
(which should not) in one row. Lost: the switch is the part worth keeping, and
it belongs where the rest of a person's configuration is.

### Option E — automatic semantic dedup of overlapping capabilities

An LLM decides which of two similar `read_file` tools to expose. Pros: less
noise with no user effort. Cons: brittle (name vs description vs schema),
costs a model call per list, and the user cannot predict which tool survives.
Lost: an explicit per-capability toggle is the right control.

## Decision

The vault stores only the user's per-capability switches
(`state/mcp-preferences/<server name>.json`, disabled capabilities only), and
`derived/derived.db` stores when this machine first and last saw each
capability (`mcp_capability_seen`). Capability lists are always queried from
the upstream, cached in memory per session (and in one process-wide instance
for management routes) for 60 seconds, invalidated by TTL, `list_changed`,
explicit refresh and recovery. Newly seen capabilities are enabled by default;
vanished ones keep their switch and their seen row.

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
- The switch document is keyed on the server's `uid`; the file name only
  follows the server's name. Because it is a vault file, each server's disabled
  set converges between machines through sync with no capability-specific code,
  and is committed, diffed and restorable like any other vault file. Seen-times
  are not synced: a capability switched off on another machine that this
  machine has never seen reads with seen-times at the epoch.
- Turning a server's last switched-off capability back on removes its document,
  and deleting the server deletes it in the same commit.
- Pruning seen rows and switches for permanently vanished capabilities is left
  undone; the volume is small for one user.
