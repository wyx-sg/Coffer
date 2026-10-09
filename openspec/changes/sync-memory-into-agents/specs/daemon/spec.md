## MODIFIED Requirements

### Requirement: Manage the daemon from the command line
Users MUST be able to run `coffer daemon start`, `stop`, `restart` and `status [--json]`, with the daemon down or wedged. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the spawned daemon to **answer its status call** — a published
`daemon.json` is not that, because the file is written before the daemon has finished starting and a
stale one left by a crash is there before it has started at all. A daemon that exits before it
answers (git is too old, say) MUST be reported as failed with a pointer to
`daemon.log`, never as started. That pre-flight
check MUST be allowed to report "free" when the port is not — a port in `TIME_WAIT` from the daemon
a `restart` has just stopped is bindable and must not be called a conflict — and MUST never err the
other way: a missed conflict resolves downstream as "already running", while a false one blocks a
legitimate start. `stop` MUST confirm the recorded pid is still a Coffer daemon before signalling
it, and MUST clean up the stale discovery file instead when it is not; it MUST give the daemon the
graceful-stop period (15 s) to exit and, when it does not, say so and point at `restart`. `restart`
is `stop` then `start`, and is how a setting read before the bind takes effect; a daemon that does
not exit within the period is forced out (see "Force out a wedged daemon on an explicit restart"). `status` MUST only look: with no
daemon answering — no `daemon.json`, or one whose port nothing answers on — it MUST report the
daemon as not running (`{"status": "stopped"}` under `--json`) and exit non-zero, and MUST NOT
start one. With a daemon answering, `status` MUST also report the passes in flight — the list
[resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"
defines, each with its kind, its target and when it started — in its own section of the table form,
which says so when nothing is running, and as part of the object under `--json`. It MUST also list
every other daemon process serving the same vault — a start still booting or waiting on the lock,
or a stray — by pid (`other_daemon_pids` under `--json`), counting a one-file daemon's bootloader
and child once and never the model proxy, because one serving daemon is the rule and an extra one
is otherwise hard to tell apart from the processes a one-file build always shows. The daemon port is
read and changed with `coffer config get|set|unset daemon.port`, which MUST work with no daemon
running (see "Bind a fixed, settable port").

#### Scenario: start reports a daemon that refused to start
- **GIVEN** a stale `~/.coffer/daemon.json` and a vault the daemon refuses to open
- **WHEN** the user runs `coffer daemon start`
- **THEN** the command exits non-zero saying the daemon exited at startup and pointing at `daemon.log`, and does not print that the daemon started

#### Scenario: a recorded pid that is not ours is never signalled
- **GIVEN** a `~/.coffer/daemon.json` whose recorded pid has been recycled onto an unrelated process,
- **WHEN** the user runs `coffer daemon stop`,
- **THEN** no signal is sent to that process; the stale discovery file is removed instead, and the command says so.

#### Scenario: status reports a stopped daemon without starting one
- **GIVEN** no daemon is running,
- **WHEN** the user runs `coffer daemon status`, or `coffer daemon status --json`,
- **THEN** it reports the daemon as not running (`{"status": "stopped"}` under `--json`) and exits non-zero,
- **AND** no daemon is spawned and no `daemon.json` is written.

#### Scenario: status names the passes in flight
- **GIVEN** a running daemon with two passes under way, one of them over a knowledge collection,
- **WHEN** the user runs `coffer daemon status --json`, and again `coffer daemon status` once both passes have ended,
- **THEN** the JSON reports the daemon as ready and lists both passes with their kind, target and start time, oldest first,
- **AND** the later table form carries a passes section saying that no pass is running, and neither call starts a pass.

#### Scenario: status names other daemon processes of the vault
- **GIVEN** a serving daemon and a second daemon process of the same vault still starting,
- **WHEN** the user runs `coffer daemon status --json`,
- **THEN** `other_daemon_pids` lists the second process's pid and not the serving daemon's,
- **AND** the table form names it on its own line.

### Requirement: Bind a fixed, settable port
The daemon's listening port MUST be **fixed by default and settable**, so a browser bookmark to
Coffer's UI keeps working across restarts. With nothing configured the daemon MUST bind exactly
`38470` and MUST NOT scan for an alternative; a drifting origin is not merely a broken bookmark,
because browser `localStorage` is keyed by origin, so the UI language, sidebar state and
preferred editor silently reset when the port moves and nothing connects the two events for the
user.

The setting MUST live in a file the daemon reads **before** it binds — `~/.coffer/daemon-config.json`,
mode `0600`, merged rather than replaced and surviving shutdown — because the port is chosen before
the database is opened and before migrations run, so no database-backed setting can carry it. It
MUST NOT be an environment variable: the daemon is spawned detached by whichever surface first
needs one, inheriting that caller's environment, which a shell profile does not reach and a
GUI-launched agent never had.

When a port is configured the daemon MUST bind exactly that port and MUST NOT fall back to another
— silently moving is the behaviour the setting exists to stop. When it cannot be bound the daemon
MUST refuse to start and MUST report which process holds the port and the exact commands that
resolve it. A config file that will not parse MUST warn and fall back to the default rather than
stopping the boot, since an unbootable daemon cannot be repaired from the UI it serves.

Users MUST be able to read and change the setting **from the CLI** as the key `daemon.port` of the
generic `coffer config` command ([resource-framework](../resource-framework/spec.md): one key
registry, typed validation, `unset` returns a key to its default) — `coffer config get daemon.port`
prints the configured port or the 38470 default, `coffer config set daemon.port <n>` pins one, and
`coffer config unset daemon.port` returns to 38470. Those three MUST read and write the pre-bind file
directly and MUST work with no daemon running, because a daemon that cannot bind its port is exactly
the state the setting has to be fixable from — the CLI stays the escape hatch where a squatted port
is diagnosed. The running daemon MUST also accept a new port from the web UI's Settings → Daemon,
through `PUT /api/v1/daemon/port`: the value MUST be a whole number from 1024 to 65535 and a port no
other process holds — the port the daemon itself answers on counts as free — and is otherwise
refused with the reason, naming the holder of a taken port. The route MUST write the pre-bind file
exactly as `coffer config set daemon.port` does and answer that the change is pending: the daemon
keeps answering on its current port. A change takes effect at the next start, which
`coffer daemon restart` — or Restart now on Settings → Daemon, which is the desktop shell's restart
in the shell and the daemon's own ("Restart itself on request") in a browser — applies in one step. After a restart on a
new port the daemon records it in `~/.coffer/daemon.json`, so the desktop shell, the CLI and the MCP
shim find it by the discovery file as they find any daemon, and no agent's configuration needs a
rewrite: Coffer's MCP entry in an agent's config runs
the shim, which finds the daemon through
`daemon.json` when it runs rather than naming a port, so every agent reconnects without a manual
step. This setting is deliberately outside the audit obligation every kind inherits: it is
neither a resource nor a capability but process configuration read before the database opens, and
the CLI that owns it must work with no daemon running — so the audit table is unreachable on
exactly the path that matters most, and recording a change only when a daemon happens to be up
would be less honest than recording none.

#### Scenario: the daemon binds the same port every start
- **GIVEN** no port has been configured, so the daemon's default of 38470 applies,
- **WHEN** the daemon is stopped and started again — by the user, by the CLI, or auto-spawned by an MCP shim, which inherits no shell profile,
- **THEN** it binds 38470 every time and records it in `~/.coffer/daemon.json`, so a browser bookmark to Coffer's UI keeps working and nothing the browser stored against that origin is lost.

#### Scenario: a configured daemon port survives restarts
- **GIVEN** the user has moved the daemon's port with `coffer config set daemon.port <n>`,
- **WHEN** the daemon is stopped and started again by any of those routes,
- **THEN** it binds that same port every time and records it in `~/.coffer/daemon.json`.

#### Scenario: a port that is taken refuses to start and says what holds it
- **GIVEN** the port the daemon would bind — its 38470 default, or one the user configured — is already held by another process,
- **WHEN** the daemon starts,
- **THEN** it refuses to start rather than binding a different port, and the message names the process holding the port and the commands that resolve it — free that process, or `coffer config set daemon.port <other>`.

#### Scenario: the port key is read and changed with no daemon running
- **GIVEN** no daemon is running and no port has been configured,
- **WHEN** the user runs `coffer config get daemon.port`, then `coffer config set daemon.port 8123`, then `coffer config get daemon.port`, then `coffer config unset daemon.port`,
- **THEN** the first prints the 38470 default, the set writes 8123 into `~/.coffer/daemon-config.json`, the second get prints 8123, and the unset leaves the file carrying no port so the default applies again,
- **AND** no daemon is spawned, no database is opened and no audit entry is recorded.

#### Scenario: a port set from the settings page is pending until restart
- **GIVEN** a running daemon on port 38470
- **WHEN** `PUT /api/v1/daemon/port` is sent with 8123, and then with a port another process holds
- **THEN** the first answers that 8123 is pending, `~/.coffer/daemon-config.json` carries 8123 and the daemon still answers on 38470
- **AND** the second is refused naming the process that holds the port, and the file is unchanged

#### Scenario: after a restart on a new port every agent reconnects
- **GIVEN** a daemon configured for 8123 while answering on 38470, and Claude Code and Codex connected to Coffer
- **WHEN** the daemon is restarted
- **THEN** it binds 8123 and records it in `~/.coffer/daemon.json`, each agent's Coffer MCP entry names no port and is left as it is, and the discovery the CLI and an MCP shim share finds the daemon on 8123

### Requirement: Report what Coffer stores
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the three kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history and how many versions it holds; no version count before the repository has been created), the
**local content** (channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size together with the log directory's, `~/.coffer/logs/` unless `COFFER_LOG_DIR` names
another, and with the skills' working files in `~/.coffer/skill-data/` and the config backups in `~/.coffer/config-backups/`). Coffer keeps no cache the user clears: what is under
`~/.coffer/derived/` is rebuilt by the daemon on its own and is not reported. Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

#### Scenario: the storage summary reports the three kinds
- **GIVEN** a vault repository of three commits, channel media, and a database with its WAL
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, the local content with the channel media location under `~/.coffer/content` and its size, the history as `runs.db` with its WAL plus the log directory, `skill-data` and `config-backups`, and no cache
- **AND** before the vault repository has been created it reports the vault with no version count

### Requirement: Uninstall Coffer from this machine
`POST /api/v1/daemon/uninstall` MUST remove what Coffer wrote outside
`~/.coffer` and then stop the daemon, so uninstalling is one action instead of a
list of manual steps. In order, it MUST take the model-provider routing out of
every agent's settings, disconnect every agent (its MCP entry),
remove every skill link Coffer delivered with its delivery records, keep any
reconcile pass from restoring them, remove the start-at-login job, remove the
terminal launch files Coffer wrote, remove the installer's `PATH` lines (the
`# Added by Coffer installer` marker and the line after it) from the shell
profiles, and delete `~/.coffer/bin`. Each step MUST be attempted even when an
earlier one failed, and the answer MUST list every step as done, nothing to do,
or failed with its reason. The vault, the settings, the skills' own folders and
the history MUST stay, so installing Coffer again finds them.

