# Persistence

::: tip Core anchor
All Coffer state lives on the user's machine. The daemon is the single writer. Everything needed to restore a working installation — database, daemon config, logs, upstream state — sits under one directory: `~/.coffer/`.
:::

## The problem this solves

Coffer is a local-first developer tool: the user's accumulated AI assets — registered MCP servers, capability preferences, audit history, knowledge, chat conversations, channels, and sync state — must never depend on a cloud service to be readable or writable. That constraint demands a persistence layer that is self-contained, zero-configuration, and trivially backed up.

The answer is two layers. A single SQLite file at `~/.coffer/coffer.db` is the system of record for all control-plane state. Bulk user content — the knowledge agents and the user write, and documents ingested to markdown — lives as plain files under `~/.coffer/knowledge/`, and the files are the whole of it: no table in `coffer.db` mirrors them and no index sits over them. There is no separate database server to install, no connection pool to tune, no network hop between the daemon and its storage. The user's data is their file.

## Why SQLite, not Postgres

The rejected alternative — a server database like Postgres or MySQL — would require the user to install and manage a database process, configure credentials, and keep a service running. For a single-user local tool, that overhead is pure friction with no benefit.

::: tip Principles invariant
Coffer's principles designate SQLite as the system of record for control-plane state. Bulk user content is stored as files on the local filesystem. Migrating the control plane to a server database requires an amendment to the principles.
:::

The practical consequences of the SQLite choice shape every detail of the persistence layer:

- **Single writer** — SQLite's write concurrency is bounded; having one writer (the daemon) eliminates all write conflicts by design. The daemon serialises every mutation; surfaces that need to write (CLI commands, HTTP handlers) go through the daemon over loopback HTTP.
- **WAL mode** — Write-Ahead Logging allows readers (e.g., a CLI `list` command calling the REST API) to proceed concurrently with the writer without blocking on a lock. In practice this means `coffer mcp list` never hangs waiting for an ongoing migration.
- **Zero-infra copy** — because all Coffer state lives under `~/.coffer/`, moving or duplicating a vault needs no tooling: `cp -r ~/.coffer/ <dest>` with the daemon stopped is a complete byte-copy. Keeping two of your own machines in step is a separate mechanism — bidirectional convergence with a git remote you own — and it is off until you configure one. Coffer ships no backup command of its own; keep `master.key` out of anything copied off-machine.

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

Schema evolution is managed by Alembic, configured in `backend/alembic.ini` with a single migration history under `backend/coffer/infrastructure/persistence/migrations/`. Revisions accumulate as successive specs land — each spec that needs new tables adds one rather than editing an existing one, and the count only goes up, so the authoritative answer to "how many, and what is head" is `ls` on that directory, not a number written here (at the time of writing: eighty-two, head `0082`). The first three set up the MCP control plane:

