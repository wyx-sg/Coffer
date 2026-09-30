## ADDED Requirements

### Requirement: Restart itself on request
A page in a browser is served by the daemon, so it cannot stop the daemon and
start another from outside the way the desktop shell and `coffer daemon restart`
do; restarting is Coffer's own deterministic work, so the daemon MUST restart
itself on the token-gated `POST /api/v1/daemon/restart`. It MUST be a true
restart, in this order: the daemon starts a successor — the same command every
surface spawns, detached, with the daemon's own environment and the pid it
succeeds — and only then answers `202` with the port the successor binds (the
pre-bind config's, so a port saved on Settings → Daemon applies), and only
after the answer is sent takes the one graceful exit of "Shut down through one
graceful exit path". The successor MUST wait for that pid to have exited before
it takes the spawn lock or binds anything, and then starts as any daemon
starts — the same detect-or-spawn lock and liveness probe — so a predecessor
that never exits makes the successor stand down as "already running" rather
than start a second daemon. A successor that cannot be started MUST answer an
error and leave the daemon serving. A second request while a restart is under
way MUST NOT start a second successor. The frozen one-file build MUST start its
successor as a new instance of itself, so the successor never relies on the
predecessor's unpacked files. A restart is recorded as a `daemon_restarted`
audit entry naming the port and the successor's pid. The successor mints a new
token, as every start does; the page reloads from the successor's origin to
receive it.

The mechanism is the same however the daemon was started — by a surface's
detached spawn, by the desktop shell or by the login service: the login
service restarts only an exit that failed, so it is not asked to restart a
deliberate one. `coffer daemon restart` keeps its own stop-then-start from
outside, because it must also work when the daemon is wedged or not running and
no route answers.

#### Scenario: a restart asked from the web ui starts a successor
- **GIVEN** a running daemon whose pre-bind config names port 8123
- **WHEN** an authenticated `POST /api/v1/daemon/restart` arrives
- **THEN** the daemon starts its successor first, answers 202 with port 8123, and only then exits gracefully
- **AND** a `daemon_restarted` audit entry records the port and the successor's pid, and a second request starts no second successor

#### Scenario: a successor that cannot start leaves the daemon serving
- **GIVEN** a running daemon whose successor cannot be started
- **WHEN** an authenticated `POST /api/v1/daemon/restart` arrives
- **THEN** it answers an error, does not exit, and records no restart

#### Scenario: the successor binds only after its predecessor has exited
- **GIVEN** a successor started by a restart, naming the pid of the daemon it succeeds
- **WHEN** it starts while that daemon is still exiting
- **THEN** it waits until that pid is gone before taking the spawn lock or binding, and gives up waiting after a bounded time so the ordinary liveness check decides
- **AND** nothing it spawns inherits the predecessor's pid

### Requirement: Hand an upgrade of Coffer to an agent
The desktop shell checks for and installs updates itself. A browser has
nothing to install with, and how a copy of Coffer is upgraded depends on how it
was installed, so the daemon MUST answer the token-gated
`GET /api/v1/daemon/upgrade` with the install method it detects — `binaries`
(the installer's or a release archive's frozen binaries), `app` (the macOS
desktop app) or `source` (a source checkout) — and a `handoff` prompt for the
person's agent. The prompt MUST name the running version and release channel,
the install method with the daemon's executable (and the checkout for a source
run), the machine, and the install page's Upgrade section, and MUST tell the
agent to keep `~/.coffer` exactly as it is, to restart the daemon, and to
confirm with `coffer --version` and `coffer daemon status` that both report the
new version. It carries the standing rules of every hand-off.

#### Scenario: the upgrade hand-off names how this copy was installed
- **GIVEN** a daemon running Coffer 0.3.1 on the stable channel from the installer's frozen binaries
- **WHEN** `GET /api/v1/daemon/upgrade` is read
- **THEN** the answer's install method is `binaries` and its prompt names 0.3.1, the stable channel, the executable, the machine and the install page's `#upgrade` section
- **AND** the prompt says to keep `~/.coffer` and to verify with `coffer --version` and `coffer daemon status`
