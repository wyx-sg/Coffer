# Desktop App

## Purpose

The macOS desktop shell: its window and tray, the handshake that credentials a locally-hosted page, the daemon it finds or starts, and the `.dmg` it ships in. The daemon itself, and the terminal install tier, belong to [daemon](../daemon/spec.md). Coffer's UI is reachable in a browser at a loopback origin, which is enough for someone already in a terminal and almost useless to anyone else — no Dock icon, nothing in Cmd-Tab, and the only route in starts by knowing whether a daemon is running and on which port. The shell is the four things a browser tab cannot do for itself: a window with a Dock icon, a resident tray, detect-or-spawn at launch, and the credential handshake a locally-hosted page has no other way to make. It is also the only place a user who has never opened a terminal can recover a daemon that is down or wedged, because the page that would carry a restart control is served by the very daemon that is not serving.

A previous shell was retired over the operating cost of every update (a rebuild plus a reinstall, and built artifacts that drifted from source) and then restored, because that judgement priced the update cost and not the access cost ([The Desktop Shell Returns](../../../docs/decisions/desktop-shell-over-a-shared-frontend.md)). The restored shell is smaller: deploying the sibling binaries stays the daemon's frozen-start job, and native file actions stay daemon HTTP routes. The retirement's failure mode is bounded rather than gone — a stale `.app` can still carry a stale `frontend/dist` — and the daemon half of it is made visible by the version-skew check. It owns no persistent state; the handshake is ephemeral and re-made on every launch.

The shell exposes no HTTP surface of its own, so it has no `contracts/`: it is a client of the daemon's `/api/v1/daemon/status` and `/api/v1/daemon/shutdown` routes, of the token-gated `/api/v1/sync/status` it polls to raise the tray and notification of [vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is", and of `~/.coffer/daemon.json`; its only internal interface is three in-process Tauri IPC commands — restart the daemon, hand the page its daemon connection, and compare the daemon's version with the app's. The offline banner is rendered by the web UI; the Restart control and the version-skew warning inside it are this capability's. The shell's `cargo test` suite is gated by `.github/workflows/desktop.yml` (`make desktop-lint`, `make desktop-test`), not by `make verify`; nothing in CI proves the `.app` assembles or the `.dmg` opens — that is the release workflow's job — and hiding the window on close, the tray's own items and the IPC commands' `AppHandle`-bound halves need a live Tauri runtime and are exercised by launching the app. The release version is written in three places, including the shell's bundle configuration; keeping them in step is release procedure, and a mismatch shows up as a version-skew warning.

