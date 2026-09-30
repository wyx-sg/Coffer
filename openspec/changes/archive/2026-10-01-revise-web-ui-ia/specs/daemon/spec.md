## ADDED Requirements

### Requirement: Report the state the shell shows
The daemon's state MUST be visible to the user while starting it stays automatic. Every fact the
web UI's shell footer, its Settings → Daemon tab and its About tab show about the daemon —
lifecycle phase, bound port, start time, version, executable, release channel, process id, the
commit a release build was stamped with, Coffer's data folder and how many agents carry Coffer's
connection — MUST come from
`GET /api/v1/daemon/status` (see "Answer the status probe without a token"), so the page can show a
daemon's state without a token and without a route of its own, and so the footer, the Daemon tab,
`coffer daemon status` and the desktop shell's version check all read one answer. The one daemon
setting those surfaces also show, whether it starts at login, comes from
`GET /api/v1/daemon/residency` (see "Change residency from the settings page or the command
line"). Showing the state MUST NOT move starting the daemon onto the user: every surface that needs
a daemon and finds none still starts one itself (see "Spawn a detached daemon from any surface that
needs one").

#### Scenario: the status probe carries what the shell shows
- **GIVEN** a running daemon,
- **WHEN** `GET /api/v1/daemon/status` is called with no token,
- **THEN** the response carries the phase, port, start time, version, executable, channel, pid, commit, data folder and connected-agent count the shell footer, Settings → Daemon and About show,
- **AND** `coffer daemon status --json` reports the same version, channel and port.

### Requirement: Report what Coffer stores and clear the rebuildable cache
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the four kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history, how many versions it holds, when and by which writer its newest version was made, and
whether a sync remote is set; no version count before the repository has been created), the
**local content** (chat uploads and channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size) and the **rebuildable cache** (the memory tree and the transcript summary cache under
`~/.coffer/derived/`, and their size). Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

`POST /api/v1/storage/cache/clear` MUST delete the files of the memory tree and of the transcript
summary cache, and nothing else: no vault, local content, history, memory trigger or other file
under `derived/`, and no partition row, so the next memory update rebuilds each partition from the
agents' own memory. It MUST be refused (`UPKEEP_ALREADY_RUNNING`) while a memory pass is running,
because that pass is writing into the tree, and MUST record the clear in the audit log with the
bytes freed.

#### Scenario: the storage summary reports the four kinds
- **GIVEN** a vault repository of three commits, chat and channel media, a database with its WAL, a memory tree and a transcript summary cache, and no sync remote set
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, its newest version's time and writer and no sync remote, the local content with both media locations under `~/.coffer/content` and their size, the history as `runs.db` with its WAL, and the cache as the size of the memory tree and the transcript cache
- **AND** before the vault repository has been created it reports the vault with no version count

#### Scenario: clearing the cache leaves everything else
- **GIVEN** a memory tree, a transcript summary cache, a knowledge document in the vault, chat media, a memory trigger, a sync round's hand-merge copy and the database
- **WHEN** `POST /api/v1/storage/cache/clear` is called
- **THEN** the memory tree and the transcript cache are empty, everything else is untouched, the answer carries the bytes freed and the audit log records the clear
- **AND** while a memory pass is running the clear is refused and nothing is deleted

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
the shim, and the memory delivery hook runs `coffer memory hook`, and both find the daemon through
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

### Requirement: Serve the daemon log tail normalised
`GET /api/v1/daemon/logs` MUST return the tail of that file, newest-first, guarded by the token even
though `/daemon/status` on the same router is not: a readiness probe is public, log contents are
not. It MUST accept `since`, a severity floor (`level`), the older `errors_only` boolean, and a
bounded `limit`, and MUST read from the tail rather than the head so a large file is never pulled
into memory whole. Every record MUST carry the timestamp, level and logger its line actually
stated, whichever writer produced it; escape sequences MUST be stripped; continuation lines such as
a traceback MUST ride with the record that raised them; and a line no format fits MUST be kept whole
rather than dropped, because it is often the interesting one. The answer MUST also carry `path`,
the absolute path of the file the tail was read from — also when that file does not exist yet — so
the Activity page's Daemon log tab can name the file it shows and open it through
`POST /api/v1/fs/open`.

`coffer log daemon [--since <when>] [--errors] [--limit <n>] [--json]` MUST read the same tail
through that route — the one the Activity page reads — so a terminal sees the same normalised
records the page shows: `--since` and `--limit` pass through, `--errors` narrows to errors, the
table form prints one record per entry with its time, level, logger and message, and `--json`
prints the records as the route returns them. A refusal from the route MUST be printed with the
route's error and a non-zero exit.

#### Scenario: the daemon log tail reads every writer's format
- **GIVEN** a `daemon.log` holding Coffer's own structured JSON, a uvicorn line, a `LEVEL - logger - message` line from an upstream, a colour-escaped line from an upstream, and a multi-line traceback,
- **WHEN** `GET /api/v1/daemon/logs` is called with a token,
- **THEN** the response is newest-first and bounded by `limit`, every record carries the time, level and logger its line actually stated, escape sequences are stripped, the traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped,
- **AND** `level` and `since` narrow the window, while the same call with no token is rejected even though `/daemon/status` on the same router is open.

#### Scenario: the daemon log tail names the file it read
- **GIVEN** a daemon whose log directory holds `daemon.log`, and one whose log directory holds none yet
- **WHEN** `GET /api/v1/daemon/logs` is called with a token on each
- **THEN** both answers carry `path`, the absolute path of that directory's `daemon.log`, the second with no records

#### Scenario: the command line reads the daemon log tail
- **GIVEN** a running daemon whose `daemon.log` holds an info record, an error record carrying a traceback, and a record older than one hour,
- **WHEN** the user runs `coffer log daemon --json --since 1h`, then `coffer log daemon --errors --limit 1`,
- **THEN** the first prints, newest-first, the two recent records exactly as `GET /api/v1/daemon/logs` returns them for that window, the older record absent,
- **AND** the second prints only the error record, with its traceback riding with it.
