# The Desktop Shell Returns, Owning Only What a Browser Cannot Do

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Spec**: [daemon](../../specs/daemon/spec.md) FR-016 / FR-011; [desktop-app](../../specs/desktop-app/spec.md) FR-001 … FR-011
**Supersedes in part**: the "A desktop shell" explicit non-goal recorded in the roadmap on 2026-09-09
**Related**: [The Daemon Serves Its Token in the Page](./daemon-serves-the-token-in-the-page.md) (which this amends — its "there is no third case" now has one), [Detect-or-Spawn](./daemon-detect-or-spawn.md), [PyInstaller Distribution](./distribution-pyinstaller.md), [The Daemon Proxies OS File Actions](./daemon-proxies-os-file-actions.md)

## Context

The Tauri shell was retired on 2026-09-09. The reasoning was about operating
cost, and it was sound: every desktop update meant a rebuild *plus* a reinstall,
and the built artifact kept drifting from source — twice on record, once from a
build made before fetching, once from a separately pinned build directory that
made UI bug reports untrustworthy until re-verified against `main`.

What the retirement did not weigh is that the shell was also the only thing that
made Coffer *reachable*. Three months of daemon-served web UI surfaced the cost
of not having it:

- **It cannot be found.** Coffer is one `127.0.0.1` tab among dozens, with no
  Dock icon, nothing in Cmd-Tab, and nothing resident to click. Every visit
  starts with hunting for a tab or retyping a port.
- **It cannot be started without a terminal.** Reaching the UI means knowing
  whether a daemon is running, on which port, and that `coffer open` is the
  command that answers both. That is a reasonable ask of a CLI user mid-session
  and an unreasonable one of someone who just wants to look at their vault.
- **It does not read as a product.** Coffer is also a portfolio project. A
  localhost page that only opens from a terminal command demonstrates the
  architecture but not the thing.

None of these is an argument for undoing the retirement. They are arguments for
a shell that owns *only* these three problems — which is a much smaller shell
than the one that was removed, because the intervening three months moved most
of its work somewhere better:

- Binary deployment moved into the daemon's own frozen-start path (spec daemon FR-027).
- Native folder picking, opening a file in the user's editor, and revealing it
  in Finder all moved onto daemon HTTP routes
  ([The Daemon Proxies OS File Actions](./daemon-proxies-os-file-actions.md)) —
  and those work unchanged inside a webview, because a webview can make HTTP
  requests to loopback exactly like a browser tab.

So the shell comes back with its two largest responsibilities already handled by
someone else, and with a constraint the original never had: **the same frontend
build must now serve both a browser and a native window.**

## Decision

**Restore the Tauri shell as a native host over the existing frontend, owning
exactly four things a browser cannot do for itself:** a window with a Dock icon,
a resident tray, detect-or-spawn of the daemon at launch, and the credential
handshake that a locally-hosted page cannot get any other way.

### The shell hosts the UI; it does not reimplement it

`tauri.conf.json` keeps `frontendDist: ../frontend/dist`. The window loads the
built SPA as a local asset — not `http://127.0.0.1:<port>/`. This is what makes
it a native app rather than a bookmarked browser window: the UI is present
before the daemon answers, so a daemon that is slow, absent or wedged produces a
rendered page with an actionable banner instead of a connection error.

It also means the port is invisible to the UI. Only API calls carry it, and the
shell reads it from `~/.coffer/daemon.json` — the same file every other client
reads.

### The frontend gains a host, not a fork

The page is a local asset, so nobody injected a token into it. The browser's
mechanism (spec daemon FR-017) cannot apply, and the shell supplies the same two globals
through an IPC command instead:

```
browser  → daemon injects window.__COFFER_TOKEN__ into index.html   (spec daemon FR-017)
Tauri    → shell invokes get_daemon_info → setDaemonConnection(...)  (spec desktop-app FR-004)
```

Three files change: `lib/tauri.ts` returns, `lib/auth.ts` regains
`setDaemonConnection`, and `main.tsx` starts the handshake when `isTauri()` —
alongside the first render, never before it. Blocking on it would undo the
paragraph above: the handshake spawns a daemon and polls when none is running,
so a launch after a reboot would sit on an empty window for most of that.
Rendering first shows the real application immediately with the banner
explaining the gap, and the queries that went out uncredentialed are refetched
when the handshake lands. `getCofferBaseUrl` / `getCofferToken` are untouched — both hosts
converge on the same globals, which is why this is a second *supplier* and not a
second *path*.

