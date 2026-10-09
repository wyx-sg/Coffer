---
title: Desktop app
description: Install and use Coffer's macOS desktop app — a native window and menu bar item over the same web UI, which updates itself, which finds or starts the daemon for you and is the only place a secret is revealed, the master key is backed up, or an approval is given.
---

# Desktop app

The Coffer desktop app is a macOS application that hosts Coffer's web UI in a native window, with a Dock icon and a menu bar item, finds or starts the daemon for you, and keeps itself up to date. It is also the only place where you see a secret's value, back up the master key, or approve sending a secret somewhere new. This page covers installing and updating it, what it adds over a browser tab, the menu bar, presence checks and approvals, how it connects to the daemon, and how quitting the app relates to the daemon's lifetime.

## What it adds

The app shows the same UI as a browser tab at the daemon's address — built from the same `frontend/dist` — so every page works identically. What it adds is what a browser tab cannot do for itself:

- **A real application.** A window with a Dock icon and a Cmd-Tab entry, and a menu bar item that stays resident when the window is closed and says whether the daemon is running and how many things need you. The window has its own title bar with the sidebar toggle and back and forward arrows (see [Web UI](/guides/web-ui#the-sidebar)).
- **Detect-or-spawn.** At launch it attaches to a running daemon or starts one. You never need to know the port.
- **Recovery without a terminal.** **Restart daemon** in the menu bar and on the offline banner. A browser page cannot offer this: a daemon that is down cannot serve the page the button would live on.
- **A version check.** It warns when it has attached to a daemon left running by an earlier version.
- **Sync alerts where you look.** When [vault sync](/guides/vault-sync) needs you, the menu bar's count, the Dock badge and a notification say so.
- **Updates.** It checks for a newer signed release at launch and every six hours, and installs it when you choose **Download and restart** on **Settings › About**. See [Update](#update).
- **Presence checks.** Revealing or copying a secret, backing up the master key, importing a master key and approving an approval each ask for Touch ID or your login password first. A browser cannot run that check, so a browser tab shows **Open in Coffer app** in their place. See [Presence checks and approvals](#presence-checks-and-approvals).
- **Approval alerts.** When a secret waits to be sent somewhere new, the app posts a notification and opens a sheet to answer it.
- **Presence checks the command line asks for.** `coffer approval approve`, `coffer secret reveal`, `coffer secret backup-key` and `coffer app update …` leave a request with the daemon; the app picks it up within about a second and runs the same flow its own buttons run, so the Touch ID prompt, the revealed value and the backup's passphrase all stay in the app. A command that finds the app closed starts it. See [Secrets → On the command line](/guides/secrets#on-the-command-line).

Everything else — opening files in your editor, choosing folders — goes through the daemon's HTTP routes exactly as it does in a browser.

::: info Platform
The desktop app is built for macOS on Apple silicon only. On other platforms, use the CLI install and open the daemon's address (`http://127.0.0.1:<port>`) in a browser.
:::

## Install

::: warning No tagged release yet
The `.dmg` is published with a tagged GitHub release, and none exists yet. Until then, build the app yourself (see [Build from source](#build-from-source)).
:::

1. Download the `.dmg` from the project's [Releases](https://github.com/wyx-sg/Coffer/releases/latest) page.
2. Open the `.dmg` and drag **Coffer** to **Applications**.
3. A release signed with the project's Developer ID (`Coffer-aarch64-apple-darwin.dmg`) is notarised and opens normally. A release built without one is named `Coffer-unsigned-aarch64-apple-darwin.dmg`, and macOS refuses a browser-downloaded copy of it with *"Coffer is damaged and can't be opened"*. It is not damaged. Clear the quarantine flag:

   ```sh
   xattr -dr com.apple.quarantine /Applications/Coffer.app
   ```

4. Open Coffer from Applications.

The app is self-contained: it carries the four frozen binaries `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` inside its bundle, and needs nothing installed beforehand.

### The app installs the CLI too

On first start, the daemon copies all four binaries (`coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge`, which loads the SeaTalk SDK) into `~/.coffer/bin`. Put that directory on your `PATH` to use `coffer` in a terminal and to let MCP clients resolve `coffer-mcp-shim`:

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add this to your shell profile
```

The app itself never writes to `~/.coffer/bin`; the daemon does it, so the two never race over that directory.

### Update

The app updates itself. It checks the newest GitHub release's update manifest 30 seconds after launch and every six hours while it runs, without interrupting you: **Settings › About** shows when it last checked and whether a newer version exists, with its release notes, and the card above the sidebar footer offers **Restart** with the version. Nothing is downloaded until you choose **Download and restart** on About or **Restart** on the card. The app then downloads the update, checks its signature against the key built into the app — refusing an update whose signature does not verify — replaces itself, relaunches, and restarts the previous version's daemon so the new one answers. Agents reconnect on their own.

- **Check for updates** on About checks now.
- **Check automatically** on About turns the launch and six-hourly checks off; checking by hand still works.
- A check that fails — no network, the manifest unreachable — says why on About, keeps the time of the last successful check, and changes nothing. Failures are also written to `~/.coffer/logs/daemon.log`.
- A build without an update key (every build from source, and a release made before the project's update key existed) says it does not check for updates. Update it by installing the new `.dmg` over it and choosing **Restart daemon**.
- In a browser, About says that updates are installed by the desktop app. A daemon running from the installer's binaries instead shows its own release check there, with `coffer update` to copy — see [Install → Upgrade](/start/install#upgrade).

### Uninstall

**Settings › About › Uninstall Coffer…** removes Coffer from this Mac. The dialog lists what goes — Coffer's MCP entry, memory hook and model routing in each agent, the skill links it delivered, start at login, the command-line tools and the installer's `PATH` lines, and the app — and what stays: `~/.coffer`, ready for a reinstall. Confirm, and the app shows each step as the daemon reports it, then moves itself to the Trash and quits.

**Also delete my data** is unticked by default. Ticking it says what is lost for good, offers **Back up the master key first**, and renames the button **Uninstall and delete data**; confirming asks for Touch ID, and only then is anything removed. `~/.coffer` and the master key's Keychain item are deleted after the daemon has stopped.

`coffer uninstall` (and `coffer uninstall --delete-data`, which ticks the box) opens this dialog when the daemon is the app's, so the decision is always made in the app.

## Presence checks and approvals

Coffer's [secret boundary](/guides/secrets) keeps a secret's value, and the decision to send it somewhere new, with a person at this Mac. The app is where that person acts:

| Action | Where | What it does |
| --- | --- | --- |
| **Reveal** or **copy** a secret | the secret, in the app | Shows or copies that one value. Audited as `secret_revealed`. |
| **Back up the master key** | the app | Asks for a passphrase, then writes `coffer-master-key.cfk` — the key encrypted under it — (mode `0600`) into a folder you pick. Audited as `master_key_exported`. See [Secret store → Back up the key](/guides/secret-store#back-up-the-key). |
| **Approve** | the approval sheet | Lets a secret go to a new destination or target, applies a replaced value, or switches the protection off. |

Each action runs its own check, with nothing remembered in between:

1. macOS asks for **Touch ID or your login password**. The prompt names what you are approving — "reveal the secret github/token", or the approval's own description — so read it before you touch.
2. Only then does the app ask the daemon for a one-time challenge for that action, sign it, and send the request. Cancelling sends nothing.
3. The next reveal or approval asks again.

**Approvals come to you.** The app checks the daemon every 15 seconds, whether or not its window is open. For each new pending approval it posts one notification, **Coffer needs your approval**, whose text names the change, and the window opens its approval sheet. From there, approve (with the check above) or reject (no check needed). A command that waits prints `waiting for approval in the Coffer app`; see [Secrets → Approvals](/guides/secrets#approvals) for what triggers one.

::: warning Development builds
A build that is not signed with Coffer's Developer ID — every build from source — is a development build. The app says **Development build** on every prompt. On a Mac without Touch ID or LocalAuthentication, a development build asks you to confirm in a dialog in its own window instead. See [Security model → Development builds](/architecture/security#development-builds).
:::

## Launch

When you open the app:

1. It looks for a daemon (see [How it finds a daemon](#how-it-finds-a-daemon)), attaching to a running one or starting one.
2. The window stays hidden until that daemon answers, so you never see a page where nothing works. With the daemon already running — for example as a [login service](#keep-the-daemon-running) — this is instant.
3. If no daemon can be reached, the window opens anyway and says why.

A daemon on a real vault can take several seconds to unpack, migrate and bring its MCP servers up. The app gives a daemon it started up to 90 seconds to answer, and keeps retrying on a backoff after that, so a slow start clears on its own without a restart.

## The menu bar

Coffer's item in the menu bar is the Coffer mark, drawn in the menu bar's own colour so it suits a light or a dark menu bar. When something on Overview needs you, it shows the count beside the icon (**9+** above nine); an item you ignored is not counted. The count follows what you do: resolve or ignore something and it drops within seconds while the window is open (within about 20 seconds otherwise), and it disappears once nothing is left. It is **dimmed and struck through** when no daemon is running. Click it for the menu:

| Item | What it does |
| --- | --- |
| **Daemon running · port 38470 · 1.0.0** | Status only: the daemon's port and version, or **Daemon offline**. |
| **N things need you** | Shown only when Overview lists something that needs you; opens Overview. A single sync problem is named instead, such as **Sync needs attention — conflict**. |
| **Open Coffer** | Shows and focuses the window. |
| **Restart daemon** | Stops the running daemon and starts a fresh one. Reads **Start daemon** while none is running. |
| **Quit Coffer** ⌘Q | Quits the app. The daemon keeps running. |

The menu is deliberately short: conversations, Settings, **Start at login** (in **Settings › Daemon**) and updates (the card above the sidebar footer and **Settings › About**) are all reached from the window. The menu follows the daemon on its own: it reads the daemon's status every 10 seconds and what needs you every minute.

The menu, its tooltip and the sync notification use the interface language you pick in **Settings › General** (English or 中文). Switching language relabels the menu at once. Until the window has loaded, it uses your macOS language.

Closing the window hides the app to the menu bar instead of quitting it. Clicking Coffer in the Dock brings the window back.

When a sync round needs a human — held for confirmation, a conflict, a failed push, a failed run, or a machine that has not joined yet — the app counts it beside its menu bar icon, badges the Dock icon and posts one macOS notification titled **Coffer sync needs you**.

## Restart the daemon

Use **Restart daemon** in the menu bar, or on the offline banner in the window. A restart:

1. asks the running daemon to shut down over its authenticated shutdown route;
2. waits for the port to be free;
3. starts a new daemon and waits for it to answer. A restart from the banner hands the new daemon's connection straight to the window.

If the port does not free up, the restart reports that instead of starting a daemon that cannot bind. Restarts are limited to one every 5 seconds, counted from the last **successful** restart, so a failed attempt can be retried at once.

A restart from the menu bar has nowhere to show a message; its outcome is written to `~/.coffer/logs/daemon.log`.

## How it finds a daemon

The app resolves a daemon in a fixed order and takes the first that applies:

1. A running daemon named by `~/.coffer/daemon.json` that answers an HTTP status check. The app attaches to it and starts nothing.
2. The `coffer-daemon` inside the app bundle.
3. `~/.coffer/bin/coffer-daemon`.
4. `coffer-daemon` on your `PATH`.
5. Otherwise, a message that lists where it looked and how to install the CLI.

The running daemon comes first so the app never starts a second daemon beside one you started from a terminal. The status check, rather than a bare port probe, keeps an unrelated process on port 38470 from being mistaken for Coffer.

A daemon the app starts:

- **outlives the app.** It is detached from the app's process, because agents use it whether or not the window is open.
- **gets your login shell's `PATH`.** An app opened from Finder or the Dock inherits a minimal `PATH`; the app asks your login shell for the real one, with a time limit, so `npx`- and `uvx`-based MCP servers resolve.

### Version skew

If the app attaches to a daemon whose version differs from its own — typically one left running by a previous installation — it keeps working with it and shows **Daemon out of date** on the banner. Choose **Restart daemon** to replace it with the daemon from the app's bundle.

## How it connects

The window loads the UI from the app bundle, not from the daemon's address. That is why a slow or absent daemon produces a banner instead of a browser connection error, and why the port never appears anywhere.

Because the daemon did not serve that page, it could not write its token into it as it does for a browser. Instead the app reads the port and token from `~/.coffer/daemon.json` and hands them to the page over an in-process IPC call, as the same two values a browser page receives. The page renders first and applies them when they arrive. Before it hands the page the token, and before every presence-gated action, the app also checks that the daemon it found is Coffer's: it sends a random nonce and verifies the answer, which only a holder of the master key can compute. If the check fails the app stops with "This is not Coffer's daemon — nothing was sent" and sends no token, grant or value (see [Security model](/architecture/security#who-is-on-the-other-end)). The app stores no secret of its own: for a presence-gated action it reads the master key at the moment it signs, and keeps neither the key nor anything derived from it.

The window's content policy allows network requests only to loopback addresses (any port) and to the app's own IPC channel; scripts and styles come only from the bundle.

## Quit the app, keep the daemon

Quitting the app with **Quit Coffer** only closes the window and the menu bar item. The daemon keeps serving your agents, channels and sync. To stop the daemon itself, run:

```sh
coffer daemon stop
```

### Keep the daemon running

Turn on **Settings → Daemon → Start at login** to start the daemon when you log in and restart it if it crashes, whether or not the app is open. With it on, the app attaches to an already-running daemon at launch and opens immediately.

## Logs

The app writes its own records — which daemon binary it chose, whether a handshake reused, started or failed, a menu bar restart that failed, an update check or install that failed — as one-line JSON with the logger name `coffer.desktop` into `~/.coffer/logs/daemon.log`, beside the daemon's own lines. Read them on **Activity → Daemon**, or:

```sh
grep coffer.desktop ~/.coffer/logs/daemon.log | tail
```

## Troubleshooting

**"Coffer is damaged and can't be opened."** Clear the quarantine flag: `xattr -dr com.apple.quarantine /Applications/Coffer.app`.

**The app says it can't find its daemon.** The bundle's binaries are missing, which happens with a development build made without them. Install the CLI, or reinstall the app from a release `.dmg`.

**The banner says the daemon is not running and never clears.** Choose **Restart daemon**. If that fails, look for `coffer.desktop` lines in `~/.coffer/logs/daemon.log`. A daemon that refuses to start because port 38470 is taken names the process holding it; move Coffer with `coffer config set daemon.port <port>`.

**MCP servers that work in a terminal fail when the app started the daemon.** The login-shell `PATH` probe timed out or failed, so the daemon got the minimal GUI `PATH`. Start the daemon from a terminal (`coffer daemon start`) or turn on **Start at login**, then reopen the app; it attaches to that daemon.

**The UI looks older than the daemon.** The app carries its own copy of the UI. Install the matching `.dmg`.

## Build from source

`make desktop` builds `Coffer.app` and the `.dmg`. It needs a Rust toolchain and runs PyInstaller for the four binaries first, so expect it to take roughly 50 minutes. The result is unsigned. See [Development setup](/contributing/development).

## Related

- [Web UI](/guides/web-ui) — the pages the app hosts.
- [Running the daemon](/guides/daemon) — ports, the login service and lifecycle.
- [Secrets](/guides/secrets) — the secret boundary, approvals and key backups.
- [Security model](/architecture/security) — why these actions live only in the app.
- [Install](/start/install) — the CLI install tier.
- [Distribution and releases](/architecture/distribution)
- [Spec: desktop-app](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/desktop-app/spec.md)
- [The Desktop Shell Returns](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md)
