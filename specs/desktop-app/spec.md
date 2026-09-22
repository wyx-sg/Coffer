# Feature Specification: Desktop App

**Status**: Accepted
**Scope note**: This spec owns the macOS desktop shell — its window and tray, the handshake that credentials a locally-hosted page, the daemon it finds or starts, and the `.dmg` it ships in. The daemon itself, and the terminal install tier, are spec daemon's.
**Input**: Coffer's UI is reachable in a browser at a loopback origin. That is enough for someone already in a terminal and almost useless to anyone else — no Dock icon, nothing in Cmd-Tab, and the only route in starts by knowing whether a daemon is running and on which port. The shell is the four things a browser tab cannot do for itself.

## User Scenarios & Testing

### User Story 1 — Open Coffer the way you open an application (Priority: P1)

Someone who is not mid-terminal-session wants to open Coffer: from the Dock, from Spotlight, from Cmd-Tab. They double-click the app, a window appears immediately, and if no daemon is running the app starts one for them. Closing the window puts Coffer in the tray rather than shutting it down, because the daemon it supervises keeps serving agents either way.

**Why this priority**: Without it Coffer is one `127.0.0.1` tab among dozens, and reaching it requires knowing a port. That is a fair ask of a CLI user and an unfair one of anybody else.

**Independent Test**: With no daemon running, double-click the installed app. A window renders at once, a daemon starts, the UI fills in, the app has a Dock icon and a tray entry, and closing the window leaves both in place.

**Covering scenarios** (full Given/When/Then under `## Acceptance Scenarios` below):

- the window renders before the daemon answers
- closing the window hides the app to the tray
- the handshake credentials a locally-hosted page

---

### User Story 2 — Recover a wedged daemon without a terminal (Priority: P2)

The daemon is down, or up but not answering. The web UI cannot help — the page that would carry a restart control is served by the very daemon that is not serving. From the tray, or from the offline banner the app is already showing, the user restarts it.

**Why this priority**: This is the one capability the browser host structurally cannot have, and it is the moment a non-terminal user is most stuck.

**Independent Test**: Start a daemon, wedge or stop it, then use the tray's restart. A new daemon comes up and the UI reconnects, without the terminal being touched.

**Covering scenarios**:

- the shell takes over a running daemon instead of spawning a second
- a restart stops the running daemon before spawning a replacement
- restarts are rate-limited, and a failed spawn does not consume the window
- a spawned daemon outlives the app

---

### User Story 3 — Install once, with nothing installed beforehand (Priority: P2)

A user downloads a `.dmg`, drags Coffer to Applications, and double-clicks. There is no Python to install, no CLI to install first, and after the first launch the `coffer` command-line tools are on disk for them to put on `PATH` if they want them.

**Why this priority**: "Desktop app" has to mean *self-contained* to be worth having; an app that asks the user to install a runtime first is a wrapper around a prerequisite.

**Independent Test**: On a machine with no Python and no Coffer checkout, install the `.dmg`, clear the quarantine attribute as the release notes describe, launch, and reach the UI — then find `coffer` under `~/.coffer/bin/`.

**Covering scenarios**:

- a release tag produces the desktop tier
- a Finder-launched app finds the user's real PATH

---

### Why Coffer ships both a web UI and a desktop shell

Coffer's UI used to be wrapped in a Tauri desktop shell that supervised the daemon, sat in the system tray, and deployed the shim on every launch. It was retired over **the operating cost of every update**: a desktop update meant a rebuild _plus_ a reinstall, and the built artifact kept drifting from source — twice on record, once from a build made before fetching, once from a separately pinned build directory that made UI bug reports untrustworthy until re-verified against `main`.

**The shell was restored**, because that judgement priced the update cost and not the access cost. The shell was also the only thing that made Coffer reachable: without it Coffer is one `127.0.0.1` tab among dozens, with no Dock icon and nothing in Cmd-Tab, and the only route to the UI starts by knowing whether a daemon is running and on which port. That is a fair ask of a CLI user mid-session and an unfair one of anybody else ([The Desktop Shell Returns](../../docs/decisions/desktop-shell-over-a-shared-frontend.md)).

