# Coffer Architecture

> Architectural snapshot of what is currently being built. The _why_ of each
> choice lives in `docs/decisions/ADR-*.md`. This file describes the system
> as scoped by the active specs in `roadmap.md`.

## Layering

```
surfaces  →  application  →  domain
                   ↓
            infrastructure
```

- `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs.
- `application/` may not import `surfaces/`.
- Enforced by `scripts/check_*.py` and importlinter contracts.

Cross-cutting modules (credentials, audit, retention, …) live under
`application/` or `infrastructure/` and are extracted only after the second
feature needs them. (Exception: the Resource framework itself is core domain,
not cross-cutting — see [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md).)

## Resource framework (kind-agnostic core)

Every user-managed entity in coffer is a **Resource** identified by
`<kind>:<name>`. The framework unifies:

- Identity (`kind`, `name`, stable `<kind>:<name>` string reference)
- Lifecycle (register / update / enable / disable / delete)
- Audit (every lifecycle change recorded with actor)
- Schema validation (per-kind Pydantic schema, kind-agnostic dispatch)

It does **not** unify invocation semantics. Each kind defines how its
capabilities are used; the framework only describes how a kind is registered,
described, and curated.

Currently registered kinds:

| Kind             | Spec                                                         | Description                                                                                                                                                           |
| ---------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)       | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs.                              |
| `agent`          | [004-agent-registry](../../specs/004-agent-registry/spec.md) | A registered coding agent (Claude Code, Cursor, Codex CLI, …). Carries the on-disk skill directory and the agent-specific config Coffer needs to drive sync.          |
| `skill`          | [005-skill-manager](../../specs/005-skill-manager/spec.md)   | A managed AgentSkills-format skill. Canonical copy lives under `~/.coffer/skills/<name>/`; per-agent visibility is delivered through `SyncEngine` link/copy bindings. |
| `knowledge_base` | [006-knowledge-base](../../specs/006-knowledge-base/spec.md) | A local RAG corpus. Documents under `~/.coffer/kb/<name>/raw/`, index under `index/`; LlamaIndex confined to the infrastructure adapter.                              |

## Code layout

Layer-first, with kind-specific subdirectories inside each layer. See
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).

```
backend/coffer/
├── domain/                       # kind-agnostic entities + kind protocol
│   ├── resource.py
│   ├── audit.py
│   └── mcp/                      # MCP-specific value objects
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; takes kinds dict
│   ├── audit_service.py
│   ├── retention_service.py
│   └── mcp/                      # MCP-specific application services
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # keychain adapter — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation
│   └── mcp/                      # subprocess, http upstream client
└── surfaces/
    ├── http/                     # FastAPI app + per-kind sub-routers
    ├── cli/                      # Typer app + per-kind subcommand groups
    └── shim/                     # coffer-mcp-shim entry
```

Composition root (`surfaces/http/app.py`, `surfaces/cli/main.py`) explicitly
wires each kind via a `KindModule` dataclass — no global registry, no import
side effects.

## Surfaces

| Surface                        | Process                | Role                                                                                                                       |
| ------------------------------ | ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| REST API                       | daemon                 | Management plane: `/api/v1/*`. Token + CORS authenticated.                                                                 |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                                            |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP.                                                                                           |
| Desktop                        | independent            | _(planned — see future UI spec)_ Embeds the Vite frontend; supervises daemon; system tray; close-to-tray; launch-at-login. |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon.                                                       |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<auto-port>`.
  Owns all state; single SQLite writer.
- **Desktop app** — GUI shell; spawns daemon on first need; never duplicates
  business logic.
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.

All three discover each other through `~/.coffer/daemon.json` (PID + port +
token, mode `0600`). See [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md).

## Persistence

- **SQLite** at `~/.coffer/coffer.db`, WAL mode, single writer.
- **SQLAlchemy 2.0 async** ORM; **Alembic** central migrations (all kinds
  register their ORM models against one metadata).
- JSON fields stored as `TEXT` validated by Pydantic at the application
  boundary.
- The database file plus daemon discovery file, logs, and per-upstream PID
  files all live under `~/.coffer/` for a single backup target.

## Cross-cutting concerns

| Concern       | Location                                                                                         | Notes                                                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Credentials   | `infrastructure/credentials/keyring_adapter.py`                                                  | Only file allowed to import `keyring`. Refs in config; materialized at upstream-spawn time; never persisted.                                                       |
| Audit         | `domain/audit.py` + `application/audit_service.py` + `audit_log` table                           | Every resource lifecycle change. Actor (cli / api / ui / system) required.                                                                                         |
| Retention     | `application/retention_service.py` + `retention_policies` table + asyncio worker                 | Each log-style table registers as a `PrunableTable`; central registry enforces SQL allowlist.                                                                      |
| Errors        | `domain/errors.py` + FastAPI global handlers                                                     | Uniform `{error: {code, message, details}}` envelope; `X-Coffer-Trace` header for correlation.                                                                     |
| Logging       | `structlog` JSON-per-line to `~/.coffer/logs/`                                                   | Per-request trace IDs via contextvar.                                                                                                                              |
| Observability | `application/observability/` (`Tracer` port) + `infrastructure/observability/langfuse_tracer.py` | Default tracer is a no-op; LangFuse adapter activates lazily when `LANGFUSE_PUBLIC_KEY` is set. Extracted in spec 006; second consumer is anticipated in spec 007. |

## Distribution

End users install one bundle and get a working daemon, shim, and desktop app
without needing system Python. Achieved via PyInstaller (daemon + shim →
binaries) packaged as Tauri sidecars. Cross-platform CI matrix produces macOS
universal, Windows x64, and Linux x64+arm64 builds. See
[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md).

## What lives where (reading guide)

| If you want to know…                   | Read                                             |
| -------------------------------------- | ------------------------------------------------ |
| What invariants the project must keep  | `.specify/memory/constitution.md`                |
| What is being built right now          | `.specify/memory/roadmap.md`                     |
| What a feature promises to users       | `specs/<NNN>-<name>/spec.md`                     |
| Why a particular architectural choice  | `docs/decisions/ADR-*.md`                        |
| How code is laid out today             | This file                                        |
| How a specific feature works in detail | `specs/<NNN>-<name>/plan.md` and `data-model.md` |
