# Persistence

::: tip Core anchor
All Coffer state lives on the user's machine. The daemon is the single writer. Everything needed to restore a working installation — database, daemon config, logs, upstream state — sits under one directory: `~/.coffer/`.
:::

## The problem this solves

Coffer is a local-first developer tool: the user's accumulated AI assets — registered MCP servers, capability preferences, audit history, knowledge bases, memory, chat conversations, channels, and sync state — must never depend on a cloud service to be readable or writable. That constraint demands a persistence layer that is self-contained, zero-configuration, and trivially backed up.

The answer is two layers. A single SQLite file at `~/.coffer/coffer.db` is the system of record for all control-plane state. Bulk user content — knowledge-base documents and memory facts — lives as markdown files on the local filesystem (the source of truth); SQLite carries a rebuildable retrieval index over it (ADR-012). There is no separate database server to install, no connection pool to tune, no network hop between the daemon and its storage. The user's data is their file.

## Why SQLite, not Postgres

The rejected alternative — a server database like Postgres or MySQL — would require the user to install and manage a database process, configure credentials, and keep a service running. For a single-user local tool, that overhead is pure friction with no benefit.

::: tip Constitutional invariant
The constitution designates SQLite as the system of record for control-plane state. Bulk user content (when introduced by later specs) is stored as files on the local filesystem, indexed on demand. Migrating the control plane to a server database requires a constitutional amendment.
:::

The practical consequences of the SQLite choice shape every detail of the persistence layer:

- **Single writer** — SQLite's write concurrency is bounded; having one writer (the daemon) eliminates all write conflicts by design. The daemon serialises every mutation; surfaces that need to write (CLI commands, HTTP handlers) go through the daemon over loopback HTTP.
- **WAL mode** — Write-Ahead Logging allows readers (e.g., a CLI `list` command calling the REST API) to proceed concurrently with the writer without blocking on a lock. In practice this means `coffer mcp list` never hangs waiting for an ongoing migration.
- **Zero-infra backup** — because all Coffer state lives under `~/.coffer/`, the full vault can be captured as a single `.tar.gz` snapshot (db + `knowledge/`/`memory/`/`skills/` trees, master key excluded by default). Run `coffer backup <dest.tar.gz>` from the CLI, or trigger `POST /api/v1/vault/backup` from the HTTP surface; both write the archive to `~/.coffer/backups/`. Restore with `coffer restore <src.tar.gz>`.

## SQLAlchemy 2.0 async ORM

The data-access layer uses SQLAlchemy 2.0 in async mode (`AsyncSession`, `create_async_engine` backed by `aiosqlite`). This matches the FastAPI daemon's async I/O model: a request handler awaits a database query without blocking the event loop, keeping the daemon responsive to concurrent MCP client connections.

All ORM models across every resource kind — both kind-agnostic core tables and MCP-specific tables — are registered against a **single central `Base.metadata`** object. This is the architectural decision that makes Alembic migrations straightforward: there is one migration history, one `alembic upgrade head` command, and no coordination between per-kind migration trees.

The boundary between ORM and domain is explicit. Each ORM model provides:

- `to_domain() → <DomainEntity>` — converts the ORM row to a pure Python domain object (no SQLAlchemy state).
- `from_domain(entity) → <Model>` — creates an ORM instance from a domain object, ready to be added to the session.

Domain objects are plain Python dataclasses; they carry no SQLAlchemy instrumentation. Application services work exclusively with domain objects; ORM models are implementation details of the infrastructure layer.

## JSON fields and Pydantic validation

Kind-specific configuration is stored as a `TEXT` column (`config_json` in the `resources` table). SQLite has no native JSON type; storing arbitrary structured configuration as text is the simplest representation that SQLite can handle.

The trade-off is that the database cannot enforce structure on a `TEXT` column — a raw string `"garbage"` is as valid to SQLite as a well-formed JSON object. The guarantee comes from the application boundary: **Pydantic validates every `Resource.config` before it is written and after it is read**. The domain `Kind.config_schema` is a Pydantic `BaseModel` subclass; the application service runs `.model_validate()` on every incoming config dict and `.model_dump(mode="json")` before writing. Nothing unvalidated ever reaches SQLite, and nothing leaves SQLite without being re-validated by Pydantic.