The restored shell is smaller than the one removed, because its two load-bearing jobs stayed where they went. Deploying the sibling binaries remains the daemon's frozen-start path (spec daemon, distribution) — the shell must not duplicate it, or two processes race to write `~/.coffer/bin/`. Native file actions remain daemon HTTP routes, which a webview reaches exactly as a browser tab does, so the shell reimplements none of them. What is left is the four things a browser cannot do for itself: a window with a Dock icon, a resident tray, detect-or-spawn at launch, and the credential handshake a locally-hosted page has no other way to make.

The retirement's failure mode is bounded rather than gone: a stale `.app` can still carry a stale `frontend/dist`. It is bounded to the UI, and the daemon half is made visible by the version-skew check in FR-006. The two hosts consume one `frontend/dist`, so neither can drift from the other.

---

### Edge Cases

- **No daemon anywhere**: the resolution chain finds nothing to spawn. The app still renders and says so in terms someone who has never opened a terminal can act on — not a blank window and not a stack trace.
- **A port squatter**: something that is not a Coffer daemon answers on the recorded port. The liveness probe is an HTTP status check rather than a bare TCP connect, so a squatter is not mistaken for a daemon.
- **A previous installation's daemon**: an older build is still listening. The shell attaches to it and reports the version skew rather than refusing to work.
- **A launch from Finder**: the app inherits the minimal GUI `$PATH`, so a daemon spawned from it could not resolve `npx` or `uvx` for MCP upstreams. The shell probes the login shell before spawning.
- **A wedged-but-listening daemon**: a restart that only spawned would be a silent no-op, because the old process still holds the port. The restart stops it first.
- **A failed spawn during restart**: the rate-limit window is not consumed, so the user can retry at once rather than waiting out a cooldown earned by a failure.

## Acceptance Scenarios

Per `.agents/sdd.md` and `.agents/testing.md`, every scenario in this section is referenced by at least one test marked `acceptance(spec="desktop-app", scenario="…")`. Coverage is audited by `make verify-acceptance`. Several of these are covered by `cargo test` in the `desktop` crate, where the marker is a line comment above the test's attributes rather than a call — Rust has no user-defined test attribute without a proc-macro crate, so the audit reads a comment the compiler ignores. Those tests are gated: `.github/workflows/desktop.yml` runs them. See `## Assumptions` for what that workflow does and does not cover.

### Scenario: the window renders before the daemon answers

- **Given** the app is launched with no daemon running,
- **When** the window opens,
- **Then** the UI is rendered from the app's own bundled assets without waiting for the handshake,
- **And** queries issued before the handshake resolves come back unauthenticated and are refetched once it lands, rather than leaving a permanent error.

### Scenario: closing the window hides the app to the tray

- **Given** the app is running with its window open,
- **When** the user closes the window,
- **Then** the process stays alive with its tray entry intact instead of exiting,
- **And** re-activating from the Dock restores the window.

### Scenario: the handshake credentials a locally-hosted page

- **Given** a running daemon whose token and port are recorded in `~/.coffer/daemon.json`,
- **When** the webview asks the shell for them over IPC,
- **Then** it receives that daemon's base URL and live token, resolved into the same two globals a daemon-served browser page receives,
- **And** the shell mints no credential of its own and stores none.

### Scenario: the shell takes over a running daemon instead of spawning a second

- **Given** a daemon the user already started from the terminal,
- **When** the app launches,
- **Then** the liveness probe answers first and the app attaches to that daemon,
- **And** no second daemon process is started.

### Scenario: a restart stops the running daemon before spawning a replacement

- **Given** a daemon that is listening but not serving usefully,
- **When** the user chooses restart from the tray or the offline banner,
- **Then** the shell asks the running daemon to shut down over its token-gated route, waits for the port to free, and only then spawns a replacement,
- **And** a restart that cannot free the port reports that rather than appearing to succeed.

### Scenario: restarts are rate-limited, and a failed spawn does not consume the window

- **Given** a successful restart just happened,
- **When** another restart is requested immediately,
- **Then** it is refused with the remaining wait stated,
- **And** a restart whose spawn failed leaves the window unconsumed, so the user may retry at once.

### Scenario: a spawned daemon outlives the app

