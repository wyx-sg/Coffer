# History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Technology & architectural constraints — Persistence; Guarantees — Single SQLite writer), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Code Layout — Layer-First](code-layout-layer-first.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Distribution — PyInstaller](distribution-pyinstaller.md), [Persistence](../../docs-site/architecture/persistence.md), spec daemon "Deploy frozen sibling binaries and back up the history database before migrating", PR #14, PR #48, PR #386

## Context

Coffer keeps a machine's **history** — the audit log, the MCP invocation log,
conversations and their messages, channel threads and the outbox, sync rounds
and usage — in a database on the user's own machine. Configuration is not
in it: resources, secrets' ciphertext and state documents are files in the
vault, and what is only true of this machine is small JSON under `local/`
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)).
What remains is the data that is append-only or time-ordered, queried by time,
kind, event and conversation, pruned by age, and never meaningful on another
machine. It must need no installation beyond Coffer itself, survive upgrades of
a product that ships often, and be copyable as a file.

Forces on the choice:

- **One user, several processes.** The daemon, the CLI, the stdio shim and the
  desktop shell all run on one machine. Only one of them is long-lived.
- **Upgrades are unattended.** A release is installed by replacing binaries;
  the next daemon start is the first moment new code meets old data. The
  lineage carries many data rewrites of user rows, not only DDL.
- **Many kinds, one framework.** Kind-agnostic tables (`audit_log`, …) sit
  beside tables a kind owns (channel threads, MCP invocations, usage); the
  kinds' tables register on the same metadata.
- **Branches share a database.** Every checkout, worktree and installed build
  on a developer's machine opens the same `~/.coffer/runs.db`. Two branches
  once shipped different revisions under the same numbers; a database stamped
  by one could not be upgraded by the other, and a build that met a revision it
  did not know died in lifespan startup with Alembic's opaque "Can't locate
  revision".
- **Stale tolerance code accumulates.** A model that kept a load-time fallback
  for an old stored shape hid a missing migration until a later field removal
  made every existing row fail validation.

## Options Considered

### Option A — SQLite (WAL) behind SQLAlchemy async, one writer, one Alembic lineage run forward at daemon startup (chosen)

- **Storage.** One file, `~/.coffer/runs.db` (`COFFER_DB_URL` overrides it;
  `runs_db_path` in `infrastructure/vault/home.py` is the one place that
  names it). SQLAlchemy 2.0 async over `aiosqlite`, matching the daemon's
  asyncio model. Every connection gets the same pragmas
  (`infrastructure/persistence/engine.py`): `journal_mode = WAL`,
  `foreign_keys = ON`, `synchronous = NORMAL`, `busy_timeout = 5000`,
  `cache_size = -64000`, `temp_store = MEMORY`.
- **One writer.** Only the daemon process opens the database. The CLI, shim and
  desktop shell read and write through its HTTP API, and the local model proxy
  spools its usage records to files the daemon ingests rather than opening it.
  WAL lets readers proceed while the one writer commits; `busy_timeout` absorbs
  the daemon's own concurrent sessions. Hot write paths batch rather than
  commit per row (the MCP invocation log is flushed by a writer task, because
  each commit is an fsync).
- **Schema.** Every ORM model registers on one `Base.metadata`; one Alembic
  lineage under `infrastructure/persistence/migrations/versions/`, linear,
  numbered, hand-written, starting at one baseline revision that creates the
  whole schema. A kind's tables arrive in the same lineage as everyone else's.
- **When.** The daemon lifespan runs `run_migrations`
  (`infrastructure/persistence/migrations_runner.py`) before it builds any
  service, off the event loop. It (1) refuses a database
  whose revision this build does not know, raising `DatabaseSchemaTooNew`
  (`DB_SCHEMA_TOO_NEW`) with an actionable message instead of Alembic's; (2) if
  an upgrade is due, copies `runs.db` and its
  `-wal`/`-shm` companions to `runs.db.pre-<revision>` — never overwriting an
  earlier copy for the same revision, keeping the three newest — and copies
  nothing when the schema is already current; (3) runs `alembic upgrade head`
  with the URL pinned on the Alembic config, so a caller that names a database
  cannot migrate a different one (such as the developer's real home from a
  test).