| Revision | File                                 | Creates                                         |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0001`   | `20260520_0001_initial.py`           | `resources`, `audit_log`, `retention_policies`  |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`, `mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

Later revisions add the skill, chat, channel, credentials and sync tables (plus index and data-fix revisions), and several are pure subtractions. `20260912_0066_knowledge_is_plain_files.py` drops every table the knowledge layer ever had, replacing none of them; `0078` drops `memory_overrides` when the per-fact decisions it backed were removed from the surface; and `0055`, `0069` and `0077` each purge the rows of a retired audit event type, on the argument that an event nothing can label costs more in `coffer__diagnose` than the record is worth. On first daemon startup, `alembic upgrade head` runs before the HTTP server accepts connections. Because Alembic migrations are bundled as data files inside the PyInstaller daemon binary, end-user installs also get correct schema creation on first launch — no separate migration step.

::: tip The database is copied before it is migrated
Before `alembic upgrade head` changes an on-disk `coffer.db`, the daemon copies it — with any `-wal` / `-shm` companions — to `coffer.db.pre-<revision>`, keeping the three newest copies. An already-current schema is not copied, and neither is an in-memory database. See [Distribution](/architecture/distribution#binary-deployment-at-frozen-start).
:::

## Table map

The tables that exist after applying all revisions, grouped by domain:

**Core (kind-agnostic):**

| Table                | Purpose                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `resources`          | Kind-agnostic registry of every user-managed resource. One row per registered MCP server (or any future kind). Carries `kind`, `name`, `config_json`, `enabled` flag, and timestamps. |
| `audit_log`          | Append-only history of every lifecycle change to any resource or capability. Records event type, actor, resource ref, timestamp, and a structured JSON payload.                       |
| `retention_policies` | One row per prunable table, recording the configured retention window (days or forever) and the last-prune metadata.                                                                  |
| `internal_engine_config` | A single row: the connection and model Coffer's own unattended passes run on, plus each pass's switch and interval.                                                               |

**MCP gateway:**

| Table                        | Purpose                                                                                                                                                                             |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_capability_preferences` | Persists the user's per-capability enable/disable decisions for each registered MCP server. Survives upstream restarts and schema changes. FK-cascades on resource delete.          |
| `mcp_invocations`            | Time-series log of every tool, resource, and prompt call through the gateway: server name, capability key, duration, status, session ID. Never stores arguments or return contents. |
| `mcp_server_health`          | Last-known health status (`healthy` / `failing` / `unknown`) for each registered MCP server, written at each health check.                                                          |

**Credentials:**

| Table              | Purpose                                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `credentials`      | Envelope-encrypted secret store: each secret is Fernet-encrypted under a master key before it reaches SQLite. Plaintext never lands on disk. See [Security](/architecture/security) and Envelope-Encrypted Credentials. |

**Knowledge:** no tables. A knowledge collection is a row in the kind-agnostic `resources` table like every other Resource, and its content is the markdown files under `~/.coffer/knowledge/<collection>/`. Nothing about those files is mirrored into SQLite — not their titles, not their text, not a digest of them.

**Chat:**

| Table           | Purpose                                                                       |
| --------------- | ---------------------------------------------------------------------------- |
| `conversations` | One row per chat conversation, including archive/retention timestamps.        |
| `chat_messages` | The messages in each conversation. Cascade-deleted with their conversation.   |

**Channel:**

| Table                           | Purpose                                                              |
| ------------------------------- | ------------------------------------------------------------------- |
| `channel_peers`                 | Paired notification channel peers (e.g. Telegram / SeaTalk).         |
| `channel_thread_conversations`  | Which Coffer conversation a given IM thread is currently bound to.   |

**Skill:**

| Table                  | Purpose                                                       |
| ---------------------- | ------------------------------------------------------------ |
| `skill_agent_bindings` | Records which skills are bound to which agent workspaces.     |

**Sync:**

| Table                    | Purpose                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| `sync_remotes`           | The configured git remote and its worktree path (default `~/.coffer/sync`). Off until set.  |
| `sync_runs`           | One row per converge round, with its outcome. Prunable — 90 days by default.                 |
| `sync_convergence_state` | The last state this vault provably held, which the next diff is applied against.            |
| `sync_held_paths`        | Paths a round stopped on rather than applying — an oversized deletion waits to be confirmed. |

**Memory:** no tables. A memory partition is a `resources` row, and its facts are files under `~/.coffer/memory/`, derived from the agents' own native memory. `memory_overrides` — the one non-derived thing the kind ever stored — was dropped in revision `0078` along with the per-fact decisions it backed.

## Knowledge is plain files

The control-plane tables above are the system of record for their rows. **Knowledge has no such row.** The markdown files under `~/.coffer/knowledge/` are not a projection of anything and are not projected into anything — they are the knowledge layer, whole.

That is what removes the dual-source-of-truth problem outright rather than managing it. There is nothing to keep level with the disk, so a file the user edited in their editor, an agent wrote, or `git` pulled is readable and searchable the instant it lands. Search is `ripgrep` over those files, which matches bytes and therefore needs no tokenizer and no import step. Backup is one directory tree, and there is no corruption to recover from: titles and descriptions are read out of each file's own frontmatter, because there is nowhere else they could come from.

