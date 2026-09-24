# The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Related**: [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), [Daemon Detect-or-Spawn](daemon-detect-or-spawn.md), [The Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [The Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md), [Distribution](distribution-pyinstaller.md), [The Daemon Proxies OS File Actions](daemon-proxies-os-file-actions.md), spec desktop-app, spec daemon "Serve the built web UI from the daemon's own origin", research note [desktop shell and daemon](../research/desktop-shell-and-daemon.md), PRs #317, #376, #412

## Context

Coffer's UI is a single-page app the daemon serves at its own loopback origin
(spec daemon "Serve the built web UI from the daemon's own origin"). That is
enough for someone already in a terminal and close to useless for anyone else:

- **It cannot be found.** It is one `127.0.0.1` tab among dozens, with no Dock
  icon, nothing in Cmd-Tab and nothing resident to click.
- **It cannot be started without a terminal.** Reaching it means knowing that a
  daemon must be running and that `coffer open` is the command that finds it.
- **It cannot recover itself.** When the daemon is down or wedged, the page that
  would carry a restart control is served by the very process that is not
  serving.
- **It does not read as a product.** Coffer is also a portfolio project, and a
  localhost page that opens only from a terminal demonstrates the architecture
  but not the thing.

A Tauri shell existed before and was removed in PR #317 (2026-09-09) over its
operating cost: every update meant a rebuild plus a reinstall, and the built
artifact drifted from source twice on record — once from a build made before
fetching, once from a separately pinned build directory that made UI bug reports
untrustworthy until re-verified against `main`. That judgement priced the cost
of each update and not the cost of access; the four problems above are what the
following days without a shell showed. By then two of the old shell's largest
jobs had moved somewhere better: deploying the frozen binaries into
`~/.coffer/bin/` had become the daemon's frozen-start job (spec daemon "Deploy
frozen sibling binaries and back up the vault before migrating"), and folder
picking, open-in-editor and reveal-in-Finder had become daemon HTTP routes
([The Daemon Proxies OS File Actions](daemon-proxies-os-file-actions.md)), which
a webview calls exactly as a browser tab does.

So the question is not whether to have a shell but what shape it takes, under
one constraint the old shell never had: **the same `frontend/dist` build must
serve a browser and a native window**, because a second UI build is a second
thing to drift.

## Options Considered

### Option A — A Tauri shell that hosts the built frontend as a local asset and owns only what a browser cannot do (chosen)

`desktop/tauri.conf.json` sets `frontendDist: ../frontend/dist`, and the window
loads that build from the bundle, not from `http://127.0.0.1:<port>/`. The shell
owns exactly four things:

1. **A window with a Dock icon and a Cmd-Tab entry.** Closing it hides to the
   tray rather than exiting (`tray.rs`).
2. **A resident tray** with Open Coffer, Restart daemon, Quit, and a Sync entry
   that exists only while the `vault_sync` experimental feature is on
   (`sync_gate.rs` reads `features.vault_sync` from the unauthenticated
   `/api/v1/daemon/status`; `sync_watch.rs`, `sync_presentation.rs` and
   `sync_alert.rs` badge the icon and raise the notification of spec vault-sync
   "Say a vault needs a human where the user already is").
3. **Detect-or-spawn at launch** (`resolve.rs`), by a fixed chain: a live daemon
   named by `~/.coffer/daemon.json`, then the binary inside the app bundle, then
   `~/.coffer/bin/coffer-daemon`, then `coffer-daemon` on `PATH`, then a message
   telling the user to install the CLI. The liveness probe is first because it
   answers a different question — *whether* to spawn — from the other steps,
   which answer *which binary*; asked the other way round, a bundled app would
   start a rival beside the daemon the user already started from the CLI, and
   under [the fixed port](daemon-binds-a-fixed-port.md) that rival cannot bind.
   The probe is an HTTP status call, not a TCP connect (`discovery.rs`), so a
   process squatting the port is not mistaken for a daemon. A spawned daemon is
   a plain detached process (`spawn.rs`), not a Tauri-managed sidecar, because
   the managed sidecar dies with the app and the daemon serves agents with no
   window open; it inherits the login shell's `PATH` (`env_path.rs`), since a
   Finder-launched app gets a minimal one and the daemon's `npx`/`uvx` upstreams
   would not resolve.
