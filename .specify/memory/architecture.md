# Coffer Architecture

> A bird's-eye view of how Coffer's pieces fit together. Spec-level detail
> lives in `specs/`. This document is the "where do things go" reference.

## Surface Inventory

Coffer is a single process on the user's machine that talks to other AI tools through several surfaces:

```
                            ┌──────────────────────────┐
                            │   coding agent           │
                            │   (Claude Code, Codex)   │
                            └────────────┬─────────────┘
                                         │ stdio (MCP)
                                         ▼
                            ┌──────────────────────────┐
                            │   coffer mcp             │  ← thin stdio shim
                            │   (Python subprocess)    │     (one per agent)
                            └────────────┬─────────────┘
                                         │ HTTP (loopback)
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
   ┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
   │  Web Workbench   │──────▶│  Coffer Daemon   │       │   Coffer CLI     │
   │  (Vite / React)  │ HTTP  │  (FastAPI :8000) │ HTTP  │  (Python)        │
   └──────────────────┘       └────────┬─────────┘       └──────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
  ┌────────────┐               ┌────────────────┐             ┌─────────────────┐
  │  SQLite    │               │  OS Keychain   │             │  upstream MCP   │
  │ (control   │               │  (credentials  │             │  servers (each  │
  │  state)    │               │  via keyring)  │             │  a subprocess)  │
  └────────────┘               └────────────────┘             └─────────────────┘
                                                                       │
                                                                       ▼
                                                          ┌────────────────────┐
                                                          │  filesystem        │
                                                          │  Memorys (folders) │
                                                          └────────────────────┘
```

## Process Roles

| Process | Lifetime | Role |
|---|---|---|
| **Coffer Daemon** | long-running (user's session) | FastAPI HTTP server; owns SQLite + keychain + upstream MCP subprocess lifecycle; serves the Web Workbench + handles MCP-over-HTTP from the shim. |
| **Coffer Web Workbench** | runs in browser (or Electron later) | React UI for CRUD'ing all resources. |
| **`coffer mcp` shim** | spawned by each coding agent | MCP stdio ⇄ MCP-over-HTTP translator. Stateless. Forwards every JSON-RPC message to the daemon and returns the response. |
| **`coffer` CLI** | per-invocation | Talks to the daemon over HTTP for inspection / scripting. |
| **upstream MCP servers** | child processes of the daemon | Each registered MCP server is a daemon-managed subprocess (stdio); the daemon proxies tool calls to the right one. |

## Layered Code Organization (backend)

```
backend/coffer/
├── surfaces/
│   ├── http/         ← FastAPI routes + Pydantic response models (for Web + CLI + shim)
│   ├── mcp/          ← MCP server endpoint (HTTP transport) + client adapter for upstream
│   └── cli/          ← coffer CLI entry points
├── application/
│   ├── <feature>/    ← commands + queries per feature spec (e.g., mcp_servers/)
│   ├── ports/        ← interfaces consumed across the app (no implementations)
│   ├── approval/     ← shared approval coordinator (cross-cutting domain)
│   ├── risk/         ← shared risk classifier (cross-cutting domain)
│   └── executor/     ← shared executor dispatcher (cross-cutting domain)
├── domain/
│   └── <entity>/     ← pure entities + value objects + domain services (no I/O)
└── infrastructure/
    ├── sqlite/       ← SQLite adapters
    ├── keyring/      ← OS keychain wrapper (only place that imports `keyring`)
    ├── subprocess/   ← upstream MCP subprocess manager
    └── http/         ← outbound HTTP client (SSRF-guarded)
```

**Import direction is one-way**: surfaces → application → domain ; infrastructure adapts to ports defined in application. `domain/` is pure.

## Data Locations

| What | Where | Why |
|---|---|---|
| Control state (agents, chats, channels, mcp_servers registrations, audit log, job queue, session state) | SQLite at `~/.coffer/coffer.db` | Single-user; SQLite is plenty |
| Credentials (API keys, env-var secrets) | OS keychain (macOS Keychain / Windows Credential Vault / Linux Secret Service) via `keyring`; SQLite stores opaque refs only | Local-first; never plaintext at rest in user-readable files |
| Memorys (user/agent content) | Filesystem under `~/.coffer/memorys/<name>/` | A Memory is a folder of files; agents and users read/write them through normal filesystem paths |
| Indexes (optional, on-demand) | SQLite (FTS5 / sqlite-vec) | When a Memory grows large enough, the daemon builds a derivative index keyed off the folder; index files are at `~/.coffer/index/...` and can be deleted/rebuilt |

## Network Defaults

- The daemon binds to `127.0.0.1:8000` only. No 0.0.0.0 binding without an explicit constitutional amendment.
- Channel webhooks (when added later) run as a **separate** process, only accepting requests on signed callback paths.
- Outbound HTTP uses a SSRF-guarded client.

## Cross-Cutting Domain Logic (Application Services)

These live in `application/` as shared modules every feature uses; they do not get their own spec:

| Service | What it does |
|---|---|
| **Risk classifier** | Maps an action (CLI invocation, MCP tool call, Memory write, external HTTP call) to a class: `read` / `write` / `destructive`. |
| **Approval coordinator** | For `write` / `destructive` actions, holds the action and asks the user (UI banner / channel ack / CLI prompt) before letting it through. State is durable + idempotent + audited. |
| **Executor dispatcher** | Given a resolved CLI / MCP / Skill invocation request, routes to the right adapter and emits structured audit events. |

Each feature that uses any of these documents *how* it uses them in its own `spec.md` (e.g., 001-mcp-servers' spec says "registering an MCP server is `write`, calling `tools/list` is `read`, calling a tool from upstream MCP follows that upstream tool's own risk class"). Approval state is persisted via the shared audit log module.

## Frontend Architecture (sketch)

```
frontend/src/
├── pages/            ← one component per route
├── components/       ← reusable components
│   └── ui/           ← shadcn/ui copies (style: default, slate base)
├── hooks/            ← custom hooks (use*)
├── lib/              ← cn() + fetch helpers + zod schemas
├── api/              ← TanStack Query hooks + fetch functions, one file per feature
└── types/            ← TS types (hand-written or generated later from OpenAPI)
```

Forms use `react-hook-form` + `zod`. Server state uses `TanStack Query`. UI state is local `useState` unless a spec explicitly needs cross-component sharing.

## Open Architectural Questions (to be answered as specs land)

- **MCP-over-HTTP transport details**: which path under `/mcp/...` does the daemon expose? How does the shim authenticate to the daemon (loopback so probably none, but documenting explicitly)?
- **Memory indexing trigger**: on every write, every N writes, manual rebuild, or daemon-managed background?
- **Approval UX**: blocking modal in Web Workbench? Toast + queue? Both? CLI-only fallback when no Web open?
- **Channel webhook process supervision**: how does the daemon start/stop the channel webhook helper process?

These are answered per spec; this document tracks them only so they don't get forgotten.
