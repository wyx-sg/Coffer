---
title: Desktop app
description: Install and use Coffer's macOS desktop app — a native window and tray over the same web UI, which finds or starts the daemon for you.
---

# Desktop app

The Coffer desktop app is a macOS application that hosts Coffer's web UI in a native window, with a Dock icon and a menu-bar tray, and finds or starts the daemon for you. This page covers installing it, what it adds over a browser tab, how it connects to the daemon, and how quitting the app relates to the daemon's lifetime.

## What it adds

The app shows the same UI as `coffer open` — built from the same `frontend/dist` — so every page works identically. What it adds is what a browser tab cannot do for itself:

- **A real application.** A window with a Dock icon and a Cmd-Tab entry, and a tray icon that stays resident when the window is closed.
- **Detect-or-spawn.** At launch it attaches to a running daemon or starts one. You never need to know the port.
- **Recovery without a terminal.** **Restart daemon** in the tray and on the offline banner. A browser page cannot offer this: a daemon that is down cannot serve the page the button would live on.
- **A version check.** It warns when it has attached to a daemon left running by an earlier version.
- **Sync alerts where you look.** When [vault sync](/guides/vault-sync) needs you, the tray entry, the Dock badge and a notification say so.

Everything else — opening files in your editor, choosing folders — goes through the daemon's HTTP routes exactly as it does in a browser.

::: info Platform
The desktop app is built for macOS on Apple silicon only. On other platforms, use the CLI install and `coffer open`.
:::

## Install