With `delete_data`, the request MUST carry a presence grant for the operation
`uninstall` over the target `delete-data`, redeemed before anything changes; an
unverified grant MUST refuse the whole request. After the daemon has stopped
serving and released its lock, it MUST then delete the master key's Keychain
items and `~/.coffer`.

`coffer uninstall` MUST run the same. With the desktop app installed it MUST
open the app's uninstall dialog instead, where the person confirms. Otherwise it
MUST ask before uninstalling, unless `--yes` is given; `--delete-data` MUST ask
for the words `delete my data` at an interactive terminal — no flag skips that,
and without a terminal it MUST refuse — and deletes `~/.coffer` only after the
daemon has exited. The command line MUST NOT touch the Keychain, which only the
daemon owns: it MUST say that the master key's Keychain items stay.

#### Scenario: uninstall removes every footprint and keeps the vault
- **GIVEN** a connected agent with a provider switch, two delivered skills, start at login on and the installer's `PATH` line in `~/.zshrc`
- **WHEN** `POST /api/v1/daemon/uninstall` is called without `delete_data`
- **THEN** the agent's MCP entry and provider keys are gone, the skill links are gone, the launch agent is gone, the `PATH` line and its marker are gone and `~/.coffer/bin` is gone
- **AND** the answer lists each step and the daemon stops, while `~/.coffer/vault` is unchanged

#### Scenario: deleting the data needs a presence grant
- **GIVEN** a running daemon
- **WHEN** `POST /api/v1/daemon/uninstall` is called with `delete_data` and no valid grant
- **THEN** it is refused and nothing is removed

#### Scenario: the command line will not delete the data without a terminal
- **GIVEN** no desktop app installed
- **WHEN** `coffer uninstall --delete-data --yes` runs with no interactive terminal
- **THEN** it refuses, and nothing is removed

## RENAMED Requirements

- FROM: `### Requirement: Report what Coffer stores and clear the rebuildable cache`
- TO: `### Requirement: Report what Coffer stores`