- **Structured payloads.** An audit entry's `details_json` and a sync round's
  `payload_json` are JSON in `TEXT` columns, serialised from typed models by the
  daemon and parsed back through them; SQLite enforces none of it.
- **Pros.** Zero installation, one file to back up or copy, no server to run or
  secure, fast enough by orders of magnitude for one user's history. The
  migration step runs exactly when new code first meets old data, with a copy
  to fall back on. One lineage means one ordering of every schema change and
  one version number to compare. Indexed queries and `DELETE … WHERE
  timestamp < …` serve the Activity pages and the retention worker without a
  query engine of our own.
- **Cons.** One writer process is a hard constraint on every surface (nothing
  may open the file directly). JSON-in-TEXT moves shape enforcement out of the
  database. SQLite's limited `ALTER TABLE` makes some changes a table rebuild.
  A long data migration delays daemon start.
- **Why it wins.** It is the only option that needs nothing installed, serves
  indexed, prunable, time-ordered history, and upgrades user data at a moment
  the daemon controls, with a backup taken first.

### Option B — A server database (PostgreSQL/MySQL), or an embedded server

- **Pros.** Real concurrent writers, richer types (JSONB, enums), full `ALTER
  TABLE`, mature tooling.
- **Cons.** The user would install, run, secure and upgrade a database process
  for a single-user tool, or Coffer would bundle and supervise one (an embedded
  Postgres adds a large binary, a second long-lived process and its own port
  and data-directory upgrades). Backup stops being "copy a file".
- **Why it loses.** It violates the zero-infrastructure premise for write
  concurrency Coffer does not need; the principles name SQLite as the history
  store, and changing that is an amendment.

### Option C — Per-kind migration lineages

Each kind owns an Alembic branch (or its own `version_locations`) and migrates
independently.

- **Pros.** A kind's schema history reads on its own; kinds could be added or
  removed without touching a shared sequence.
- **Cons.** History tables of different kinds still refer to the same
  identities (a resource uid, a conversation), and a data migration often has
  to change a kind's table and a kind-agnostic one together. Independent
  lineages need explicit cross-branch dependencies for exactly those cases, and
  "what revision is this database at" becomes a set of heads to compare, which
  multiplies the divergence problem the shared-database incident showed.
- **Why it loses.** The kinds are not independent in the schema, so separate
  lineages would only hide the ordering they actually have.

### Option D — `create_all()` at startup, no migrations

- **Pros.** No migration files; a fresh install gets the current schema.
- **Cons.** `create_all` only creates missing tables. It cannot add a column,
  change a key, or rewrite data — and the lineage is largely that: re-keying
  history from names to uids, stripping retired config keys, purging retired
  audit events. Every upgrade would need hand-written fix-up code in the
  application or a manual reset.
- **Why it loses.** Existing installs carry user data forward; `create_all`
  has no way to.

### Option E — Everything in one SQLite file, `coffer.db`

The design this replaced. One database held configuration as well as history:
resource rows with their config and reach as JSON in `TEXT` columns, the
ciphertext of every secret, MCP capability preferences, channel pairings,
retention policies and the sync remote, beside the audit log and the
conversations. Kind-agnostic tables were referenced by kind-owned ones through
foreign keys with `ON DELETE CASCADE`.

- **Pros.** Transactions and foreign keys across a resource and its
  dependents; one backup; one engine.
- **Cons.** Rows of utterly different natures shared one file and therefore one
  backup, retention and sync answer, and none of those answers was right for
  every row: the only copy of the user's configuration beside an append-only
  log, machine-local reach beside resources meant for every machine. Sync had
  to serialise the database into files and translate them back, with a rule
  for every field that must not travel. A person could not edit configuration
  as a file.