::: warning Serialisation note
Pydantic fields that use types like `AnyUrl` or `datetime` must be serialised with `model_dump(mode="json")` before passing to `json.dumps()`. The default `model_dump()` keeps these as Python objects, which `json.dumps` rejects. This is an enforced convention, not an optional style choice.
:::

## Alembic migrations

Schema evolution is managed by Alembic, configured in `backend/alembic.ini` with a single migration history under `backend/coffer/infrastructure/persistence/migrations/`. Twenty revisions (`0001` through `0020`) have accumulated as successive specs landed — each spec that needs new tables adds a revision rather than editing an existing one. The first three set up the MCP control plane:

| Revision | File                                 | Creates                                         |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0001`   | `20260520_0001_initial.py`           | `resources`, `audit_log`, `retention_policies`  |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`, `mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

Later revisions add the skill, knowledge, memory, embedding-config, chat, channel, credentials, and sync tables (plus index and data-fix revisions), ending at `0020`. On first daemon startup, `alembic upgrade head` runs before the HTTP server accepts connections. Because Alembic migrations are bundled as data files inside the PyInstaller daemon binary, end-user installs also get correct schema creation on first launch — no separate migration step.

## Table map

The tables that exist after applying all revisions, grouped by domain:

**Core (kind-agnostic):**

| Table                | Purpose                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `resources`          | Kind-agnostic registry of every user-managed resource. One row per registered MCP server (or any future kind). Carries `kind`, `name`, `config_json`, `enabled` flag, and timestamps. |
| `audit_log`          | Append-only history of every lifecycle change to any resource or capability. Records event type, actor, resource ref, timestamp, and a structured JSON payload.                       |
| `retention_policies` | One row per prunable table, recording the configured retention window (days or forever) and the last-prune metadata.                                                                  |

**MCP gateway:**

| Table                        | Purpose                                                                                                                                                                             |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_capability_preferences` | Persists the user's per-capability enable/disable decisions for each registered MCP server. Survives upstream restarts and schema changes. FK-cascades on resource delete.          |
| `mcp_invocations`            | Time-series log of every tool, resource, and prompt call through the gateway: server name, capability key, duration, status, session ID. Never stores arguments or return contents. |
| `mcp_server_health`          | Last-known health status (`healthy` / `failing` / `unknown`) for each registered MCP server, written at each health check.                                                          |

**Credentials & embedding:**

| Table              | Purpose                                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `credentials`      | Envelope-encrypted secret store: each secret is Fernet-encrypted under a master key before it reaches SQLite. Plaintext never lands on disk. See [Security](/architecture/security) and ADR-015. |
| `embedding_config` | The active embedding provider/model configuration used by the retrieval index.                                                                                      |

**Knowledge substrate:**

| Table           | Purpose                                                                                                                            |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `documents`     | One row per knowledge-base / memory document, mirroring the markdown file on disk.                                               |
| `chunks`        | Per-document chunk rows that the retrieval pipeline produces from the markdown.                                                  |
| `documents_fts` | FTS5 virtual table backing keyword search over chunk text.                                                                       |
| _sqlite-vec_    | A per-store `vec0` virtual table (created lazily per store, named by kind + dimensions) holding chunk embeddings for vector search. |

**Memory:**

| Table                        | Purpose                                                                                        |
| ---------------------------- | ---------------------------------------------------------------------------------------------- |
| `memory_projection_bindings` | Records which agent/project a memory store is projected into.                                   |
| `memory_store_project_roots` | Maps memory project stores to their on-disk project roots.                                      |

**Chat:**

| Table           | Purpose                                                                       |
| --------------- | ---------------------------------------------------------------------------- |
| `conversations` | One row per chat conversation, including archive/retention timestamps.        |
| `chat_messages` | The messages in each conversation. Cascade-deleted with their conversation.   |
| `chat_models`   | User-configured chat model definitions.                                       |

**Channel:**

| Table           | Purpose                                                              |
| --------------- | ------------------------------------------------------------------- |
| `channel_peers` | Paired notification channel peers (e.g. Telegram / SeaTalk).         |

**Skill:**

| Table                  | Purpose                                                       |
| ---------------------- | ------------------------------------------------------------ |
| `skill_agent_bindings` | Records which skills are bound to which agent workspaces.     |