Nothing else forks. In particular the Tauri `dialog` and `opener` plugin
branches deleted in 2026-09-09 stay deleted: `filePicker.ts`, `fsActions.ts`,
`FileActions.tsx` and `FolderPicker.tsx` keep going through the daemon in both
hosts. Restoring them would recreate the `isTauri()` fan-out that made the
frontend expensive to change, in exchange for nothing a user could perceive.

Two affordances become meaningful again *because* the page is local, and both
are gated on `isTauri()`:

- **A restart control on the offline banner.** In a browser this is impossible —
  a daemon that is down cannot serve the page the button would live on. In the
  shell the page is already there, and the shell can spawn the daemon.
- **A daemon version-skew check.** The app pairs with a daemon; a previous
  version's daemon can still be listening. The browser has no such pairing.

### The daemon binds a fixed port by default

Spec daemon FR-011 made the port configurable, defaulting to a scan of 8000–8009. The
default inverts: **the daemon binds 8000, and refuses to start if it cannot**,
naming the process that holds it — machinery spec daemon FR-011 already built for its
configured-port path.

The scan was always the unusual choice. Local services with a web UI fix a
default port and allow it to be changed — Ollama, Syncthing, Grafana, Home
Assistant, Tailscale — and the ones that scan forward (Jupyter, Vite) are
development tools that print their real URL on every start and that nobody
bookmarks. A drifting origin costs more than a broken bookmark: browser
`localStorage` is keyed by origin, so the UI language, sidebar state, page size
and preferred editor silently reset when the port moves, and nothing connects
the two events for the user.

The Settings → General "Web address" card and `GET`/`PUT /settings/daemon` are
removed with it. A port that is correct by default does not deserve a panel, and
the escape hatch is better placed where a squatted port is diagnosed:
`coffer daemon port set/clear`, which works with no daemon running.

### The app is a self-contained installer, and installing it installs the CLI

The `.app` bundles four frozen binaries as Tauri `externalBin` — `coffer`,
`coffer-daemon`, `coffer-mcp-shim` and `coffer-callback` — and the build emits a
`.dmg`. Download, drag to Applications, double-click: nothing else is required,
which is what "desktop app" has to mean to be worth having.

`coffer-hook` and `whisper-cli`, which the old shell also bundled, are not in
that list. Both were retired in the intervening months — the SessionStart hook
with the last of the native-config writes, voice transcription when it moved off
the machine — so this is a strictly smaller bundle than the one that was removed.

The shell resolves the daemon through a five-step chain: an already-running
daemon named by `daemon.json`, then its own bundle, then `~/.coffer/bin/`, then
`$PATH`, then a message saying to install the CLI. The liveness probe is first
and that position is correctness rather than preference — steps two through four
all answer *which binary would we spawn*, while step one answers *whether to
spawn at all*. Ask them the other way round and a bundled build opens a second
daemon beside the one the user already started from the CLI; under the fixed-port
default that rival cannot bind, so an app that should simply have attached
instead reports a port conflict. Bundling makes step two the normal way to find
a binary rather than a dead one; the rest stay as the recovery path for a bundle
whose sidecar is missing or unrunnable.

**Installing the app also installs the CLI**, without the shell doing anything.
The daemon deploys its own siblings — all four, `coffer` included — into
`~/.coffer/bin/` on frozen start (spec daemon FR-027), so the first launch of the app leaves
the command-line tools on disk for the user to put on `PATH`. This is the
arrangement Ollama, Docker Desktop and Tailscale all use: one installable app,
with the CLI linked out of it rather than installed before it.

What this costs is build time. `make desktop` now runs PyInstaller for four
binaries before it runs Tauri — on the order of an hour — where a shell without
bundling would have taken minutes. That is the operating cost the 2026-09-09
retirement objected to, accepted deliberately this time, and bounded by the fact
that only a release needs the full build.