- **Given** the app spawned the daemon itself,
- **When** the user quits the app,
- **Then** the daemon is still running and still serving agents.

### Scenario: a Finder-launched app finds the user's real PATH

- **Given** the app is launched from Finder or the Dock, inheriting the minimal GUI `$PATH`,
- **When** it spawns a daemon,
- **Then** that daemon's `$PATH` includes the login shell's, so `npx`/`uvx` MCP upstreams resolve,
- **And** a login shell that hangs or fails the probe does not hold up the launch.

### Scenario: the shell's own records land in the daemon log

- **Given** the shell reports which binary it resolved, or that a tray restart failed,
- **When** the user opens the daemon log,
- **Then** those records are in `~/.coffer/logs/daemon.log` as one-line JSON carrying `logger: coffer.desktop`, readable beside the daemon's own lines,
- **And** no second log file exists for the shell.

### Scenario: the shell reimplements no daemon route

- **Given** the shell's source,
- **When** its capabilities and dependencies are read,
- **Then** it declares no dialog or opener plugin and writes nothing into `~/.coffer/bin/`,
- **And** the webview's content policy allows loopback and IPC and nothing else.

### Scenario: a release tag produces the desktop tier

- **Given** a release tag matching `v*` is pushed,
- **When** the release workflow finishes,
- **Then** the release contains a macOS arm64 `.dmg` holding the shell with `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-callback` embedded,
- **And** those binaries are the artifacts the terminal tier's build already produced, not a second PyInstaller run,
- **And** no other platform is built.

## Requirements

### Functional Requirements

**The shell and its window ([The Desktop Shell Returns](../../docs/decisions/desktop-shell-over-a-shared-frontend.md))**

- **FR-001**: Coffer MUST ship a macOS desktop shell that hosts the built web UI **as a local asset**, not as a page loaded from the daemon's origin. Hosting it locally is what distinguishes an application from a bookmarked browser window: the UI is rendered before the daemon answers, so a daemon that is slow, absent or wedged yields an actionable screen rather than a connection error, and the daemon's port is never visible in an address bar. The shell MUST present a window the OS treats as an application — Dock icon, Cmd-Tab entry — and a resident tray offering at least open, restart daemon, and quit; closing the window MUST hide to the tray rather than exit, and re-activating from the Dock MUST restore it.
- **FR-002**: The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (FR-004) and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting.
- **FR-003**: The webview's content-security policy MUST permit loopback origins on any port and the shell's own IPC scheme, and nothing else; scripts and styles MUST be served from the bundle itself. The port is not known until the handshake, which is why the loopback allowance is port-wildcarded rather than absent.

**Credentialing a locally-hosted page**

- **FR-004**: The shell MUST supply the frontend with the running daemon's base URL and live API token through an IPC command, and MUST NOT hold up the first render waiting for it. Blocking would contradict FR-001: the handshake spawns a daemon and polls when none is running, so awaiting it would leave every launch-after-reboot on an empty window for as long as that takes, which is the failure hosting the UI locally exists to prevent. Queries issued before it resolves come back `UNAUTHENTICATED`, which the offline banner already reads as "daemon not ready"; the frontend MUST therefore refetch them once the handshake lands, or they keep a 401 nothing else will clear. The daemon's own injection of the token into a served document cannot reach a locally-hosted page — nobody served that document — so this is the only channel, and it MUST resolve to the same `window.__COFFER_BASE_URL__` / `window.__COFFER_TOKEN__` globals the browser host receives, so the frontend gains a second *supplier* and not a second *code path*. When the handshake fails the frontend MUST still render and surface the failure in the offline banner; a blank window is not an acceptable report of "no daemon".
- **FR-005**: The shell MUST read the daemon's port and token from `~/.coffer/daemon.json` like every other client, and MUST NOT mint, store or cache a credential of its own. The file's format and lifecycle are spec daemon's; the shell is one of its readers, in a different language, so any change to it MUST be made on both sides together.

**Finding, starting and restarting a daemon**

