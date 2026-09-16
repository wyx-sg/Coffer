# Implementation Plan: Daemon

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

The daemon is the process every other Coffer surface is a client of. This plan
covers the four things that make it one process rather than several: the
detect-or-spawn critical section that guarantees one daemon per vault, the
pre-bind configuration that fixes its port before any database exists, the
loopback + token + `Host` posture that lets it serve a secret-bearing page to a
browser, and the frozen distribution that puts all four binaries on a machine
with no Python. It adds the OS-action routes a web page cannot perform for
itself, and the one log file everything appends to.

Everything here is shipped. The spec was extracted from spec mcp-gateway and
spec agent-registry, which each carried half of it.

## Technical Context

| Dimension | Value |
| --- | --- |
| **Language / Version** | Python 3.12+ (the shell that reads `daemon.json` is Rust — spec desktop-app) |
| **New runtime dependencies** | None. `psutil` and `httpx` were already present. |
| **Storage** | Three files outside SQLite: `~/.coffer/daemon.json`, `~/.coffer/daemon-config.json`, `~/.coffer/daemon.lock`; plus `~/.coffer/logs/`, `~/.coffer/bin/<version>/` and `~/.coffer/upstream-pids/`. No table of its own. |
| **Testing** | 4-tier; acceptance markers tie to scenarios. The lifecycle rules are exercised with real processes, because every one of them is about what two processes do to each other. |
| **Target Platforms** | macOS arm64 is the platform the release builds and the one exercised end to end. Linux is exercised in CI and is where the `SO_REUSEADDR` difference in the port pre-flight is visible at all. Windows degrades: no advisory lock, no native folder dialog. |
| **Performance Goals** | Spawn to `status: ready` within the CLI's 10 s boot budget on a cold vault. The liveness probe's timeout is deliberately generous (a warming daemon has been measured at ~9 s) because a timeout produces a second daemon. |
| **Constraints** | Loopback-only; the port is chosen before the database is open; nothing in the lifecycle path may depend on a migration having run. |
| **Scale** | One daemon, a handful of concurrent clients, a handful of long-lived children. |

## Constitution Check

| Clause | Compliance | Notes |
| --- | --- | --- |
| I. Local-First | ✅ | The daemon binds loopback and is never tunnelled; only the separate callback listener of spec channels is. |
| II. Spec-as-Truth | ⚠️ | This spec was written after the code, as an extraction. From here it leads. |
| III. Open-Source-Readiness | ✅ | No new closed-source dependencies; the release archive is reproducible from the workflow in the repo. |
| Architecture: layered | ✅ | `infrastructure/daemon/` imports no surface; the CLI and HTTP surfaces import it. |
| Persistence | ✅ | The lifecycle files are deliberately outside SQLite, because they are read before it exists. |
| Credentials | ✅ | The API token is not a vault credential: it is minted per start and published only in a `0600` file. |
| Network defaults | ✅ | Loopback bind, token on every route but the readiness probe, `Host` guard on every surface. |

## Project Structure

### Backend modules

```
backend/coffer/
  infrastructure/daemon/
    bootstrap.py          # the detect-or-spawn critical section: lock, probe,
                          #   bind, publish, announce, release; plus
                          #   superseded_by() for FR-007 and release() for FR-008
    pid_lock.py           # DaemonInfo + atomic 0600 read/write of daemon.json;
                          #   pid_is_coffer_daemon() (FR-003)
    config.py             # ~/.coffer/daemon-config.json: DEFAULT_PORT,
                          #   effective_port(), merge-not-replace writes (FR-011)
    port_alloc.py         # bind_fixed_socket / bind_free_socket, PortInUse
    atomic_write.py       # write_json_0600 — one staging path for both files
    spawn.py              # daemon_spawn_command(): source vs frozen resolution (FR-002)
    entry.py              # what a spawn runs: bind, hand the fd to uvicorn,
                          #   release the lock at "serving", signal handlers,
                          #   the supersession loop (FR-005, FR-007, FR-008)
    version_skew.py       # skew_warning(): detect, never refuse (FR-006)
    child_process.py      # one spawn+record path, one termination ladder (FR-010)
    orphan_sweep.py       # startup_sweep(): recorded children + provably-ours
                          #   sibling daemons (FR-010)
  application/
    binary_deploy.py      # frozen sibling deployment into ~/.coffer/bin/<version>/ (FR-027)
    log_reader.py         # the shared normaliser over daemon.log's several formats (FR-023)
    fs/                   # browse_service, open_service, pick_service,
                          #   editor_service (FR-019 – FR-021)
  infrastructure/logging/
    files.py              # log_dir(), per-upstream sinks, prune_log_dir() (FR-022)
  surfaces/http/
    daemon_routes.py      # /daemon/status, /logs, /shutdown, /rotate-token
    fs_routes.py          # /fs/browse, /open, /reveal, /editors, /pick-folder
    webui.py              # static mount, token injection, SPA-vs-404 (FR-016 – FR-018)
    host_guard.py         # the 421 HOST_NOT_LOOPBACK middleware (FR-015)
    auth.py               # the in-process token the header check and the page share
    migrations_runner.py  # the pre-migration vault copy (FR-027)
  surfaces/cli/
    daemon_cmd.py         # start|stop|restart|status|rotate-token
    daemon_port_cmd.py    # port show|set|clear
    open_cmd.py           # coffer open (FR-017)
    _client.py            # every CLI command's detect-or-spawn path (FR-002)
```