**Sync:**

| Table         | Purpose                                                                |
| ------------- | --------------------------------------------------------------------- |
| `sync_config` | The user's multi-machine sync configuration (remote, branch, toggles). |
| `sync_state`  | Last-sync bookkeeping (commit refs, conflict state).                   |

## Files as truth, SQLite as a rebuildable index (ADR-012)

The control-plane tables above are the system of record for their rows. The **knowledge substrate** is different: the markdown files under `~/.coffer/knowledge/` and `~/.coffer/memory/` are the source of truth, and the SQLite retrieval index (the `documents` / `chunks` / `documents_fts` FTS5 tables plus the per-store sqlite-vec virtual tables) is a **fully rebuildable** projection of those files.

This kills the dual-source-of-truth problem: if the index is corrupted, lost, or schema-migrated, it is regenerated from the files. `coffer kb reindex` rebuilds it from the markdown on disk. Backup is one directory tree; corruption recovery is a reindex.

## Cascade and integrity rules

The schema enforces several invariants that the application layer alone cannot express:

- Deleting a resource cascades to `mcp_capability_preferences` (via `ON DELETE CASCADE`). It does **not** cascade to `audit_log` or `mcp_invocations` — history is preserved even after a server is deleted.
- `kind` and `name` are immutable once written. The application layer never issues `UPDATE resources SET kind=?` or `UPDATE resources SET name=?`. Renaming means delete + re-register.
- `retention_policies` rows are upserted at daemon startup; they are never deleted. The application layer treats them as always-present configuration.

## Everything under `~/.coffer/`

The full set of files Coffer writes:

| Path                       | Contents                                               |
| -------------------------- | ------------------------------------------------------ |
| `~/.coffer/coffer.db`      | SQLite database (WAL mode) — the system of record      |
| `~/.coffer/daemon.json`    | Daemon PID, port, and bearer token (mode `0600`)       |
| `~/.coffer/master.key`     | Credential-store master key (file-default; opt-in keychain). See [Security](/architecture/security). |
| `~/.coffer/knowledge/`     | Knowledge-base documents as markdown — source of truth indexed by SQLite |
| `~/.coffer/memory/`        | Memory facts as markdown — source of truth indexed by SQLite |
| `~/.coffer/sync/`          | Git working tree mirroring the file-backed trees for multi-machine sync |
| `~/.coffer/logs/`          | Structured JSON log files from `structlog`             |
| `~/.coffer/bin/`           | `coffer-mcp-shim` + `coffer-daemon` binaries deployed by the desktop app |
| `~/.coffer/backups/`       | Point-in-time SQLite backup copies                     |
| `~/.coffer/upstream-pids/` | Per-upstream subprocess PID files for session tracking |

Keeping everything under one parent directory makes backup simple, migration unambiguous, and clean-uninstall complete. The daemon's detect-or-spawn protocol (ADR-006) also benefits: every process that needs to find the daemon reads `~/.coffer/daemon.json` — there is no registry, no environment variable, and no platform-specific service directory to probe.

## Retention defaults

The `RetentionService.initialize_defaults()` call at daemon startup seeds the `retention_policies` table if rows are absent. The seeds are defined at the composition root, not in migrations, so new prunable tables introduced by later specs can register their own defaults without a new migration revision:

| Policy                  | Action                                          | Default retention |
| ----------------------- | ----------------------------------------------- | ----------------- |
| `audit_log`             | Delete rows older than the window               | 365 days          |
| `mcp_invocations`       | Delete rows older than the window               | 30 days           |
| `conversations_archive` | Auto-archive chats idle for this many days      | 7 days            |
| `conversations`         | Delete archived chats this many days after archival (with their messages) | 30 days |

Conversations follow a two-stage lifecycle: idle threads are auto-archived, then archived threads are deleted later. Any policy can be changed by the user via `PATCH /api/v1/retention/{table_name}` or the equivalent CLI command; the change itself is audited.

## See also

- [Data model reference](/reference/specs/001-mcp-gateway/data-model) — full DDL, ORM mapping table, cascade rules, and default seeds
- [Architecture reference](/reference/project/architecture) — persistence section and the full cross-cutting concerns table