## Cascade and integrity rules

The schema enforces several invariants that the application layer alone cannot express:

- Deleting a resource cascades to `mcp_capability_preferences` (via `ON DELETE CASCADE`). It does **not** cascade to `audit_log` or `mcp_invocations` — history is preserved even after a server is deleted.
- `kind` and `name` are immutable once written. The application layer never issues `UPDATE resources SET kind=?` or `UPDATE resources SET name=?`. Renaming means delete + re-register.
- `retention_policies` rows are upserted at daemon startup; they are never deleted. The application layer treats them as always-present configuration.

## Everything under `~/.coffer/`

The full set of files Coffer writes:

| Path                          | Contents                                               |
| ----------------------------- | ------------------------------------------------------ |
| `~/.coffer/coffer.db`         | SQLite database (WAL mode) — the system of record for control-plane state |
| `~/.coffer/daemon.json`       | Runtime state: daemon PID, port and bearer token (mode `0600`). Unlinked on exit. |
| `~/.coffer/daemon-config.json` | Configuration read before the database opens: the port (mode `0600`). Written only by `coffer daemon port`. |
| `~/.coffer/master.key`        | Credential-store master key (file-default; opt-in keychain). See [Security](/architecture/security). |
| `~/.coffer/machine-id`        | This machine's stable identity for sync                |
| `~/.coffer/knowledge/`        | One directory per collection of markdown files — the knowledge layer itself, one tree of documents each, plus a hidden `.inbox/` of new material waiting for curation to merge it |
| `~/.coffer/memory/`           | The facts aggregated out of each agent's own native memory, one directory per partition |
| `~/.coffer/skills/`           | The canonical master copy of every managed skill       |
| `~/.coffer/sync/`             | The git working tree the vault converges through (default; the remote's row can name another) |
| `~/.coffer/workspace/`        | The default working directory a chat turn runs in      |
| `~/.coffer/vendor/`           | SDKs Coffer deliberately does not bundle — the SeaTalk client library |
| `~/.coffer/channel-media/`    | Attachments in flight between an IM channel and an agent |
| `~/.coffer/cache/agent/`      | Derived, rebuildable agent data (transcript summaries) |
| `~/.coffer/state/`            | One-shot markers for things shown to the user exactly once |
| `~/.coffer/logs/`             | Structured JSON log files from `structlog`             |
| `~/.coffer/bin/`              | The four deployed binaries: one directory per version, with the public names as symlinks into the current one |
| `~/.coffer/upstream-pids/`    | Per-upstream subprocess PID files for session tracking |

Keeping everything under one parent directory makes backup simple, migration unambiguous, and clean-uninstall complete. The daemon's detect-or-spawn protocol (Detect-or-Spawn) also benefits: every process that needs to find the daemon reads `~/.coffer/daemon.json` — there is no registry, no environment variable, and no platform-specific service directory to probe.

## Retention defaults

The `RetentionService.initialize_defaults()` call at daemon startup seeds the `retention_policies` table if rows are absent. The seeds are defined at the composition root, not in migrations, so new prunable tables introduced by later specs can register their own defaults without a new migration revision:

| Policy                  | Action                                          | Default retention |
| ----------------------- | ----------------------------------------------- | ----------------- |
| `audit_log`             | Delete rows older than the window               | 365 days          |
| `mcp_invocations`       | Delete rows older than the window               | 30 days           |
| `sync_runs`             | Delete converge-round history older than the window | 90 days       |
| `conversations_archive` | Auto-archive chats idle for this many days      | 7 days            |
| `conversations`         | Delete archived chats this many days after archival (with their messages) | 30 days |

Conversations follow a two-stage lifecycle: idle threads are auto-archived, then archived threads are deleted later. Any policy can be changed by the user via `PATCH /api/v1/retention/{table_name}` or the equivalent CLI command; the change itself is audited.
