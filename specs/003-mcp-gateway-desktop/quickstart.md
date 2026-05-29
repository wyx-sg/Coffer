# Quickstart — Coffer Desktop

A 5-minute path from a fresh download to a Coffer desktop app sitting in
your tray, with `coffer-mcp-shim` already on `PATH` and the daemon running
in the background. This is the **end-user** companion to
[`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md)
(CLI / shim) and [`specs/002-ui-shell/quickstart.md`](../002-ui-shell/quickstart.md)
(dev-checkout walkthrough); it covers the bundled installer path.

## Prerequisites

- A laptop or desktop running macOS 12+, Linux x64 (a glibc-based distro
  for the AppImage / deb), or Windows 10+ x64. No Python required.
- An MCP client (Claude Code, Claude Desktop, Cursor, or any other client
  that supports stdio MCP servers).

## 1. Download the installer

Go to the [GitHub Releases page](https://github.com/coffer/coffer/releases)
and download the file matching your platform:

| Platform                          | File                                                                 |
| --------------------------------- | -------------------------------------------------------------------- |
| macOS, Apple silicon (M-series)   | `Coffer_<version>_aarch64.dmg`                                       |
| macOS, Intel                      | `Coffer_<version>_x64.dmg`                                           |
| Linux x64 (AppImage, recommended) | `Coffer_<version>_amd64.AppImage`                                    |
| Linux x64 (deb)                   | `coffer_<version>_amd64.deb`                                         |
| Windows 10+ x64 (installer)       | `Coffer_<version>_x64_en-US.msi` or `Coffer_<version>_x64-setup.exe` |

Each download has a `.sha256` sibling. Verify (optional but recommended):

```bash
shasum -a 256 -c Coffer_<version>_aarch64.dmg.sha256   # macOS / Linux
certutil -hashfile Coffer_<version>_x64_en-US.msi SHA256   # Windows
```

> **macOS Gatekeeper**: until Coffer has an Apple Developer ID, the DMG
> ships unsigned. On first open, macOS will refuse to launch it. Either
> right-click the app and pick **Open** (one-time bypass), or run
> `xattr -d com.apple.quarantine /Applications/Coffer.app`. See
> [macos-notarization.md](../../docs/distribution/macos-notarization.md).

## 2. Install

- **macOS**: open the DMG, drag **Coffer.app** to `/Applications`.
- **Linux (AppImage)**: `chmod +x Coffer_<version>_amd64.AppImage`, then
  double-click or run it from a terminal.
- **Linux (deb)**: `sudo apt install ./coffer_<version>_amd64.deb`.
- **Windows**: double-click the MSI (or NSIS `setup.exe`) and follow the
  installer.

## 3. First launch

Open **Coffer** from your application menu (or run the AppImage). On first
launch:

- The main window opens to the Resources welcome view (the same web UI
  documented in [002-ui-shell quickstart](../002-ui-shell/quickstart.md)
  step 2).
- The desktop shell silently deploys `coffer-mcp-shim` to a stable PATH
  location:
  - **macOS / Linux**: `~/.coffer/bin/coffer-mcp-shim`
  - **Windows**: `%LOCALAPPDATA%\Coffer\bin\coffer-mcp-shim.exe`
- The daemon comes up on a free port (defaults to 8000, falls back to
  8001–8009 if taken) and writes `~/.coffer/daemon.json`.
- A tray icon appears in your menu bar / system tray.

If the shim's target directory is not on `PATH`, Coffer shows a one-time
prompt on the **Settings → App** tab with the exact line to add to your
shell rc file (`~/.zshrc`, `~/.bashrc`, etc.).

## 4. Add an MCP server

From the welcome view, click **Add MCP server**. Paste the standard
`mcpServers` JSON from any vendor's README, confirm the secrets-review
step, and submit. The server lands on the Resources list and reaches
"healthy" within ~10 seconds.

## 5. Point your MCP client at Coffer

In your MCP client's config, add Coffer's shim as a server. Paste these
snippets verbatim — they self-discover the daemon, no per-machine
parameterisation:

**Claude Code / Claude Desktop / Cursor** (`.mcp.json` or vendor-specific
config):

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

Restart your MCP client. It should now see every enabled capability from
every registered Coffer server.

## 6. Tray usage

Right-click (or left-click on macOS) the tray icon. The menu offers:

| Item               | What it does                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| **Open**           | Restore the main Coffer window (the same one closing-the-X just hid).                               |
| **Restart daemon** | Stop the local `coffer-daemon` process and start a fresh one on the same port.                      |
| **Quit**           | Stop the desktop process **and** the daemon, removing the tray icon. (Closing the window does not.) |

Closing the main window with the OS close button just **hides** the window
to the tray; the daemon stays alive and your MCP clients keep working.

## 7. Optional: launch Coffer at login

Open **Settings → App**, flip the **Launch at login** toggle. Coffer
re-registers itself with your OS's autostart mechanism:

- macOS: a LaunchAgent under `~/Library/LaunchAgents/`.
- Linux: a `.desktop` file under `~/.config/autostart/`.
- Windows: a Run key under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

Log out and back in (or reboot) to confirm — the tray icon appears without
you opening anything.

## Troubleshooting

- **Tray icon never shows up** — the desktop shell falls back to an
  embedded PNG when the platform tray icon fails to load (see spec's Edge
  Cases). If you still see nothing, check
  `~/.coffer/logs/desktop.log`.
- **`coffer-mcp-shim: command not found`** — your shell's `PATH` does not
  include the shim directory. Re-launch Coffer once, follow the prompt on
  Settings → App, then open a new terminal.
- **Daemon does not start** — open `~/.coffer/logs/daemon.log` and search
  for `ERROR`. The most common cause is another process already bound to
  every port in 8000–8009; quit that process or wait for it to free up.
- **Updates** — check the
  [GitHub Releases page](https://github.com/coffer/coffer/releases) for
  new versions; install the new bundle over the existing app (your data
  in `~/.coffer/` is preserved).
