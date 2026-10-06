# Desktop App

## Purpose

The macOS desktop shell: its window and menu bar item, the handshake that credentials a locally-hosted page, the daemon it finds or starts, how it updates itself, and the signed `.dmg` it ships in. The daemon itself, and the terminal install tier, belong to [daemon](../daemon/spec.md). Coffer's UI is reachable in a browser at a loopback origin, which is enough for someone already in a terminal and almost useless to anyone else — no Dock icon, nothing in Cmd-Tab, and the only route in starts by knowing whether a daemon is running and on which port. The shell is the things a browser tab cannot do for itself: a window with a Dock icon, a resident menu bar item, detect-or-spawn at launch, the credential handshake a locally-hosted page has no other way to make, and replacing the application with a newer signed version. It is also the only place a user who has never opened a terminal can recover a daemon that is down or wedged, because the page that would carry a restart control is served by the very daemon that is not serving.

A previous shell was retired over the operating cost of every update (a rebuild plus a reinstall, and built artifacts that drifted from source) and then restored, because that judgement priced the update cost and not the access cost ([The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](../../../docs/decisions/desktop-shell-over-a-shared-frontend.md)). The restored shell is smaller: deploying the sibling binaries stays the daemon's frozen-start job, and native file actions stay daemon HTTP routes. The retirement's failure mode is bounded rather than gone — a stale `.app` can still carry a stale `frontend/dist` — and the daemon half of it is made visible by the version-skew check. It owns no persistent state; the handshake is ephemeral and re-made on every launch.