### Release

```
.github/workflows/release.yml   # the v* matrix: freeze once, archive, hash
scripts/build_binaries.sh       # the four PyInstaller targets
scripts/smoke_test_bundle.sh    # extract-and-start against a throwaway HOME
```

## Layers and boundaries

- `infrastructure/daemon/` may not import `coffer.surfaces`. This is the reason
  `entry.py` reads `daemon.json` and hands the socket to uvicorn itself rather
  than asking the HTTP composition root to do it, and the reason the phase
  reported by `/daemon/status` is written *into* the route module by the
  composition root instead of read *out* of the app.
- The port is chosen before anything opens the database. Nothing in
  `config.py` may import SQLAlchemy, and nothing in the bind path may assume a
  migration has run.
- `application/log_reader.py` is pure — it reads the path it is handed and
  knows nothing about who is asking — because it has two callers with opposite
  audiences: the daemon-log route of FR-023, and `coffer__diagnose`.
- The `fs/` services shell out with fixed argument vectors. No caller-supplied
  string is ever interpolated into a shell.

## Decisions

- **The spawn lock is held past the publish.** Releasing it when `daemon.json`
  was written was tried first, and left a sub-second window in which a racing
  spawn probed a bound-but-not-serving port, saw nothing, and bound a second.
  The lock is now released by the entrypoint only once uvicorn reports it is
  serving; the release callable is idempotent so a `finally` can also call it.
- **Liveness is an HTTP probe with a generous timeout.** A short timeout is not
  a conservative choice here: it reads as "nobody is live" and produces the
  extra daemon. Fifteen seconds costs nothing in the common failure case, where
  a stale file points at a port that refuses the connection immediately.
- **Two lifecycle files, not one.** `daemon.json` comes out and is removed at
  exit; `daemon-config.json` goes in and survives. Collapsing them would put a
  user's setting in a file the daemon deletes.
- **The port pre-flight is allowed to be wrong in one direction only.** It may
  report "free" when the port is not — a `TIME_WAIT` port from the daemon a
  `restart` just stopped is bindable, and on Linux `SO_REUSEADDR` lets a second
  socket bind straight through a bound-but-not-listening one. It may never
  report a conflict that is not there, because that blocks a legitimate start.
- **The orphan sweep matches the vault, not the executable name.** Matching the
  name alone once reaped the maintainer's live daemon during a release smoke
  test run against a throwaway `HOME`.
- **The reserved-root check is by whole path segment.** A `startswith("mcp")`
  test would claim the UI's own `/mcp-servers` route.

## Risks / unknowns

- **Windows degrades quietly.** No `fcntl`, so the spawn lock becomes a bare
  open descriptor and only the liveness refusal plus the atomic publish defend
  the invariant. No native dialog, so `/fs/pick-folder` answers
  `available: false` forever. Neither is exercised.
- **`SO_REUSEADDR` is a platform difference in a correctness-shaped place.**
  The bound-but-not-listening case is only visible on Linux, which means only
  CI can catch a regression in it.
- **The pre-migration vault copy is a size multiplier.** Three copies of a
  large `coffer.db` is three times the disk, on a path the user never chose.
- **The daemon log is a shared mutable file with several writers.** Its reader
  must stay tolerant; a format that appears in it without being taught to
  `log_reader` degrades to a raw line rather than an error, which is the right
  failure but an invisible one.

## Open items deferred to future specs

- A `coffer daemon logs` command, closing the one REST/CLI parity gap this spec
  records in its `## Assumptions`.
- Signing and notarisation of the frozen binaries. Today they are unsigned and
  the quarantine step is documentation — see spec desktop-app FR-014 for the
  tier where it bites hardest.
