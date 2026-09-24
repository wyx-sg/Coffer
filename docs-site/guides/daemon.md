---
title: Running the daemon
description: Start, stop and supervise Coffer's daemon, pin its port, run it at login, and upgrade, roll back and back up a vault safely.
---

# Running the daemon

The daemon is the Coffer process itself: one background program per vault that serves the MCP gateway, the REST API and the web UI on `127.0.0.1`. This page is for anyone who installs Coffer and wants to know how the daemon is started, where it listens, what it writes to disk, and how to upgrade, roll back and back it up.

## What the daemon is for

Everything else in Coffer is a client of the daemon: the `coffer` CLI, the `coffer-mcp-shim` that your agents launch, the web UI in a browser tab, and the [desktop app](/guides/desktop-app). None of them holds vault state of its own.

You rarely need to start it by hand. Any surface that needs a daemon and finds none starts one itself, detached from the caller:

- any `coffer` command that talks to the daemon (except `coffer daemon status`, which only looks),
- an agent connecting to Coffer through `coffer-mcp-shim`,
- the desktop app on launch.

Exactly one daemon runs per vault. If two surfaces race to start one, a lock on `~/.coffer/daemon.lock` makes one of them win and the other attach to it. The daemon binds only the loopback interface, and every management call carries a token it mints at start, so nothing it serves is reachable from another machine.

## Start, stop and check the daemon

```sh
coffer daemon start      # spawn it in the background, if none is running
coffer daemon status     # ask the running daemon how it is; never starts one
coffer daemon stop       # SIGTERM, then wait for it to exit
coffer daemon restart    # stop (if running), then start
```

`coffer daemon status` prints what the daemon reports about itself:

```text
status:  ready
version: 0.2.0
channel: stable
port:    8000
pid:     41822
```

`status` is `ready` while the daemon serves and `draining` while it shuts down. There is no earlier phase to see: the daemon opens its port only once it has finished starting. `channel` is the build's release channel, which decides which [experimental features](/guides/experimental-features) are on by default. Add `--json` for scripts.

With no daemon running, `coffer daemon status` prints `status:  not running` (`{"status": "stopped"}` under `--json`) and exits 3. It does not start a daemon, so its answer never changes what it reports on; use `coffer daemon start` for that.

A few behaviours worth knowing:

- `start` decides "already running" by asking the daemon, not by checking whether `daemon.json` exists. A discovery file left behind by a crash never blocks a start.
- `start` checks the port before spawning. If something else holds it, you get the diagnosis at once instead of a ten-second timeout (see [When the port is taken](#when-the-port-is-taken)).
- `stop` checks that the recorded pid really is a Coffer daemon before signalling it. If the pid has been recycled onto another process, `stop` removes the stale `daemon.json` and says so instead of killing a stranger.
- `restart` is how a setting read before the daemon binds (the port) takes effect.

To open the UI the daemon serves, run `coffer open`. It reads the daemon's port from `~/.coffer/daemon.json` and opens your browser at that address; `--no-browser` prints the URL instead.

## Choose the port

The daemon listens on **port 8000** by default and never scans for another one. A fixed port keeps a bookmark to the UI working, and it keeps what the browser stores for that origin (the interface language, page size, sidebar state, preferred editor) from resetting when the port moves.

To move it:

```sh
coffer daemon port show          # configured port, and the port the daemon is on
coffer daemon port set 8765      # always bind 8765 from now on
coffer daemon restart            # apply it
coffer daemon port clear         # back to 8000
```

`set` accepts ports from 1024 to 65535. The setting is written to `~/.coffer/daemon-config.json`, which the daemon reads before it binds, so these commands work with no daemon running. That is on purpose: the state you most need to change the port from is a daemon that cannot start because its port is taken. For the same reason the port has no page in the web UI and no REST route.

A change applies at the next start. If a daemon is running on the old port, `set` and `clear` say so and tell you to run `coffer daemon restart`.

### When the port is taken

If the port is held by another process, the daemon refuses to start rather than binding a different port, and names what holds it:

```text
port 8000 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  python3 -m http.server 8000
  fix one of:
    stop that process, then    coffer daemon start
    use a different port       coffer daemon port set <port>
```

When the holder is itself a Coffer daemon, the message says so: most often it is your own daemon still starting up, so wait a few seconds and run `coffer daemon status`. If it serves a different vault (for example a test run under a throwaway `HOME`), the message gives you the `kill` command for it.

## Start the daemon at login (macOS)

Started on demand, the daemon is down exactly when an agent makes its first call of the day or a chat message arrives with no Coffer window open, and whoever asks first waits for a cold start. On macOS you can install it as a per-user launchd agent instead:

::: code-group

```sh [CLI]
coffer daemon service install     # start at login, restart after a crash
coffer daemon service status      # installed or not, and where
coffer daemon service uninstall   # stop starting it at login
```

```text [Web UI]
Settings → General → Coffer's daemon → Start at login
```

:::

The service is the plist `~/Library/LaunchAgents/dev.coffer.daemon.plist` (label `dev.coffer.daemon`). It:

- starts the daemon when you log in;
- restarts it **only after an unsuccessful exit**. A deliberate stop (`coffer daemon stop`, quitting from the desktop app, or a daemon standing down because another one superseded it) is left alone;
- carries your own `PATH`, read from your login shell at install time, so MCP servers launched with `npx` or `uvx` still resolve;
- runs `~/.coffer/bin/coffer-daemon`, the symlink that always points at the current build, so it keeps working across upgrades (a source install falls back to the Python module command);
- writes to the same `~/.coffer/logs/daemon.log` as every other start.

`uninstall` deletes the plist and leaves a running daemon running. Neither command needs a daemon. The web toggle does the same through the daemon and records a `daemon_residency_updated` audit entry; the CLI records none, because it must work when no daemon, and so no database, is available.

::: info
The login service is macOS only. On any other host, `service install` and `service uninstall` exit non-zero with a message, and `service status` reports that it is not supported.
:::

## Files the daemon reads and writes

| Path | What it is |
| --- | --- |
| `~/.coffer/daemon.json` | The discovery file every client reads: `version` (the file's schema), `pid`, `port`, `token`, `started_at`, `binary_path`. Mode `0600`, written atomically, removed when the daemon exits. A missing or malformed file means "no daemon". |
| `~/.coffer/daemon.lock` | The lock that keeps it to one daemon per vault. It stays on disk between runs; the lock lives on the open file, not on its existence. |
| `~/.coffer/daemon-config.json` | Machine-local settings read before the database opens: `port`, `features`, `machine_id`, `machine_name`, and the agents a switched-off `memory` feature withdrew its hook from. Mode `0600`. Never synced. |
| `~/.coffer/coffer.db` | The vault's SQLite database. |
| `~/.coffer/logs/` | Logs; see below. |
| `~/.coffer/bin/` | Deployed binaries (frozen builds only); see [Upgrades](#upgrades-and-rollback). |

The full layout is in [Files and directories](/reference/filesystem).

## Logs

Everything the daemon, the processes it spawns and the surfaces acting for it write goes to one file, so one timeline answers "what else happened around then":

```text
~/.coffer/logs/daemon.log        one JSON object per line for the daemon's own records
~/.coffer/logs/daemon.log.1..3   rotations (10 MB each, three kept)
~/.coffer/logs/shim-<pid>-<time>.log     one per coffer-mcp-shim process
~/.coffer/logs/upstream/<server>.log     each stdio MCP server's stderr
```

Shim logs and rolled-aside upstream logs older than seven days are pruned automatically. `daemon.log` and its rotations are never deleted, only rotated. Set `COFFER_LOG_DIR` in the daemon's environment to put the directory elsewhere.

You rarely need to open the file: the **Activity → Daemon** tab reads it with a level filter, and agents can read it through `coffer__diagnose`. See [Activity and audit](/guides/activity).

## The access token

The daemon mints a new random token on every start and writes it into `daemon.json`. Clients read it from there; the page the daemon serves to your browser carries it too, so a plain reload after a restart is authenticated again with no action from you.

To rotate it without restarting:

```sh
coffer daemon rotate-token
```

Clients that read `daemon.json` pick up the new value; an open browser tab needs a reload.

## Upgrades and rollback

A frozen build (the desktop app or the release archive) deploys its own binaries at every start. Each version gets its own directory, and the public names are symlinks into it:

```text
~/.coffer/bin/coffer           -> 0.2.0/coffer
~/.coffer/bin/coffer-daemon    -> 0.2.0/coffer-daemon
~/.coffer/bin/coffer-mcp-shim  -> 0.2.0/coffer-mcp-shim
~/.coffer/bin/0.2.0/           the build now in use
~/.coffer/bin/0.1.1/           the previous build, kept for rollback
```

Files are copied atomically and the symlinks are flipped atomically, so an agent launching `coffer-mcp-shim` mid-upgrade never sees a half-written binary. The two newest version directories are kept; older ones are pruned. A link for a binary the new build no longer ships is removed.

The daemon outlives the CLI and shim processes that attach to it, so after installing a new version the old daemon may still be the one answering. Every client compares versions and warns, then carries on:

```text
coffer: WARNING: attached to a Coffer daemon at version 0.1.1 (/Users/you/.coffer/bin/0.1.1/coffer-daemon) but this coffer is 0.2.0; run `coffer daemon restart` to serve the current build
```

Run `coffer daemon restart` and the warning goes away. The desktop app shows the same situation as a **Daemon out of date** notice with a **Restart daemon** button.

To roll back to the previous build:

1. Stop the daemon: `coffer daemon stop`.
2. Point the links back at the older directory:
   ```sh
   cd ~/.coffer/bin
   for b in coffer coffer-daemon coffer-mcp-shim; do ln -sfn 0.1.1/$b $b; done
   ```
3. If the newer build migrated the database, restore the copy it took first (next section). Otherwise the older build refuses to open it.
4. Start again: `coffer daemon start`.

## Database migrations and automatic backups

Schema migrations run when the daemon starts. Before a migration changes an on-disk `coffer.db`, the daemon copies it (with its `-wal` and `-shm` companions) beside the original as `coffer.db.pre-<revision>`, where `<revision>` is the schema revision the file was at. The three newest copies are kept. Nothing is copied when the schema is already current, which is every start except the first one after an upgrade.

To go back to a pre-migration copy:

```sh
coffer daemon stop
cd ~/.coffer
mv coffer.db coffer.db.broken
cp coffer.db.pre-0103 coffer.db          # and the -wal / -shm files, if present
```

Then start the build that matches that schema.

### DB_SCHEMA_TOO_NEW

If the database was migrated by a newer build, or by a development branch whose migrations this build does not ship, the daemon stops at startup with:

```text
database schema revision '0105' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove ~/.coffer/coffer.db to start fresh.
```

Install the newer build again, or restore the `coffer.db.pre-*` copy taken before that build migrated it.

## Back up a vault

Everything Coffer holds is under `~/.coffer`. The parts that cannot be rebuilt are:

| Path | Why it matters |
| --- | --- |
| `coffer.db` (+ `-wal`, `-shm`) | Every resource, setting, conversation and log table. |
| `master.key` | The key that decrypts every stored credential. It is absent if you moved the key to the OS keychain (**Settings → Security**). |
| `knowledge/` | Your knowledge collections. |
| `skills/` | The master skill store. |

`memory/` is derived from your agents' own memory files and can be regenerated. To take a consistent copy, stop the daemon first:

```sh
coffer daemon stop
cp -R ~/.coffer ~/coffer-backup-$(date +%F)
coffer daemon start
```

::: warning
A backup that includes `master.key` can decrypt every credential in it. Store it like a password. A backup without the key keeps the credentials as ciphertext nobody can read.
:::

If you run Coffer on several machines, [vault sync](/guides/vault-sync) keeps a history of the vault's documents in a git repository you own, which doubles as an off-machine backup of knowledge, skills and resource definitions.

## Agent home variables are not inherited

If you start the daemon from a shell that exports `CLAUDE_CONFIG_DIR` or `CODEX_HOME`, the daemon removes them from its own environment at start and logs which ones it removed. Otherwise every agent it spawned would run against that directory while Coffer delivers skills and configuration into the agent's registered one. An agent registered with a custom configuration directory gets that directory in its own variable when Coffer spawns it. See [Agents](/guides/agents).

## How it works

Detect-or-spawn, the discovery file, supersession and the graceful exit path are described in [Daemon and processes](/architecture/daemon). Release packaging and the binary layout are in [Distribution and releases](/architecture/distribution).

## Related

- [Troubleshooting](/guides/troubleshooting)
- [Activity and audit](/guides/activity)
- [Experimental features](/guides/experimental-features)
- [Desktop app](/guides/desktop-app)
- [CLI reference](/reference/cli)
- Spec: [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md) · Decision: [Detect-or-Spawn](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md)
