# Research — 001 MCP Gateway

Library choices, alternatives evaluated, and references for decisions that are
not architecturally significant enough for their own ADR. Architecturally
significant choices have their own ADR in `docs/decisions/`; this file
captures the layer below that — concrete dependencies, protocol details, and
build-time tooling decisions.

## Backend runtime dependencies (additions to `backend/pyproject.toml`)

| Add                   | Version                                 | Why this choice                                                                                                                                                                                                                                                                                                                                            |
| --------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sqlalchemy[asyncio]` | `>=2.0,<3.0`                            | Async ORM matches FastAPI's async story; SQLAlchemy 2.0 has cleaner typed declarative. Considered raw `sqlite3` + handwritten queries — rejected because four kinds × CRUD + retention + audit would be enough hand-written SQL to justify an ORM.                                                                                                         |
| `aiosqlite`           | `>=0.20`                                | Async SQLite driver SQLAlchemy uses under the hood for async sessions.                                                                                                                                                                                                                                                                                     |
| `alembic`             | `>=1.13`                                | Schema migrations. Considered code-managed schema (call `Base.metadata.create_all`) — rejected because the constitution requires schema evolution to be reviewed in PRs and reversible.                                                                                                                                                                    |
| `keyring`             | `>=25.0`                                | OS keychain access. Only `infrastructure/credentials/` imports this (Contract 4).                                                                                                                                                                                                                                                                          |
| `httpx`               | `>=0.27`                                | Already a dev dep; promote to runtime. Used for HTTP MCP upstreams and (in tests) the in-process FastAPI test client.                                                                                                                                                                                                                                      |
| `typer`               | `>=0.12`                                | CLI framework. Considered Click — Typer wraps Click and adds Pydantic-friendly type-hint-driven argument parsing, which matches the existing FastAPI/Pydantic code style.                                                                                                                                                                                  |
| `rich`                | `>=13.7`                                | CLI output rendering (Typer recommends it; tables + tree views needed by `coffer mcp list`).                                                                                                                                                                                                                                                               |
| `structlog`           | `>=24.1`                                | Structured JSON logging. Considered stdlib `logging` + a JSON formatter — rejected because structlog's contextvars integration is needed for the trace-id propagation required by FR-014.                                                                                                                                                                  |
| `mcp`                 | `>=1.0` (official Anthropic Python SDK) | Used for: (a) the test oracle in contract tests; (b) the framing helpers (`stdio_server`, `streamable_http_server`) coffer wraps. Considered handwriting the JSON-RPC framing — rejected because the SDK already implements protocol-level corner cases (cancellation, progress tokens, initialize negotiation) we'd otherwise re-discover.                |
| `psutil`              | `>=5.9`                                 | PID liveness + command-line verification for orphan subprocess cleanup ([ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)). Considered POSIX-only `os.kill(pid, 0)` — rejected because the orphan sweep needs to verify the process is actually a coffer-spawned MCP server, not an unrelated process that happens to have reused the PID. |

## Frontend additions (`frontend/package.json`)

| Add                                                              | Why                                                                                                                                    |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `@tanstack/react-query` `^5.x`                                   | Server-state cache + revalidation. Spec FR mentions polling for daemon status; TanStack Query handles this cleanly.                    |
| `react-router-dom` `^6.x`                                        | Routing. (`agents/stack.md` mentions TanStack Router OR React Router; pick React Router for now — more familiar to most contributors.) |
| `i18next` + `react-i18next` + `i18next-browser-languagedetector` | i18n per FR-020. Locales `en`, `zh`.                                                                                                   |
| `react-hook-form` + `@hookform/resolvers` + `zod`                | Per `agents/stack.md`. Used by ServerForm.                                                                                             |
| `openapi-typescript` `^7.x` (dev)                                | Generate TypeScript types from `contracts/api.openapi.yaml`.                                                                           |
| `openapi-fetch` `^0.x`                                           | Typed fetch wrapper.                                                                                                                   |
| `@tauri-apps/api` `^2.x`                                         | Frontend-side Tauri command invocation (already pulled transitively by Tauri 2 scaffolding, but list explicitly).                      |
| `@tauri-apps/plugin-shell` (only if needed)                      | Likely not for v0. Document in case install-shim-to-PATH needs it.                                                                     |

## MCP protocol — concrete forwarding decisions

These are pinned in [ADR-004](../../docs/decisions/ADR-004-capability-state-model.md) and [ADR-005](../../docs/decisions/ADR-005-session-subprocess-model.md); concrete protocol semantics are listed here so the implementation has a single reference point.

### Methods coffer forwards

| Direction         | Method                                                                                                                                           | Coffer behaviour                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| client → upstream | `initialize`                                                                                                                                     | Coffer responds itself (declares capabilities to the client). On first need it issues its own `initialize` to each upstream.                                    |
| client → upstream | `tools/list` `tools/call`                                                                                                                        | Forward through namespace transform (Section "Namespace transformation" below).                                                                                 |
| client → upstream | `resources/list` `resources/read` `resources/subscribe` `resources/unsubscribe`                                                                  | Forward through URI-prefix transform.                                                                                                                           |
| client → upstream | `prompts/list` `prompts/get`                                                                                                                     | Forward through namespace transform.                                                                                                                            |
| client → upstream | `roots/list` (request from upstream)                                                                                                             | Pass through to downstream client; relay response back.                                                                                                         |
| client → upstream | `sampling/createMessage` (request from upstream)                                                                                                 | Capability-negotiated. If downstream client declared `sampling` capability during initialize, forward; else respond with `method-not-found`.                    |
| upstream → client | `notifications/tools/list_changed` `notifications/resources/list_changed` `notifications/prompts/list_changed` `notifications/resources/updated` | Forward to downstream client; invalidate coffer's per-upstream cache.                                                                                           |
| upstream → client | `notifications/progress`                                                                                                                         | Pass through; preserve `progressToken`; reset the corresponding pending-request idle timer ([Streaming progress decision](#streaming-progress-decision) below). |
| upstream → client | `notifications/message` (server log)                                                                                                             | Drop (avoid flooding the downstream client; recorded to `~/.coffer/logs/upstream-<name>.log`).                                                                  |

### Namespace transformation

| Capability   | Wire form upstream uses | Wire form coffer presents downstream    |
| ------------ | ----------------------- | --------------------------------------- |
| Tool         | `<original_name>`       | `<server_name>__<original_name>`        |
| Prompt       | `<original_name>`       | `<server_name>__<original_name>`        |
| Resource URI | `<original_uri>`        | `coffer://<server_name>/<original_uri>` |

