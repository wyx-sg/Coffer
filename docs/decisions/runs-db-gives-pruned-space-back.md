# `runs.db` Gives Pruned Space Back With a Threshold `VACUUM`, and Copies Itself With `VACUUM INTO`

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md),
[Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](audit-and-retention.md),
spec resource-framework "Give the space pruning frees back to the disk",
spec daemon "Deploy frozen sibling binaries and back up the history database before migrating",
architecture [persistence](../../docs-site/architecture/persistence.md#runs-db)

## Context

Retention deletes old rows from `runs.db` every six hours
([Audit and Retention](audit-and-retention.md)). SQLite does not shrink a file
when rows go: their pages join the file's freelist and wait to be reused. With
the default `auto_vacuum = NONE` and no `VACUUM` anywhere in the backend, the
file only grows to its high-water mark and stays there.

Measured on the maintainer's install on 2026-10-07, read-only:

| | |
| --- | --- |
| `runs.db` | 149.7 MB, `page_size` 4096, `page_count` 36,560 |
| `freelist_count` | 35,394 — 145 MB, 97 % of the file |
| Live data | about 4.6 MB (the largest table, `audit_log`, 2.4 MB) |
| `runs.db.pre-0149`, `runs.db.pre-0150` | 150 MB each |

The pre-migration backup made it worse. Before each schema upgrade the runner
copied the whole file byte for byte, free pages included, with its `-wal` and
`-shm` companions. Three kept copies of a file that is 97 % empty is 450 MB to
protect 14 MB of history, and every upgrade repeats it.

The decision has two halves that answer the same problem — how large the file
on disk is relative to the history it holds — and each is argued on its own.

## Options Considered

### Giving free pages back

#### Option A1 — `VACUUM` after a retention pass, only past a threshold (chosen)

After each retention pass the worker reads `page_count`, `freelist_count` and
`page_size` and, when free pages are at least half the file **and** at least
8 MB, runs `VACUUM` on its own short-lived connection in a worker thread, then
`PRAGMA wal_checkpoint(TRUNCATE)` so the WAL the rebuild went through does not
keep the space instead (`infrastructure/persistence/space.py`).

- **Pros.** No schema or pragma change, so nothing to migrate and nothing for
  every connection to remember. A full `VACUUM` also defragments: the rebuilt
  file has its tables contiguous again. The cost is proportional to the live
  data, not the file: rebuilding 4.6 MB takes well under a second, and the
  thresholds mean it happens only after a prune freed a lot, which for a
  steady install is rarely. It runs where the space is freed — the retention
  worker, already off the request path.
- **Cons.** A `VACUUM` needs the write lock for its duration and temporary
  space up to the live data's size; a writer waits on `busy_timeout` meanwhile
  (readers carry on in WAL mode). Between passes the file can still hold up to
  half free pages or 8 MB; that slack is reused by new rows anyway.

#### Option A2 — `auto_vacuum = INCREMENTAL` and `PRAGMA incremental_vacuum` after each prune

Switch the database to incremental auto-vacuum and give pages back in each
retention pass.

- **Pros.** Each give-back is small and bounded; no full rebuild in steady state.
- **Cons.** An existing database switches only through one full `VACUUM`
  anyway, and `VACUUM` cannot run inside the transaction Alembic wraps a
  revision in, so the switch needs its own out-of-band step in the runner.
  Every commit then maintains pointer-map pages, and incremental vacuum moves
  pages to the end without defragmenting, so the file fragments over time and
  still wants an occasional full `VACUUM`. More moving parts for a file whose
  live data is a few megabytes. Lost.

#### Option A3 — `VACUUM` on a fixed schedule, unconditionally

Home Assistant's recorder repacks (`VACUUM`s) its SQLite database every second
Sunday after its nightly purge; Firefox's vacuum manager runs a `VACUUM` on
idle for each database that asks for one, at most once a month.

- **Pros.** Simple and predictable.
- **Cons.** Rewrites the file when nothing was freed, and leaves a large free
  space in place until the schedule comes round after a big prune (a person
  shortening a window from a year to a week). The threshold in A1 is the same
  idea, triggered by the thing that actually frees space. Lost, though A1 can
  be read as A3 with a better trigger.

#### Option A4 — Leave it, or offer a manual "Compact" action

- **Pros.** No code in the background.
- **Cons.** The measurement above is the result: nobody knows the file is 97 %
  empty, so nobody presses the button. A person should not have to know what a
  freelist is to get their disk back. Lost.

### Copying the file before a migration

#### Option B1 — `VACUUM INTO '<db>.pre-<revision>'` (chosen)

- **Pros.** One statement writes a self-contained, consistent snapshot of the
  live data: it reads through the WAL, so there are no companions to copy and no
  window where the main file and its WAL disagree. It writes only live pages,
  so the copy is the size of the history (about 5 MB on the install above, not
  150 MB). SQLite has had it since 3.27; Python 3.12 bundles a newer one.
- **Cons.** It reads and writes through SQLite rather than copying bytes, so it
  takes as long as a `VACUUM`; for the sizes involved that is a fraction of a
  second. A file SQLite cannot read cannot be copied this way; the runner then
  removes the half-written copy and fails, which is right, because Alembic
  could not have migrated that file either.

#### Option B2 — Copy the file and its `-wal`/`-shm` byte for byte (the previous design)

- **Pros.** Works on any bytes, even a damaged file.
- **Cons.** Copies every free page, and three files instead of one, whose
  consistency depends on nothing writing between the copies (true at startup,
  but only by convention). Lost on size.

#### Option B3 — The SQLite online backup API (`sqlite3.Connection.backup`)

- **Pros.** Consistent snapshot, works while others write.
- **Cons.** Copies pages as they are, free pages included, so it fixes the
  companions but not the size. Lost.

## Decision

After each retention pass, the retention worker rebuilds `runs.db` with
`VACUUM` and truncates its WAL when free pages are at least half of the file
and at least 8 MB; otherwise it leaves the file alone. The pre-migration copy
is written with `VACUUM INTO` as one compact file; a copy that fails is removed
and the migration does not run.

## Consequences

- The first retention pass after this ships shrinks an install like the one
  measured from 150 MB to about 5 MB, and its next migration copy is as small.
  Copies an earlier build took keep their companions until pruning removes
  them with their main file.
- Restoring a copy is moving it into place as `runs.db` with the daemon
  stopped, after moving the live `runs.db-wal` and `runs.db-shm` aside: a
  leftover WAL would otherwise be replayed onto the restored file.
- The thresholds are constants in `space.py`, not settings: nobody should need
  to tune them, and the Data tab does not grow a knob for them.