- **FR-006**: The shell MUST locate a daemon by a fixed resolution order — a live daemon named by `~/.coffer/daemon.json`, then its own bundle, then `~/.coffer/bin/`, then `PATH` — taking over an already-running daemon rather than spawning a second one. The liveness probe MUST come first: the other three answer which binary to spawn, while it answers whether to spawn at all, and reversing them makes a bundled app race the daemon the user already started for its port. The probe MUST be an HTTP status check rather than a bare TCP connect, so a process squatting the recorded port is not mistaken for a daemon. When no daemon can be found or started it MUST say so in terms a user who has never opened a terminal can act on. It MUST offer a restart, reachable from both the tray and the offline banner — an affordance the browser host cannot have, because a daemon that is down cannot serve the page the control would live on. It MUST detect version skew between itself and the daemon it is talking to, since a previous installation's daemon may still be listening.
- **FR-007**: Restart MUST be a true restart: when a daemon is responsive it MUST be asked to shut down over its token-gated shutdown route and the port MUST be observed free before a replacement is spawned. A restart that silently became a no-op would do nothing at exactly the moment a user reaches for it — a wedged-but-listening daemon — and a failure to free the port MUST be reported rather than followed by a spawn that cannot bind.
- **FR-008**: Restarts MUST be serialised and rate-limited to at most one every five seconds, measured from the last **successful** restart. A failed spawn MUST NOT consume the window, so the user can retry immediately rather than waiting out a cooldown a failure earned.
- **FR-009**: A daemon the shell spawns MUST be detached and MUST outlive the app. It MUST NOT be started through the framework's managed-sidecar mechanism, which tears its children down when the app quits — the daemon serves agents that have nothing to do with the window being open.
- **FR-010**: Before spawning a daemon, an app launched from Finder or the Dock MUST discover the user's real `$PATH` by probing the login shell, and pass it on. A GUI-launched application inherits a minimal `$PATH`, so without this the daemon — and the `npx` / `uvx` MCP upstreams it spawns in turn — fail to resolve. The probe MUST be bounded in time and MUST degrade to the inherited `$PATH` rather than delay the launch.

**What the shell must not do**

- **FR-011**: The shell MUST NOT reimplement any capability the daemon already exposes over HTTP. Native folder selection, opening a file in the user's editor and revealing it in the file manager are daemon routes, and a webview reaches them exactly as a browser tab does; duplicating them in the shell would reintroduce a host-conditional branch in the frontend for no user-visible gain. It MUST declare no native dialog or opener plugin. A native plugin is admissible only where the daemon **cannot** stand in: a system notification is the one such case today, because there is no loopback route that raises one and only the installed bundle can post a notification as Coffer at all (spec vault-sync FR-096). The shell MUST NOT deploy binaries into `~/.coffer/bin/` — that is the daemon's frozen-start job (spec daemon, distribution), and two processes writing that directory race.

**The shell's own records**

- **FR-012**: The shell MUST install a logger before anything else runs, and MUST write its own records — which binary the resolution chain picked, that a restart asked from the tray failed — as one-line JSON shaped like the daemon's own structured lines, carrying `coffer.desktop` as the logger name, appended to `~/.coffer/logs/daemon.log`. It MUST NOT create a second log file. Until the logger existed a failed tray restart failed in silence, on the one surface a user reaches when the daemon is down and the web UI is therefore unreachable; a separate `desktop.log` would be a second place to look that nothing tells anyone about.

**Distribution ([PyInstaller Distribution](../../docs/decisions/distribution-pyinstaller.md))**