4. **The credential handshake** a locally-hosted page cannot get any other way.
   No daemon served the document, so nothing injected a token into it (the
   browser path of [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md)).
   The page calls the IPC command `get_daemon_info`, and
   `applyDaemonConnection` in `frontend/src/lib/tauri.ts` writes the answer onto
   the same `window.__COFFER_BASE_URL__` / `window.__COFFER_TOKEN__` globals the
   other suppliers write (`frontend/src/lib/auth.ts`). Readers never learn which
   host they are in, which is why this is a second *supplier* and not a second
   *code path*.

Because the page is local, two affordances become possible that a browser
cannot have, both inside the offline banner and both reached through
`lib/tauri.ts`: a **Restart** control (the `restart_daemon` command — in a browser
a down daemon cannot serve the button), and a **version-skew check**
(`daemon_version_matches`), since a daemon left detached by an earlier app
version can still be listening; the shell attaches to it and warns rather than
refusing to work.

Pros: the UI is on screen whatever the daemon is doing, so "no daemon" becomes a
rendered, actionable banner rather than a connection error; the port never
appears in an address bar; the shell can restart the daemon, which is the only
recovery path open to someone who has never used a terminal; one frontend build
serves both hosts. Cons: the page's origin is the webview's (`tauri://localhost`
on macOS) while its API is `http://127.0.0.1:<port>`, so every call is
cross-origin, and the page has no address until the handshake lands. Both are
handled rather than avoided — see Decision. It wins because it is the only shape
that fixes all four problems in Context without forking the frontend.

### Option B — No shell; the daemon-served browser tab is the only UI

The design between PR #317 and PR #376. Pros: nothing to rebuild or reinstall
for an update (restart the daemon, hard-refresh), no Rust toolchain, no second
artifact to drift. Cons: every problem in Context — no Dock presence, no route in
that does not start in a terminal, and no recovery when the daemon is down,
because the page is the daemon's. It loses because it optimised the cost of an
update, which the owner pays, over the cost of access, which every user pays.
The browser host is not replaced by Option A; it stays the right answer for a
terminal user and is served by the same build.

### Option C — A thin shell that navigates to `http://127.0.0.1:<port>/`

The cheapest possible shell: a native window pointed at the daemon's origin.
Pros: no drift at all (the daemon serves whatever it shipped), no cross-origin
calls, no handshake — the daemon injects the token as it does for a browser.
Cons: it is a bookmarked browser window. Nothing renders until the daemon
answers, so a launch after a reboot shows a blank or error page; a daemon that
is down leaves a dead page with nowhere to put a Restart control; and Tauri IPC
is not available to a remote origin without per-domain capability configuration.
It loses because it solves discoverability but not recovery, which is the
problem only a shell can solve.

### Option D — Revert PR #317 wholesale

Restore the old shell as it was: Tauri `dialog` and `opener` plugins for native
file actions, and binary deployment into `~/.coffer/bin/` from the shell. Pros:
known code. Cons: the file actions already work in a webview through daemon
routes, so restoring the plugins would rebuild the `isTauri()` branches across
the frontend's file components for nothing a user could perceive; and the daemon
already deploys the binaries, so two processes would race to write
`~/.coffer/bin/`. It loses because roughly half of what it would restore had
since been replaced by something both hosts share.

### Option E — Electron

Ship Chromium and Node with the app. Pros: one rendering engine everywhere, a
large ecosystem. Cons: on the order of 100 MB of runtime before Coffer's own
three frozen binaries, and a second JavaScript runtime in a product whose logic
lives in Python; Tauri uses the system WKWebView and a small Rust host. It loses
on size and on the fact that the shell's job is small — nothing it does needs a
bundled browser.

## Decision

**Coffer ships a Tauri shell that hosts the one `frontend/dist` build as a local
asset and owns exactly four things a browser cannot do for itself: a window, a
tray, detect-or-spawn at launch, and the IPC credential handshake.** Rules a
change must respect:

- **No second frontend path.** Outside `lib/tauri.ts`, `lib/auth.ts`'s
  `setDaemonConnection` and the offline banner (Restart and version skew), no
  frontend module branches on `isTauri()` (spec desktop-app "Consume the one
  frontend build the daemon serves"). File actions stay daemon routes in both
  hosts — `lib/fsActions.ts`, `components/FileActions.tsx` and
  `components/FolderPicker.tsx` call the daemon, and `desktop/Cargo.toml`
  declares no `dialog` or `opener` plugin. A native plugin is admissible only
  where the daemon cannot stand in; the one today is `tauri-plugin-notification`,
  because no loopback route can post a notification as Coffer (spec desktop-app
  "Reimplement no daemon route in the shell").
- **The shell owns no state and deploys nothing.** It reads
  `~/.coffer/daemon.json`, appends `coffer.desktop` records to
  `~/.coffer/logs/daemon.log` (`logging.rs`), and never writes
  `~/.coffer/bin/` — that is the daemon's job.
- **The window waits for a daemon; the page does not.** `tauri.conf.json`
  creates the window hidden and `reveal_main_window` (`daemon.rs`) shows it once
  the handshake reaches a daemon or fails — an app that showed itself only on
  success would stay invisible when no daemon can start. The page itself starts
  the handshake alongside its first render (`main.tsx`), never before it.
- **A readiness ceiling, not an expectation, and a handshake that retries.** A
  daemon the shell starts gets 90 seconds to answer
  (`DAEMON_READY_TIMEOUT_SECS` in `ready.rs`), shared by launch and restart. The
  earlier 15-second ceiling sat inside the five to fourteen seconds a real
  vault's daemon takes to unpack, migrate and bring its upstreams up, so a slow start was declared dead while seconds from serving and
  the banner never cleared (PR #412). The page also retries a failed handshake
  on a 1 s, 2 s, 5 s, 10 s, then every-30 s backoff
  (`HANDSHAKE_RETRY_DELAYS_MS`), so the ceiling decides how long one attempt
  waits, never whether the app recovers.
- **No guessed address.** Until a supplier names a base URL, `getCofferBaseUrl`
  returns `null` for a non-http document and callers report "daemon not ready".
  Falling back to the document's origin produced `tauri://localhost/api/v1`,
  which WebKit refuses to build a request from ("The string did not match the
  expected pattern"), and the banner called a healthy daemon offline (PR #412).
- **The daemon admits the shell's origin.** Calls from `tauri://localhost` to
  `http://127.0.0.1:<port>` carry `X-Coffer-Token`, which forces a CORS
  preflight, so `SHELL_ORIGINS` in `backend/coffer/surfaces/http/cors.py` is
  allowed by default. It lives in the daemon rather than being passed in by the
  shell because the shell usually attaches to a daemon it did not start. The
  token, not CORS, is the boundary.
- **Restart is a true restart, rate-limited from the last success.**
  `restart_daemon` holds one lock across the rate-limit check, the stop, the
  spawn and the timestamp; asks a responsive daemon to shut down over its
  token-gated route and waits for the port to free; allows one restart per five
  seconds counted from the last *successful* one; and returns the replacement's
  connection so the page installs it instead of handshaking again — a second
  handshake arrived before the new daemon bound its port and spawned a rival.
  The policy arithmetic is pure (`restart.rs`).

The port the daemon binds is decided in
[The Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md); how the `.dmg`
bundles the frozen binaries and installs the CLI is decided in
[Distribution](distribution-pyinstaller.md).

## Consequences

- **Two hosts, one build.** `frontend/dist` is consumed by the daemon's static
  mount and by the Tauri bundle; a UI change reaches both, and they cannot
  diverge in source.
- **The retirement's failure mode is bounded, not gone.** A stale `.app` can
  still carry a stale `frontend/dist`. The daemon half of that staleness is made
  visible by the version-skew warning; the UI half is accepted as the price of
  reachability.
- **A third credential supplier.** The daemon's injected page and the Vite dev
  plugin were the first two; the shell's IPC handshake is the third, and all
  three converge on the same two globals.
- **Rust is in the build, outside `make verify`.** `cargo` is a prerequisite of
  `make desktop` and of the release's desktop leg only. The crate's pure
  helpers (close-to-tray, rate limit, port parsing, sync gating, ready budget)
  are unit-tested by `make desktop-test` and linted by `make desktop-lint` in
  `.github/workflows/desktop.yml`. A local `make desktop` runs PyInstaller over
  three binaries before the Tauri build and takes roughly 50 minutes (the
  `Makefile` says so when it starts); the release reuses the binaries its CLI leg
  already froze.
- **Nothing in CI opens the app.** The window's hidden-until-ready behaviour,
  the tray items and the `AppHandle`-bound halves of the IPC commands need a
  live Tauri runtime and are exercised by launching the built `.app`.
- **macOS arm64 only.** No Windows, Linux or Intel shell is built; those legs
  were never validated end to end (spec desktop-app "Ship the desktop tier as a
  macOS arm64 dmg").
