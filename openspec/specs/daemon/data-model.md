# Data Model — Daemon

The daemon owns no table. Everything it records is a file, and for one reason:
each of these is read or written at a moment when the database is not available
— before it is opened, while it is being migrated, or after the process that
opened it has died.

## `~/.coffer/daemon.json` — the discovery file

Runtime state published **by** a daemon and read by every client: the CLI, the
MCP shim, the desktop shell of spec desktop-app, and the daemon's own
supersession check. Written atomically at mode `0600`
(`infrastructure/daemon/pid_lock.py`, `atomic_write.write_json_0600`).

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | int | Schema version of this file. `1` today. |
| `pid` | int | The daemon process. Never trusted on its own — every reader confirms the pid is still a Coffer daemon before acting on it. |
| `port` | int | The bound port. The one authority for "where is Coffer" (spec daemon "Publish one private discovery file"). |
| `token` | string | The API token for this daemon's lifetime (spec daemon "Require a token on every management call"). Why the file is `0600`. |
| `started_at` | ISO-8601 | When this daemon bound its port. Reported by `/daemon/status`. |
| `binary_path` | string | The executable that is serving — the frozen binary, or the interpreter of a run-from-source daemon. Named in the version-skew warning. |

Lifecycle:

- **Written** inside the spawn lock, after the port is bound and before the
  lock is released, by `bootstrap.acquire()`.
- **Rewritten** in place by a token rotation, through the same atomic `0600`
  path, so the file never exists at wider permissions.
- **Unlinked** at exit by `bootstrap.release()` — and **only** while it still
  records this process's own pid, so an orphaned daemon cannot delete the live
  daemon's file on its way out.
- **Absent or malformed reads as "no daemon"**, never as an error. Every
  reader catches `FileNotFoundError`, `ValueError`, `KeyError` and `OSError`
  onto the same answer.

A pid is not identity. `pid_is_coffer_daemon(pid)` inspects the process's
command line for one of the daemon markers
(`coffer.infrastructure.daemon.entry`, `coffer-daemon`); a process that cannot
be inspected answers `False`, and every caller treats that as "do nothing".

## `~/.coffer/daemon-config.json` — pre-bind configuration

Settings read **before** the database is opened, so nothing here can live in
SQLite (`infrastructure/daemon/config.py`). Mode `0600`. Written by **merge**,
never by replacement, so several settings share one file and a key written by a
newer build survives being touched by an older one.

| Field | Type | Meaning |
| --- | --- | --- |
| `port` | int or absent | The port the user pinned. Absent, unreadable or nonsensical all mean "no usable instruction", which resolves to the default of `8000` — never to some other port. Validated to `1024 ≤ port ≤ 65535`, because below 1024 needs privileges the daemon does not have and must not acquire. |
| `idle_shutdown_hours` | number, `null` or absent | How long the daemon serves nothing before standing down (spec daemon "Stand down after an idle window"). Absent means the default of `12`; `null` means never stand down, which a bare absent key could not say. At least `0.25`: below that the setting stops meaning "nobody is using it" and starts meaning "restart constantly". A value that is not a number or is below the floor is warned about and read as the default. Read once at start, so a change takes effect at the next one. |
| `machine_name` | string or absent | This machine's display label. Defaults to the hostname with a `.local` suffix stripped. Free to change: nothing references it. |
| `features` | object or absent | This machine's own experimental-feature switches, `{"<key>": true\|false}` (spec experimental-features "Decide a feature's state per machine"). A key that is absent falls back to the build channel's default — off on `stable`, on on `dev` — and a `COFFER_FEATURES` pin (`key=on\|off`, comma-separated, read once at start) overrides it. Written by `PUT /api/v1/daemon/features/{key}` before it answers, and takes effect at once, without a restart. A value that is not a boolean is warned about and ignored; keys the build does not know are kept. Machine-local on purpose: the database syncs, and a switch in it would switch every machine. |
| `memory_delivery_withdrawn` | array of strings or absent | The agents, by uid, whose memory delivery hook was taken out when the `memory` feature was switched off (spec experimental-features "Withdraw what a switched-off feature put in front of agents"). Switching `memory` back on — at once, or at a later boot — reinstalls the hook into exactly these agents and empties the list; an agent deleted meanwhile is dropped. Machine-local for the same reason as `features`. |
| `machine_id` | string or absent | A **cache** of the derived machine id (spec vault-sync). Never authoritative — deleting it recomputes the same value, and a cached value that disagrees with the host loses. |

