# Control-Plane State Is One SQLite File, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Technology & architectural constraints — Persistence; Guarantees — Single SQLite writer), [The Resource Framework Is Core Domain](resource-framework-upfront.md), [Code Layout — Layer-First](code-layout-layer-first.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [Distribution — PyInstaller](distribution-pyinstaller.md), [Persistence](../../docs-site/architecture/persistence.md), spec daemon "Deploy frozen sibling binaries and back up the vault before migrating", PR #14, PR #48, PR #386

## Context

Coffer's control-plane state — resources, audit log, retention policies,
credentials ciphertext, MCP capability preferences and invocation log, chat
conversations, channel pairings, sync state — has to live on the user's
machine, need no installation beyond Coffer itself, survive upgrades of a
product that ships often, and be copyable as files. Bulk content (knowledge,
memory) is plain files and is not in the database at all
([Knowledge Is Plain Files](knowledge-is-plain-files.md)).

Forces on the choice:

- **One user, several processes.** The daemon, the CLI, the stdio shim and the
  desktop shell all run on one machine. Only one of them is long-lived.
- **Upgrades are unattended.** A release is installed by replacing binaries;
  the next daemon start is the first moment new code meets old data. There are
  103 revisions in the lineage today (head `0103`), many of them data rewrites
  of user rows rather than DDL.
- **Many kinds, one framework.** Kind-agnostic tables (`resources`,
  `audit_log`, …) are referenced by kind-owned ones (`skill_agent_bindings`,
  `channel_peers`, `mcp_capability_preferences`, …) through foreign keys with
  `ON DELETE CASCADE`.
- **Branches share a database.** Every checkout, worktree and installed build
  on a developer's machine opens the same `~/.coffer/coffer.db`. Two branches
  once shipped different revisions under the same numbers (0006/0007); a
  database stamped by one could not be upgraded by the other, and a build that
  met a revision it did not know died in lifespan startup with Alembic's opaque
  "Can't locate revision".
- **Stale tolerance code accumulates.** A model that kept a load-time fallback
  for an old stored shape (`AgentConfig` carried two such legacy keys) hid a
  missing migration until a later field removal made every existing agent row
  fail validation.

## Options Considered

### Option A — SQLite (WAL) behind SQLAlchemy async, one writer, one central Alembic lineage run forward at daemon startup (chosen)

- **Storage.** One file, `~/.coffer/coffer.db` (`COFFER_DB_URL` overrides it).
  SQLAlchemy 2.0 async over `aiosqlite`, matching the daemon's asyncio model.
  Every connection gets the same pragmas
  (`infrastructure/persistence/engine.py`): `journal_mode = WAL`,
  `foreign_keys = ON`, `synchronous = NORMAL`, `busy_timeout = 5000`,
  `cache_size = -64000`, `temp_store = MEMORY`.
- **One writer.** Only the daemon process opens the database. The CLI, shim and
  desktop shell read and write through its HTTP API. WAL lets readers proceed
  while the one writer commits; `busy_timeout` absorbs the daemon's own
  concurrent sessions. Hot write paths batch rather than commit per row (the
  MCP invocation log is flushed by a writer task, because each commit is an
  fsync).
- **Schema.** Every ORM model registers on one `Base.metadata`; one Alembic
  lineage under `infrastructure/persistence/migrations/versions/`, linear,
  numbered, hand-written. A kind's tables arrive in the same lineage as
  everyone else's.
