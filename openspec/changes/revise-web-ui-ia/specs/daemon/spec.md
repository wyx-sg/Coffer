## ADDED Requirements

### Requirement: Report the state the shell shows
The daemon's state MUST be visible to the user while starting it stays automatic. Every fact the
web UI's shell footer and its Settings → Daemon tab show about the daemon — lifecycle phase, bound
port, start time, version, executable and release channel — MUST come from
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
- **THEN** the response carries the phase, port, start time, version, executable and channel the shell footer and Settings → Daemon show,
- **AND** `coffer daemon status --json` reports the same version, channel and port.

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
`coffer daemon restart` — or the desktop shell's Restart — applies in one step. After a restart on a
new port the daemon records it in `~/.coffer/daemon.json`, so the desktop shell, the CLI and the MCP
shim find it by the discovery file as they find any daemon, and the first reconcile after the
start MUST re-project every connected agent's Coffer entries that name the daemon's address — its
MCP entry and its memory delivery hook — to the new port, so every agent reconnects without a
manual step. This setting is deliberately outside the audit obligation every kind inherits: it is
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
- **THEN** it binds 8123 and records it in `~/.coffer/daemon.json`, the first reconcile rewrites each agent's Coffer MCP entry and delivery hook to 8123, and the desktop shell, the CLI and an MCP shim reach the daemon on 8123
