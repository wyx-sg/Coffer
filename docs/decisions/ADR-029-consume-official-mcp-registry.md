# ADR-029 — Consume the official MCP Registry for server discovery

> 中文版: [ADR-029-consume-official-mcp-registry.zh.md](./ADR-029-consume-official-mcp-registry.zh.md)

- **Status:** Reverted (2026-06-20) — see the revert note below
- **Date:** 2026-06-19
- **Deciders:** Yuxing Wu
- **Spec:** 001-mcp-gateway (spec.md updated before implementation)
- **Related:** [ADR-004](./ADR-004-capability-state-model.md) (list live-queried, not mirrored), [ADR-015](./ADR-015-envelope-encrypted-credential-store.md) (secrets become credential refs)

> **⚠️ Reverted 2026-06-20.** The online MCP-Registry browse/autofill (PR #114) was removed (simplification backlog 1.7): it only saved one paste and depended on an external preview API. Adding an MCP server is once again done via the **paste-JSON** path (the standard `mcpServers` config). The original decision below is kept as the historical record.

## Context

Adding an MCP server to Coffer today means hand-pasting `mcpServers` JSON — the
user has to already know the server's id, run command, arguments, and which
environment variables it needs. There is no discovery path.

The MCP-ecosystem survey (`docs/research/mcp-ecosystem.md`) flagged this as a
real gap: **Coffer has no catalog while the field has a rich registry layer**
(the official Registry plus downstream marketplaces like Smithery / Glama /
PulseMCP). The **official MCP Registry** (`https://registry.modelcontextprotocol.io`,
Anthropic + Linux Foundation) is an open, unauthenticated metadata API — the
root that the downstream marketplaces themselves scrape. It is explicitly **not**
a gateway, just a catalog, which is exactly the layer Coffer lacks.

Two constraints shape the design. First, the registry is a **preview** API: its
schema is not frozen and fields come and go — most notably `packages[].runtimeHint`
is often absent, so we cannot rely on it to know how to launch a server. Second,
Coffer is local-first: the frontend talks only to localhost, so the outbound
call cannot originate in the browser.

## Decision

Consume the official MCP Registry through a thin daemon-side proxy and autofill a
server config draft. Five moves.

1. **Daemon-side read-only proxy.** Add `GET /api/v1/mcp-registry/search?q=&limit=`.
   The daemon makes the outbound call to the registry; the frontend talks only to
   localhost. The response is a list of matching servers, each with an
   `installable` flag and an editable config `draft`.

2. **Infer the run command from `registryType`, not `runtimeHint`.** Because
   `runtimeHint` is often missing, the mapper derives the launch command from each
   package's `registryType`:

   | `registryType` | Inferred command         | Installable |
   | -------------- | ------------------------ | ----------- |
   | `npm`          | `npx -y <package>`       | yes         |
   | `pypi`         | `uvx <package>`          | yes         |
   | `oci`          | `docker run -i --rm <…>` | yes         |
   | `nuget`        | `dnx <package>`          | yes         |
   | `cargo`        | —                        | no          |
   | `mcpb`         | —                        | no          |

   `cargo` and `mcpb` packages are not auto-installable; those servers come back
   with `installable: false` and no runnable draft (the user can still hand-edit).

3. **Live query + short cache, no persistence.** Registry results are fetched
   live with only a short-TTL in-memory cache. Nothing about the registry is
   written to SQLite — no mirror, no new tables, no migration revision. Only a
   server the user actually adds lands in `resources`, via the normal
   registration path.

4. **Secrets via credential refs, never inline.** An `environmentVariables[]`
   entry flagged `isSecret` becomes a credential reference in the draft, never an
   inline value, so the autofill path inherits the [ADR-015](./ADR-015-envelope-encrypted-credential-store.md)
   guarantee that secret plaintext never lands in any persisted config.

5. **Graceful degradation.** When the registry is unreachable or times out, the
   endpoint returns a clear, non-fatal `502 REGISTRY_UNAVAILABLE`. Discovery is
   pure leverage on top of the existing flow — the hand-entered paste-JSON path
   stays fully usable when the registry is down.

## Alternatives considered

A — **Frontend calls the registry directly.** Have the browser fetch the registry
API itself and skip the daemon hop. **Rejected.** It breaks the local-first
contract (the frontend would make a cross-origin outbound call), is exposed to
CORS, and scatters the defensive parsing into the UI. The daemon is the right
place for outbound calls and for one tolerant mapper.

B — **Mirror the registry into SQLite.** Periodically sync the whole registry
into a local table and search that. **Rejected.** It adds a sync job, a schema,
and a staleness window for data that is already a fast live query, all to cache a
catalog the user touches occasionally. Live query + short in-memory cache is far
cheaper and never goes stale.

C — **Aggregate downstream marketplaces too** (Smithery / Glama / PulseMCP).
Query several catalogs and merge. **Rejected for now.** The official registry is
the root the others scrape; one open, unauthenticated source covers the need
without per-marketplace auth, rate limits, and divergent schemas. Revisit if a
marketplace exposes servers the root registry does not.

## Consequences

- **Closes the discovery gap.** Users can find and autofill a server by keyword
  instead of hand-pasting JSON they had to source elsewhere; the paste path stays
  as the fallback and the manual escape hatch.
- **The mapper must be defensive.** Because the registry is a **preview** API,
  absent or renamed fields are expected; the mapper tolerates missing
  `runtimeHint`, missing `title`/`version`/`homepage`, and unknown
  `registryType`s (treated as not-installable) rather than failing the search.
- **Preview-API risk.** The registry's schema may shift under us; a breaking
  change degrades discovery (worst case `installable: false` for everything) but
  never the paste-JSON path. The contract treats every field as optional.
- **No new persistence.** No tables, no migration, no mirror — registry results
  live only in memory for a short TTL, so there is nothing to back up, prune, or
  keep in sync.
- **Secrets stay safe by construction.** `isSecret` env vars flow into credential
  refs, so the new autofill surface cannot introduce inline-secret regressions.