It also inherits Coffer's standing macOS problem: the binaries are unsigned, so
a browser-downloaded `.dmg` carries `com.apple.quarantine` and macOS refuses the
app on double-click with "Coffer is damaged", recoverable only through System
Settings. The release notes and README must carry the quarantine-clearing step
as prominently as they already do for the CLI archive. Notarisation remains a
documented non-goal pending a paid Apple Developer account, and it is now the
single highest-value thing that account would buy.

## Consequences

- **Two hosts, one build.** `frontend/dist` is consumed by the daemon's static
  mount and by the Tauri bundle. Any UI change reaches both; neither can drift
  from the other, because there is only one artifact.
- **The retirement's failure mode is bounded, not gone.** A stale `.app` can
  still ship a stale `frontend/dist`. It is now bounded to the UI — no daemon,
  no shim, no helper binaries travel inside the app — and the version-skew check
  makes the daemon half visible. This is a real cost, accepted for reachability.
- **[The Daemon Serves Its Token in the Page](./daemon-serves-the-token-in-the-page.md)
  gains a third case.** Its consequence "A browser that is not served by the
  daemon has no token… There is no third case" was true when written. The shell
  is the third case, and it supplies the token by IPC rather than by document.
  That ADR is amended rather than superseded: injection remains how *browsers*
  are credentialed, and the `Host` guard that makes it safe is unchanged.
- **A bookmark works again, and so do browser-stored preferences.** Both follow
  from the fixed port, and both accrue to the web host the shell does not
  replace.
- **A port conflict is now a startup failure rather than a silent move.** The
  diagnosis names the holder and the fix, but the daemon does not start until
  the user acts. This is the intended trade: a predictable origin is worth more
  than an automatic one.
- **The release grows a second tier again, and it is nearly free.** Spec daemon
  FR-025 collapsed the release to one `coffer-cli-<triple>.tar.gz`; a `.dmg` joins it.
  The expensive half — PyInstaller over four binaries — is work the release job
  already does for the CLI archive, so the desktop tier reuses those artifacts
  and adds only a Tauri build. The hour-long cost is a *local* `make desktop`
  cost, not a release one.
- **Rust re-enters the build, and its tests are not in `make verify`.** `cargo`
  is a prerequisite for `make desktop` and for the release's desktop leg only;
  no verification gate grows a toolchain.
  The cost is that `tray.rs`'s close-to-tray decision and `daemon.rs`'s
  rate-limit and port-parsing helpers — all written as pure functions precisely
  so they could be unit-tested — are covered by `cargo test` that no gate runs.
  They are reachable through `make desktop-test` for anyone with a toolchain.
  Accepted because the shell is small, changes rarely, and cannot break the
  daemon or the web host when it does; revisit if it starts accumulating logic.

## Alternatives considered

- **A thin shell loading `http://127.0.0.1:<port>/`.** Rejected. It is the
  cheapest possible shell and it dissolves the drift risk entirely, but the
  window is then a browser pointed at the daemon: nothing renders until the
  daemon answers, a restart onto a different port leaves a dead page until the
  shell re-navigates, and Tauri's IPC is not available to a remote origin
  without explicit per-domain capability configuration. The reachability
  problems would be solved; the "it should feel like a product" one would not.
- **Reverting PR #317 wholesale.** Rejected. Roughly half of what it deleted has
  since been replaced by daemon HTTP routes that work in both hosts, so
  restoring the Tauri `dialog` / `opener` branches would rebuild the `isTauri()`
  fan-out for no user-visible gain, and restoring the shell's binary deployment
  would put two processes in a race to write `~/.coffer/bin/`.
- **Keeping the 8000–8009 scan and relying on the shell.** Rejected. It would
  work for the desktop host, which reads the port from a file, and it would
  quietly keep punishing the browser host — which the shell explicitly does not
  replace — with broken bookmarks and resetting preferences.
- **Leaving the binaries out and presenting the app as an optional layer over an
  already-installed CLI.** Rejected. It builds in minutes instead of an hour and
  it sidesteps Gatekeeper — a `curl | sh` download carries no quarantine
  attribute and runs immediately, where an unsigned `.dmg` does not. But an app
  that refuses to run until you have already used the terminal does not answer
  the reason the shell is being restored at all, which is that reaching Coffer
  should not require knowing what a daemon is. The quarantine step is one
  documented command; needing the CLI first is a permanent second product.
