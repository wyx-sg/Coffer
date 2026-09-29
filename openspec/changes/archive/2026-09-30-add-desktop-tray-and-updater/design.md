## Context

The shell's tray was built when the shell was restored (ADR desktop-shell-over-a-shared-frontend) with the minimum the spec asked for: open, restart, quit, and a red dot badged onto the colour app icon by the sync watcher. The design canvas (1.5 Menu bar, four boards; 6.2.13–6.2.15 Settings › About) draws the finished item and the About tab's update states. Auto-update was listed out of scope because a new version was a new `.dmg`; it was specified in `revise-web-ui-ia` and moves here, where it is built. Signing was a non-goal pending a Developer ID; the Keychain access-group backend (ADR master-key-lives-in-the-macos-keychain) was built behind a stamp nothing could yet apply.

## Decisions

### D1. One light poll feeds the menu bar, not the event stream

`tray_watch.rs` reads `daemon.json` and `GET /api/v1/daemon/status` every 10 s, the attention list and the login service every 60 s and at once whenever the daemon comes (back) up, and is woken early by a tray action that changes something (a restart, the Start at login switch). The sync watcher is handed each status answer instead of reading its own, so one status request per tick serves both.

*Rejected:* subscribing to `/api/v1/events`. The shell talks to the daemon over raw HTTP/1.1 on a `TcpStream` (`daemon_http.rs`) precisely so it carries no HTTP client; an SSE client with reconnect and `Last-Event-ID` would be the largest thing in the crate, to learn a count that changes on a human timescale a minute sooner. A daemon going down is not an event at all — the stream simply ends — so the status poll would stay anyway.

### D2. "Restart to install" means on offer, not already downloaded

The canvas note says the update entry reads "Update available — Restart to install" once a signed update is downloaded. The requirement says nothing is downloaded or installed until the user chooses to. Both hold if the entry appears when a check has found a signed release, and choosing it is the user's Download and restart: it downloads, verifies, installs and relaunches, with its progress in the entry's own label. A background download would spend a metered connection's bandwidth on an update the user may never want, and would need somewhere to keep a verified archive between runs, which the shell does not have.

### D3. The shell owns no update state on disk

"Check automatically" lives in the page's `localStorage`, like the interface language, and the page reports it at startup (`followUpdatePreferenceInShell`); the shell's first check waits 30 s, long enough for that report to land. The last-checked time and the result are in memory: a relaunch checks again 30 s after launch, which is what "at launch" asks for. The schedule uses wall time, because an `Instant` stops while a Mac sleeps and a laptop that sleeps overnight should check when it wakes.

### D4. The updater key is compiled in, and a build without one never checks

`updater.rs` reads `COFFER_UPDATER_PUBKEY` with `option_env!`, and the release workflow sets it from a repository variable. `tauri.conf.json` names the endpoint and `requireSignedVersion` and leaves `pubkey` empty rather than committing a key a fork would ship. A build without a key — every build from source — reports itself unconfigured: About says it does not check, and no request leaves the machine. `requireSignedVersion` rejects an archive whose signed trusted comment names a different version than the manifest, which closes the downgrade the unsigned manifest otherwise allows; it is safe to require from the first signed release because none predates it.

### D5. The relaunched shell replaces the old daemon through the one restart

`tauri::process::restart` spawns the new executable directly, so an environment variable set before it (`COFFER_RELAUNCHED_FOR_UPDATE`) is inherited. The new process reads it once at startup and removes it, and its first handshake, finding a running daemon whose version differs, runs `restart_daemon` and returns that connection. Without the mark the shell attaches and reports skew as before, so an ordinary launch never kills a daemon the user started.

### D6. PyInstaller signs the frozen binaries

With `codesign_identity` set, PyInstaller signs every binary it collects and then the executable, under the hardened runtime. A one-file build unpacks those libraries at start, so signing only the outer executable would fail library validation the moment Python loaded its first extension. The specs read the identity and entitlements from `COFFER_CODESIGN_IDENTITY` / `COFFER_ENTITLEMENTS_FILE`, set only by the release workflow; everywhere else they stay `None`. The entitlements carry `keychain-access-groups` and nothing else: no `get-task-allow`, and no `cs.*` exception, since everything loaded is signed by the same team. `release_signing.sh verify` checks team, hardened runtime, entitlement and the absence of `get-task-allow` before anything is packaged.

*Open:* whether the access-group entitlement needs a provisioning profile for a Developer ID build (the ADR's open question). An optional `APPLE_PROVISIONING_PROFILE` secret is embedded in the app when present. A bare CLI binary cannot carry a profile; if the entitlement turns out to need one, the ADR's fallback applies (the daemon runs from inside the signed app).

### D7. Tauri notarises the app; notarytool does the rest

Given `APPLE_API_ISSUER` / `APPLE_API_KEY` / `APPLE_API_KEY_PATH`, `tauri build` notarises and staples the `.app` before it builds the `.dmg` and the updater archive from it, so both carry a stapled app. The workflow then notarises and staples the `.dmg` itself, and notarises the three CLI binaries as a zip (a bare Mach-O cannot be stapled; Gatekeeper finds the ticket online).

### D8. Every signing step is gated, and says so

`scripts/release_plan.py` receives each credential's presence — `${{ secrets.X != '' }}`, never the value — and writes `codesign`, `notarize` and `updater` outputs the steps' `if:` read, with one annotation per step naming what is missing. The updater is independent of Apple signing. An unsigned `.dmg` keeps its `Coffer-unsigned-` name and the release notes keep the quarantine step.

### D9. The icon is pre-rendered template PNGs

Three SVGs (normal, needs-you, offline) are rendered to 18 px and 36 px PNGs by `scripts/render_tray_icons.sh` and checked in; the shell picks the 36 px set on a Retina primary display. macOS draws a menu bar item 18 pt tall and tints a template image itself, so drawing a dot into pixels at runtime (the old `badge_rgba`) is replaced by a variant the designer drew.

### D10. The Sync entry folds into "needs you"

Sync problems are already items of the attention list (`SyncAttentionSource`), so a separate Sync entry counted them twice. A single sync problem is named in the "needs you" entry; the notification and Dock badge the vault-sync requirement asks for are unchanged.