- **When.** The daemon lifespan runs `run_migrations` (`surfaces/http/migrations_runner.py`)
  before it builds any service, off the event loop. It (1) refuses a database
  whose revision this build does not know, raising `DatabaseSchemaTooNew`
  (`DB_SCHEMA_TOO_NEW`) with an actionable message instead of Alembic's; (2)
  if an upgrade is due, copies `coffer.db` and its `-wal`/`-shm` companions to
  `coffer.db.pre-<revision>` — never overwriting an earlier copy for the same
  revision, keeping the three newest — and copies nothing when the schema is
  already current; (3) runs `alembic upgrade head` with the URL pinned on the
  Alembic config, so a caller that names a database cannot migrate a different
  one (such as the developer's real vault from a test).
- **Structured config.** Kind config and scope are JSON in `TEXT` columns
  (`config_json`, `scope_json`), validated by the kind's Pydantic schema on
  every write and parsed on every read; SQLite enforces none of it.
- **Pros.** Zero installation, one file to back up or copy, no server to run or
  secure, fast enough by orders of magnitude for one user's control plane. The
  migration step runs exactly when new code first meets old data, with a copy
  to fall back on. One lineage means one ordering of every schema change and
  one version number to compare.
- **Cons.** One writer process is a hard constraint on every surface (nothing
  may open the file directly). JSON-in-TEXT moves shape enforcement out of the
  database. SQLite's limited `ALTER TABLE` makes some changes a table rebuild,
  which the lineage avoids for `resources` because four tables cascade from it.
  A long data migration delays daemon start.
- **Why it wins.** It is the only option that needs nothing installed, keeps
  cross-kind foreign keys, and upgrades user data at a moment the daemon
  controls, with a backup taken first.

### Option B — A server database (PostgreSQL/MySQL), or an embedded server

- **Pros.** Real concurrent writers, richer types (JSONB, enums), full `ALTER
  TABLE`, mature tooling.
- **Cons.** The user would install, run, secure and upgrade a database process
  for a single-user tool, or Coffer would bundle and supervise one (an embedded
  Postgres adds a large binary, a second long-lived process and its own port
  and data-directory upgrades). Backup stops being "copy a file".
- **Why it loses.** It violates the zero-infrastructure premise for write
  concurrency Coffer does not need; the principles name SQLite as the system of
  record, and changing that is an amendment.

### Option C — Per-kind migration lineages

Each kind owns an Alembic branch (or its own `version_locations`) and migrates
independently.

- **Pros.** A kind's schema history reads on its own; kinds could be added or
  removed without touching a shared sequence.
- **Cons.** Kind tables hold foreign keys into `resources`, and several
  migrations change a kind table and the core together (0096 rewrote
  `resources.scope_json` and `conversations.channel_name` in one step; 0097
  re-keyed two MCP tables against `resources.uid` added by 0095). Independent
  lineages need explicit cross-branch dependencies for exactly those cases,
  and "what revision is this database at" becomes a set of heads to compare,
  which multiplies the divergence problem the shared-database incident showed.
- **Why it loses.** The kinds are not independent in the schema, so separate
  lineages would only hide the ordering they actually have.

### Option D — `create_all()` at startup, no migrations

- **Pros.** No migration files; a fresh install gets the current schema.
- **Cons.** `create_all` only creates missing tables. It cannot add a column,
  change a key, or rewrite data — and most of this lineage is exactly that:
  moving names to uids, stripping retired config keys, purging retired audit
  events, re-keying MCP history. Every upgrade would need hand-written fix-up
  code in the application or a manual reset.
- **Why it loses.** Existing installs carry user data forward; `create_all`
  has no way to.

### Option E — JSON or YAML files instead of a database

One document per resource on disk (the sync bundle's shape), plus files for
logs.

- **Pros.** Human-readable, diffable, trivially synced.
- **Cons.** No transactions across a resource and its dependents, no foreign
  keys or cascades, no indexed queries over the audit and invocation logs,
  and every concurrent writer inside the daemon would need its own locking.
  The retention worker, the activity pages and the gateway's tiering queries
  would each reimplement a query engine.
- **Why it loses.** The control plane is relational and transactional. Files
  are kept for what is genuinely document-shaped: knowledge, memory, skills,
  and the sync bundle, which is serialised *from* the database.

### Option F — Migrate at install time instead of at startup

An installer step or a `coffer db upgrade` command runs migrations.

- **Pros.** Start-up stays fast; a failed migration surfaces during install,
  not as a daemon that will not start.
- **Cons.** Coffer is installed by replacing binaries (an archive, a `.dmg`, or
  `pip`), with no install hook that runs on every path, and a daemon started by
  detect-or-spawn from a new binary would meet an old schema whenever the step
  was skipped. The migration also has to be able to back up the file, which is
  only safe while no daemon holds it — true at lifespan start by construction.
- **Why it loses.** Startup is the one moment every install path passes
  through, with the database guaranteed to be closed by everyone else.

### Option G — Two-way migrations: an older build downgrades a newer database

- **Pros.** Rolling back a release would just work.
- **Cons.** Many data migrations cannot be inverted honestly: once a name has
  become a uid, or a name-derived credential ref has been rewritten to a
  derived hash, the old value is not recoverable (0099's downgrade is a
  documented no-op). An older build would also need the newer build's revision
  scripts to downgrade through them, which by definition it does not have.
- **Why it loses.** The failure mode it prevents is better handled by refusing
  to start with a clear message and keeping a pre-migration copy of the file to
  restore.

## Decision

Control-plane state is one SQLite file in WAL mode, accessed through
SQLAlchemy async with Coffer's pragma suite on every connection. Only the
daemon writes it. Its schema is one linear, hand-written Alembic lineage over
one `Base.metadata`, and the daemon runs it forward at startup before building
any service — refusing a database from a newer or divergent build
(`DB_SCHEMA_TOO_NEW`) and copying the file aside as `coffer.db.pre-<revision>`
before any upgrade.

Rules this implies for every future change:

- **Forward at runtime.** The daemon never runs a downgrade. `downgrade()`
  functions are still written, and a round-trip test drives the whole lineage
  `upgrade head → downgrade base → upgrade head`
  (`tests/integration/infrastructure/persistence/test_migrations_roundtrip.py`),
  but where a data rewrite cannot be undone the downgrade says so rather than
  inventing values.
- **Migrations leave no load-time shims.** Because the migration runs before
  any row is read, models accept only the current shape. Removing or renaming a
  stored field ships, in the same change, a migration that rewrites the stored
  rows, and no fallback parser stays behind for the old shape (`Scope.from_json`
  accepts only the post-migration shape; 0098 strips `skill_md_name` because
  `SkillConfig` forbids extra keys and a leftover key would make the skill
  unloadable). The only path that can bring an old shape in after the migration
  is a synced document written by an older build, and that is normalised or
  held by the sync import gates at the boundary, not tolerated by the model.
- **Idempotent data rewrites.** A revision runs at startup against whatever
  state a user's database is in, so a data rewrite touches only rows that still
  need it and a second run is a no-op (0095–0098 and 0100 each state how
  they achieve this).
- **JSON columns are validated, not trusted.** Nothing reaches `config_json`
  without passing the kind's schema, serialised with `model_dump(mode="json")`.
- **One lineage across branches.** A revision that has shipped stays in the
  lineage even if the feature that added it is withdrawn: the workflow tables
  (0090–0094, 0100) remain after the feature was taken off `main`, because
  removing a revision a user's database is stamped with would turn that
  database into one this build refuses.

## Consequences

- A fresh install and an upgraded one converge on the same schema through the
  same code path, and a failed or wrong migration is recovered by renaming a
  `coffer.db.pre-*` file.
- The frozen build bundles the migration scripts as data, so an end-user
  install needs no separate step ([Distribution — PyInstaller](distribution-pyinstaller.md)).
- Surfaces other than the daemon never hold a database connection; this is also
  why the CLI must reach credentials through the daemon.
- Branches that add revisions must renumber on rebase so the lineage stays
  linear; two revisions with the same number on two branches is the incident
  above.
- Retention is a registry of prunable tables consulted by one worker rather than
  per-table code; see [Audit and Retention](audit-and-retention.md).