Out of scope: any platform but macOS arm64 (no Windows or Linux shell, no Intel build — those legs were never validated end to end); supervising anything but the daemon (upstream MCP processes are the daemon's job); and auto-update (a new version is a new `.dmg`).

## Requirements

### Requirement: Host the UI locally in an application window
Coffer MUST ship a macOS desktop shell that hosts the built web UI **as a local asset**, not as a page loaded from the daemon's origin. Hosting it locally is what distinguishes an application from a bookmarked browser window: a daemon that is slow, absent or wedged yields an actionable screen rather than a connection error, and the daemon's port is never visible in an address bar.

The window MUST NOT be shown before a daemon answers. Every surface the UI can offer before then is an apology — a page whose every query reports "not ready" under a banner explaining why — and an application that opens on that reads as broken rather than as early; with the daemon running as a login service ([daemon](../daemon/spec.md)) the wait is normally imperceptible. It MUST be shown once the attempt to reach a daemon has failed, since an invisible app cannot report why it has nothing to show. Building the page MUST NOT wait on the handshake either — the wait belongs to the shell, and a webview that blocks on a retrying handshake would never paint at all.

The shell MUST present a window the OS treats as an application — Dock icon, Cmd-Tab entry — and a resident tray offering at least open, restart daemon, and quit; closing the window MUST hide to the tray rather than exit, and re-activating from the Dock MUST restore it.

#### Scenario: the window waits for a daemon, and opens either way
- **GIVEN** the app is launched with no daemon running,
- **WHEN** the app starts one,
- **THEN** no window is shown until that daemon answers, so the application is never on screen in a state where nothing in it works,
- **AND** the window is shown anyway once the attempt has failed, because an invisible app cannot report that it could not start a daemon,
- **AND** the page itself is built without waiting on the handshake, so the wait is the shell's and not a blank webview's.

#### Scenario: closing the window hides the app to the tray
- **GIVEN** the app is running with its window open,
- **WHEN** the user closes the window,
- **THEN** the process stays alive with its tray entry intact instead of exiting,
- **AND** re-activating from the Dock restores the window.

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Two host-conditional affordances are sanctioned, both rendered in the offline banner and both reached through the credential supplier's module, because only the shell can offer them: the Restart control, and the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"). Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the credential supplier and the offline banner — which carries the Restart control and the version-skew warning — no frontend module branches on whether it is running inside the shell.

### Requirement: Restrict the webview to loopback and IPC
The webview's content-security policy MUST permit loopback origins on any port and the shell's own IPC scheme, and nothing else; scripts and styles MUST be served from the bundle itself. The port is not known until the handshake, which is why the loopback allowance is port-wildcarded rather than absent.

#### Scenario: the content policy admits loopback on any port and the bundle's own scripts
- **GIVEN** the webview's content-security policy,
- **WHEN** its directives are read,
- **THEN** `connect-src` admits a loopback origin with a wildcarded port and the shell's IPC scheme, and no other host,
- **AND** scripts load only from the bundle itself (`'self'`), styles only from the bundle or inline in it, images only from the bundle, inline `data:` URLs or the shell's asset protocol (`asset:`, `http://asset.localhost`), fonts only from the bundle or inline `data:` URLs, and every other fetch falls back to `'self'`.

### Requirement: Supply the page its daemon connection over IPC
The shell MUST supply the frontend with the running daemon's base URL and live API token through an IPC command, and MUST NOT hold up the first render waiting for it. Blocking would contradict "Host the UI locally in an application window": the handshake spawns a daemon and polls when none is running, so awaiting it would leave every launch-after-reboot on an empty window for as long as that takes, which is the failure hosting the UI locally exists to prevent.

Queries issued before it resolves come back `UNAUTHENTICATED`, which the offline banner already reads as "daemon not ready"; the frontend MUST therefore refetch them once the handshake lands, or they keep a 401 nothing else will clear. The daemon's own injection of the token into a served document cannot reach a locally-hosted page — nobody served that document — so this is the only channel, and it MUST resolve to the same `window.__COFFER_BASE_URL__` / `window.__COFFER_TOKEN__` globals the browser host receives, so the frontend gains a second *supplier* and not a second *code path*.

When the handshake fails the frontend MUST still render and surface the failure in the offline banner; a blank window is not an acceptable report of "no daemon". A failed handshake MUST be retried on a backoff until one lands: a single attempt is a cliff, and the app that fell off it reported a daemon that was seconds from serving as dead, permanently — the page kept no address to retry with, so its own status poll could not clear the banner and only a manual restart could. Until a supplier has named a base URL, the frontend MUST NOT infer one from the document's own origin: a page the daemon served is same-origin with the API and may, but a page nobody served is not, and guessing there produced a URL the webview refuses outright, turning "still connecting" into an unreadable transport error on every surface.

#### Scenario: a handshake that misses is retried until it lands
- **GIVEN** a daemon that takes longer to start serving than one handshake attempt waits for,
- **WHEN** that attempt gives up,
- **THEN** the app asks again on a backoff until a daemon answers, and credentials the page the moment one does,
- **AND** the user does nothing: the offline banner clears itself rather than waiting for the restart control.

#### Scenario: a page nobody served does not guess where the API is
- **GIVEN** the shell's window, whose document was loaded from a local asset origin rather than served by a daemon,
- **WHEN** a query is issued before the handshake has supplied a base URL,
- **THEN** it fails as "daemon not ready" rather than as a request to the asset origin,
- **AND** the banner reports a daemon that is still starting, not a daemon that is offline.

### Requirement: Read the daemon's credentials from its discovery file
The shell MUST read the daemon's port and token from `~/.coffer/daemon.json` like every other client, and MUST NOT mint, store or cache a credential of its own. The file's format and lifecycle are [daemon](../daemon/spec.md)'s; the shell is one of its readers, in a different language in a different crate, which is precisely where a silent drift would live — so any change to it MUST be made on both sides together.

#### Scenario: the handshake credentials a locally-hosted page
- **GIVEN** a running daemon whose token and port are recorded in `~/.coffer/daemon.json`,
- **WHEN** the webview asks the shell for them over IPC,
- **THEN** it receives that daemon's base URL and live token, resolved into the same two globals a daemon-served browser page receives,
- **AND** the shell mints no credential of its own and stores none.

### Requirement: Find or start a daemon by a fixed resolution order
The shell MUST locate a daemon by a fixed resolution order — a live daemon named by `~/.coffer/daemon.json`, then its own bundle, then `~/.coffer/bin/`, then `PATH` — taking over an already-running daemon rather than spawning a second one. The liveness probe MUST come first: the other three answer which binary to spawn, while it answers whether to spawn at all, and reversing them makes a bundled app race the daemon the user already started for its port. The probe MUST be an HTTP status check rather than a bare TCP connect, so a process squatting the recorded port is not mistaken for a daemon.

When no daemon can be found or started it MUST say so in terms a user who has never opened a terminal can act on — not a blank window and not a stack trace. It MUST offer a restart, reachable from both the tray and the offline banner — an affordance the browser host cannot have, because a daemon that is down cannot serve the page the control would live on. It MUST detect version skew between itself and the daemon it is talking to, since a previous installation's daemon may still be listening; it attaches to that daemon and reports the skew rather than refusing to work.

A daemon it starts MUST be given a readiness budget that is a ceiling rather than an expectation — clear of the seconds a real vault's daemon spends unpacking, migrating and bringing its upstreams up before it accepts — and the outcome of every handshake, reused or spawned or failed, MUST be recorded (see "Write the shell's records into the daemon log"). Neither waiting nor resolving may run on the thread that draws the window.

#### Scenario: the shell takes over a running daemon instead of spawning a second
- **GIVEN** a daemon the user already started from the terminal,
- **WHEN** the app launches,
- **THEN** the liveness probe answers first and the app attaches to that daemon,
- **AND** no second daemon process is started.

### Requirement: Restart by stopping the running daemon first
Restart MUST be a true restart: when a daemon is responsive it MUST be asked to shut down over its token-gated shutdown route and the port MUST be observed free before a replacement is spawned. A restart that silently became a no-op would do nothing at exactly the moment a user reaches for it — a wedged-but-listening daemon, whose old process still holds the port — and a failure to free the port MUST be reported rather than followed by a spawn that cannot bind.

A restart MUST wait for its replacement to answer and return that daemon's connection with the result, and the page MUST install what it is handed rather than run a handshake of its own — a page that asked again the instant the restart returned asked before the new daemon had bound anything, and the handshake's cold-start branch answered by spawning a rival for it.

#### Scenario: a restart stops the running daemon before spawning a replacement
- **GIVEN** a daemon that is listening but not serving usefully,
- **WHEN** the user chooses restart from the tray or the offline banner,
- **THEN** the shell asks the running daemon to shut down over its token-gated route, waits for the port to free, and only then spawns a replacement,
- **AND** a restart that cannot free the port reports that rather than appearing to succeed.

#### Scenario: a restart hands back the connection it waited for
- **GIVEN** the user restarts the daemon from the tray or the offline banner,
- **WHEN** the replacement starts answering,
- **THEN** the shell returns its base URL and token alongside the new PID,
- **AND** the page installs those rather than running a second handshake, so the restart starts exactly one daemon.

### Requirement: Rate-limit restarts from the last success
Restarts MUST be serialised and rate-limited to at most one every five seconds, measured from the last **successful** restart. A failed spawn MUST NOT consume the window, so the user can retry immediately rather than waiting out a cooldown a failure earned.

#### Scenario: restarts are rate-limited, and a failed spawn does not consume the window
- **GIVEN** a successful restart just happened,
- **WHEN** another restart is requested immediately,
- **THEN** it is refused with the remaining wait stated,
- **AND** a restart whose spawn failed leaves the window unconsumed, so the user may retry at once.

### Requirement: Detach a spawned daemon from the app
A daemon the shell spawns MUST be detached and MUST outlive the app. It MUST NOT be started through the framework's managed-sidecar mechanism, which tears its children down when the app quits — the daemon serves agents that have nothing to do with the window being open.

#### Scenario: a spawned daemon outlives the app
- **GIVEN** the app spawned the daemon itself,
- **WHEN** the user quits the app,
- **THEN** the daemon is still running and still serving agents.

### Requirement: Give a spawned daemon the login shell's PATH
Before spawning a daemon, an app launched from Finder or the Dock MUST discover the user's real `$PATH` by probing the login shell, and pass it on. A GUI-launched application inherits a minimal `$PATH`, so without this the daemon — and the `npx` / `uvx` MCP upstreams it spawns in turn — fail to resolve. The probe MUST be bounded in time and MUST degrade to the inherited `$PATH` rather than delay the launch.

#### Scenario: a Finder-launched app finds the user's real PATH
- **GIVEN** the app is launched from Finder or the Dock, inheriting the minimal GUI `$PATH`,
- **WHEN** it spawns a daemon,
- **THEN** that daemon's `$PATH` includes the login shell's, so `npx`/`uvx` MCP upstreams resolve,
- **AND** a login shell that hangs or fails the probe does not hold up the launch.

### Requirement: Reimplement no daemon route in the shell
The shell MUST NOT reimplement any capability the daemon already exposes over HTTP. Native folder selection, opening a file in the user's editor and revealing it in the file manager are daemon routes, and a webview reaches them exactly as a browser tab does; duplicating them in the shell would reintroduce a host-conditional branch in the frontend for no user-visible gain. It MUST declare no native dialog or opener plugin. A native plugin is admissible only where the daemon **cannot** stand in: a system notification is the one such case today, because there is no loopback route that raises one and only the installed bundle can post a notification as Coffer at all ([vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is"). The shell MUST NOT deploy binaries into `~/.coffer/bin/` — that is the daemon's frozen-start job ([daemon](../daemon/spec.md), distribution), and two processes writing that directory race.

#### Scenario: the shell reimplements no daemon route
- **GIVEN** the shell's source,
- **WHEN** its capabilities and dependencies are read,
- **THEN** it declares no dialog or opener plugin and writes nothing into `~/.coffer/bin/`,
- **AND** the webview's content policy allows loopback and IPC and nothing else.

### Requirement: Write the shell's records into the daemon log
The shell MUST install a logger before anything else runs, and MUST write its own records — which binary the resolution chain picked, that a restart asked from the tray failed — as one-line JSON shaped like the daemon's own structured lines, carrying `coffer.desktop` as the logger name, appended to `~/.coffer/logs/daemon.log`, where the daemon-log reader parses them interleaved with the daemon's own. It MUST NOT create a second log file. Until the logger existed a failed tray restart failed in silence, on the one surface a user reaches when the daemon is down and the web UI is therefore unreachable; a separate `desktop.log` would be a second place to look that nothing tells anyone about.

#### Scenario: the shell's own records land in the daemon log
- **GIVEN** the shell reports which binary it resolved, or that a tray restart failed,
- **WHEN** the user opens the daemon log,
- **THEN** those records are in `~/.coffer/logs/daemon.log` as one-line JSON carrying `logger: coffer.desktop`, readable beside the daemon's own lines,
- **AND** no second log file exists for the shell.

### Requirement: Ship the desktop tier as a macOS arm64 dmg
The release pipeline MUST produce, per `v*` tag, a **macOS arm64** `.dmg` containing the Tauri shell with the four frozen binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-callback` — embedded as Tauri `externalBin`, so that installing it requires nothing installed beforehand. macOS x64 (Intel), Linux and Windows are deliberately not built; those legs were never validated end to end. The desktop leg MUST reuse the artifacts the terminal leg already built rather than running PyInstaller a second time; the freezing is the expensive half and it is done once. This `.dmg` is the double-click install and it ships on every tag; the terminal install is the archive tier of [daemon](../daemon/spec.md), and neither tier is a substitute for the other.

#### Scenario: a release tag produces the desktop tier
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains a macOS arm64 `.dmg` holding the shell with `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-callback` embedded,
- **AND** those binaries are the artifacts the terminal tier's build already produced, not a second PyInstaller run,
- **AND** no other platform is built.

### Requirement: Document clearing the quarantine attribute
Because the embedded binaries are unsigned, a browser-downloaded `.dmg` carries macOS's quarantine attribute and the app is refused on double-click. The release notes and the README MUST therefore carry the quarantine-clearing step as prominently as they carry it for the terminal tier. Notarisation is a documented non-goal pending a paid developer account.

#### Scenario: the install instructions carry the quarantine-clearing step for the app
- **GIVEN** the release notes the release workflow publishes and the README,
- **WHEN** a user reads how to install the `.dmg`,
- **THEN** each carries the exact command that clears the quarantine attribute from `/Applications/Coffer.app`,
- **AND** the release notes carry it in the same notice as the terminal tier's quarantine step.
