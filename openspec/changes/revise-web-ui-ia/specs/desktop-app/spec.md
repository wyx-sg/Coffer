## MODIFIED Requirements

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Three host-conditional affordances are sanctioned, all reached through the secret supplier's module, because only the shell can offer them: the Restart control, the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"), and the update check and install (see "Check for updates against a signed release manifest"). The first two are each rendered in exactly two places — the offline banner and the web UI's Settings → Daemon tab — and the shell footer reads the skew check's answer to show its version warning; in a browser, the same two places name the `coffer daemon start` or `coffer daemon restart` command instead of a Restart control. The update check and install are rendered in one place, the web UI's Settings › About tab; in a browser that tab says updates are installed by the desktop app and offers no control. Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with. One host-conditional report is sanctioned beside them, in the same module and rendering nothing: the page tells the shell its interface language so the tray can be labelled in it (see "Host the UI locally in an application window"); outside the shell it does nothing, since a browser has no tray.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the secret supplier, the offline banner, the Settings → Daemon tab, the Settings › About tab and the shell footer — which carry the Restart control, the version-skew warning, the skew check's answer, or the update check — no frontend module branches on whether it is running inside the shell.

### Requirement: Find or start a daemon by a fixed resolution order
The shell MUST locate a daemon by a fixed resolution order — a live daemon named by `~/.coffer/daemon.json`, then its own bundle, then `~/.coffer/bin/`, then `PATH` — taking over an already-running daemon rather than spawning a second one. The liveness probe MUST come first: the other three answer which binary to spawn, while it answers whether to spawn at all, and reversing them makes a bundled app race the daemon the user already started for its port. The probe MUST be an HTTP status check rather than a bare TCP connect, so a process squatting the recorded port is not mistaken for a daemon.

When no daemon can be found or started it MUST say so in terms a user who has never opened a terminal can act on — not a blank window and not a stack trace. It MUST offer a restart, reachable from the tray, the offline banner and the web UI's Settings → Daemon tab — an affordance the browser host cannot have, because a daemon that is down cannot serve the page the control would live on. It MUST detect version skew between itself and the daemon it is talking to, since a previous installation's daemon may still be listening; it attaches to that daemon and reports the skew rather than refusing to work.

A daemon it starts MUST be given a readiness budget that is a ceiling rather than an expectation — clear of the seconds a real vault's daemon spends unpacking, migrating and bringing its upstreams up before it accepts — and the outcome of every handshake, reused or spawned or failed, MUST be recorded (see "Write the shell's records into the daemon log"). Neither waiting nor resolving may run on the thread that draws the window.

#### Scenario: the shell takes over a running daemon instead of spawning a second
- **GIVEN** a daemon the user already started from the terminal,
- **WHEN** the app launches,
- **THEN** the liveness probe answers first and the app attaches to that daemon,
- **AND** no second daemon process is started.

### Requirement: Restart by stopping the running daemon first
Restart MUST be a true restart: when a daemon is responsive it MUST be asked to shut down over its token-gated shutdown route and the port MUST be observed free before a replacement is spawned. A restart that silently became a no-op would do nothing at exactly the moment a user reaches for it — a wedged-but-listening daemon, whose old process still holds the port — and a failure to free the port MUST be reported rather than followed by a spawn that cannot bind. The same restart MUST run whichever place it was chosen from: the tray, the offline banner or the web UI's Settings → Daemon tab.

A restart MUST wait for its replacement to answer and return that daemon's connection with the result, and the page MUST install what it is handed rather than run a handshake of its own — a page that asked again the instant the restart returned asked before the new daemon had bound anything, and the handshake's cold-start branch answered by spawning a rival for it.

#### Scenario: a restart stops the running daemon before spawning a replacement
- **GIVEN** a daemon that is listening but not serving usefully,
- **WHEN** the user chooses restart from the tray, the offline banner or Settings → Daemon,
- **THEN** the shell asks the running daemon to shut down over its token-gated route, waits for the port to free, and only then spawns a replacement,
- **AND** a restart that cannot free the port reports that rather than appearing to succeed.

#### Scenario: a restart hands back the connection it waited for
- **GIVEN** the user restarts the daemon from the tray, the offline banner or Settings → Daemon,
- **WHEN** the replacement starts answering,
- **THEN** the shell returns its base URL and token alongside the new PID,
- **AND** the page installs those rather than running a second handshake, so the restart starts exactly one daemon.