The shell exposes no HTTP surface of its own, so it has no `contracts/`: it is a client of the daemon's `/api/v1/daemon/status` and `/api/v1/daemon/shutdown` routes, of the token-gated `/api/v1/attention` it polls for the menu bar's "needs you" entry, of `/api/v1/sync/status` it polls to raise the notification of [vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is", and of `~/.coffer/daemon.json`; outside the machine it reads only the release manifest on GitHub Releases. Its internal interface is in-process Tauri IPC commands — restart the daemon, hand the page its daemon connection, compare the daemon's version with the app's, take the interface language the page reports so the menu bar can be labelled in it, open the daemon log file in the system viewer for the offline screen (it needs no daemon), the presence-gated reveal, key backup and approval, and the update status, check, install and Check automatically switch. The offline banner is rendered by the web UI; the Restart control, the Open daemon log control and the version-skew warning inside it are this capability's. The shell's `cargo test` suite is gated by `.github/workflows/desktop.yml` (`make desktop-lint`, `make desktop-test`), not by `make verify`; nothing in CI proves the `.app` assembles or the `.dmg` opens — that is the release workflow's job — and hiding the window on close, the tray's own items and the IPC commands' `AppHandle`-bound halves need a live Tauri runtime and are exercised by launching the app. The release version is written in six files (`scripts/bump_version.py` lists them), including the shell's bundle configuration; keeping them in step is release procedure, and a mismatch shows up as a version-skew warning. Signing, notarisation and the updater feed run in the release workflow only when their secrets are present; `RELEASING.md` lists what the owner provides.

Out of scope: any platform but macOS arm64 (no Windows or Linux shell, no Intel build — those legs were never validated end to end) and supervising anything but the daemon (upstream MCP processes are the daemon's job).

## Requirements

### Requirement: Host the UI locally in an application window
Coffer MUST ship a macOS desktop shell that hosts the built web UI **as a local asset**, not as a page loaded from the daemon's origin. Hosting it locally is what distinguishes an application from a bookmarked browser window: a daemon that is slow, absent or wedged yields an actionable screen rather than a connection error, and the daemon's port is never visible in an address bar.

The window MUST NOT be shown before a daemon answers. Every surface the UI can offer before then is an apology — a page whose every query reports "not ready" under a banner explaining why — and an application that opens on that reads as broken rather than as early; with the daemon running as a login service ([daemon](../daemon/spec.md)) the wait is normally imperceptible. It MUST be shown once the attempt to reach a daemon has failed, since an invisible app cannot report why it has nothing to show. Building the page MUST NOT wait on the handshake either — the wait belongs to the shell, and a webview that blocks on a retrying handshake would never paint at all.

The shell MUST present a window the OS treats as an application — Dock icon, Cmd-Tab entry — and a resident menu bar item (see "Show the daemon and what needs the user in the menu bar"); closing the window MUST hide to the menu bar rather than exit, and re-activating from the Dock MUST restore it.

The menu bar item's labels, its tooltip and the sync notification MUST be in the interface language the user chose in the web UI, and MUST follow a switch without a restart. The choice lives in the webview's storage, which the shell cannot read, so the page reports it over IPC when it starts and on every switch. Until it has, the tray MUST follow the OS language — the same fallback the page itself uses.

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
- **AND** a window closed in full screen first leaves full screen and is hidden once it has, so no empty black screen is left in its place.

#### Scenario: the tray speaks the interface language
- **GIVEN** the user has chosen Chinese as the interface language,
- **WHEN** the app starts,
- **THEN** the tray reads 打开 Coffer, 重启守护进程 and 退出 Coffer,
- **AND** switching the interface to English relabels the tray in English without a restart.

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Three host-conditional affordances are sanctioned, all reached through the secret supplier's module, because only the shell can offer them: the Restart control, the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"), and the update check and install (see "Check for updates against a signed release manifest"). The first two are each rendered in exactly two places — the offline banner and the web UI's Settings → Daemon tab; in a browser, the offline banner names the `coffer daemon start` command instead of a Restart control, because no daemon is running that could restart itself, and Settings → Daemon offers the same Restart control, which there asks the running daemon to restart itself (spec daemon "Restart itself on request"). The update check and install are rendered in one place, the web UI's Settings › About tab; in a browser that tab says updates are installed by the desktop app, offers no update control, and hands the upgrade to the person's agent instead (spec daemon "Hand an upgrade of Coffer to an agent"). The presence-gated actions — reveal and copy a secret, write a master key backup, approve a pending approval — are sanctioned the same way, reached through the same module (see "Release plaintext and approvals only after a presence check in the shell"): outside the shell they answer that they are unavailable, and the page offers "Open in Coffer app" in their place. Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with. One host-conditional report is sanctioned beside them, in the same module and rendering nothing: the page tells the shell its interface language so the tray can be labelled in it (see "Host the UI locally in an application window"); outside the shell it does nothing, since a browser has no tray.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the secret supplier (with its update half) and the offline banner — which carries the Restart control and the version-skew warning — no frontend module reads which host it runs in; the Settings → Daemon tab, the Settings › About tab and the presence-gated actions ask the secret supplier's module.

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
- **THEN** the app asks again on a backoff until a daemon answers, and secrets the page the moment one does,
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
- **AND** the shell mints no secret of its own and stores none.

### Requirement: Find or start a daemon by a fixed resolution order
The shell MUST locate a daemon by a fixed resolution order — a live daemon named by `~/.coffer/daemon.json`, then its own bundle, then `~/.coffer/bin/`, then `PATH` — taking over an already-running daemon rather than spawning a second one. The liveness probe MUST come first: the other three answer which binary to spawn, while it answers whether to spawn at all, and reversing them makes a bundled app race the daemon the user already started for its port. The probe MUST be an HTTP status check rather than a bare TCP connect, so a process squatting the recorded port is not mistaken for a daemon. Its read timeout MUST outlast the slowest status a warming daemon produces (the daemon spec's "Decide liveness by the status call"), because a timeout reads as "nobody is live": resolution would then spawn a second daemon, and a restart would skip stopping a slow but running one.

When no daemon can be found or started it MUST say so in terms a user who has never opened a terminal can act on — not a blank window and not a stack trace. It MUST offer a restart, reachable from the tray, the offline banner and the web UI's Settings → Daemon tab — an affordance the browser host cannot have, because a daemon that is down cannot serve the page the control would live on. It MUST detect version skew between itself and the daemon it is talking to, since a previous installation's daemon may still be listening; it attaches to that daemon and reports the skew rather than refusing to work.

A daemon it starts MUST be given a readiness budget that is a ceiling rather than an expectation — clear of the seconds a real vault's daemon spends unpacking, migrating and bringing its upstreams up before it accepts — and the outcome of every handshake, reused or spawned or failed, MUST be recorded (see "Write the shell's records into the daemon log"). Neither waiting nor resolving may run on the thread that draws the window.

#### Scenario: the shell takes over a running daemon instead of spawning a second
- **GIVEN** a daemon the user already started from the terminal,
- **WHEN** the app launches,
- **THEN** the liveness probe answers first and the app attaches to that daemon,
- **AND** no second daemon process is started.

### Requirement: Restart by stopping the running daemon first
Restart MUST be a true restart: when a daemon is responsive it MUST be asked to shut down over its token-gated shutdown route and the port MUST be observed free before a replacement is spawned. A restart that silently became a no-op would do nothing at exactly the moment a user reaches for it — a wedged-but-listening daemon, whose old process still holds the port — and a failure to free the port MUST be reported rather than followed by a spawn that cannot bind. The same restart MUST run whichever place it was chosen from: the tray, the offline banner or the web UI's Settings → Daemon tab.

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
The shell MUST NOT reimplement any capability the daemon already exposes over HTTP. Native folder selection, opening a file in the user's editor and revealing it in the file manager are daemon routes, and a webview reaches them exactly as a browser tab does; duplicating them in the shell would reintroduce a host-conditional branch in the frontend for no user-visible gain. It MUST declare no native dialog or opener plugin. A native plugin is admissible only where the daemon **cannot** stand in, and then only on the Rust side, with no permission granted to the webview: a system notification is one such case, because there is no loopback route that raises one and only the installed bundle can post a notification as Coffer at all ([vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is"); the updater is the other, because a process the app spawned cannot replace the app it runs inside (see "Check for updates against a signed release manifest"). The presence check behind a reveal, a key backup or an approval is not a daemon route and is the shell's alone: a LocalAuthentication prompt can only be raised by the installed app, and the grant it produces is what the daemon's presence-gated routes require (see "Release plaintext and approvals only after a presence check in the shell"); the folder a key backup goes into is still picked through the daemon's folder route. The shell MUST NOT deploy binaries into `~/.coffer/bin/` — that is the daemon's frozen-start job ([daemon](../daemon/spec.md), distribution), and two processes writing that directory race.

#### Scenario: the shell reimplements no daemon route
- **GIVEN** the shell's source,
- **WHEN** its capabilities and dependencies are read,
- **THEN** it declares no dialog or opener plugin, grants the webview no updater permission, and writes nothing into `~/.coffer/bin/`,
- **AND** the webview's content policy allows loopback and IPC and nothing else.

### Requirement: Write the shell's records into the daemon log
The shell MUST install a logger before anything else runs, and MUST write its own records — which binary the resolution chain picked, that a restart asked from the tray failed — as one-line JSON shaped like the daemon's own structured lines, carrying `coffer.desktop` as the logger name, appended to `~/.coffer/logs/daemon.log`, where the daemon-log reader parses them interleaved with the daemon's own. It MUST NOT create a second log file. Until the logger existed a failed tray restart failed in silence, on the one surface a user reaches when the daemon is down and the web UI is therefore unreachable; a separate `desktop.log` would be a second place to look that nothing tells anyone about.

#### Scenario: the shell's own records land in the daemon log
- **GIVEN** the shell reports which binary it resolved, or that a tray restart failed,
- **WHEN** the user opens the daemon log,
- **THEN** those records are in `~/.coffer/logs/daemon.log` as one-line JSON carrying `logger: coffer.desktop`, readable beside the daemon's own lines,
- **AND** no second log file exists for the shell.

### Requirement: Ship the desktop tier as a macOS arm64 dmg
The release pipeline MUST produce, per `v*` tag, a **macOS arm64** `.dmg` containing the Tauri shell with the four frozen binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` — embedded as Tauri `externalBin`, so that installing it requires nothing installed beforehand. macOS x64 (Intel), Linux and Windows are deliberately not built; those legs were never validated end to end. The desktop leg MUST reuse the artifacts the terminal leg already built rather than running PyInstaller a second time; the freezing is the expensive half and it is done once. This `.dmg` is the double-click install and it ships on every tag; the terminal install is the archive tier of [daemon](../daemon/spec.md), and neither tier is a substitute for the other.

#### Scenario: a release tag produces the desktop tier
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains a macOS arm64 `.dmg` holding the shell with `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` embedded, and no other binary,
- **AND** those binaries are the artifacts the terminal tier's build already produced, not a second PyInstaller run,
- **AND** no other platform is built.

### Requirement: Document clearing the quarantine attribute
A release built without a Developer ID is neither signed nor notarised (see "Sign and notarise a release when its credentials are present"), so a browser-downloaded `.dmg` from it carries macOS's quarantine attribute and the app is refused on double-click. Such a `.dmg` MUST say so in its name (`Coffer-unsigned-…`), and the release notes and the install guide on the docs site (the README links to it) MUST carry the quarantine-clearing step as prominently as they carry it for the terminal tier, for as long as an unsigned build can be published.

#### Scenario: the install instructions carry the quarantine-clearing step for the app
- **GIVEN** the release notes the release workflow publishes and the docs site's install guide,
- **WHEN** a user reads how to install the `.dmg`,
- **THEN** each carries the exact command that clears the quarantine attribute from `/Applications/Coffer.app`,
- **AND** the release notes carry it in the same notice as the terminal tier's quarantine step.

### Requirement: Release plaintext and approvals only after a presence check in the shell
The shell MUST expose, over IPC, revealing a secret, writing a master key
backup, approving a pending approval, approving several at once (it reads each from the daemon, keeps those still
waiting and signs one grant over a digest of exactly that list) and reporting whether the daemon is a
development build, and MUST run a fresh LocalAuthentication check
(`deviceOwnerAuthentication`: Touch ID or the login password) before each one,
with no reuse window. The operating system's prompt MUST name what it approves —
the secret, the backup, or the approval's own description (for several
approvals at once: the first few descriptions and the count of the rest) — and in a
development build MUST say so. Only after the check passes does the shell ask
the daemon for a challenge, sign it with the grant key derived from the master
key ([secret](../secret/spec.md) "Release plaintext only to a
present human in the desktop app") and send the request; a cancelled check
sends nothing. The backup command takes the passphrase the page collected,
refuses one under eight characters before the presence check, and MUST pass it
only in the daemon's export request — never into a log, a stored file or the
signed grant. The shell reads the master key at the moment of signing — from
the signed release's Keychain access group, or in a development build from the
key file — and MUST NOT store or cache it or the grant key. Before it does either, and before it hands the page the daemon's token (on attach, on a cold start and after a restart), it MUST challenge the daemon it found through `~/.coffer/daemon.json` with `POST /api/v1/secrets/presence/attest` and verify the answer against its own derivation from the master key, bound to the port it dialled ([secret](../secret/spec.md) "Release plaintext only to a present human in the desktop app"); when the answer does not verify it MUST abort with "This is not Coffer's daemon — nothing was sent" and send no token, grant or value. Installing a master key is one more operation behind a presence check, over the fingerprint of the key being imported. In a development
build without LocalAuthentication the check MUST fall back to a modal
confirmation in the app window, never to no check. The shell MUST raise one
native notification per pending approval it has not seen, and tell the page so
its approval sheet opens.

#### Scenario: a presence grant signs exactly the approved operation
- **GIVEN** a master key and a challenge for one operation and one target
- **WHEN** the shell signs it
- **THEN** the signature is the one the daemon computes for that operation, target and nonce, and differs for any other

#### Scenario: every presence prompt names what it approves
- **GIVEN** a reveal, a key backup and an approval
- **WHEN** the shell builds each presence prompt
- **THEN** each names its operation and target, and in a development build each says it is a development build
- **AND** a prompt for several approvals names the first few and counts the rest

#### Scenario: a pending approval raises one notification
- **GIVEN** the daemon lists a pending approval the shell has not seen
- **WHEN** the shell polls twice
- **THEN** it raises one notification for it, and none for an approval it already announced

### Requirement: Approve a save's own binding on the spot
When the person saves a change in the desktop app that leaves a secret's
binding waiting for approval ([secret](../secret/spec.md) "Hold a secret for a
new destination until a person approves it") — a resource pointed at another
stored secret, a new MCP server, channel, provider or custom tool group, a
moved target, the sync remote — the page MUST approve it as part of that save:
right after the save returns it asks the shell to approve, under one presence
check, exactly the bind approvals created on that save's destination since the
save started, and only then reports the save done. It MUST NOT sweep in an
approval for another destination or one created before the save. While such a
save runs, the approval sheet MUST NOT open on its own; a presence check the
person cancels leaves the approval waiting, shown on its resource, and the sheet
does not open over it. In a browser, which has no presence check, the save
leaves the approval waiting as before.

#### Scenario: a save in the app approves its own binding with one presence check
- **GIVEN** the desktop app and a save that leaves two bind approvals on its destination
- **WHEN** the save returns
- **THEN** the shell approves both under one presence check before the save reports done
- **AND** an approval on another destination, or one older than the save, is left waiting

#### Scenario: a cancelled check leaves the approval waiting without the sheet
- **GIVEN** the desktop app and a save that leaves an approval waiting
- **WHEN** the person cancels the presence check
- **THEN** the approval stays waiting and the approval sheet does not open over it

#### Scenario: a save in a browser leaves its approval waiting
- **GIVEN** the page open in a browser
- **WHEN** a save leaves an approval waiting
- **THEN** no presence check is asked for and the approval waits for the app

### Requirement: Show the daemon and what needs the user in the menu bar
The shell MUST keep an item in the macOS menu bar whose icon is the Stroke C mark as a monochrome template image, so macOS tints it for a light or a dark menu bar, dimmed and struck through while no daemon is serving. While anything needs the user, the icon MUST carry that count beside it as a number, "9+" past nine; the count is the length of the Overview's attention list, which leaves out what the user has ignored. The count MUST follow that list down as well as up: once something is resolved or ignored the count MUST drop, and once nothing is left it MUST disappear — within seconds while the window is open, and by the shell's next read of the list otherwise. A raised sync alert counts as one only until the list is next read; after that the list alone decides. Its menu MUST offer, in this order, and nothing more: a status line naming the daemon's port and version while it runs, or that it is offline, which cannot be chosen; an entry "N things need you" ("1 thing needs you" for one) — shown only when something does, directly under the status line, and opening Overview; a separator; Open Coffer; Restart daemon, which reads Start daemon while none is serving and runs the one restart (see "Restart by stopping the running daemon first"); a separator; and Quit Coffer (⌘Q). The icon's tooltip MUST read "Coffer · N things need you" ("Coffer · 1 thing needs you" for one) while something needs the user, and plain "Coffer" otherwise, offline included. While no daemon is serving the attention entry and the count MUST be absent. What the menu bar says MUST follow the daemon without the user opening the window: a daemon that stops answering MUST read as offline within one poll, and a launching app MUST allow a cold daemon a few polls before calling it offline.

#### Scenario: the menu bar says whether the daemon is running
- **GIVEN** a daemon serving on port 38470 at version 1.0.0 and nothing that needs the user
- **WHEN** the user opens the menu bar item
- **THEN** the first line reads "Daemon running · port 38470 · 1.0.0" and cannot be chosen
- **AND** the icon is the plain mark with no count, and the entries after it are Open Coffer, Restart daemon and Quit Coffer

#### Scenario: the menu bar counts what needs the user
- **GIVEN** a daemon whose attention list holds nine items
- **WHEN** the menu bar polls it
- **THEN** the icon carries the number 9 beside it and the menu shows "9 things need you" under the status line
- **AND** choosing it opens the window on Overview

#### Scenario: the count on the icon stops at 9+
- **GIVEN** a daemon whose attention list holds ten items
- **WHEN** the menu bar polls it
- **THEN** the icon carries "9+" beside it and the menu line reads "10 things need you"

#### Scenario: the count drops as soon as what needs the user is resolved
- **GIVEN** the menu bar icon carries the count 2 and a sync alert is raised
- **WHEN** the user resolves one item, then the other, in the window
- **THEN** the count reads 1, then disappears, without waiting for the sync watcher's own poll

#### Scenario: the icon tooltip carries the count
- **GIVEN** a daemon whose attention list holds nine items
- **WHEN** the user hovers the menu bar icon
- **THEN** the tooltip reads "Coffer · 9 things need you"
- **AND** with nothing needing the user, or no daemon serving, it reads "Coffer"

#### Scenario: an offline daemon offers to start
- **GIVEN** the menu bar item of an app whose daemon has stopped
- **WHEN** the next poll finds no daemon answering
- **THEN** the icon is dimmed and struck through with no count, the status line reads "Daemon offline" and the attention entry is gone
- **AND** the restart entry reads Start daemon

### Requirement: Check for updates against a signed release manifest
The shell MUST check for a newer version of Coffer at launch and every six hours while it runs, unless the user has switched Check automatically off on the web UI's Settings › About tab, and on demand from that tab (spec [web-ui](../web-ui/spec.md) "Check for and install updates on Settings › About"), through the Tauri updater against a release manifest published on GitHub Releases. A new version otherwise reaches a user only if they think to download a new `.dmg`, and a desktop user is the one least likely to watch a releases page. The check and the download MUST run in the shell's own process, not in the webview, so the webview's content policy stays loopback and IPC only (see "Restrict the webview to loopback and IPC"). A build made without an updater key MUST say it does not check for updates and MUST NOT check.

Every update MUST be signed with the project's updater key and verified against the public key built into the shell — including the version it was signed for — before it is installed; an update whose signature is missing or does not verify MUST be refused and reported, never installed. The release workflow MUST publish, beside each tag's `.dmg`, the updater archive of the same `.app`, its signature, and the manifest naming the version, the archive's URL and the signature. A check at launch or on the timer MUST NOT interrupt the user: it records its time and result for the About tab to show, and only the user's own Download and restart on the About tab downloads and installs anything. Installing MUST download and verify the archive, replace the `.app`, and relaunch the shell; the relaunched shell finds the previous version's daemon and replaces it through the one restart (see "Restart by stopping the running daemon first"), so the new version's daemon answers. A check or download that fails — no network, an unreachable manifest, a refused signature — MUST be reported to the About tab and recorded (see "Write the shell's records into the daemon log"), and MUST leave the running version untouched.

#### Scenario: the shell checks at launch and every six hours
- **GIVEN** the shell launched with a newer signed release on the manifest
- **WHEN** it starts, and again after six hours of running
- **THEN** each time it checks the manifest without showing a dialog, and records the check's time and the newer version for the About tab
- **AND** nothing is downloaded or installed until the user chooses Download and restart

#### Scenario: an update is installed only with a valid signature
- **GIVEN** a manifest whose archive's signature does not verify against the shell's built-in public key
- **WHEN** the user chooses Download and restart
- **THEN** the shell refuses the update, reports the refused signature to the About tab and the daemon log, and keeps running the current version

#### Scenario: installing an update relaunches onto the new version
- **GIVEN** a newer signed release and a daemon from the running version
- **WHEN** the user chooses Download and restart and the archive verifies
- **THEN** the shell replaces the `.app`, relaunches, and restarts the previous version's daemon through the one restart
- **AND** the About tab and the daemon status both report the new version

#### Scenario: a release publishes the update manifest
- **GIVEN** a release tag matching `v*` is pushed with the updater key in the repository's secrets
- **WHEN** the release workflow finishes
- **THEN** the release carries, beside the `.dmg`, the updater archive, its signature and a manifest naming that version, the archive's URL and the signature

### Requirement: Sign and notarise a release when its credentials are present
When the repository holds a Developer ID Application certificate and its Team ID, the release workflow MUST sign the four frozen binaries — and every library they unpack — and the app with that Developer ID under the hardened runtime, without `get-task-allow`, with the `keychain-access-groups` entitlement for `<Team ID>.coffer` on every one of them except `coffer-seatalk-bridge`, which is signed without that entitlement and is shipped in the app bundle's `MacOS` directory without being re-signed (it runs third-party SDK code and must not be able to read the master key), and MUST stamp the same group into the daemon's and the shell's build so the master key is kept where only those binaries can read it ([secret](../secret/spec.md) "Keep the master key behind a storage port chosen by the build"). When it also holds an App Store Connect API key it MUST notarise the CLI binaries, the app and the `.dmg`, and staple the app and the `.dmg`. Each of these steps MUST run only when the credentials it needs are present, and a run without them MUST say which are missing and still build and publish the unsigned release, so the pipeline stays green before the owner has an Apple Developer Program membership.

#### Scenario: a release without signing credentials builds unsigned
- **GIVEN** a release run with no Developer ID, notary or updater secrets
- **WHEN** the workflow runs
- **THEN** every signing, notarisation and updater step is skipped with a line naming the missing secret
- **AND** the run publishes the unsigned CLI archive and `Coffer-unsigned-<triple>.dmg` as before

#### Scenario: a signed release carries the hardened runtime and its keychain access group
- **GIVEN** a release run holding the Developer ID certificate, its password and the Team ID
- **WHEN** the binaries and the app are built
- **THEN** each is signed by that team under the hardened runtime with `keychain-access-groups` for `<Team ID>.coffer` and without `get-task-allow`
- **AND** `build_identity.KEYCHAIN_ACCESS_GROUP` in the frozen daemon, and the shell's compiled access group, are that same `<Team ID>.coffer`

### Requirement: Serve the command line's desktop requests
The shell MUST serve the requests the command line leaves with the daemon (`/api/v1/desktop/requests`):
it asks for the next one about once a second — each ask is how the daemon knows the app is running —
and runs the same presence-checked flow its own buttons run, one request at a time. For an approval
request it MUST read each approval from the daemon, refuse one whose target fingerprint is not the
one the request was pinned to, show the operating system's prompt and sign the grant pinned to that
target ("Release plaintext and approvals only after a presence check in the shell"); for a reveal it
MUST run the reveal flow and show the value in the window, sending it nowhere else; for a key backup
it MUST open the page's own backup dialog, where the person types the passphrase; and for the update
commands it MUST run the updater and report its state. It then tells the daemon how the request
ended — done, cancelled or failed with its reason — which approves nothing by itself. The shell
never acts on a request by clicking or scripting its own window.

#### Scenario: the shell serves a command line approval
- **GIVEN** a desktop request for two approvals, each pinned to its target
- **WHEN** the shell claims it
- **THEN** it reads both approvals from the daemon, shows one prompt naming them, signs over exactly those approvals and targets, and reports the request done
- **AND** a request whose approval's target moved is reported failed, with nothing signed