- **Why it loses.** The foreign keys it kept were between a resource and its
  dependents, and the dependents moved into the vault with it. What stays in
  SQLite is the data that is genuinely relational and time-ordered, which
  needs none of them.

### Option F — JSON files instead of a database for history too

One document per record, or JSON-lines files, for the audit and invocation
logs and the conversations.

- **Pros.** Human-readable, diffable; the same engine as the vault.
- **Cons.** No indexed queries over the audit and invocation logs, no
  transactions between a conversation and its messages, and every concurrent
  writer inside the daemon would need its own locking. The retention worker,
  the activity pages and the gateway's tiering queries would each reimplement a
  query engine.
- **Why it loses.** History is relational, large and queried by time and kind.
  Files are kept for what is genuinely document-shaped: configuration,
  knowledge, skills and memory.

### Option G — Migrate at install time instead of at startup

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

### Option H — Two-way migrations: an older build downgrades a newer database

- **Pros.** Rolling back a release would just work.
- **Cons.** Many data migrations cannot be inverted honestly: once a name has
  become a uid, or a stored reference has been rewritten to a derived hash, the
  old value is not recoverable. An older build would also need the newer
  build's revision scripts to downgrade through them, which by definition it
  does not have.
- **Why it loses.** The failure mode it prevents is better handled by refusing
  to start with a clear message and keeping a pre-migration copy of the file to
  restore.

## Decision

History is one SQLite file, `~/.coffer/runs.db`, in WAL mode, accessed through
SQLAlchemy async with Coffer's pragma suite on every connection. Only the
daemon writes it. Its schema is one linear, hand-written Alembic lineage over
one `Base.metadata`, and the daemon runs it forward at startup before building
any service — refusing a database from a newer or divergent build
(`DB_SCHEMA_TOO_NEW`) and copying the file aside as `runs.db.pre-<revision>`
before any upgrade.

Rules this implies for every future change:

- **Forward at runtime.** The daemon never runs a downgrade. `downgrade()`
  functions are still written, and a round-trip test drives the whole lineage
  `upgrade head → downgrade base → upgrade head`
  (`backend/tests/integration/infrastructure/persistence/test_migrations_roundtrip.py`),
  but where a data rewrite cannot be undone the downgrade says so rather than
  inventing values.
- **Migrations leave no load-time shims.** Because the migration runs before
  any row is read, models accept only the current shape. Removing or renaming a
  stored field ships, in the same change, a migration that rewrites the stored
  rows, and no fallback parser stays behind for the old shape.
- **Idempotent data rewrites.** A revision runs at startup against whatever
  state a user's database is in, so a data rewrite touches only rows that still
  need it and a second run is a no-op.
- **One lineage across branches.** A revision that has shipped stays in the
  lineage even if the feature that added it is withdrawn, because removing a
  revision a user's database is stamped with would turn that database into one
  this build refuses; the tables nothing reads any more are the visible cost.
- **Only history lives here.** New state is classified first
  ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md));
  only history that is append-only or time-ordered, relational and local to
  this machine is added to `runs.db`.

## Consequences

- A fresh install and an upgraded one converge on the same schema through the
  same code path, and a failed or wrong migration is recovered by renaming a
  `runs.db.pre-*` file.
- The frozen build bundles the migration scripts as data, so an end-user
  install needs no separate step ([Distribution — PyInstaller](distribution-pyinstaller.md)).
- Surfaces other than the daemon never hold a database connection; this is also
  why the CLI must reach secrets through the daemon.
- Branches that add revisions must renumber on rebase so the lineage stays
  linear; two revisions with the same number on two branches is the incident
  above.
- Retention is a registry of prunable tables consulted by one worker rather than
  per-table code; see [Audit and Retention](audit-and-retention.md).
- `derived.db`, the small SQLite file under `derived/`, is outside this
  lineage: it holds only rebuildable state, carries a schema version in
  `PRAGMA user_version`, and is deleted and created again when that differs.