Tool / prompt separator is `__` (double underscore). Considered `:`, `.`, `/`, `-` — all of these collide with characters already legal in upstream tool names. `__` is the convention mcpjungle adopted; surveying the public MCP server registry shows zero tool names contain `__`.

### Streaming progress decision

Public MCP gateways (mcpjungle, metamcp, mcp-proxy) all preserve `progressToken` and reset their request timeout when progress arrives, but **none actively forward `notifications/progress` from upstream to downstream**. Verified against `mcpjungle/internal/service/mcp/tool.go` (progressToken preservation; no progress-forward) and `metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts` (`resetTimeoutOnProgress: true`; no progress-forward). Coffer matches the ecosystem:

- preserve incoming `_meta.progressToken` when forwarding `tools/call`
- when upstream sends `notifications/progress`, reset the per-request idle timer (so a long tool doesn't hit our 120s timeout)
- v0 does **not** forward those progress notifications downstream; documented as a non-goal in roadmap.md.

### Initialize handshake

Coffer plays both server (to downstream client) and client (to upstream servers). Two separate handshakes:

| Pair                        | Coffer's role | Capabilities coffer declares                                                                                             |
| --------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------ |
| downstream client ↔ coffer | server        | `tools`, `resources`, `prompts`. `logging` not declared. `sampling` conditional on downstream client's declared support. |
| coffer ↔ each upstream     | client        | `roots` (so upstream can ask), `sampling` (pass-through), `experimental: {}`                                             |

Protocol version: coffer declares the **highest version supported by its bundled `mcp` SDK** to both sides. Inter-version negotiation is handled by the SDK.

## SQLite configuration

PRAGMAs applied at every connection open:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;
```

Set via SQLAlchemy `event.listens_for(engine.sync_engine, "connect")` so they apply to every new connection (WAL mode is per-database but the rest are per-connection).

## Daemon discovery file format

`~/.coffer/daemon.json` (mode `0600`):

```json
{
  "version": 1,
  "pid": 12345,
  "port": 8001,
  "token": "<32-char URL-safe random>",
  "started_at": "2026-05-20T12:34:56Z",
  "binary_path": "/Applications/Coffer.app/Contents/.../coffer-daemon"
}
```

`version` allows future schema evolution. Clients tolerate unknown fields. Mismatched `version` → client re-reads after a respawn.

Discovery sequence (used by shim, CLI, Tauri):

1. Open `~/.coffer/daemon.json`; if missing → spawn flow.
2. Parse JSON; if invalid → backup file + spawn flow.
3. Check `pid` liveness via `psutil.pid_exists`; if dead → spawn flow.
4. Verify `psutil.Process(pid).name()` contains `coffer-daemon`; if not → spawn flow (PID has been recycled).
5. Open a TCP connection to `127.0.0.1:port`; if refused → spawn flow.
6. Otherwise: connected.

Spawn flow uses `flock` on `~/.coffer/daemon.lock` to serialise concurrent detect-or-spawn races.

## Port allocation

Range: `8000`–`8009`. Tried in order; first free wins. If all 10 are taken, daemon refuses to start with a clear error message and exits non-zero. Range chosen because it's small (operational hygiene), close to the conventional default (`8000`), and outside the well-known ports range (≥1024).

## PyInstaller hidden imports (FastAPI + SQLAlchemy + Pydantic 2)

Empirically-required `--hidden-import` entries (from PyInstaller + FastAPI/SQLAlchemy issue trackers; pinned here so future maintainers don't re-discover):

```
sqlalchemy.dialects.sqlite
sqlalchemy.dialects.sqlite.aiosqlite
aiosqlite
pydantic.deprecated.decorator
pydantic._internal._core_metadata
pydantic._internal._validators
pydantic_core
mcp
mcp.server
mcp.server.stdio
mcp.server.streamable_http
mcp.client
mcp.client.stdio
mcp.client.streamable_http
keyring.backends
```

OS-conditional:

- macOS: `keyring.backends.macOS`
- Windows: `keyring.backends.Windows`
- Linux: `keyring.backends.SecretService`

These live in `backend/packaging/daemon.spec` and `backend/packaging/shim.spec`.

## Test fixtures

### `fake_mcp_server.py`

A real MCP server implemented with the official `mcp` SDK, parameterised by CLI flags:

```bash
python -m coffer.tests.fixtures.fake_mcp_server \
  --scenario basic \
  --tools read_file write_file \
  --resources file:///tmp/example.txt \
  --crash-after-calls 0 \
  --init-delay-ms 0 \
  --notify-list-changed-after 0
```

| Scenario   | Behaviour                                                                                                                            |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `basic`    | Returns the configured tools/resources/prompts; echoes call args.                                                                    |
| `slow`     | Adds `--init-delay-ms` before responding to `initialize`.                                                                            |
| `crash`    | Exits after `--crash-after-calls` tool calls.                                                                                        |
| `mutating` | Sends `notifications/tools/list_changed` after `--notify-list-changed-after` calls; subsequent `tools/list` returns a different set. |

Lives at `backend/tests/fixtures/fake_mcp_server.py`. Importable from integration tests via a pytest fixture that yields a `Popen`.

## CORS allowlist

| Origin                   | Purpose                          |
| ------------------------ | -------------------------------- |
| `tauri://localhost`      | Tauri windows on macOS / Windows |
| `http://tauri.localhost` | Tauri windows on Linux           |
| `http://localhost:5173`  | `make dev` Vite dev server       |
| `http://127.0.0.1:5173`  | Vite dev server addressed by IP  |

CORS headers set in FastAPI middleware. Plus `X-Coffer-Token` required on every request; CSRF surface is closed because (a) tokens are not in cookies (custom header), (b) origin is allowlisted.

## References

- [Model Context Protocol Specification 2025-06-18](https://spec.modelcontextprotocol.io/specification/2025-06-18/)
- [mcpjungle source](https://github.com/mcpjungle/MCPJungle) — token-passthrough oracle
- [metamcp source](https://github.com/metatool-ai/metamcp) — `resetTimeoutOnProgress` pattern
- [PyInstaller + FastAPI guide](https://fastapi.tiangolo.com/deployment/) — hidden-imports patterns
- [SQLite WAL documentation](https://www.sqlite.org/wal.html)
- [Tauri 2 sidecar guide](https://v2.tauri.app/develop/sidecar/)
- Coffer ADRs: `docs/decisions/ADR-001` through `ADR-007`.
