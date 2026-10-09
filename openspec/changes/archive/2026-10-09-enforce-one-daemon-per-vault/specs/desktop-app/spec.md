## MODIFIED Requirements

### Requirement: Restart by stopping the running daemon first
Restart MUST be a true restart: when a daemon is responsive it MUST be asked to shut down over its token-gated shutdown route and the port MUST be observed free before a replacement is spawned. A restart that silently became a no-op would do nothing at exactly the moment a user reaches for it — a wedged-but-listening daemon, whose old process still holds the port — and a failure to free the port MUST be reported rather than followed by a spawn that cannot bind. A daemon that does not answer, or answers the shutdown request but keeps its port, is wedged: the restart MUST force it out — signal the pid `~/.coffer/daemon.json` records once its command line shows a Coffer daemon, and kill it when it does not exit — before spawning (spec [daemon](../daemon/spec.md) "Force out a wedged daemon on an explicit restart"), rather than spawn a replacement beside it. The same restart MUST run whichever place it was chosen from: the tray, the offline banner or the web UI's Settings → Daemon tab.

A restart MUST wait for its replacement to answer and return that daemon's connection with the result — read from the daemon's discovery file while waiting, never carried over from the daemon it stopped, so a restart that moves the daemon to a port saved in Settings → Daemon (spec [daemon](../daemon/spec.md) "Bind a fixed, settable port") reconnects the shell on that port — and the page MUST install what it is handed rather than run a handshake of its own — a page that asked again the instant the restart returned asked before the new daemon had bound anything, and the handshake's cold-start branch answered by spawning a rival for it.

#### Scenario: a restart stops the running daemon before spawning a replacement
- **GIVEN** a daemon that is listening but not serving usefully,
- **WHEN** the user chooses restart from the tray, the offline banner or Settings → Daemon,
- **THEN** the shell asks the running daemon to shut down over its token-gated route, waits for the port to free, and only then spawns a replacement,
- **AND** a restart that cannot free the port reports that rather than appearing to succeed.

#### Scenario: a restart onto a changed port reconnects the shell to the new port
- **GIVEN** a port saved on Settings → Daemon, so the replacement binds a different port from the daemon being stopped,
- **WHEN** the user presses Restart now in the desktop shell,
- **THEN** the shell stops the daemon on the old port, then reads `~/.coffer/daemon.json` afresh while it waits and answers only when the daemon the file names responds,
- **AND** the base URL and token it returns name the new port, which the page installs, so the window is connected to the daemon on the new port without relaunching the app

#### Scenario: a restart hands back the connection it waited for
- **GIVEN** the user restarts the daemon from the tray, the offline banner or Settings → Daemon,
- **WHEN** the replacement starts answering,
- **THEN** the shell returns its base URL and token alongside the new PID,
- **AND** the page installs those rather than running a second handshake, so the restart starts exactly one daemon.

#### Scenario: a restart forces out a daemon that will not stop
- **GIVEN** a daemon that does not answer its status call, or that answers the shutdown request but keeps its port,
- **WHEN** the user chooses restart from the tray, the offline banner or Settings → Daemon,
- **THEN** the shell ends the daemon process `~/.coffer/daemon.json` records and waits for the port to free before spawning a replacement,
- **AND** a discovery file that names no live Coffer daemon is not acted on, and the restart goes straight to spawning.