::: warning No tagged release yet
The `.dmg` is published with a tagged GitHub release, and none exists yet. Until then, build the app yourself (see [Build from source](#build-from-source)).
:::

1. Download `Coffer-unsigned-aarch64-apple-darwin.dmg` from the project's [Releases](https://github.com/wyx-sg/Coffer/releases/latest) page.
2. Open the `.dmg` and drag **Coffer** to **Applications**.
3. The app is not code-signed or notarised, so macOS refuses a browser-downloaded copy with *"Coffer is damaged and can't be opened"*. It is not damaged. Clear the quarantine flag:

   ```sh
   xattr -dr com.apple.quarantine /Applications/Coffer.app
   ```

4. Open Coffer from Applications.

The app is self-contained: it carries the three frozen binaries `coffer`, `coffer-daemon` and `coffer-mcp-shim` inside its bundle, and needs nothing installed beforehand.

### The app installs the CLI too

On first start, the daemon copies all three binaries into `~/.coffer/bin`. Put that directory on your `PATH` to use `coffer` in a terminal and to let MCP clients resolve `coffer-mcp-shim`:

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add this to your shell profile
```

The app itself never writes to `~/.coffer/bin`; the daemon does it, so the two never race over that directory.

### Update

There is no auto-update. To update, install the new `.dmg` over the old app, clear the quarantine flag again, and restart the daemon from the tray so the app and the daemon run the same version.

## Launch

When you open the app:

1. It looks for a daemon (see [How it finds a daemon](#how-it-finds-a-daemon)), attaching to a running one or starting one.
2. The window stays hidden until that daemon answers, so you never see a page where nothing works. With the daemon already running — for example as a [login service](#keep-the-daemon-running) — this is instant.
3. If no daemon can be reached, the window opens anyway and says why.

A daemon on a real vault can take several seconds to unpack, migrate and bring its MCP servers up. The app gives a daemon it started up to 90 seconds to answer, and keeps retrying on a backoff after that, so a slow start clears on its own without a restart.

## The tray

Click the tray icon for its menu:

| Item | What it does |
| --- | --- |
| **Open Coffer** | Shows and focuses the window. |
| **Sync status** | Opens the Sync page. Shown only while the Sync feature is on. When a sync round needs you, its label names the problem, such as **Sync needs attention — conflict**. |
| **Restart daemon** | Stops the running daemon and starts a fresh one. |
| **Quit Coffer** | Quits the app. The daemon keeps running. |

Closing the window hides the app to the tray instead of quitting it. Clicking Coffer in the Dock brings the window back.

When a sync round needs a human — held for confirmation, a conflict, a failed push, a failed run, or a machine that has not joined yet — the app badges the tray icon and the Dock icon and posts one macOS notification titled **Coffer sync needs you**. Choosing **Sync status** takes you to the page that resolves it.

## Restart the daemon

Use **Restart daemon** in the tray, or on the offline banner in the window. A restart:

1. asks the running daemon to shut down over its authenticated shutdown route;
2. waits for the port to be free;
3. starts a new daemon and waits for it to answer. A restart from the banner hands the new daemon's connection straight to the window.

If the port does not free up, the restart reports that instead of starting a daemon that cannot bind. Restarts are limited to one every 5 seconds, counted from the last **successful** restart, so a failed attempt can be retried at once.

A restart from the tray has nowhere to show a message; its outcome is written to `~/.coffer/logs/daemon.log`.

## How it finds a daemon

The app resolves a daemon in a fixed order and takes the first that applies:

1. A running daemon named by `~/.coffer/daemon.json` that answers an HTTP status check. The app attaches to it and starts nothing.
2. The `coffer-daemon` inside the app bundle.
3. `~/.coffer/bin/coffer-daemon`.
4. `coffer-daemon` on your `PATH`.
5. Otherwise, a message that lists where it looked and how to install the CLI.

The running daemon comes first so the app never starts a second daemon beside one you started from a terminal. The status check, rather than a bare port probe, keeps an unrelated process on port 8000 from being mistaken for Coffer.

A daemon the app starts:

- **outlives the app.** It is detached from the app's process, because agents use it whether or not the window is open.
- **gets your login shell's `PATH`.** An app opened from Finder or the Dock inherits a minimal `PATH`; the app asks your login shell for the real one, with a time limit, so `npx`- and `uvx`-based MCP servers resolve.

### Version skew

If the app attaches to a daemon whose version differs from its own — typically one left running by a previous installation — it keeps working with it and shows **Daemon out of date** on the banner. Choose **Restart daemon** to replace it with the daemon from the app's bundle.

## How it connects

The window loads the UI from the app bundle, not from the daemon's address. That is why a slow or absent daemon produces a banner instead of a browser connection error, and why the port never appears anywhere.

Because the daemon did not serve that page, it could not write its token into it as it does for a browser. Instead the app reads the port and token from `~/.coffer/daemon.json` and hands them to the page over an in-process IPC call, as the same two values a browser page receives. The page renders first and applies them when they arrive. The app stores no credential of its own.

The window's content policy allows network requests only to loopback addresses (any port) and to the app's own IPC channel; scripts and styles come only from the bundle.

## Quit the app, keep the daemon

Quitting the app with **Quit Coffer** only closes the window and the tray. The daemon keeps serving your agents, channels and sync. To stop the daemon itself, run:

```sh
coffer daemon stop
```

### Keep the daemon running

Turn on **Settings → General → Coffer's daemon → Start at login** to start the daemon when you log in and restart it if it crashes, whether or not the app is open. The CLI equivalent is `coffer daemon service install`. With it on, the app attaches to an already-running daemon at launch and opens immediately.

## Logs

The app writes its own records — which daemon binary it chose, whether a handshake reused, started or failed, a tray restart that failed — as one-line JSON with the logger name `coffer.desktop` into `~/.coffer/logs/daemon.log`, beside the daemon's own lines. Read them on **Activity → Daemon**, or:

```sh
grep coffer.desktop ~/.coffer/logs/daemon.log | tail
```

## Troubleshooting

**"Coffer is damaged and can't be opened."** Clear the quarantine flag: `xattr -dr com.apple.quarantine /Applications/Coffer.app`.

**The app says it can't find its daemon.** The bundle's binaries are missing, which happens with a development build made without them. Install the CLI, or reinstall the app from a release `.dmg`.

**The banner says the daemon is not running and never clears.** Choose **Restart daemon**. If that fails, look for `coffer.desktop` lines in `~/.coffer/logs/daemon.log`. A daemon that refuses to start because port 8000 is taken names the process holding it; move Coffer with `coffer daemon port set <port>`.

**MCP servers that work in a terminal fail when the app started the daemon.** The login-shell `PATH` probe timed out or failed, so the daemon got the minimal GUI `PATH`. Start the daemon from a terminal (`coffer daemon start`) or turn on **Start at login**, then reopen the app; it attaches to that daemon.

**The UI looks older than the daemon.** The app carries its own copy of the UI. Install the matching `.dmg`.

## Build from source

`make desktop` builds `Coffer.app` and the `.dmg`. It needs a Rust toolchain and runs PyInstaller for the three binaries first, so expect it to take roughly 50 minutes. The result is unsigned. See [Development setup](/contributing/development).

## Related

- [Web UI](/guides/web-ui) — the pages the app hosts.
- [Running the daemon](/guides/daemon) — ports, the login service and lifecycle.
- [Install](/start/install) — the CLI install tier.
- [Distribution and releases](/architecture/distribution)
- [Spec: desktop-app](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/desktop-app/spec.md)
- [The Desktop Shell Returns](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md)
