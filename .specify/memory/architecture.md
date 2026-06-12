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

The import rules and the "extract cross-cutting modules only after the second
feature needs them" rule are invariants owned by
[`constitution.md`](./constitution.md); the rationale for the layer-first code
layout is in [ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).
Enforced by `scripts/check_*.py` and importlinter contracts.

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

| Kind         | Spec                                                          | Description                                                                                                                              |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server` | [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)       | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs. |
| `agent`      | [004-agent-registry](../../specs/004-agent-registry/spec.md) | A registered coding agent (e.g. Claude Code). Carries its config directory and the Coffer-MCP install state. The workspace amendment also surfaces the agent's own files as facets — MCP entries (remove/toggle/adopt into Coffer), plugins (toggle/Codex-uninstall), and directory config entries with per-child edit — all derived at read time, never stored. |
| `skill`      | [005-skill-manager](../../specs/005-skill-manager/spec.md)   | A master skill bundle Coffer can deliver into one or more agents' skill directories. The workspace amendment adds an unmanaged-skill scan (adopt hand-placed skills into the master store) and a per-agent follow-master-library policy (flag + exclusions on the agent's config) that the sync engine reconciles. |

## Code layout

Layer-first, with kind-specific subdirectories inside each layer. See
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).

```
backend/coffer/
├── domain/                       # kind-agnostic entities + kind protocol
│   ├── resource.py               # Resource, Kind, ResourceRef
│   ├── kind_module.py            # KindModule composition-root carrier
│   ├── audit.py
│   ├── mcp/                      # MCP-specific value objects
│   ├── agent/                   # agent-specific value objects (config, etc.)
│   └── skill/                   # skill-specific value objects
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; takes kinds dict
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── mcp/                      # MCP-specific application services
│   ├── agent/                   # agent services + make_agent_kind
│   ├── skill/                   # skill services + make_skill_kind
│   └── fs/                      # filesystem-browse service
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # keychain adapter — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation
│   ├── mcp/                      # subprocess, http upstream client
│   ├── agent/                   # agent config-file store
│   └── skill/                   # master store, source fetcher, sync engine
└── surfaces/
    ├── http/                     # FastAPI app + per-kind sub-routers (incl. agent/skill/fs routes)
    ├── cli/                      # Typer app + per-kind subcommand groups
    └── shim/                     # coffer-mcp-shim entry
```

Composition root (`surfaces/http/app.py`, `surfaces/cli/main.py`) explicitly
wires each kind — no global registry, no import side effects. Each kind's
`make_*_kind()` factory (e.g. `make_mcp_kind`, `make_agent_kind`,
`make_skill_kind`) returns a frozen `Kind` (`domain/resource.py`), and the
composition root populates the per-app `app.state.kinds` dict
(`kind_name → Kind`) directly: `app_mcp_composition.py` sets `"mcp_server"`,
and `agent_skill_wiring.py` sets `"agent"` and `"skill"`. `ResourceService`
reads that dict for kind-agnostic dispatch. The surface-layer artefacts a kind
contributes (HTTP routers, Typer groups) are carried by the `KindModule`
dataclass (`domain/kind_module.py`), which references them via `Any`-typed
fields so the domain layer never imports them.

FastAPI dependency providers (`surfaces/http/dependencies.py`) are plain
module-level `set_*` / `get_*` pairs over module-global singletons — the
composition root calls each `set_*` once at startup; the matching `get_*` is
the `Depends()` target and raises if accessed before initialisation. Kind-
specific services are typed `Any` there to keep the kind-agnostic core from
importing kind modules (Contract 6).

## Surfaces

| Surface                        | Process                | Role                                                                                                                       |
| ------------------------------ | ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| REST API                       | daemon                 | Management plane: `/api/v1/*`. Token + CORS authenticated.                                                                 |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                                            |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP.                                                                                           |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon.                                                       |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<auto-port>`.
  Owns all state; single SQLite writer.
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.

Both discover the daemon through `~/.coffer/daemon.json` (PID + port +
token, mode `0600`). See [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md).

## Persistence

- **SQLite** at `~/.coffer/coffer.db`, WAL mode, single writer.
- **SQLAlchemy 2.0 async** ORM; **Alembic** central migrations (all kinds
  register their ORM models against one metadata). Migrations run on daemon
  startup (`upgrade head`); if the DB's current revision is unknown to the
  running build (created by a newer/divergent version), startup fails fast
  with `DB_SCHEMA_TOO_NEW` instead of an opaque Alembic error.
- JSON fields stored as `TEXT` validated by Pydantic at the application
  boundary.
- The database file plus daemon discovery file, logs, and per-upstream PID
  files all live under `~/.coffer/` for a single backup target.

## Cross-cutting concerns

| Concern     | Location                                                                         | Notes                                                                                                        |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Credentials | `infrastructure/credentials/keyring_adapter.py`                                  | Only file allowed to import `keyring`. The **daemon is the sole keychain owner**: every surface (desktop, CLI, shim) reaches the keychain through the daemon's `/api/v1/keychain` routes — the CLI never accesses it in-process (spec 006). Refs in config; materialized at upstream-spawn time; never persisted. |
| Audit       | `domain/audit.py` + `application/audit_service.py` + `audit_log` table           | Every resource lifecycle change. Actor (cli / api / ui / system) required.                                   |
| Retention   | `application/retention_service.py` + `retention_policies` table + asyncio worker | Each log-style table registers as a `PrunableTable`; central registry enforces SQL allowlist.                |
| Errors      | `domain/errors.py` + FastAPI global handlers                                     | Uniform `{error: {code, message, details}}` envelope; `X-Coffer-Trace` header for correlation.               |
| Logging     | `structlog` JSON-per-line to `~/.coffer/logs/`                                   | Per-request trace IDs via contextvar.                                                                        |