A file that will not parse is warned about and ignored, not fatal: an
unbootable daemon cannot be repaired from the UI it serves.

## `~/.coffer/daemon.lock` — the spawn lock

An empty file whose only purpose is to carry an advisory exclusive `flock`. It
is left on disk between runs on purpose: the lock lives on the open descriptor,
not on the file's existence, so deleting it accomplishes nothing and recreating
it costs a syscall. Where `fcntl` is unavailable the lock degrades to a bare
open descriptor and the invariant rests on the liveness refusal and the atomic
publish alone.

## `~/.coffer/upstream-pids/<name>-<pid>.json` — child process records

One file per long-lived child the daemon spawned, written by the same call that
spawns it so a child can never exist unrecorded
(`infrastructure/daemon/child_process.py` → `orphan_sweep.record_spawn`).

| Field | Meaning |
| --- | --- |
| name | Which child — the callback listener, a channel tunnel, an agent app-server, an MCP upstream. |
| pid | The child. |
| command line | What it was spawned as, so a startup sweep can tell a live child from a recycled pid. |
| spawned at | When. |

The record is removed only after the child has been reaped through the
termination ladder, because a lingering record sends the next startup sweep
chasing a pid that may by then belong to a stranger.

## `~/.coffer/bin/` — deployed frozen builds

```
~/.coffer/bin/coffer-daemon            -> 0.2.0/coffer-daemon   (symlink)
~/.coffer/bin/0.2.0/coffer-daemon
~/.coffer/bin/0.2.0/.coffer-daemon.version   (sentinel, written last)
~/.coffer/bin/0.1.1/coffer-daemon            (the previous build, kept)
```

Four binaries per version: `coffer`, `coffer-daemon`, `coffer-mcp-shim`,
`coffer-callback`. The public names never move, so every caller's path is
stable; what changes is which version directory the symlink points into. Two
version directories are kept, so the last upgrade can always be undone by
pointing the links back.

Staleness is decided by **byte size** and the **version sentinel**, never by
mtime — a build's mtime says when it was extracted, not what it contains, which
re-copied every binary on every start after a reinstall of the same release.

## `coffer.db.pre-<revision>` — the pre-migration copy

Written beside the live database before `alembic upgrade head` changes it, with
its `-wal` and `-shm` companions when they exist. The three newest are kept. A
start against an already-current schema copies nothing, and an in-memory
database copies nothing.

## `~/.coffer/logs/` — the log directory

| Path | Writer | Bounded by |
| --- | --- | --- |
| `daemon.log` (+ rotations) | the daemon, its children, and every surface writing on their behalf | rotation, never deletion — it is held open |
| `shim-*.log` | one per MCP shim process start | the retention sweep, by age |
| `upstream/<server>.log` (+ `.log.1`) | one per registered MCP upstream's stderr | a roll-aside at open time, then the retention sweep |

`COFFER_LOG_DIR` relocates the whole directory.

### The parsed log record

`daemon.log` is deliberately not one format. `application/log_reader.py`
normalises every writer onto the same shape, and keeps what it cannot parse:

| Field | Meaning |
| --- | --- |
| `timestamp` | ISO-8601, whichever writer's spelling it arrived in. |
| `level` | Normalised onto one vocabulary — `debug`, `info`, `warning`, `error`, `critical` — across structured JSON, the stdlib formatter's five-character truncations, uvicorn, and a child's three-character zerolog tokens. |
| `logger` | The emitting logger, where the line named one. |
| `event` | The message. |
| `continuation` | The lines that belong to this record — a traceback, a wrapped message — rather than a run of empty rows. |
| `raw` | The whole line, for a line no format fits. Kept, because it is often the interesting one. |

An unparseable line is treated as error-level, so it surfaces rather than
hiding at the bottom of a severity filter.

## Audit events

| Event | Emitted by |
| --- | --- |
| `token_rotated` | A rotation through either surface (spec daemon "Rotate the token from REST or the command line"). |
| `daemon_residency_updated` | `PUT /api/v1/daemon/residency` (spec daemon "Change residency from the settings page or the command line"). Details `{login_service_installed, idle_shutdown_hours}`, read back after the change, so they record what became true rather than what was asked for. The `coffer daemon idle` and `coffer daemon service` commands write the same settings with no daemon involved and record nothing, for the reason the port records nothing. |

The fixed-port setting deliberately emits nothing — see spec daemon "Bind a fixed, settable port" for
why recording it only when a daemon happens to be running would be less honest
than recording none.