- **FR-013**: The release pipeline MUST produce, per `v*` tag, a **macOS arm64** `.dmg` containing the Tauri shell with the four frozen binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-callback` — embedded as Tauri `externalBin`, so that installing it requires nothing installed beforehand. macOS x64 (Intel), Linux and Windows are deliberately not built; those legs were never validated end to end. The desktop leg MUST reuse the artifacts the terminal leg already built rather than running PyInstaller a second time; the freezing is the expensive half and it is done once. This `.dmg` is the double-click install and it ships on every tag; the terminal install is the archive tier of spec daemon, and neither tier is a substitute for the other.
- **FR-014**: Because the embedded binaries are unsigned, a browser-downloaded `.dmg` carries macOS's quarantine attribute and the app is refused on double-click. The release notes and the README MUST therefore carry the quarantine-clearing step as prominently as they carry it for the terminal tier. Notarisation is a documented non-goal pending a paid developer account.

### Key Entities

- **The shell**: one macOS application bundle. Holds a window, a tray, a webview over the shared frontend build, and the resolution policy for finding a daemon. It owns no persistent state of its own.
- **The handshake**: the IPC exchange that hands the webview a base URL and a token. Ephemeral — it is re-made on every launch and never written down.
- **The desktop tier**: the `.dmg` artifact of a release, and the four binaries inside it.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with no Python and no Coffer checkout, installing the `.dmg` and double-clicking the app reaches Coffer's UI, authenticated, with no terminal step beyond clearing the quarantine attribute.
- **SC-002**: The app's window renders in under a second from launch even when no daemon is running, and fills in without user action once one is.
- **SC-003**: Launching the app while a terminal-started daemon is running produces exactly one daemon process.
- **SC-004**: After the app quits, a daemon it spawned is still serving.
- **SC-005**: The shell's records and the daemon's appear interleaved in one log file, and the daemon-log reader parses both.
- **SC-006**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="desktop-app", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.

## Assumptions

- **This spec needs no `contracts/` directory, because it exposes no HTTP surface of its own.** The shell is a client: it calls the daemon's routes (`/api/v1/daemon/status`, `/api/v1/daemon/shutdown`) and reads `~/.coffer/daemon.json`, both of which spec daemon's contract carries. Its only internal interface is a Tauri IPC command, which is in-process and not a wire contract. The repo's one-contract-per-spec rule is satisfied by having none.
- **The shell's tests are gated, but only the cheap half of the shell is.** `.github/workflows/desktop.yml` installs a Rust toolchain and runs `make desktop-lint` (`cargo check --all-targets`, `cargo clippy -- -D warnings`) and `make desktop-test` (`cargo test`) on every push and pull request touching `desktop/`, the `Makefile`, or the workflow itself. So the pure functions written precisely so they could be unit-tested — the close-to-tray decision, the restart rate limit and its stop-then-start order, the resolution chain's ordering, the port and status parsing, the login-shell `$PATH` probe, the detachment of a spawned daemon — are run by CI, and the acceptance markers on them are honest. `make verify` still excludes the crate, so a local `make verify` proves nothing about the shell; `make desktop-test` is how anyone with a toolchain runs it by hand.

  What that workflow does **not** run is `make desktop` — the PyInstaller-plus-Tauri bundling step, roughly fifty minutes — so nothing in CI proves the `.app` assembles, that `externalBin` resolves to real binaries rather than the placeholders `make desktop-stage-binaries` fakes, or that the `.dmg` opens. That is the release workflow's job, and it only runs on a tag. Nor can `cargo test` reach anything needing a live Tauri runtime: hiding the window on close, restoring it from the Dock, the tray menu's own items, and the IPC commands' `AppHandle`-bound halves are exercised by launching the app, not by a gate.
- **The offline banner is rendered by the web UI; this spec owns the control inside it.** The banner is one component with a host-conditional affordance: in the shell it offers Restart, because only the shell can. FR-006 is where that control's behaviour is specified; spec web-ui states where it appears.
- **`~/.coffer/daemon.json` is spec daemon's file, read here by a different language in a different crate.** That is precisely where a silent drift would live, so a change to its shape is a change to both specs.
- **The version in the shell's bundle configuration is one of three places a release version is written.** Keeping them in step is release procedure rather than a requirement of this spec; a mismatch shows up as a version-skew warning rather than a failure.
- **One `frontend/dist` feeds both hosts.** A stale `.app` can carry a stale UI build, which is the bounded residue of the retirement this shell reversed. There is no second frontend to drift from.

## Deliberately out of scope

- **Any platform but macOS arm64.** No Windows shell, no Linux shell, no Intel build. Those legs were never validated end to end, and a shell is the tier where "never validated" is most visible to the user.
- **Supervising anything but the daemon.** The shell does not watch upstream MCP processes, does not restart them, and does not report their health; that is the daemon's job and the UI already shows it.
- **Auto-update.** The operating cost of updating a desktop build is what retired the previous shell; adding an updater to it would be adding machinery to the expensive half rather than removing it. A new version is a new `.dmg`.
