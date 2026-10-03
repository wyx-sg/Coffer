## MODIFIED Requirements

### Requirement: Bind a fixed, settable port
The daemon's listening port MUST be **fixed by default and settable**, so a browser bookmark to
Coffer's UI keeps working across restarts. With nothing configured the daemon MUST bind exactly
`8000` and MUST NOT scan for an alternative; a drifting origin is not merely a broken bookmark,
because browser `localStorage` is keyed by origin, so the UI language, sidebar state, page size and
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
prints the configured port or the 8000 default, `coffer config set daemon.port <n>` pins one, and
`coffer config unset daemon.port` returns to 8000. Those three MUST read and write the pre-bind file
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
the shim, and the memory delivery hook runs `coffer memory hook` (an internal entry point, hidden from help), and both find the daemon through
`daemon.json` when they run rather than naming a port, so every agent reconnects without a manual
step. This setting is deliberately outside the audit obligation every kind inherits: it is
neither a resource nor a capability but process configuration read before the database opens, and
the CLI that owns it must work with no daemon running — so the audit table is unreachable on
exactly the path that matters most, and recording a change only when a daemon happens to be up
would be less honest than recording none.

#### Scenario: the daemon binds the same port every start
- **GIVEN** no port has been configured, so the daemon's default of 8000 applies,
- **WHEN** the daemon is stopped and started again — by the user, by the CLI, or auto-spawned by an MCP shim, which inherits no shell profile,
- **THEN** it binds 8000 every time and records it in `~/.coffer/daemon.json`, so a browser bookmark to Coffer's UI keeps working and nothing the browser stored against that origin is lost.

#### Scenario: a configured daemon port survives restarts
- **GIVEN** the user has moved the daemon's port with `coffer config set daemon.port <n>`,
- **WHEN** the daemon is stopped and started again by any of those routes,
- **THEN** it binds that same port every time and records it in `~/.coffer/daemon.json`.

#### Scenario: a port that is taken refuses to start and says what holds it
- **GIVEN** the port the daemon would bind — its 8000 default, or one the user configured — is already held by another process,
- **WHEN** the daemon starts,
- **THEN** it refuses to start rather than binding a different port, and the message names the process holding the port and the commands that resolve it — free that process, or `coffer config set daemon.port <other>`.

#### Scenario: the port key is read and changed with no daemon running
- **GIVEN** no daemon is running and no port has been configured,
- **WHEN** the user runs `coffer config get daemon.port`, then `coffer config set daemon.port 8123`, then `coffer config get daemon.port`, then `coffer config unset daemon.port`,
- **THEN** the first prints the 8000 default, the set writes 8123 into `~/.coffer/daemon-config.json`, the second get prints 8123, and the unset leaves the file carrying no port so the default applies again,
- **AND** no daemon is spawned, no database is opened and no audit entry is recorded.

#### Scenario: a port set from the settings page is pending until restart
- **GIVEN** a running daemon on port 8000
- **WHEN** `PUT /api/v1/daemon/port` is sent with 8123, and then with a port another process holds
- **THEN** the first answers that 8123 is pending, `~/.coffer/daemon-config.json` carries 8123 and the daemon still answers on 8000
- **AND** the second is refused naming the process that holds the port, and the file is unchanged

#### Scenario: after a restart on a new port every agent reconnects
- **GIVEN** a daemon configured for 8123 while answering on 8000, and Claude Code and Codex connected to Coffer
- **WHEN** the daemon is restarted
- **THEN** it binds 8123 and records it in `~/.coffer/daemon.json`, each agent's Coffer MCP entry and delivery hook name no port and are left as they are, and the discovery the CLI, an MCP shim and the hook share finds the daemon on 8123

### Requirement: Report what Coffer stores and clear the rebuildable cache
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the four kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history and how many versions it holds; no version count before the repository has been created), the
**local content** (chat uploads and channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size) and the **rebuildable cache** (the memory tree and the transcript summary cache under
`~/.coffer/derived/`, and their size). Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

`POST /api/v1/storage/cache/clear` MUST delete the files of the memory tree and of the transcript
summary cache, and nothing else: no vault, local content, history or other file
under `derived/`, and no partition row, so the next memory update rebuilds each partition from the
agents' own memory. It MUST be refused (`UPKEEP_ALREADY_RUNNING`) while a memory pass is running,
because that pass is writing into the tree, and MUST record the clear in the audit log with the
bytes freed.

#### Scenario: the storage summary reports the four kinds
- **GIVEN** a vault repository of three commits, chat and channel media, a database with its WAL, a memory tree and a transcript summary cache
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, the local content with both media locations under `~/.coffer/content` and their size, the history as `runs.db` with its WAL, and the cache as the size of the memory tree and the transcript cache
- **AND** before the vault repository has been created it reports the vault with no version count

#### Scenario: clearing the cache leaves everything else
- **GIVEN** a memory tree, a transcript summary cache, a knowledge document in the vault, chat media, a sync round's hand-merge copy and the database
- **WHEN** `POST /api/v1/storage/cache/clear` is called
- **THEN** the memory tree and the transcript cache are empty, everything else is untouched, the answer carries the bytes freed and the audit log records the clear
- **AND** while a memory pass is running the clear is refused and nothing is deleted
